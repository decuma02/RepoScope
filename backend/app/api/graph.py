"""
graph.py — Focused relationship-graph query endpoint.

Route (prefixed with ``/api/v1/repositories/{id}``):
  GET /graph  – Return a focused sub-graph (nodes + edges) for visualisation.
               Optional query params:
                 ``nodeId``    – centre the graph on a specific node
                 ``sourceIds`` – seed the graph from a list of node IDs
               Without params the endpoint returns the entire graph (up to a
               configurable limit defined in GraphService).

The response is consumed by the frontend GraphVisualizer component which
renders the graph using a force-directed layout.
"""

import sqlite3
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from backend.app.core.database import get_db
from backend.app.schemas.api import GraphResponse
from backend.app.services.graph.graph_service import GraphService
from backend.app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repositories/{id}", tags=["Graph"])

@router.get("/graph", response_model=GraphResponse)
def get_focused_graph(
    id: str,
    nodeId: Optional[str] = Query(None, alias="nodeId"),
    sourceIds: Optional[List[str]] = Query(None, alias="sourceIds"),
    db: sqlite3.Connection = Depends(get_db)
):
    repo = RepositoryService.get_repository(db, id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return GraphService.get_focused_graph(db, id, nodeId, sourceIds)
