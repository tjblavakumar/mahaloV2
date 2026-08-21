from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from agents.context_manager import context_manager
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/api/chat", tags=["Chat"])
orchestrator = OrchestratorAgent()


class ChatMessage(BaseModel):
    persona: str
    message: str
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    timestamp: str
    conversation_id: str
    agents_used: list[str] | None = None


@router.get("/personas")
def personas():
    return {
        "personas": [
            {"id": "Executive", "name": "Executive", "description": "High-level metrics and status"},
            {"id": "Product Manager", "name": "Product Manager", "description": "Stories, backlog, priorities"},
            {"id": "Developer", "name": "Developer", "description": "Implementation and bug details"},
            {"id": "QA", "name": "QA", "description": "Regression and defect analysis"},
        ],
        "count": 4,
    }


@router.post("/message", response_model=ChatResponse)
async def send_message(payload: ChatMessage):
    conversation_id = payload.conversation_id or f"conv-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    history = [
        {"role": message["role"], "content": message["content"]}
        for message in context_manager.get_conversation_history(last_n=10, project_id=payload.project_id)
        if message["role"] in {"user", "assistant"}
    ]
    context_manager.add_message(
        "user",
        payload.message,
        {"conversation_id": conversation_id, "persona": payload.persona},
        project_id=payload.project_id,
    )

    response_text = await orchestrator.process_query(
        user_persona=payload.persona,
        user_query=payload.message,
        conversation_history=history,
        project_id=payload.project_id,
    )
    if orchestrator.last_agents_used:
        agents_used = orchestrator.last_agents_used
    else:
        route = orchestrator.route_query(payload.message)
        agents_used = [route.split(":", 1)[0]] if ":" in route else ["Orchestrator"]
    context_manager.add_message(
        "assistant",
        response_text,
        {"conversation_id": conversation_id, "agents_used": agents_used},
        project_id=payload.project_id,
    )

    return ChatResponse(
        response=response_text,
        timestamp=datetime.utcnow().isoformat(),
        conversation_id=conversation_id,
        agents_used=agents_used,
    )


@router.get("/history/{conversation_id}")
def get_history(conversation_id: str, limit: int = 10, project_id: Optional[str] = None):
    messages = [
        message
        for message in context_manager.get_conversation_history(last_n=limit, project_id=project_id)
        if message.get("metadata", {}).get("conversation_id") == conversation_id
    ]
    return {"conversation_id": conversation_id, "messages": messages, "count": len(messages)}
