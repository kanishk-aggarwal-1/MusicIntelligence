from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.filter_service import (
    get_songs_by_tag,
    get_top_songs,
    get_top_songs_by_tag
)

router = APIRouter(prefix="/filter", tags=["Filter"])


@router.get("/top-songs")
def top_songs(db: Session = Depends(get_db)):

    songs = get_top_songs(db)

    return [
        {
            "title": s.title,
            "artist": s.artist.name,
            "popularity": s.popularity_score
        }
        for s in songs
    ]


@router.get("/tag/{tag_name}")
def songs_by_tag(tag_name: str, db: Session = Depends(get_db)):

    songs = get_songs_by_tag(db, tag_name)

    return [
        {
            "title": s.title,
            "artist": s.artist.name
        }
        for s in songs
    ]


@router.get("/top/{tag_name}")
def top_songs_tag(tag_name: str, db: Session = Depends(get_db)):

    songs = get_top_songs_by_tag(db, tag_name)

    return [
        {
            "title": s.title,
            "artist": s.artist.name,
            "popularity": s.popularity_score
        }
        for s in songs
    ]
