from .lastfm_service import get_artist_tags, get_track_info, get_track_tags


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def enrich_song(song):

    title = song.title
    artist = song.artist.name

    genre = None
    tags = []
    listeners = 0
    playcount = 0
    errors = []

    try:
        tags_data = get_track_tags(artist, title)
        tag_list = tags_data.get("toptags", {}).get("tag", [])
        tags = [t.get("name") for t in tag_list[:8] if t.get("name")]
        if tags:
            genre = tags[0]
    except Exception as exc:
        errors.append(f"track tags failed: {exc}")

    if not tags:
        try:
            artist_tags_data = get_artist_tags(artist)
            artist_tag_list = artist_tags_data.get("toptags", {}).get("tag", [])
            tags = [t.get("name") for t in artist_tag_list[:5] if t.get("name")]
            if tags and not genre:
                genre = tags[0]
        except Exception as exc:
            errors.append(f"artist tags failed: {exc}")

    try:
        info = get_track_info(artist, title)
        track_info = info.get("track", {})
        listeners = _to_int(track_info.get("listeners"), 0)
        playcount = _to_int(track_info.get("playcount"), 0)
    except Exception as exc:
        errors.append(f"track info failed: {exc}")

    return {
        "genre": genre,
        "tags": tags,
        "listeners": listeners,
        "playcount": playcount,
        "_errors": errors,
    }
