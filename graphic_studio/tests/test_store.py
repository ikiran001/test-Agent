import pytest

from graphic_studio import store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIC_STUDIO_DB", str(tmp_path / "store.sqlite"))


def test_create_append_list_events():
    store.init_schema()
    job = store.create_job("brief here")
    store.append_event(job.id, "test", {"a": 1})
    store.append_event(job.id, "test", {"b": 2})
    ev = store.list_events(job.id)
    assert len(ev) == 2
    assert ev[0]["kind"] == "test"
    assert ev[0]["body"]["a"] == 1
