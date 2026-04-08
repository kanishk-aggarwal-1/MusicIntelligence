from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..services.spotify_service import load_request_user_session

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/weekly")
def weekly_report(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    now = datetime.utcnow()
    start = now - timedelta(days=7)

    total_plays = (
        db.query(func.count(ListeningHistory.id))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start, Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    top_artists = (
        db.query(Artist.name, func.count(ListeningHistory.id))
        .join(Song, Song.artist_id == Artist.id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start, Song.is_deleted.is_(False))
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(5)
        .all()
    )

    top_songs = (
        db.query(Song.title, func.count(ListeningHistory.id))
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start, Song.is_deleted.is_(False))
        .group_by(Song.title)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(5)
        .all()
    )

    out_dir = Path("output/pdf")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_recap_{user_id}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    out_path = out_dir / filename

    c = canvas.Canvas(str(out_path), pagesize=letter)
    y = 760

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "MusicIntelligence Weekly Recap")
    y -= 24

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"User: {user_id}")
    y -= 16
    c.drawString(40, y, f"Period: {start.date()} to {now.date()}")
    y -= 16
    c.drawString(40, y, f"Total Plays: {total_plays}")
    y -= 28

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Top Artists")
    y -= 18

    c.setFont("Helvetica", 10)
    for idx, (name, plays) in enumerate(top_artists, start=1):
        c.drawString(50, y, f"{idx}. {name} - {plays} plays")
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Top Songs")
    y -= 18

    c.setFont("Helvetica", 10)
    for idx, (title, plays) in enumerate(top_songs, start=1):
        c.drawString(50, y, f"{idx}. {title} - {plays} plays")
        y -= 14

    c.save()

    return {
        "message": "Weekly report generated",
        "file_path": str(out_path.resolve()),
        "total_plays": total_plays,
    }
