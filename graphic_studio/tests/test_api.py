import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIC_STUDIO_DB", str(tmp_path / "api.sqlite"))
    from graphic_studio.api.main import app

    return TestClient(app)


def test_create_and_review_flow(client):
    r = client.post("/jobs", json={"brief": "card design"})
    assert r.status_code == 200
    job_id = r.json()["id"]
    assert r.json()["status"] == "awaiting_review"

    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job"]["latest_artifact"].startswith("stub://design/")

    r3 = client.post(f"/jobs/{job_id}/action", json={"action": "approve"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "awaiting_send_confirm"

    r4 = client.post(
        f"/jobs/{job_id}/action",
        json={"action": "send_stub", "note": "client@example.com"},
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == "sent"
