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
