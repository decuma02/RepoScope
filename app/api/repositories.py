import sqlite3
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.database import get_db
from app.models.api import RepositoryCreateRequest, RepositoryResponse, RepositoryListResponse, TreeResponse, FileDetailResponse
from app.services.repository_service import RepositoryService
from app.security.repository_boundary import RepositoryBoundaryError

router = APIRouter(prefix="/repositories", tags=["Repositories"])

@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def create_repository(request: RepositoryCreateRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        return RepositoryService.create_repository(db, request)
    except RepositoryBoundaryError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_REPOSITORY", "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST", "message": str(e)}
        )

@router.get("", response_model=RepositoryListResponse)
def list_repositories(db: sqlite3.Connection = Depends(get_db)):
    repos = RepositoryService.get_all_repositories(db)
    return RepositoryListResponse(repositories=repos)

@router.get("/{id}", response_model=RepositoryResponse)
def get_repository(id: str, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return repo

@router.get("/{id}/tree", response_model=TreeResponse)
def get_repository_tree(id: str, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    tree = RepositoryService.get_tree(db, id)
    return TreeResponse(repositoryId=id, tree=tree)

@router.get("/{id}/files/{file_id}", response_model=FileDetailResponse)
def get_file_detail(
    id: str,
    file_id: str,
    startLine: Optional[int] = Query(1, alias="startLine"),
    endLine: Optional[int] = Query(None, alias="endLine"),
    db: sqlite3.Connection = Depends(get_db)
):
    detail = RepositoryService.get_file_detail(db, id, file_id, startLine, endLine)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": f"File '{file_id}' not found in repository '{id}'."}
        )
    return detail
