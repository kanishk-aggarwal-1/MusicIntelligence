from .lastfm_service import get_artist_top_tracks, get_similar_artists


def discover_songs_from_artist(artist, include_stats=False):

    similar_artists = get_similar_artists(artist)

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
