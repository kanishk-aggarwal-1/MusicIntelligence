from backend.app.routes.insights_routes import _canonical_title


def test_canonical_title_removes_common_noise():
    assert _canonical_title("My Song (Remastered 2011)") == "my song"
    assert _canonical_title("Track Name - Live Version") in {"track name -", "track name"}
