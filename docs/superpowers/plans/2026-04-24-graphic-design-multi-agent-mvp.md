# Graphic design multi-agent MVP — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a runnable **P0** vertical slice: FastAPI backend with **planner + worker stubs**, typed **agent messages**, in-memory bus, SQLite job store, and a **minimal review API** that simulates Approve / Try new / Modify—so later tasks can swap in real image and Gmail adapters without rewriting the orchestration.

**Architecture:** **Supervisor (planner)** runs a deterministic state machine per job; **workers** are plain callables registered by role name. Events append to `job_events`. Human actions POST to `/jobs/{id}/action`. Gmail and image generation are **stubbed** in P0 behind interfaces.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLite (aiosqlite or stdlib sqlite3), pytest, httpx for API tests.

---

### Task 1: Repository hygiene and Python package layout

**Files:**
- Create: `graphic_studio/pyproject.toml`
- Create: `graphic_studio/README.md`
- Create: `graphic_studio/graphic_studio/__init__.py`
- Modify: `.gitignore` (repo root): ensure `.worktrees/`, `job-search-box*.md` patterns if missing

- [ ] **Step 1: Add `pyproject.toml`** (package name `graphic-studio`, deps: fastapi, uvicorn, pydantic)

```toml
[project]
name = "graphic-studio"
version = "0.1.0"
description = "Multi-agent graphic design studio (MVP scaffold)"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "pydantic>=2.10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "httpx>=0.27.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["graphic_studio"]
```

- [ ] **Step 2: Add package `graphic_studio/graphic_studio/__init__.py`** with `__version__ = "0.1.0"`

- [ ] **Step 3: Install in editable mode**

Run: `cd graphic_studio && pip install -e ".[dev]"`  
Expected: install succeeds

- [ ] **Step 4: Commit**

```bash
git add graphic_studio/pyproject.toml graphic_studio/README.md graphic_studio/graphic_studio/__init__.py .gitignore
git commit -m "chore(graphic-studio): scaffold Python package"
```

---

### Task 2: Agent message schemas and in-memory bus

**Files:**
- Create: `graphic_studio/graphic_studio/agents/messages.py`
- Create: `graphic_studio/graphic_studio/agents/bus.py`
- Create: `graphic_studio/graphic_studio/agents/__init__.py`
- Test: `graphic_studio/tests/test_messages.py`

- [ ] **Step 1: Write failing test for message round-trip**

```python
# graphic_studio/tests/test_messages.py
from graphic_studio.agents.messages import AgentEnvelope, AgentRole, AgentTask


def test_envelope_task_json_roundtrip():
    task = AgentTask(
        job_id="job-1",
        task_id="t1",
        role=AgentRole.RESEARCH,
        payload={"brief": "chocolate wrapper"},
    )
    env = AgentEnvelope(task=task)
    data = env.model_dump(mode="json")
    restored = AgentEnvelope.model_validate(data)
    assert restored.task is not None
    assert restored.task.role == AgentRole.RESEARCH
```

- [ ] **Step 2: Run test — expect failure** (`pytest graphic_studio/tests/test_messages.py -q`)

- [ ] **Step 3: Implement `messages.py`**

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    PLANNER = "planner"
    RESEARCH = "research"
    DESIGN = "design"
    EMAIL = "email"
    MARKETING = "marketing"


class AgentTask(BaseModel):
    job_id: str
    task_id: str
    role: AgentRole
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    job_id: str
    task_id: str
    role: AgentRole
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class HumanGate(BaseModel):
    job_id: str
    gate: Literal["review", "send_confirm"]
    prompt: str


class AgentEnvelope(BaseModel):
    task: AgentTask | None = None
    result: AgentResult | None = None
    human_gate: HumanGate | None = None
```

- [ ] **Step 4: Implement in-memory bus** (`bus.py`: `publish`, `subscribe` list, simple fan-out for tests)

- [ ] **Step 5: Run tests** — expect PASS

- [ ] **Step 6: Commit** — `feat(agents): add message schemas and in-memory bus`

---

### Task 3: SQLite job store and event log

**Files:**
- Create: `graphic_studio/graphic_studio/store.py`
- Test: `graphic_studio/tests/test_store.py`

- [ ] **Step 1: Failing test** — create job, append event, load events

- [ ] **Step 2: Implement** SQLite schema: `jobs(id, status, brief, created_at)`, `job_events(id, job_id, kind, body_json, created_at)`

- [ ] **Step 3: pytest PASS, commit** — `feat(store): sqlite job and event log`

---

### Task 4: Planner + stub workers (single-process loop)

**Files:**
- Create: `graphic_studio/graphic_studio/agents/workers.py`
- Create: `graphic_studio/graphic_studio/agents/planner.py`
- Test: `graphic_studio/tests/test_planner.py`

- [ ] **Step 1: Stub workers** return fixed dicts per role (research → `references`, design → `image_url` stub)

- [ ] **Step 2: Planner** — on new job: enqueue research → design → set status `awaiting_review` + human_gate

- [ ] **Step 3: Test** full loop until gate

- [ ] **Step 4: Commit** — `feat(planner): supervisor loop with stub workers`

---

### Task 5: FastAPI HTTP API

**Files:**
- Create: `graphic_studio/graphic_studio/api/main.py`
- Create: `graphic_studio/graphic_studio/api/__init__.py`
- Test: `graphic_studio/tests/test_api.py`

- [ ] **Step 1: Endpoints**
  - `POST /jobs` body `{ "brief": "..." }` → creates job, starts planner
  - `GET /jobs/{id}` → status + latest artifact + pending gate
  - `POST /jobs/{id}/action` body `{ "action": "approve" | "try_new" | "modify", "note": "optional" }`

- [ ] **Step 2: httpx async tests** against `TestClient`

- [ ] **Step 3: Commit** — `feat(api): job CRUD and review actions`

---

### Task 6: Runbook

**Files:**
- Modify: `graphic_studio/README.md`

- [ ] **Step 1: Document** `uvicorn graphic_studio.api.main:app --reload` and example curl

- [ ] **Step 2: Commit** — `docs(graphic-studio): runbook for P0 API`

---

## Self-review (plan)

- Spec coverage: P0 planner, workers, review gates, Gmail deferred to P2 per design phases — covered by stubs and follow-up tasks (not all in this file; add P2 plan later).
- No TBD steps in P0 tasks above.

## Execution handoff

Plan complete. Prefer **subagent-driven-development** per task, or **executing-plans** inline with checkpoints.
