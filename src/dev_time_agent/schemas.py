from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator


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


class SelectedResource(BaseModel):
    type: str
    id: str
    name: str


class PageContext(BaseModel):
    route: str = ""
    locale: str = ""
    timezone: str = ""
    user_role: str = ""
    selected_resource: SelectedResource | None = None
    visible_fields: dict = Field(default_factory=dict)
    recent_actions: list[dict] = Field(default_factory=list)


class ConversationTurnRequest(BaseModel):
    conversation_id: str
    project_id: str
    risk_assessment_id: str
    message: str
    page_context: PageContext | None = None


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
    program: AgentProgram | None = None
    answer_strategy: str
    reasoning_summary: str
    safety_notes: list[str] = Field(default_factory=list)


class AgentProgramArgumentRef(BaseModel):
    var: str = Field(alias="$var")


class AgentProgramStep(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["tool", "select"]
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    from_step: str = ""
    selector: str = ""
    output_key: str = ""

    @model_validator(mode="after")
    def validate_step_shape(self) -> Self:
        if self.kind == "tool":
            if self.tool == "":
                raise ValueError("tool steps require tool")
            if self.selector or self.from_step or self.output_key:
                raise ValueError("tool steps cannot declare selectors")
        if self.kind == "select":
            if self.from_step == "":
                raise ValueError("select steps require from_step")
            if not is_valid_agent_program_selector(self.selector):
                raise ValueError("select steps require a valid selector")
            if self.output_key == "":
                raise ValueError("select steps require output_key")
            if self.tool or self.arguments:
                raise ValueError("select steps cannot call tools")
        return self


class AgentProgramAnswerContract(BaseModel):
    format: Literal["text", "json"] = "text"
    required_sections: list[str] = Field(default_factory=list)
    must_cite_evidence: bool = False


class AgentProgram(BaseModel):
    version: Literal["agent_program.v1"]
    goal: str
    steps: list[AgentProgramStep] = Field(min_length=1, max_length=12)
    answer_contract: AgentProgramAnswerContract

    @model_validator(mode="after")
    def validate_step_references(self) -> Self:
        seen_steps: set[str] = set()
        seen_variables: set[str] = set()
        for step in self.steps:
            if step.id in seen_steps:
                raise ValueError(f"duplicate step id: {step.id}")
            if step.kind == "select":
                if step.from_step not in seen_steps:
                    raise ValueError(
                        f"select step {step.id} references unknown step "
                        f"{step.from_step}"
                    )
                if step.output_key in seen_variables:
                    raise ValueError(f"duplicate variable: {step.output_key}")
                seen_variables.add(step.output_key)
            if step.kind == "tool":
                for variable_name in agent_program_variable_refs(step.arguments):
                    if variable_name not in seen_variables:
                        raise ValueError(
                            f"tool step {step.id} references unknown variable "
                            f"{variable_name}"
                        )
            seen_steps.add(step.id)
        return self

    def validate_against_tool_specs(self, registry) -> Self:
        registered_tools = set(registry.names())
        for step in self.steps:
            if step.kind != "tool":
                continue
            if step.tool not in registered_tools:
                raise ValueError(f"tool is not registered: {step.tool}")
            capability = registry.get(step.tool)
            validate_agent_program_arguments(step, capability.input_schema)
        return self


def is_valid_agent_program_selector(selector: str) -> bool:
    if selector == "":
        return False
    if not selector.startswith("$."):
        return False
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "$._[]"
    )
    return all(character in allowed for character in selector)


def agent_program_variable_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        if set(value.keys()) == {"$var"} and isinstance(value["$var"], str):
            refs.append(value["$var"])
        else:
            for nested in value.values():
                refs.extend(agent_program_variable_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.extend(agent_program_variable_refs(nested))
    return refs


def validate_agent_program_arguments(
    step: AgentProgramStep,
    input_schema: dict[str, Any],
) -> None:
    required_arguments = input_schema.get("required", [])
    for argument_name in required_arguments:
        if argument_name not in step.arguments:
            raise ValueError(
                f"tool step {step.id} is missing required argument {argument_name}"
            )
    properties = input_schema.get("properties", {})
    for argument_name, argument_value in step.arguments.items():
        property_schema = properties.get(argument_name)
        if property_schema is None or is_agent_program_variable_ref(argument_value):
            continue
        expected_type = property_schema.get("type")
        if expected_type == "string" and not isinstance(argument_value, str):
            raise ValueError(
                f"tool step {step.id} argument {argument_name} must be string"
            )
        if expected_type == "integer" and not isinstance(argument_value, int):
            raise ValueError(
                f"tool step {step.id} argument {argument_name} must be integer"
            )


def is_agent_program_variable_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {"$var"}


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
