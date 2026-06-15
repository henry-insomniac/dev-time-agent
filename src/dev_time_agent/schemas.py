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
    model: str = "deterministic"
    prompt_version: str = "dev-time-agent@v1"


class ActionSuggestion(BaseModel):
    action_type: str
    target_ref: str
    draft_body: str
    reason: str
    evidence_refs: list[str]
    required_permission: str


class LLMProviderConfig(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: str


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


class ConversationTurnRequest(BaseModel):
    conversation_id: str
    project_id: str
    risk_assessment_id: str
    message: str


class ConversationTurnResponse(BaseModel):
    conversation_id: str
    user_message: str
    agent_response: str
    evidence_refs: list[str]
    intent: str


class IntentClassification(BaseModel):
    intent: str
    confidence: float
    requires_evidence: bool
    requires_tool: bool = False
    requires_approval: bool = False
    clarifying_question: str = ""


class AgentPlan(BaseModel):
    intent: str
    domain: str = ""
    entities: dict = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    confidence: float
    needs_evidence: bool
    needs_tools: bool
    tool_names: list[str] = Field(default_factory=list)
    answer_strategy: str
    reasoning_summary: str
    safety_notes: list[str] = Field(default_factory=list)


class AgentDraftResponse(BaseModel):
    answer: str
    evidence_refs: list[str] = Field(default_factory=list)
    suggested_actions: list[dict] = Field(default_factory=list)
    reasoning_summary: str
    confidence: float


class ResponseVerification(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    rewrite_instruction: str = ""


class AgentTraceEvent(BaseModel):
    node: str
    title: str


class ReasoningTraceStep(BaseModel):
    stage: str
    title: str
    summary: str
    status: str = "completed"
    confidence: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    tool_call: dict | None = None


class AgentSessionTurnResponse(BaseModel):
    session_id: str
    conversation_id: str
    user_message: str
    agent_response: str
    intent: str
    domain: str = ""
    entities: dict = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    confidence: float
    evidence_refs: list[str]
    current_node: str
    trace_events: list[AgentTraceEvent]
    tool_calls: list[dict] = Field(default_factory=list)
    approval_request: dict | None = None
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)
