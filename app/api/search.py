import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.database import get_db
from app.models.api import SearchRequest, SearchResponse, RetrievalComparisonResponse
from app.services.retrieval_service import RetrievalService
from app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repositories/{id}", tags=["Search"])

@router.post("/search", response_model=SearchResponse)
def search_repository(id: str, request: SearchRequest, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return RetrievalService.search(db, id, request)

@router.post("/compare-retrieval", response_model=RetrievalComparisonResponse)
def compare_retrieval(id: str, request: SearchRequest, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return RetrievalService.compare_retrieval(db, id, request.query)
