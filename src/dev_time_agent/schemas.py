from pydantic import BaseModel, Field


class AgentJob(BaseModel):
    job_id: str
    project_id: str
    risk_assessment_id: str
    agent_type: str
    trigger: str


class AgentArtifact(BaseModel):
    job_id: str
    project_id: str
    risk_assessment_id: str
    agent_type: str
    status: str
    summary: str
    evidence_refs: list[str]
    action_suggestions: list["ActionSuggestion"] = Field(default_factory=list)


class ActionSuggestion(BaseModel):
    action_type: str
    target_ref: str
    draft_body: str
    reason: str
    evidence_refs: list[str]
    required_permission: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    risk_score: int
    risk_level: str


class RiskAssessment(BaseModel):
    id: str
    project_id: str
    score: int
    level: str
    trend: str


class RiskSignal(BaseModel):
    id: str
    project_id: str
    category: str
    severity: int
    reason: str
    evidence_refs: list[str]


class EvidenceEvent(BaseModel):
    id: str
    event_type: str
    payload: dict


class EvidenceBundle(BaseModel):
    project: ProjectSummary
    assessment: RiskAssessment
    signals: list[RiskSignal]
    events: list[EvidenceEvent]
    allowed_actions: list[str]
