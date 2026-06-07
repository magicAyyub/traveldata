import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from traveldata.api.main import app  # noqa: E402


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"