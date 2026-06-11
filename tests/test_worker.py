from dev_time_agent.schemas import (
    AgentArtifact,
    AgentJob,
    EvidenceBundle,
    EvidenceEvent,
    ProjectSummary,
    RiskAssessment,
    RiskSignal,
)
from dev_time_agent.worker import process_next_agent_job


def test_worker_runs_risk_scout_with_evidence_bundle() -> None:
    server = FakeServerClient(
        AgentJob(
            job_id="job_123",
            project_id="project_123",
            risk_assessment_id="risk_123",
            agent_type="risk_scout",
            trigger="risk.assessment.created",
        ),
        EvidenceBundle(
            project=ProjectSummary(
                id="project_123",
                name="dev-time-agent",
                risk_score=82,
                risk_level="high",
            ),
            assessment=RiskAssessment(
                id="risk_123",
                project_id="project_123",
                score=82,
                level="high",
                trend="up",
            ),
            signals=[
                RiskSignal(
                    id="signal_123",
                    project_id="project_123",
                    category="ci",
                    severity=85,
                    reason="unit tests failed on main",
                    evidence_refs=["event_check-run-123"],
                )
            ],
            events=[],
            allowed_actions=[],
        ),
    )

    processed = process_next_agent_job(server)

    assert processed is True
    assert server.succeeded_artifact is not None
    assert server.succeeded_artifact.job_id == "job_123"
    assert server.succeeded_artifact.agent_type == "risk_scout"
    assert server.succeeded_artifact.status == "succeeded"
    assert server.succeeded_artifact.summary == (
        "dev-time-agent is high risk because unit tests failed on main"
    )
    assert server.succeeded_artifact.evidence_refs == ["event_check-run-123"]


def test_worker_runs_pr_doctor_with_evidence_bundle() -> None:
    server = FakeServerClient(
        AgentJob(
            job_id="job_456",
            project_id="project_456",
            risk_assessment_id="risk_456",
            agent_type="pr_doctor",
            trigger="manual_refresh",
        ),
        EvidenceBundle(
            project=ProjectSummary(
                id="project_456",
                name="dev-time-server",
                risk_score=76,
                risk_level="high",
            ),
            assessment=RiskAssessment(
                id="risk_456",
                project_id="project_456",
                score=76,
                level="high",
                trend="up",
            ),
            signals=[
                RiskSignal(
                    id="signal_456",
                    project_id="project_456",
                    category="ci",
                    severity=80,
                    reason="check run failed",
                    evidence_refs=["event_check-run-456"],
                )
            ],
            events=[
                EvidenceEvent(
                    id="event_check-run-456",
                    event_type="check_run",
                    payload={"check_run": {"name": "go test"}},
                ),
                EvidenceEvent(
                    id="event_pull-request-456",
                    event_type="pull_request",
                    payload={"pull_request": {"number": 18, "title": "Add agent jobs"}},
                ),
            ],
            allowed_actions=["pr_comment"],
        ),
    )

    processed = process_next_agent_job(server)

    assert processed is True
    assert server.succeeded_artifact is not None
    assert server.succeeded_artifact.summary == "PR #18 is blocked by a failing go test check."
    assert len(server.succeeded_artifact.action_suggestions) == 1
    assert server.succeeded_artifact.action_suggestions[0].target_ref == "pull_request:18"


class FakeServerClient:
    def __init__(self, job: AgentJob, evidence_bundle: EvidenceBundle) -> None:
        self.job = job
        self.evidence_bundle = evidence_bundle
        self.succeeded_artifact: AgentArtifact | None = None

    def claim_next_agent_job(self) -> AgentJob | None:
        return self.job

    def get_evidence_bundle(self, risk_assessment_id: str) -> EvidenceBundle:
        assert risk_assessment_id == self.job.risk_assessment_id
        return self.evidence_bundle

    def complete_agent_job(self, artifact: AgentArtifact) -> None:
        self.succeeded_artifact = artifact
