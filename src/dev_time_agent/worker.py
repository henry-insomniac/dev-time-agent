from typing import Protocol

from dev_time_agent.llm import OpenAICompatibleLLMClient
from dev_time_agent.schemas import AgentArtifact, AgentJob, EvidenceBundle
from dev_time_agent.workflows.pr_doctor import run_pr_doctor
from dev_time_agent.workflows.risk_scout import run_risk_scout


class ServerClient(Protocol):
    def claim_next_agent_job(self) -> AgentJob | None: ...

    def get_evidence_bundle(self, risk_assessment_id: str) -> EvidenceBundle: ...

    def complete_agent_job(self, artifact: AgentArtifact) -> None: ...


class LLMClient(Protocol):
    def generate_agent_artifact(
        self,
        job: AgentJob,
        bundle: EvidenceBundle,
    ) -> AgentArtifact: ...


def process_next_agent_job(server_client: ServerClient) -> bool:
    job = server_client.claim_next_agent_job()
    if job is None:
        return False

    evidence_bundle = server_client.get_evidence_bundle(job.risk_assessment_id)
    artifact = run_workflow(job, evidence_bundle, llm_client_for(server_client))
    server_client.complete_agent_job(artifact)

    return True


def run_workflow(
    job: AgentJob,
    evidence_bundle: EvidenceBundle,
    llm_client: LLMClient | None = None,
) -> AgentArtifact:
    if llm_client is not None:
        return llm_client.generate_agent_artifact(job, evidence_bundle)

    if job.agent_type == "risk_scout":
        return run_risk_scout(job, evidence_bundle)
    if job.agent_type == "pr_doctor":
        return run_pr_doctor(job, evidence_bundle)

    raise ValueError(f"unsupported agent type: {job.agent_type}")


def llm_client_for(server_client: ServerClient) -> LLMClient | None:
    get_llm_provider_config = getattr(server_client, "get_llm_provider_config", None)
    if not callable(get_llm_provider_config):
        return None

    return OpenAICompatibleLLMClient(get_llm_provider_config())
