from sqlalchemy.orm import joinedload

from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag


def get_songs_by_tag(db, tag_name):
    tag = db.query(Tag).filter(
        Tag.name == tag_name
    ).first()

    if not tag:
        return []

    songs = (
        db.query(Song)
        .join(SongTag)
        .filter(SongTag.tag_id == tag.id, Song.is_deleted.is_(False))
        .options(joinedload(Song.artist))
        .all()
    )

    return songs


def get_top_songs(db, limit=20):
    songs = (
        db.query(Song)
        .filter(Song.is_deleted.is_(False))
        .order_by(Song.popularity_score.desc())
        .limit(limit)
        .all()
    )

    return songs


def get_top_songs_by_tag(db, tag_name, limit=20):
    tag = db.query(Tag).filter(
        Tag.name == tag_name
    ).first()

    if not tag:
        return []

    songs = (
        db.query(Song)
        .join(SongTag)
        .filter(SongTag.tag_id == tag.id, Song.is_deleted.is_(False))
        .order_by(Song.popularity_score.desc())
        .limit(limit)
        .all()
    )

    return songs
