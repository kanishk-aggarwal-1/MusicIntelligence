from backend.app.services.spotify_service import fetch_recent_tracks


def _item(played_at, spotify_id):
    return {
        "played_at": played_at,
        "track": {
            "id": spotify_id,
            "uri": f"spotify:track:{spotify_id}",
            "name": f"Track {spotify_id}",
            "artists": [{"id": "artist", "name": "Artist"}],
            "album": {"images": []},
        },
    }


def test_fetch_recent_tracks_stops_at_saved_checkpoint():
    class FakeSpotify:
        def __init__(self):
            self.calls = []

        def current_user_recently_played(self, **kwargs):
            self.calls.append(kwargs)
            return {"items": [
                _item("2026-07-14T12:00:00Z", "new-2"),
                _item("2026-07-14T11:00:00Z", "new-1"),
                _item("2026-07-14T10:00:00Z", "old"),
            ]}

    spotify = FakeSpotify()
    tracks = fetch_recent_tracks(spotify, max_tracks=1000, since_played_at="2026-07-14T10:30:00Z")

    assert [track["spotify_id"] for track in tracks] == ["new-2", "new-1"]
    assert len(spotify.calls) == 1


def test_fetch_recent_tracks_paginates_until_empty():
    pages = [
        [_item("2026-07-14T12:00:00Z", "one")],
        [_item("2026-07-14T11:00:00Z", "two")],
        [],
    ]

    class FakeSpotify:
        def current_user_recently_played(self, **kwargs):
            return {"items": pages.pop(0)}

    tracks = fetch_recent_tracks(FakeSpotify(), max_tracks=1000)
    assert [track["spotify_id"] for track in tracks] == ["one", "two"]
