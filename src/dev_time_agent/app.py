from fastapi import FastAPI
from pydantic import BaseModel

from dev_time_agent.conversation import answer_conversation_turn, classify_intent
from dev_time_agent.schemas import ConversationTurnRequest, EvidenceBundle


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
    return answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id=payload.conversation_id,
            project_id=project_id or "",
            risk_assessment_id=payload.risk_assessment_id,
            message=payload.message,
        ),
        payload.evidence_bundle,
    )
