"""Fetches Spotify genre labels for artists that have a spotify_id but no genres yet."""
import json
import logging

from ..models.artist import Artist

logger = logging.getLogger(__name__)


def enrich_artist_genres(db, sp, batch_size: int = 50) -> dict:
    """Batch-fetch Spotify genre labels for artists missing them.

    Takes an already-authenticated Spotipy client so callers (sync_all, import job)
    can reuse the token they already hold.
    """
    artists = (
        db.query(Artist)
        .filter(Artist.spotify_id.is_not(None), Artist.genres.is_(None))
        .limit(batch_size)
        .all()
    )

    if not artists:
        return {"enriched": 0}

    id_to_artist = {a.spotify_id: a for a in artists}
    spotify_ids = list(id_to_artist.keys())
    enriched = 0

    # Spotify allows up to 50 IDs per /artists batch call
    for i in range(0, len(spotify_ids), 50):
        batch = spotify_ids[i : i + 50]
        try:
            results = sp.artists(batch)
            for artist_data in results.get("artists") or []:
                if not artist_data:
                    continue
                artist = id_to_artist.get(artist_data["id"])
                if artist is not None:
                    artist.genres = json.dumps(artist_data.get("genres") or [])
                    enriched += 1
        except Exception:
            logger.exception("enrich_artist_genres batch failed (offset=%s)", i)

    if enriched:
        db.commit()
        logger.info("enrich_artist_genres enriched=%s", enriched)

    return {"enriched": enriched}
