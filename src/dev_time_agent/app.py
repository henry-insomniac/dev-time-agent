from fastapi import FastAPI
from pydantic import BaseModel

from dev_time_agent.conversation import answer_conversation_turn
from dev_time_agent.schemas import ConversationTurnRequest, EvidenceBundle


class ConversationTurnPayload(BaseModel):
    conversation_id: str
    risk_assessment_id: str
    message: str
    evidence_bundle: EvidenceBundle


app = FastAPI(title="Dev Time Agent Runtime")


@app.post("/conversation/turn")
def conversation_turn(payload: ConversationTurnPayload):
    return answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id=payload.conversation_id,
            project_id=payload.evidence_bundle.project.id,
            risk_assessment_id=payload.risk_assessment_id,
            message=payload.message,
        ),
        payload.evidence_bundle,
    )
