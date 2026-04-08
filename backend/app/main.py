from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, run_startup_migrations

# IMPORTANT: import models
from app.models import song
from app.models import listening_history
from app.models import artist
from app.models import tag
from app.models import song_tag
from app.models import user_session
from app.models import recommendation_feedback
from app.models import listening_goal
from app.models import dedup_merge_log
from .routes import user_routes
from .routes import playlist_routes
from .routes import music_routes
from .routes import dashboard_routes
from .routes import insights_routes
from .routes import reports_routes
from .routes import ops_routes
from app.routes import filter_routes

app = FastAPI(title="Music Recommendation API")

# Local development CORS configuration for frontend testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Run migrations before and after create_all:
# before for legacy column/table compatibility, after for indexes on freshly created tables.
run_startup_migrations()
Base.metadata.create_all(bind=engine)
run_startup_migrations()
app.include_router(user_routes.router)
app.include_router(playlist_routes.router)
app.include_router(music_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(insights_routes.router)
app.include_router(reports_routes.router)
app.include_router(filter_routes.router)
app.include_router(ops_routes.router)


@app.get("/")
def root():
    return {"message": "Music Recommendation API Running"}
