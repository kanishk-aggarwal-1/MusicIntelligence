from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import engine, Base, run_startup_migrations

# IMPORTANT: import models
from .models import song
from .models import listening_history
from .models import artist
from .models import api_cache
from .models import generated_playlist
from .models import generated_playlist_track
from .models import job
from .models import tag
from .models import song_tag
from .models import user_session
from .models import recommendation_feedback
from .models import listening_goal
from .models import dedup_merge_log
from .routes import user_routes
from .routes import playlist_routes
from .routes import music_routes
from .routes import dashboard_routes
from .routes import insights_routes
from .routes import job_routes
from .routes import discovery_routes
from .routes import reports_routes
from .routes import ops_routes
from .routes import filter_routes

app = FastAPI(title="Music Recommendation API")

# Local development CORS configuration for frontend testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
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
app.include_router(job_routes.router)
app.include_router(discovery_routes.router)
app.include_router(reports_routes.router)
app.include_router(filter_routes.router)
app.include_router(ops_routes.router)


@app.get("/")
def root():
    return {"message": "Music Recommendation API Running"}
