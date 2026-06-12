from fastapi import FastAPI
from pydantic import BaseModel

from dev_time_agent.conversation import classify_intent
from dev_time_agent.graph_runtime import run_agent_session_turn
from dev_time_agent.schemas import EvidenceBundle


class ConversationIntentPayload(BaseModel):
    conversation_id: str
    project_id: str
    risk_assessment_id: str
    message: str


class ConversationTurnPayload(BaseModel):
    conversation_id: str
    project_id: str | None = None
    risk_assessment_id: str
    message: str
    evidence_bundle: EvidenceBundle | None = None


app = FastAPI(title="Dev Time Agent Runtime")


@app.post("/conversation/intent")
def conversation_intent(payload: ConversationIntentPayload):
    return classify_intent(payload.message)


@app.post("/conversation/turn")
def conversation_turn(payload: ConversationTurnPayload):
    project_id = payload.project_id
    if payload.evidence_bundle is not None:
        project_id = payload.evidence_bundle.project.id
    graph_response = run_agent_session_turn(
        session_id="legacy_" + payload.conversation_id,
        conversation_id=payload.conversation_id,
        project_id=project_id or "",
        risk_assessment_id=payload.risk_assessment_id,
        message=payload.message,
        evidence_bundle=payload.evidence_bundle,
    )
    return {
        "conversation_id": graph_response.conversation_id,
        "user_message": graph_response.user_message,
        "agent_response": graph_response.agent_response,
        "evidence_refs": graph_response.evidence_refs,
        "intent": graph_response.intent,
    }


@app.post("/agent/sessions/{session_id}/turns")
def agent_session_turn(session_id: str, payload: ConversationTurnPayload):
    project_id = payload.project_id
    if payload.evidence_bundle is not None:
        project_id = payload.evidence_bundle.project.id
    return run_agent_session_turn(
        session_id=session_id,
        conversation_id=payload.conversation_id,
        project_id=project_id or "",
        risk_assessment_id=payload.risk_assessment_id,
        message=payload.message,
        evidence_bundle=payload.evidence_bundle,
    )
