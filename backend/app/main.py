from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, run_startup_migrations
from .error_handlers import install_error_handlers

# IMPORTANT: import models
from .models import (
    api_cache,
    artist,
    dedup_merge_log,
    generated_playlist,
    generated_playlist_track,
    job,
    listening_goal,
    listening_history,
    metric_counter,
    playlist_schedule,
    recommendation_feedback,
    song,
    song_tag,
    tag,
    user_session,
    user_song_pref,
)
from .routes import (
    dashboard_routes,
    insights_routes,
    job_routes,
    music_routes,
    ops_routes,
    playlist_routes,
    stats_routes,
    user_routes,
)

app = FastAPI(title="Music Recommendation API")
install_error_handlers(app)

# In development allow any localhost/127.0.0.1 port so Vite port-increment
# and hostname differences (localhost vs 127.0.0.1) never cause CORS 400s.
_dev_origin_regex = (
    r"http://(localhost|127\.0\.0\.1)(:\d+)?" if settings.APP_ENV != "production" else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=_dev_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Migration strategy:
# - run_startup_migrations() handles legacy additive compatibility fixes for
#   deployed databases that predate Alembic.
# - Base.metadata.create_all() creates any missing SQLAlchemy model tables.
# - Alembic is the migration path going forward; run_startup_migrations() is
#   legacy/frozen and should not grow further.
run_startup_migrations()
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    # Transient DB connection error at cold-start — same pattern as
    # run_startup_migrations().  Tables already exist on production; don't
    # crash the import and trigger a Render restart loop.
    import logging as _logging

    _logging.getLogger(__name__).exception("create_all failed at startup — continuing")
app.include_router(user_routes.router)
app.include_router(playlist_routes.router)
app.include_router(music_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(insights_routes.router)
app.include_router(job_routes.router)
app.include_router(ops_routes.router)
app.include_router(stats_routes.router)


@app.get("/")
def root():
    return {"message": "Music Recommendation API Running"}
