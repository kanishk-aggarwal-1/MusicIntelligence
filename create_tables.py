from backend.app.database import Base, engine, run_startup_migrations

# Import each model module so SQLAlchemy registers all tables/relationships.
from backend.app.models.artist import Artist
from backend.app.models.dedup_merge_log import DedupMergeLog
from backend.app.models.listening_goal import ListeningGoal
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.recommendation_feedback import RecommendationFeedback
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession


def create_tables():

    run_startup_migrations()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations()

    print("Database tables created/migrated successfully")


if __name__ == "__main__":
    create_tables()
