"""
Seed the demo user account with realistic listening history.

Usage:
    cd backend
    python seed_demo.py

Set DATABASE_URL in your .env (or environment) before running.
The script is idempotent — running it twice won't duplicate rows.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

# Make sure the app package is importable when run from backend/
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.config import settings
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_tag import SongTag
from app.models.tag import Tag
from app.models.listening_history import ListeningHistory
from app.models.user_session import UserSession

DEMO_USER_ID = settings.DEMO_USER_ID or "musicintel_demo"

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

ARTISTS_AND_SONGS = [
    {
        "name": "The Weeknd",
        "genre": "R&B",
        "tags": ["r&b", "pop", "synthpop", "dark pop"],
        "songs": [
            ("Blinding Lights", "7MXVkk9YMctZqd1Srtv4MB"),
            ("Save Your Tears", "5QO79kh1waicV47BqGRL3g"),
            ("Starboy", "7MXVkk9YMctZqd1Srtv4MB"),
            ("Can't Feel My Face", "56k0tprjBXEMn4UNTn6kXy"),
            ("After Hours", "6oEcpODQyRXK9RB1NjkQBW"),
        ],
    },
    {
        "name": "Kendrick Lamar",
        "genre": "Hip-Hop",
        "tags": ["hip-hop", "rap", "west coast rap", "conscious hip-hop"],
        "songs": [
            ("HUMBLE.", "7KXjTSCq5nL1LoYtL7XAwS"),
            ("DNA.", "6HZILIRieu8S0iqY8kIKhj"),
            ("Money Trees", "2HbKqm4o0w5wEeEFXm2sD1"),
            ("Alright", "3iVcZ5G6tvkXZkZKlMpIUs"),
            ("Swimming Pools", "39zSPAkqJSWDCzBs5GCDwJ"),
        ],
    },
    {
        "name": "Arctic Monkeys",
        "genre": "Indie Rock",
        "tags": ["indie rock", "alternative rock", "garage rock", "british indie"],
        "songs": [
            ("Do I Wanna Know?", "5FVd6KXrgO9B3JPmC8OPst"),
            ("R U Mine?", "2AT0nOCiM2T6LMRXgR0mAJ"),
            ("505", "0BxE4FqsDD1Ot4YuBXwAPp"),
            ("Why'd You Only Call Me When You're High?", "3EYOJ48Et7MIiinuF3NOFQ"),
            ("Fluorescent Adolescent", "0rIgdVBOKYV5P0pRGf6c8R"),
        ],
    },
    {
        "name": "Frank Ocean",
        "genre": "R&B",
        "tags": ["r&b", "neo-soul", "alternative r&b", "indie r&b"],
        "songs": [
            ("Nights", "7eqoqGkKwgOaWNNHx90uEZ"),
            ("Chanel", "2AeUQRKFNnYPj6EKyMJWpJ"),
            ("Ivy", "2nRIFNGPaFtLEKTc98pfTT"),
            ("Self Control", "4sPmO7WMQUAf45kwMOtONw"),
            ("Lost", "3rS7SFKE9JH5HfRhXkFmBi"),
        ],
    },
    {
        "name": "Tame Impala",
        "genre": "Psychedelic Rock",
        "tags": ["psychedelic rock", "neo-psychedelia", "indie rock", "dream pop"],
        "songs": [
            ("The Less I Know The Better", "6K4t31amVTZDgR3sKmwUJJ"),
            ("Let It Happen", "4oGMOPGOtBNzZnSBmLvLGH"),
            ("Feels Like We Only Go Backwards", "0V3wPSX9ygBnCm8psDIegu"),
            ("New Person, Same Old Mistakes", "2QV99rMFsE96gBMG6JG5k1"),
            ("Eventually", "3yfqSUWxFvZELEM4PmlwIR"),
        ],
    },
    {
        "name": "Tyler, The Creator",
        "genre": "Hip-Hop",
        "tags": ["hip-hop", "experimental hip-hop", "neo-soul", "alternative hip-hop"],
        "songs": [
            ("EARFQUAKE", "2RlgNHKcydI9sayD2Df2xp"),
            ("See You Again", "7KA4W4McWYRpgZKwDiEwot"),
            ("GONE, GONE / THANK YOU", "3hNBhS6rIRZaGq9hAOxnse"),
            ("NEW MAGIC WAND", "7FIWs6HMvTpHpIbmaqkCSD"),
            ("IGOR'S THEME", "33tGJvBvQbJ0YJWJGPZ0Ec"),
        ],
    },
    {
        "name": "SZA",
        "genre": "R&B",
        "tags": ["r&b", "neo-soul", "alternative r&b", "indie pop"],
        "songs": [
            ("Kill Bill", "1Qrg8KqiBpW07V7PNxwwwL"),
            ("Good Days", "6t8XRqJFuhBLBrKUCAg0Kt"),
            ("20 Something", "7kDlqGDmfGLMwMbP5l3HQm"),
            ("Normal Girl", "5F8bTp0rLlzZiX7Vm8cMaS"),
            ("Drew Barrymore", "3O0x7YkFqMqVflqWe5azEY"),
        ],
    },
    {
        "name": "Mac Miller",
        "genre": "Hip-Hop",
        "tags": ["hip-hop", "rap", "alternative hip-hop", "jazz rap"],
        "songs": [
            ("Small Worlds", "0CcNFEIQMjBMKqIPzeBzNm"),
            ("Circles", "4ABo9YxsYRQdQWCO2LHPYJ"),
            ("Self Care", "6qJ9wuIBTVLIqBdxHDRoJe"),
            ("Come Back to Earth", "2qSTV7C3IKAIJFJwxYxLvz"),
            ("Good News", "6sFIWsNpZYqfjUpaCgueju"),
        ],
    },
    {
        "name": "Radiohead",
        "genre": "Alternative Rock",
        "tags": ["alternative rock", "art rock", "post-rock", "experimental rock"],
        "songs": [
            ("Creep", "70LcF31zb1H0PyJoS1Sx1r"),
            ("No Surprises", "10nyNJ6zNy2YVYLrcwLccB"),
            ("Karma Police", "63OQupATfueTdZMWTxW03A"),
            ("Paranoid Android", "6LgJvl0Xdtc73RJ1mmpotq"),
            ("Fake Plastic Trees", "2ciSBNxXkHWnLV4gYFXFEP"),
        ],
    },
    {
        "name": "J. Cole",
        "genre": "Hip-Hop",
        "tags": ["hip-hop", "rap", "conscious hip-hop", "east coast rap"],
        "songs": [
            ("MIDDLE CHILD", "0yc6Gst2xkRu0xjGSAVGXP"),
            ("No Role Modelz", "58ge6dfP91o9oXMzq3XkIS"),
            ("Wet Dreamz", "3wuJbpkpTheFDKvhNx9tqI"),
            ("Power Trip", "4n2qwOtmr2Gu5oTnYJcLas"),
            ("Love Yourz", "6mxBM4gJFgcG9Xs6J33s99"),
        ],
    },
    {
        "name": "Bon Iver",
        "genre": "Indie Folk",
        "tags": ["indie folk", "folk", "chamber pop", "indietronica"],
        "songs": [
            ("Skinny Love", "3Hvu1pq89D4R0lyPBoujou"),
            ("Holocene", "2ijqnBkRER8pafOEHMdBrO"),
            ("Towers", "5SkqM2AyYdSxGJfCNJHqXD"),
            ("Flume", "4Z2Tku2Ogjq9fP8Jjgn2P6"),
            ("Re: Stacks", "3KHGT4lLFjKGf5pDzOO6FK"),
        ],
    },
    {
        "name": "Daniel Caesar",
        "genre": "R&B",
        "tags": ["r&b", "neo-soul", "indie r&b", "soul"],
        "songs": [
            ("Best Part", "1pMGdHm1HCd2PBiJEMXYNm"),
            ("Get You", "5VnRlJb7pmA3bAitHaG3kM"),
            ("Japanese Denim", "01PXnj0pJnITRKHHvjWuSh"),
            ("Cyanide", "2mKjVQHkwFI9JMqGUVHhGR"),
            ("Hold Me Down", "7oxVq3FWhOuS6I4kXFnQ8N"),
        ],
    },
    {
        "name": "James Blake",
        "genre": "Electronic",
        "tags": ["electronic", "post-dubstep", "art pop", "r&b"],
        "songs": [
            ("Retrograde", "2AO9OKBj12rfkQr1b7pGaM"),
            ("The Wilhelm Scream", "4jVFzGPaFjBdIEcUcFdB5H"),
            ("Limit to Your Love", "26d1fxrfVXGKwJXBZJyNmJ"),
            ("Assume Form", "4R16IuMUWTTnf7X7NeJ5F6"),
            ("Are You in Love?", "1G6SuB7hJLjSIrWRjMSoxs"),
        ],
    },
    {
        "name": "Childish Gambino",
        "genre": "Hip-Hop",
        "tags": ["hip-hop", "r&b", "neo-soul", "alternative hip-hop"],
        "songs": [
            ("Redbone", "4qSOjORHJHXoUAI5iM7WZ3"),
            ("This Is America", "0b9oOr2ZgvyQu88wzixux9"),
            ("3005", "56pkXvPXk7IIMstBGrjm0J"),
            ("Camp", "3rfNiOAFmGGP5NxN0iFsZ4"),
            ("Heartbeat", "5PUf3LoxHjxjCWPwJtnmQ3"),
        ],
    },
    {
        "name": "Rex Orange County",
        "genre": "Indie Pop",
        "tags": ["indie pop", "indie r&b", "lo-fi pop", "bedroom pop"],
        "songs": [
            ("Loving Is Easy", "48WnHvbh9pZpJPDPQrHFbY"),
            ("Corduroy Dreams", "3R2kjYLXqjr8mO1NLnRLbE"),
            ("Sunflower", "0RiRZpuVRbi7oqRdSMwhQY"),
            ("Happiness", "1Vs3QXN6E2laTMrU7gy9Ql"),
            ("10/10", "7r0OVBbPvAXbNRsPCNOY3c"),
        ],
    },
]

# ---------------------------------------------------------------------------
# How many times each song gets played and when
# ---------------------------------------------------------------------------

def _generate_history(song_id: int, user_id: str, base_plays: int, months_back: int = 6):
    """Return a list of ListeningHistory kwargs spread over the last N months."""
    now = datetime.now(timezone.utc)
    rows = []
    for _ in range(base_plays):
        days_ago = random.randint(0, months_back * 30)
        hour = random.choices(
            range(24),
            weights=[1,1,1,1,1,1,2,3,4,4,4,5,5,5,5,5,6,7,8,9,9,8,7,4],
            k=1
        )[0]
        played_at = (now - timedelta(days=days_ago)).replace(
            hour=hour,
            minute=random.randint(0, 59),
            second=random.randint(0, 59),
            microsecond=0,
            tzinfo=None,
        )
        rows.append({
            "user_id": user_id,
            "song_id": song_id,
            "played_at": played_at,
        })
    return rows


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

def seed():
    db = SessionLocal()
    try:
        print(f"Seeding demo user: {DEMO_USER_ID}")

        # 1. Ensure the demo user has a UserSession row.
        # token is NOT NULL in the schema, so we store a placeholder and set
        # token_expires_at in the past — load_user_session will see it as expired,
        # find no refresh_token, and return token=None (spotify_connected=False).
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)
        existing_session = db.query(UserSession).filter(UserSession.user_id == DEMO_USER_ID).first()
        if existing_session:
            existing_session.token_expires_at = past
        else:
            db.add(UserSession(user_id=DEMO_USER_ID, token="__demo__", token_expires_at=past))
        db.commit()
        print("  OK UserSession created/updated")

        # 2. Upsert tags
        tag_cache: dict[str, Tag] = {}
        all_tag_names = {t for artist in ARTISTS_AND_SONGS for t in artist["tags"]}
        for tname in all_tag_names:
            existing = db.query(Tag).filter(Tag.name == tname).first()
            if not existing:
                existing = Tag(name=tname)
                db.add(existing)
                db.flush()
            tag_cache[tname] = existing
        db.commit()
        print(f"  OK {len(tag_cache)} tags ready")

        # 3. Upsert artists + songs
        song_id_map: dict[str, int] = {}   # spotify_id → db song.id
        total_songs = 0
        for artist_data in ARTISTS_AND_SONGS:
            # Artist
            artist = db.query(Artist).filter(Artist.name == artist_data["name"]).first()
            if not artist:
                artist = Artist(name=artist_data["name"])
                db.add(artist)
                db.flush()

            # Songs — find existing first, create only if truly absent
            for title, spotify_id in artist_data["songs"]:
                # 1. Match by spotify_id
                song = db.query(Song).filter(Song.spotify_id == spotify_id).first()
                # 2. Fall back to title + artist_id (real library may have the song
                #    under a different / missing spotify_id)
                if not song:
                    song = db.query(Song).filter(
                        Song.title == title,
                        Song.artist_id == artist.id,
                        Song.is_deleted.is_(False),
                    ).first()
                # 3. Create only when the song is genuinely absent
                if not song:
                    song = Song(
                        title=title,
                        artist_id=artist.id,
                        spotify_id=spotify_id,
                        genre=artist_data["genre"],
                        enrichment_status="complete",
                        discovery_source="history_sync",
                        discovery_confidence=1.0,
                        is_deleted=False,
                    )
                    db.add(song)
                    db.flush()
                    # Attach seed tags only for brand-new songs; existing songs
                    # already have real tags from enrichment — don't touch them.
                    for tname in artist_data["tags"]:
                        tag = tag_cache[tname]
                        db.add(SongTag(song_id=song.id, tag_id=tag.id))
                    total_songs += 1
                else:
                    # Backfill genre/enrichment_status if missing, leave tags alone
                    if not song.genre:
                        song.genre = artist_data["genre"]
                    if not song.enrichment_status:
                        song.enrichment_status = "complete"

                song_id_map[spotify_id] = song.id

        db.commit()
        print(f"  OK {len(ARTISTS_AND_SONGS)} artists, {len(song_id_map)} songs ready ({total_songs} new)")

        # 4. Find the real user — the non-demo account with the most history
        from sqlalchemy import func as _func
        real_user_row = (
            db.query(ListeningHistory.user_id, _func.count(ListeningHistory.id).label("n"))
            .filter(ListeningHistory.user_id != DEMO_USER_ID)
            .group_by(ListeningHistory.user_id)
            .order_by(_func.count(ListeningHistory.id).desc())
            .first()
        )
        if not real_user_row:
            print("  WARNING: no real user history found — skipping history copy")
        else:
            real_user_id = real_user_row[0]
            real_count   = real_user_row[1]
            print(f"  OK found real user {real_user_id!r} with {real_count:,} history rows")

            # 5. Clear existing demo history then bulk-copy from real user
            deleted = db.query(ListeningHistory).filter(
                ListeningHistory.user_id == DEMO_USER_ID
            ).delete(synchronize_session=False)
            db.commit()
            if deleted:
                print(f"  OK cleared {deleted:,} old demo history rows")

            # Copy in chunks to avoid huge single INSERT
            CHUNK = 5000
            offset = 0
            inserted = 0
            while True:
                rows = (
                    db.query(ListeningHistory)
                    .filter(ListeningHistory.user_id == real_user_id)
                    .order_by(ListeningHistory.id)
                    .offset(offset)
                    .limit(CHUNK)
                    .all()
                )
                if not rows:
                    break
                for r in rows:
                    db.add(ListeningHistory(
                        user_id=DEMO_USER_ID,
                        song_id=r.song_id,
                        played_at=r.played_at,
                    ))
                db.commit()
                inserted += len(rows)
                print(f"  ... copied {inserted:,} / {real_count:,} rows", end="\r")
                offset += CHUNK

            print(f"  OK {inserted:,} listening history rows copied          ")
        print()
        print(f"Demo seed complete. User ID: {DEMO_USER_ID}")
        print("Remember to set DEMO_USER_ID in your backend .env / Render env vars.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
