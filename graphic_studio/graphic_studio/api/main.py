from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from graphic_studio import store
from graphic_studio.agents.planner import Planner

app = FastAPI(title="Graphic Studio", version="0.1.0")
planner = Planner()


class CreateJobBody(BaseModel):
    brief: str = Field(min_length=1)


class ActionBody(BaseModel):
    action: str
    note: str | None = None


@app.on_event("startup")
def _startup() -> None:
    store.init_schema()


def _job_to_dict(job: store.JobRecord) -> dict:
    pending = None
    if job.pending_gate:
        try:
            pending = json.loads(job.pending_gate)
        except json.JSONDecodeError:
            pending = {"raw": job.pending_gate}
    return {
        "id": job.id,
        "status": job.status,
        "brief": job.brief,
        "latest_artifact": job.latest_artifact,
        "variant": job.variant,
        "pending_gate": pending,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/jobs")
def create_job(body: CreateJobBody) -> dict:
    job = store.create_job(body.brief)
    planner.start_job(job.id)
    return _job_to_dict(store.get_job(job.id))


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        job = store.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    events = store.list_events(job_id)
    return {"job": _job_to_dict(job), "events": events}


@app.post("/jobs/{job_id}/action")
def job_action(job_id: str, body: ActionBody) -> dict:
    try:
        store.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    try:
        planner.handle_action(job_id, body.action, body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _job_to_dict(store.get_job(job_id))
