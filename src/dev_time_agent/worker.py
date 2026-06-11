from typing import Protocol

from dev_time_agent.schemas import AgentArtifact, AgentJob, EvidenceBundle
from dev_time_agent.workflows.pr_doctor import run_pr_doctor
from dev_time_agent.workflows.risk_scout import run_risk_scout


class ServerClient(Protocol):
    def claim_next_agent_job(self) -> AgentJob | None: ...

    def get_evidence_bundle(self, risk_assessment_id: str) -> EvidenceBundle: ...

    def complete_agent_job(self, artifact: AgentArtifact) -> None: ...


def process_next_agent_job(server_client: ServerClient) -> bool:
    job = server_client.claim_next_agent_job()
    if job is None:
        return False

    evidence_bundle = server_client.get_evidence_bundle(job.risk_assessment_id)
    artifact = run_workflow(job, evidence_bundle)
    server_client.complete_agent_job(artifact)

    return True


def run_workflow(job: AgentJob, evidence_bundle: EvidenceBundle) -> AgentArtifact:
    if job.agent_type == "risk_scout":
        return run_risk_scout(job, evidence_bundle)
    if job.agent_type == "pr_doctor":
        return run_pr_doctor(job, evidence_bundle)

    raise ValueError(f"unsupported agent type: {job.agent_type}")
