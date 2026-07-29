"""
AI DJ agent: reads the user's taste profile via DB tools, then calls
the existing playlist pipeline to build a grounded, personalised playlist.
"""
import json
import logging
from datetime import timedelta
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:  # package not installed yet (e.g. local dev without requirements)
    anthropic = None  # type: ignore[assignment]

MAX_ITERATIONS = 6

SYSTEM_PROMPT = (
    "You are an AI DJ for a personal music app. Build a playlist that fits the user's request.\n\n"
    "Steps:\n"
    "1. Call get_listening_profile to understand their taste.\n"
    "2. If the request mentions recency (\"lately\", \"this week\", \"recently\"), also call get_recent_listening.\n"
    "3. Choose context_type, familiarity (0=all new discoveries, 1=only familiar songs), "
    "diversity (0=fewer artists, 1=maximum variety).\n"
    "4. Call build_playlist with your chosen parameters. Inspect the tracks.\n"
    "5. If the result does not fit the vibe, you may call build_playlist once more with adjusted parameters.\n"
    "6. End your response with ONLY a one-sentence DJ note — mention specific artists or tags you saw in the data.\n\n"
    "Limits: call get_listening_profile at most once, build_playlist at most twice.\n"
    "Output nothing except the DJ note sentence at the very end."
)

TOOL_SCHEMAS = [
    {
        "name": "get_listening_profile",
        "description": (
            "Returns the user's all-time taste profile: top tags by play-weighted score, "
            "top artists by play count, library size, and total plays."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_listening",
        "description": "Returns what the user has listened to in the last N days: top artists and top tags in that window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to look (1–30). Default 7.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "build_playlist",
        "description": (
            "Build a playlist preview with the given parameters and return the track list "
            "so you can evaluate whether it matches the requested vibe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": ["string", "null"],
                    "enum": ["focus", "workout", "late-night", "chill", None],
                    "description": (
                        "Preset context: focus (ambient/instrumental), workout (energetic/hype), "
                        "late-night (moody/soul), chill (relaxed/acoustic), or null for mixed."
                    ),
                },
                "familiarity": {
                    "type": "number",
                    "description": "0.0 = all new discoveries, 1.0 = only songs the user already knows. Default 0.5.",
                },
                "diversity": {
                    "type": "number",
                    "description": "0.0 = can repeat artists, 1.0 = maximum artist variety. Default 0.5.",
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_get_listening_profile(db: Session, user_id: str) -> dict:
    listened_subq = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )
    tag_rows = (
        db.query(Tag.name, func.sum(func.coalesce(SongTag.weight, 1.0)).label("w"))
        .join(SongTag, SongTag.tag_id == Tag.id)
        .join(listened_subq, listened_subq.c.song_id == SongTag.song_id)
        .group_by(Tag.name)
        .order_by(func.sum(func.coalesce(SongTag.weight, 1.0)).desc())
        .limit(15)
        .all()
    )
    artist_rows = (
        db.query(Artist.name, func.count(ListeningHistory.id).label("plays"))
        .join(Song, Song.artist_id == Artist.id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(
            ListeningHistory.user_id == user_id,
            Song.is_deleted.is_(False),
            Artist.name.is_not(None),
        )
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(10)
        .all()
    )
    total_plays = (
        db.query(func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id)
        .scalar()
    ) or 0
    library_size = (
        db.query(func.count(func.distinct(ListeningHistory.song_id)))
        .filter(ListeningHistory.user_id == user_id)
        .scalar()
    ) or 0

    return {
        "top_tags": [{"name": n, "weight": round(float(w), 1)} for n, w in tag_rows],
        "top_artists": [{"name": n, "plays": int(p)} for n, p in artist_rows],
        "library_size": int(library_size),
        "total_plays": int(total_plays),
    }


def _tool_get_recent_listening(db: Session, user_id: str, days: int) -> dict:
    days = max(1, min(days, 30))
    cutoff = utcnow_naive() - timedelta(days=days)

    listened_subq = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= cutoff)
        .distinct()
        .subquery()
    )
    tag_rows = (
        db.query(Tag.name, func.count(SongTag.id).label("cnt"))
        .join(SongTag, SongTag.tag_id == Tag.id)
        .join(listened_subq, listened_subq.c.song_id == SongTag.song_id)
        .group_by(Tag.name)
        .order_by(func.count(SongTag.id).desc())
        .limit(8)
        .all()
    )
    artist_rows = (
        db.query(Artist.name, func.count(ListeningHistory.id).label("plays"))
        .join(Song, Song.artist_id == Artist.id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= cutoff,
            Song.is_deleted.is_(False),
            Artist.name.is_not(None),
        )
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(5)
        .all()
    )
    plays = (
        db.query(func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= cutoff)
        .scalar()
    ) or 0

    return {
        "days": days,
        "plays": int(plays),
        "top_artists": [{"name": n, "plays": int(p)} for n, p in artist_rows],
        "top_tags": [{"name": n, "count": int(c)} for n, c in tag_rows],
    }


def _dispatch(db: Session, user_id: str, max_tracks: int, build_fn: Callable, tool_name: str, tool_input: dict) -> dict:
    logger.info("dj_agent.tool_call name=%s user_id=%s", tool_name, user_id)

    if tool_name == "get_listening_profile":
        return _tool_get_listening_profile(db, user_id)

    if tool_name == "get_recent_listening":
        days = int(tool_input.get("days") or 7)
        return _tool_get_recent_listening(db, user_id, days)

    if tool_name == "build_playlist":
        context_type = tool_input.get("context_type") or None
        familiarity  = float(max(0.0, min(1.0, tool_input.get("familiarity", 0.5))))
        diversity    = float(max(0.0, min(1.0, tool_input.get("diversity",   0.5))))
        preview = build_fn(
            db, user_id,
            context_type=context_type,
            familiarity=familiarity,
            diversity=diversity,
            max_tracks=max_tracks,
        )
        gp = preview.get("generated_playlist") or {}
        tracks_slim = [
            {
                "title": t.get("title"),
                "artist": t.get("artist"),
                "is_discovery": t.get("is_discovery", False),
            }
            for t in (gp.get("tracks") or [])
        ]
        return {
            "_preview": preview,
            "_summary": {
                "tracks": tracks_slim,
                "warnings": preview.get("warnings", []),
                "candidate_count": preview.get("recommendation_candidates", 0),
            },
            "_params": {
                "context_type": context_type,
                "familiarity":  familiarity,
                "diversity":    diversity,
            },
        }

    logger.warning("dj_agent.unknown_tool name=%s", tool_name)
    return {"error": f"unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_dj_agent(
    db: Session,
    user_id: str,
    prompt: str,
    max_tracks: int,
    api_key: str,
    *,
    build_fn: Callable,
) -> dict:
    """
    Run the AI DJ agent loop and return the full playlist result dict.

    ``build_fn(db, user_id, *, context_type, familiarity, diversity, max_tracks)``
    must return the same shape as ``_build_preview()`` in playlist_routes.py.
    Passing it as a callable keeps this service free of circular imports.
    """
    if anthropic is None:
        raise RuntimeError("anthropic package not installed — add it to requirements.txt")

    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    _built: dict | None = None
    response = None

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = _dispatch(db, user_id, max_tracks, build_fn, block.name, block.input)
            if block.name == "build_playlist" and "_preview" in result:
                _built = result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result.get("_summary", result)),
            })
        messages.append({"role": "user", "content": tool_results})

    # Extract DJ note from the final text block
    dj_note = ""
    if response:
        for block in response.content:
            text = getattr(block, "text", None)
            if text and text.strip():
                dj_note = text.strip()
                break

    # Fallback: Claude exited without ever calling build_playlist
    if _built is None:
        logger.info("dj_agent.fallback_build user_id=%s", user_id)
        preview = build_fn(
            db, user_id,
            context_type=None,
            familiarity=0.5,
            diversity=0.5,
            max_tracks=max_tracks,
        )
        _built = {"_preview": preview, "_params": {}}

    result = dict(_built["_preview"])
    result["dj_note"]   = dj_note
    result["dj_params"] = _built.get("_params", {})
    return result
