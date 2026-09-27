"""
search.py — Semantic/lexical search and retrieval comparison endpoints.

Routes (prefixed with ``/api/v1/repositories/{id}``):
  POST /search            – Relationship-aware code search against a READY repository.
                            Returns ranked ``SearchResultItem`` chunks with lexical
                            and relationship-bonus scores.
  POST /compare-retrieval – Side-by-side comparison of relationship-aware vs
                            plain text-only retrieval for the same query.  Useful
                            for demonstrating the value of the graph expansion step.

Both endpoints require the repository to be in READY status; in-progress or
unanalysed repositories return HTTP 409.
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.core.database import get_db
from backend.app.schemas.api import SearchRequest, SearchResponse, RetrievalComparisonResponse
from backend.app.services.retrieval.search_engine import RetrievalService
from backend.app.services.repository_service import RepositoryService
from backend.app.models.domain import RepositoryStatus

router = APIRouter(prefix="/repositories/{id}", tags=["Search"])


def _require_ready_repository(repo_id: str, db: sqlite3.Connection):
    """Fetch the repository and raise appropriate HTTP errors if it is missing or not READY."""
    repo = RepositoryService.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{repo_id}' not found."}
        )
    if repo.status == RepositoryStatus.ANALYZING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REPOSITORY_ANALYZING", "message": "Analysis in progress, try again shortly."}
        )
    if repo.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REPOSITORY_NOT_READY", "message": f"Repository is not ready for retrieval (status: {repo.status.value})."}
        )
    return repo


@router.post("/search", response_model=SearchResponse)
def search_repository(id: str, request: SearchRequest, db: sqlite3.Connection = Depends(get_db)):
    _require_ready_repository(id, db)
    return RetrievalService.search(db, id, request)

@router.post("/compare-retrieval", response_model=RetrievalComparisonResponse)
def compare_retrieval(id: str, request: SearchRequest, db: sqlite3.Connection = Depends(get_db)):
    _require_ready_repository(id, db)
    return RetrievalService.compare_retrieval(db, id, request.query)
