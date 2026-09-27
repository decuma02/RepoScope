"""
chat.py — AI-grounded chat endpoint for RepoScope.

Route (prefixed with ``/api/v1/repositories/{id}``):
  POST /chat  – Accept a natural-language question and return an AI-generated
               answer grounded in the repository’s indexed code.  The response
               includes cited source ranges, relationship evidence, and a
               GraphFocus hint so the UI can highlight relevant graph nodes.

The heavy lifting is done by ``AIService.answer_question`` which retrieves
relevant code chunks via the RetrievalService and passes them as context to
the configured AI provider.
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.core.database import get_db
from backend.app.schemas.api import ChatRequest, ChatResponse
from backend.app.services.ai.ai_service import AIService
from backend.app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repositories/{id}", tags=["AI Chat"])

@router.post("/chat", response_model=ChatResponse)
def ask_grounded_question(id: str, request: ChatRequest, db: sqlite3.Connection = Depends(get_db)):
    """Answer a natural-language question grounded in the repository’s code.

    The endpoint:
      1. Validates the repository exists.
      2. Delegates to ``AIService.answer_question`` which performs retrieval-
         augmented generation (RAG) using the indexed code chunks.
      3. Returns a structured response with the answer text, cited source
         ranges, relationship evidence, and graph focus node IDs.

    Args:
        id:      Repository ID (path parameter).
        request: JSON body containing the ``question`` string.
        db:      Injected SQLite connection.

    Returns:
        ``ChatResponse`` with ``answer``, ``sources``, ``relationshipEvidence``,
        ``graphFocus``, and ``confidence`` fields.
    """
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return AIService.answer_question(db, id, request)
