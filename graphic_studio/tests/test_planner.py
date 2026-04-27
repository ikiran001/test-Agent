import pytest

from graphic_studio import store
from graphic_studio.agents.bus import InMemoryBus
from graphic_studio.agents.planner import Planner


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIC_STUDIO_DB", str(tmp_path / "planner.sqlite"))


def test_planner_runs_until_review_gate():
    store.init_schema()
    job = store.create_job("chocolate wrapper")
    bus = InMemoryBus()
    seen: list[str] = []

    def sub(env):
        if env.task:
            seen.append(f"task:{env.task.role.value}")
        if env.result:
            seen.append(f"result:{env.result.role.value}")

    bus.subscribe(sub)
    planner = Planner(bus=bus)
    planner.start_job(job.id)

    j = store.get_job(job.id)
    assert j.status == "awaiting_review"
    assert j.latest_artifact is not None
    assert "task:research" in seen and "task:design" in seen
