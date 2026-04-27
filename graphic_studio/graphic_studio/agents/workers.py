from __future__ import annotations

import uuid
from typing import Any, Protocol

from graphic_studio.agents.messages import AgentResult, AgentRole, AgentTask


class Worker(Protocol):
    def run(self, task: AgentTask) -> AgentResult: ...


class StubResearchWorker:
    def run(self, task: AgentTask) -> AgentResult:
        brief = str(task.payload.get("brief", ""))
        data = {
            "references": [
                {"title": "Category moodboard A", "notes": "premium minimal patterns (generic)"},
                {"title": "Category moodboard B", "notes": "warm confectionery palette (generic)"},
            ],
            "constraints": "Avoid logos and distinctive third-party trade dress; original layout.",
            "summary": f"Research summary for: {brief}",
        }
        return AgentResult(
            job_id=task.job_id,
            task_id=task.task_id,
            role=AgentRole.RESEARCH,
            ok=True,
            data=data,
        )


class StubDesignWorker:
    def run(self, task: AgentTask) -> AgentResult:
        variant = int(task.payload.get("variant", 0))
        note = str(task.payload.get("modify_note", ""))
        stub_url = f"stub://design/{task.job_id}/v{variant}"
        data = {
            "image_url": stub_url,
            "prompt_used": task.payload.get("prompt", ""),
            "modify_note": note,
        }
        return AgentResult(
            job_id=task.job_id,
            task_id=task.task_id,
            role=AgentRole.DESIGN,
            ok=True,
            data=data,
        )


class StubEmailWorker:
    def run(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            job_id=task.job_id,
            task_id=task.task_id,
            role=AgentRole.EMAIL,
            ok=True,
            data={"message_id": f"stub-{uuid.uuid4()}", "to": task.payload.get("to")},
        )


def new_task_id() -> str:
    return str(uuid.uuid4())
