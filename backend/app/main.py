from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import engine, Base, run_startup_migrations
from .error_handlers import install_error_handlers

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
from .models import user_song_pref
from .models import playlist_schedule
from .models import metric_counter
from .routes import user_routes
from .routes import playlist_routes
from .routes import music_routes
from .routes import dashboard_routes
from .routes import insights_routes
from .routes import job_routes
from .routes import ops_routes
from .routes import stats_routes

app = FastAPI(title="Music Recommendation API")
install_error_handlers(app)

# In development allow any localhost/127.0.0.1 port so Vite port-increment
# and hostname differences (localhost vs 127.0.0.1) never cause CORS 400s.
_dev_origin_regex = (
    r"http://(localhost|127\.0\.0\.1)(:\d+)?"
    if settings.APP_ENV != "production"
    else None
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
