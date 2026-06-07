"""
TF-IDF + KNN recommendation engine.

Represents each song as a TF-IDF vector over its combined Last.fm tags and
Spotify artist genres. Computes the user's taste centroid as a play-count-weighted
average of those vectors (with a time-of-day bias), then finds K-nearest neighbours
via cosine similarity. Session co-occurrence adds an implicit collaborative signal:
songs frequently heard in the same listening session score higher.

Temperature sampling is applied before returning results so consecutive playlist
generations produce different tracks rather than always the same deterministic top-N.
"""
import json
import logging
from collections import defaultdict
from datetime import timedelta
from math import log

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "tfidf-knn-v1"

CONTEXT_TERMS = {
    "focus":      ["ambient", "instrumental", "classical", "lofi", "piano", "minimal", "study"],
    "workout":    ["hip_hop", "edm", "dance", "energetic", "gym", "trap", "electronic"],
    "late-night": ["chill", "soul", "jazz", "ambient", "downtempo", "rnb", "night"],
    "chill":      ["chill", "acoustic", "indie", "relax", "ambient", "dream_pop", "lofi"],
}


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _song_document(song) -> str:
    """One text document per song: Last.fm tags + Spotify artist genres as space-joined terms."""
    terms = []
    for st in (song.song_tags or []):
        if st.tag and st.tag.name:
            terms.append(st.tag.name.lower().replace(" ", "_"))
    if song.artist and song.artist.genres:
        try:
            for g in json.loads(song.artist.genres):
                if g:
                    terms.append(g.lower().replace(" ", "_"))
        except Exception:
            pass
    return " ".join(terms)


def _get_play_counts(db, user_id: str) -> dict[int, int]:
    rows = (
        db.query(ListeningHistory.song_id, func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id)
        .group_by(ListeningHistory.song_id)
        .all()
    )
    return {sid: int(cnt or 0) for sid, cnt in rows}


def _get_temporal_play_counts(db, user_id: str, hour: int) -> dict[int, int]:
    """Play counts restricted to the 6-hour time bucket that contains `hour`."""
    if 6 <= hour < 12:
        lo, hi = 6, 12
    elif 12 <= hour < 18:
        lo, hi = 12, 18
    elif 18 <= hour < 24:
        lo, hi = 18, 24
    else:
        lo, hi = 0, 6

    rows = (
        db.query(ListeningHistory.song_id, func.count(ListeningHistory.id))
        .filter(
            ListeningHistory.user_id == user_id,
            func.extract("hour", ListeningHistory.played_at) >= lo,
            func.extract("hour", ListeningHistory.played_at) < hi,
        )
        .group_by(ListeningHistory.song_id)
        .all()
    )
    return {sid: int(cnt or 0) for sid, cnt in rows}


def _build_cooccurrence(db, user_id: str, session_gap_minutes: int = 30) -> dict[int, dict[int, int]]:
    """
    Implicit collaborative signal from listening sessions.

    Songs played within `session_gap_minutes` of each other belong to the same
    session. We count how often each pair appears in the same session; songs
    co-occurring with the user's most-played tracks get a score boost.
    """
    rows = (
        db.query(ListeningHistory.song_id, ListeningHistory.played_at)
        .filter(
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at.is_not(None),
        )
        .order_by(ListeningHistory.played_at)
        .all()
    )
    if not rows:
        return {}

    gap = timedelta(minutes=session_gap_minutes)
    sessions: list[list[int]] = []
    current: list[int] = [rows[0][0]]

    for i in range(1, len(rows)):
        prev_time = rows[i - 1][1]
        curr_time = rows[i][1]
        if prev_time and curr_time and (curr_time - prev_time) <= gap:
            current.append(rows[i][0])
        else:
            sessions.append(current)
            current = [rows[i][0]]
    sessions.append(current)

    cooccurrence: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for session in sessions:
        unique = list(set(session))
        for a_idx, a in enumerate(unique):
            for b in unique[a_idx + 1:]:
                cooccurrence[a][b] += 1
                cooccurrence[b][a] += 1

    return dict(cooccurrence)


def _temperature_sample(candidates: list, n: int, temperature: float) -> list:
    """
    Sample n candidates with probability proportional to score^(1/temperature).

    temperature=0.35 → top-scored songs strongly preferred but not guaranteed,
    producing different playlists on successive calls without sacrificing quality.
    """
    if not candidates or n <= 0:
        return []
    if len(candidates) <= n:
        return candidates[:]

    scores = np.array([c["score"] for c in candidates], dtype=float)
    log_scores = np.log(np.maximum(scores, 1e-9)) / max(temperature, 0.01)
    log_scores -= log_scores.max()
    probs = np.exp(log_scores)
    probs /= probs.sum()

    chosen = np.random.choice(len(candidates), size=n, replace=False, p=probs)
    return [candidates[i] for i in chosen]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def knn_recommend(
    db,
    user_id: str,
    limit: int = 30,
    context_type: str | None = None,
    excluded_song_ids: set | None = None,
    temperature: float = 0.35,
) -> list[dict]:
    """
    Return up to `limit` recommended songs ranked by TF-IDF cosine similarity to
    the user's taste centroid, boosted by session co-occurrence.

    Each result dict contains:
        song, score, tfidf_similarity, co_occurrence_boost,
        play_count, familiarity_score, tags, algorithm_version
    """
    excluded = excluded_song_ids or set()

    # ── Phase 1: lightweight scalars only ────────────────────────────────────
    # get_play_counts returns {song_id: int} — no ORM objects.
    play_counts = _get_play_counts(db, user_id)
    if not play_counts:
        return []
    max_plays = max(play_counts.values(), default=1)

    # Top-N song IDs by play count — the recommendation centroid is
    # play-count-weighted so songs beyond the cap have negligible influence.
    # This prevents loading 20 k ORM objects when the model only needs 5 k.
    _MODEL_CAP = 5_000
    user_song_ids = sorted(
        (sid for sid in play_counts if sid not in excluded),
        key=lambda s: play_counts[s],
        reverse=True,
    )[:_MODEL_CAP]

    if not user_song_ids:
        return []

    # ── Phase 2: build TF-IDF documents without loading ORM objects ──────────
    # Query only the three lightweight columns needed for ML:
    #   song_id (int), tag_names (list[str]), artist_genres (list[str])
    # Returning plain tuples keeps memory proportional to raw data size
    # rather than to SQLAlchemy ORM object overhead (~8-10 KB per object).

    # 2a — (song_id, artist_id) for songs in the cap
    song_meta = (
        db.query(Song.id, Song.artist_id)
        .filter(Song.id.in_(user_song_ids), Song.is_deleted.is_(False))
        .all()
    )
    song_id_to_artist: dict[int, int] = {row[0]: row[1] for row in song_meta}
    valid_ids = list(song_id_to_artist)

    if not valid_ids:
        return []

    # 2b — (song_id, tag_name) pairs — one row per tag
    tag_rows = (
        db.query(SongTag.song_id, Tag.name)
        .join(Tag, Tag.id == SongTag.tag_id)
        .filter(SongTag.song_id.in_(valid_ids))
        .all()
    )
    song_tags_map: dict[int, list[str]] = defaultdict(list)
    for song_id, tag_name in tag_rows:
        if tag_name:
            song_tags_map[song_id].append(tag_name.lower().replace(" ", "_"))

    # 2c — (artist_id, genres_json)
    artist_ids = list({aid for aid in song_id_to_artist.values() if aid})
    artist_genres: dict[int, list[str]] = {}
    if artist_ids:
        for artist_id, genres_json in (
            db.query(Artist.id, Artist.genres)
            .filter(Artist.id.in_(artist_ids))
            .all()
        ):
            try:
                artist_genres[artist_id] = [
                    g.lower().replace(" ", "_")
                    for g in json.loads(genres_json or "[]")
                    if g
                ]
            except Exception:
                pass

    # 2d — assemble document strings; skip songs with no tags/genres
    model_ids: list[int] = []
    documents: list[str] = []
    for sid in user_song_ids:          # preserve play-count order
        if sid not in song_id_to_artist:
            continue
        aid = song_id_to_artist[sid]
        tags = song_tags_map.get(sid, [])
        genres = artist_genres.get(aid, [])
        doc = " ".join(tags + genres).strip()
        if doc:
            model_ids.append(sid)
            documents.append(doc)

    if len(model_ids) < 2:
        logger.info(
            "knn_recommend.insufficient_tagged_songs user_id=%s count=%s",
            user_id, len(model_ids),
        )
        return []

    # ── Phase 3: TF-IDF + KNN (pure numpy/scipy, no ORM objects) ────────────
    vectorizer = TfidfVectorizer(
        min_df=2 if len(documents) >= 50 else 1,
        max_features=400,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(documents)   # sparse (N × 400)

    now_hour = utcnow_naive().hour
    temporal_counts = _get_temporal_play_counts(db, user_id, now_hour)

    weights = np.array([
        max(1, play_counts.get(sid, 1)) * 0.7
        + temporal_counts.get(sid, 0) * 0.3 * 3
        for sid in model_ids
    ], dtype=float)
    weights /= weights.sum()

    # Sparse dot product — no toarray() call, no dense N×400 allocation
    centroid = np.asarray(tfidf_matrix.T.dot(weights)).reshape(1, -1)

    if context_type:
        terms = CONTEXT_TERMS.get(context_type.lower().strip(), [])
        if terms:
            try:
                ctx_vec = vectorizer.transform([" ".join(terms)]).toarray()
                centroid = centroid * 0.80 + ctx_vec * 0.20
            except Exception:
                pass

    n_neighbors = min(len(model_ids), max(limit * 4, 60))
    knn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine", algorithm="brute")
    knn.fit(tfidf_matrix)
    distances, indices = knn.kneighbors(centroid)

    # Candidate song IDs ranked by cosine similarity
    ranked_ids   = [model_ids[i] for i in indices[0]]
    ranked_dists = list(distances[0])

    # ── Phase 4: load full Song ORM objects for candidates ONLY (~50-100) ───
    # Everything before this point used only int/str primitives.
    n_fetch = min(len(ranked_ids), limit * 6)
    fetch_ids = ranked_ids[:n_fetch]

    songs_by_id = {
        s.id: s
        for s in db.query(Song)
        .options(
            joinedload(Song.artist),
            joinedload(Song.song_tags).joinedload(SongTag.tag),
        )
        .filter(Song.id.in_(fetch_ids))
        .all()
    }

    # ── Phase 5: score + build candidate dicts ───────────────────────────────
    cooccurrence   = _build_cooccurrence(db, user_id)
    top_anchor_ids = sorted(play_counts, key=play_counts.get, reverse=True)[:15]

    candidates: list[dict] = []
    for dist, song_id in zip(ranked_dists, ranked_ids):
        song = songs_by_id.get(song_id)
        if not song:
            continue
        tfidf_sim  = float(1.0 - dist)
        play_count = play_counts.get(song_id, 0)
        familiarity = (
            min(1.0, log(play_count + 1) / log(max_plays + 1)) if max_plays > 0 else 0.0
        )
        co_count = sum(cooccurrence.get(song_id, {}).get(a, 0) for a in top_anchor_ids)
        co_boost = min(0.15, co_count * 0.015)
        score    = min(1.0, tfidf_sim + co_boost)

        candidates.append({
            "song":               song,
            "score":              score,
            "tfidf_similarity":   round(tfidf_sim, 4),
            "co_occurrence_boost": round(co_boost, 4),
            "play_count":         play_count,
            "familiarity_score":  round(familiarity, 4),
            "tags":               [st.tag.name for st in song.song_tags if st.tag and st.tag.name],
            "algorithm_version":  ALGORITHM_VERSION,
        })

    if len(candidates) > limit:
        candidates = _temperature_sample(candidates, min(len(candidates), limit * 2), temperature)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates[:limit]
