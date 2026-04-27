from __future__ import annotations

import json
from typing import Any

from graphic_studio.agents.bus import InMemoryBus, default_bus
from graphic_studio.agents.messages import AgentEnvelope, AgentResult, AgentRole, AgentTask, HumanGate
from graphic_studio.agents.workers import (
    StubDesignWorker,
    StubEmailWorker,
    StubResearchWorker,
    new_task_id,
)
from graphic_studio import store


class Planner:
    """Supervisor: runs stub research → design, then waits at review gate."""

    def __init__(self, bus: InMemoryBus | None = None) -> None:
        self.bus = bus or default_bus
        self.research = StubResearchWorker()
        self.design = StubDesignWorker()
        self.email = StubEmailWorker()

    def start_job(self, job_id: str) -> None:
        job = store.get_job(job_id)
        if job.status != "new":
            return
        store.update_job(job_id, status="running")
        store.append_event(job_id, "planner", {"phase": "start"})
        self._run_research_and_design(job_id, job.brief, job.variant)

    def _run_research_and_design(self, job_id: str, brief: str, variant: int, modify_note: str = "") -> None:
        r_task = AgentTask(
            job_id=job_id,
            task_id=new_task_id(),
            role=AgentRole.RESEARCH,
            payload={"brief": brief},
        )
        self.bus.publish(AgentEnvelope(task=r_task))
        r_result = self.research.run(r_task)
        self.bus.publish(AgentEnvelope(result=r_result))
        store.append_event(job_id, "agent_result", {"role": "research", "data": r_result.data})

        prompt = self._build_prompt(brief, r_result.data, variant, modify_note)
        d_task = AgentTask(
            job_id=job_id,
            task_id=new_task_id(),
            role=AgentRole.DESIGN,
            payload={"brief": brief, "variant": variant, "modify_note": modify_note, "prompt": prompt},
        )
        self.bus.publish(AgentEnvelope(task=d_task))
        d_result = self.design.run(d_task)
        self.bus.publish(AgentEnvelope(result=d_result))
        store.append_event(job_id, "agent_result", {"role": "design", "data": d_result.data})

        artifact = d_result.data.get("image_url", "")
        gate = HumanGate(
            job_id=job_id,
            gate="review",
            prompt="Review the concept. Approve, try a new direction, or request a modification.",
        )
        store.update_job(
            job_id,
            status="awaiting_review",
            latest_artifact=str(artifact),
            pending_gate=json.dumps({"gate": "review", "prompt": gate.prompt}),
        )
        store.append_event(job_id, "human_gate", {"gate": "review"})
        self.bus.publish(AgentEnvelope(human_gate=gate))

    @staticmethod
    def _build_prompt(brief: str, research: dict[str, Any], variant: int, modify_note: str) -> str:
        base = f"Original brief: {brief}. Variant {variant}. Research summary: {research.get('summary', '')}"
        if modify_note:
            return f"{base}. User modification request: {modify_note}"
        return base

    def handle_action(self, job_id: str, action: str, note: str | None = None) -> None:
        job = store.get_job(job_id)
        note = note or ""

        if action == "approve" and job.status == "awaiting_review":
            store.append_event(job_id, "user_action", {"action": "approve"})
            store.update_job(job_id, status="awaiting_send_confirm", pending_gate=None)
            gate = HumanGate(
                job_id=job_id,
                gate="send_confirm",
                prompt="Confirm recipient email and send via Gmail (P2). P0: POST send_stub with body.",
            )
            store.update_job(
                job_id,
                pending_gate=json.dumps({"gate": "send_confirm", "prompt": gate.prompt}),
            )
            store.append_event(job_id, "human_gate", {"gate": "send_confirm"})
            self.bus.publish(AgentEnvelope(human_gate=gate))
            return

        if action == "try_new" and job.status == "awaiting_review":
            new_variant = job.variant + 1
            store.update_job(job_id, variant=new_variant, status="running", pending_gate=None)
            store.append_event(job_id, "user_action", {"action": "try_new", "variant": new_variant})
            self._run_research_and_design(job_id, job.brief, new_variant, modify_note="")
            return

        if action == "modify" and job.status == "awaiting_review":
            new_variant = job.variant + 1
            store.update_job(job_id, variant=new_variant, status="running", pending_gate=None)
            store.append_event(job_id, "user_action", {"action": "modify", "note": note, "variant": new_variant})
            self._run_research_and_design(job_id, job.brief, new_variant, modify_note=note)
            return

        if action == "send_stub" and job.status == "awaiting_send_confirm":
            to = note or "client@example.com"
            task = AgentTask(
                job_id=job_id,
                task_id=new_task_id(),
                role=AgentRole.EMAIL,
                payload={"to": to, "artifact": job.latest_artifact},
            )
            self.bus.publish(AgentEnvelope(task=task))
            result = self.email.run(task)
            self.bus.publish(AgentEnvelope(result=result))
            store.append_event(job_id, "agent_result", {"role": "email", "data": result.data})
            store.update_job(job_id, status="sent", pending_gate=None)
            store.append_event(job_id, "completed", {"status": "sent"})
            return

        raise ValueError(f"Invalid action {action!r} for status {job.status!r}")
