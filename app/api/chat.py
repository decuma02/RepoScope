import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.database import get_db
from app.models.api import ChatRequest, ChatResponse
from app.services.ai_service import AIService
from app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repositories/{id}", tags=["AI Chat"])

@router.post("/chat", response_model=ChatResponse)
def ask_grounded_question(id: str, request: ChatRequest, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return AIService.answer_question(db, id, request)
