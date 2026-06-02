from .lastfm_service import get_artist_top_tracks, get_similar_artists


def discover_songs_from_artist(artist, include_stats=False, max_similar_artists=None):
    """Discover tracks from artists similar to ``artist`` via Last.fm.

    ``max_similar_artists`` bounds how many similar artists are queried. Each
    similar artist triggers a (potentially uncached, rate-limited) Last.fm call,
    so callers on a latency-sensitive path should cap it.
    """

    similar_artists = get_similar_artists(artist)
    if max_similar_artists is not None:
        similar_artists = similar_artists[:max(0, int(max_similar_artists))]

    songs = []
    source_artists = 0

    for a in similar_artists:

        name = (a.get("name") or "").strip()
        if not name:
            continue

        try:
            tracks = get_artist_top_tracks(name, limit=5)
            if tracks:
                for track in tracks:
                    songs.append({
                        "title": track["title"],
                        "artist": track["artist"],
                        "discovery_source": "lastfm_top_tracks",
                        "discovery_confidence": 0.7,
                    })
                source_artists += 1
        except Exception:
            pass

    seen = set()
    unique_songs = []
    for song in songs:
        key = (song["title"].lower(), song["artist"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique_songs.append(song)

    if include_stats:
        return {
            "songs": unique_songs,
            "source_artists": source_artists,
            "source": "lastfm",
        }

    return unique_songs
