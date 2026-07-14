"""Central capability policy for authenticated and shared demo sessions."""

from fastapi import HTTPException

from .config import settings


CAPABILITY_KEYS = (
    "sync_spotify",
    "import_history",
    "enrich_metadata",
    "preview_playlists",
    "create_spotify_playlists",
    "manage_schedules",
    "mutate_library",
    "submit_feedback",
    "manage_goals",
    "manage_account",
)


def is_demo_user(user_id: str | None) -> bool:
    return bool(user_id and user_id == settings.DEMO_USER_ID)


def capabilities_for(user_id: str | None, *, spotify_connected: bool = False) -> dict[str, bool]:
    if not user_id:
        return {key: False for key in CAPABILITY_KEYS}
    if is_demo_user(user_id):
        return {
            "sync_spotify": False,
            "import_history": False,
            "enrich_metadata": False,
            "preview_playlists": True,
            "create_spotify_playlists": False,
            "manage_schedules": False,
            "mutate_library": False,
            "submit_feedback": False,
            "manage_goals": False,
            "manage_account": False,
        }
    return {
        "sync_spotify": bool(spotify_connected),
        "import_history": True,
        "enrich_metadata": True,
        "preview_playlists": True,
        "create_spotify_playlists": bool(spotify_connected),
        "manage_schedules": True,
        "mutate_library": True,
        "submit_feedback": True,
        "manage_goals": True,
        "manage_account": True,
    }


def require_capability(user_id: str | None, capability: str, *, spotify_connected: bool = False) -> None:
    capabilities = capabilities_for(user_id, spotify_connected=spotify_connected)
    if not capabilities.get(capability, False):
        message = (
            "This action is not available in guest demo mode."
            if is_demo_user(user_id)
            else "Connect or reconnect Spotify to use this action."
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "capability_not_available",
                "capability": capability,
                "message": message,
            },
        )
