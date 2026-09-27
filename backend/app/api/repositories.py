"""
repositories.py — REST endpoints for repository CRUD and relationship graph queries.

All routes are prefixed with ``/api/v1/repositories`` (or the value of
``settings.API_PREFIX + '/repositories'``).

Endpoints:
  POST   /                              – Register a new repository (local or GitHub)
  GET    /                              – List all registered repositories
  GET    /{id}                          – Retrieve a single repository by ID
  GET    /{id}/tree                     – Return the file tree of a repository
  GET    /{id}/files/{file_id}          – Get file content, metadata and components
  GET    /{id}/components               – List all extracted code components
  GET    /{id}/relationships            – List all dependency relationships
  GET    /{id}/relationships/nodes/{node_id}/outgoing  – Outgoing edges for a node
  GET    /{id}/relationships/nodes/{node_id}/incoming  – Incoming edges for a node
  GET    /{id}/relationships/nodes/{node_id}/neighbors – One-hop neighbour IDs
  GET    /{id}/relationships/by-type/{rel_type}        – Filter edges by type
  GET    /{id}/files/{file_id}/relationships           – Edges touching a file
  POST   /{id}/reset                    – Wipe all analysis data for a repository
"""

import sqlite3
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from backend.app.core.database import get_db
from backend.app.models.domain import RelationshipType
from backend.app.schemas.api import (
    RepositoryCreateRequest, RepositoryResponse, RepositoryListResponse,
    TreeResponse, FileDetailResponse, ComponentListResponse,
    RelationshipListResponse, NeighborListResponse,
)
from backend.app.services.repository_service import RepositoryService
from backend.app.services.relationships.index import RelationshipIndex
from backend.app.storage.boundary import RepositoryBoundaryError

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

@router.get("/{id}/components", response_model=ComponentListResponse)
def get_components(id: str, type: Optional[str] = Query(None), db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return RepositoryService.get_components(db, id, type)

@router.get("/{id}/relationships", response_model=RelationshipListResponse)
def get_relationships(id: str, type: Optional[str] = Query(None), db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return RepositoryService.get_relationships(db, id, type)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _require_repo(db: sqlite3.Connection, repo_id: str) -> None:
    if not RepositoryService.get_repository(db, repo_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{repo_id}' not found."},
        )


# ---------------------------------------------------------------------------
# Relationship index query endpoints
# ---------------------------------------------------------------------------

@router.get("/{id}/relationships/nodes/{node_id}/outgoing", response_model=RelationshipListResponse)
def get_outgoing_relationships(id: str, node_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Return all relationships where the given node is the source."""
    _require_repo(db, id)
    return RelationshipIndex.get_outgoing(db, id, node_id)


@router.get("/{id}/relationships/nodes/{node_id}/incoming", response_model=RelationshipListResponse)
def get_incoming_relationships(id: str, node_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Return all relationships where the given node is the target."""
    _require_repo(db, id)
    return RelationshipIndex.get_incoming(db, id, node_id)


@router.get("/{id}/relationships/nodes/{node_id}/neighbors", response_model=NeighborListResponse)
def get_one_hop_neighbors(id: str, node_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Return unique node IDs that are one hop away from the given node."""
    _require_repo(db, id)
    return RelationshipIndex.get_neighbors(db, id, node_id)


@router.get("/{id}/relationships/by-type/{rel_type}", response_model=RelationshipListResponse)
def get_relationships_by_type(id: str, rel_type: str, db: sqlite3.Connection = Depends(get_db)):
    """Return all relationships of a specific type (IMPORTS, EXPORTS, USES)."""
    _require_repo(db, id)
    try:
        rtype = RelationshipType(rel_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_RELATIONSHIP_TYPE", "message": f"Unknown relationship type: '{rel_type}'"},
        )
    return RelationshipIndex.get_by_type(db, id, rtype)


@router.get("/{id}/files/{file_id}/relationships", response_model=RelationshipListResponse)
def get_file_relationships(id: str, file_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Return all relationships that touch a specific file as source or target."""
    _require_repo(db, id)
    return RelationshipIndex.get_for_file(db, id, file_id)

@router.post("/{id}/reset", status_code=status.HTTP_200_OK)
def reset_repository(id: str, db: sqlite3.Connection = Depends(get_db)):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    RepositoryService.reset_repository(db, id)
    return {"message": f"Repository '{id}' index has been reset successfully."}
