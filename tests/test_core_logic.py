from backend.app.routes.insights_routes import _canonical_title
from backend.app.services.recommendation_service import cosine_similarity


def test_canonical_title_removes_common_noise():
    assert _canonical_title("My Song (Remastered 2011)") == "my song"
    assert _canonical_title("Track Name - Live Version") in {"track name -", "track name"}


def test_cosine_similarity_basic_cases():
    a = {"rock": 1, "indie": 1}
    b = {"rock": 1, "indie": 1}
    c = {"edm": 1}

    assert cosine_similarity(a, b) == 1
    assert cosine_similarity(a, c) == 0
