"""
analysis.py — REST endpoints for triggering and polling repository analysis jobs.

Routes (all prefixed with ``/api/v1/repositories/{id}``):
  POST /analyze  – Trigger a new analysis pipeline run.
                   Accepts an optional ``force`` flag to re-run even if ANALYZING.
                   Returns HTTP 202 with the initial AnalysisJobResponse.
  GET  /status   – Poll the latest analysis job for a repository.
                   Clients should call this on a short interval while status is
                   ANALYZING; the job transitions to READY or FAILED on completion.
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.core.database import get_db
from backend.app.schemas.api import AnalysisTriggerRequest, AnalysisJobResponse
from backend.app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/repositories/{id}", tags=["Analysis"])

@router.post("/analyze", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(id: str, request: AnalysisTriggerRequest = AnalysisTriggerRequest(), db: sqlite3.Connection = Depends(get_db)):
    """Trigger the four-stage analysis pipeline for a repository.

    Stages: DISCOVERY → PARSING_STRUCTURE → EXTRACTING_RELATIONSHIPS → COMPLETED

    The pipeline runs synchronously in the request thread (suitable for small/medium
    repos).  If the repository is already ANALYZING and ``force`` is False, the
    in-progress job is returned instead of spawning a duplicate run.

    Args:
        id:      Repository ID (path parameter).
        request: Optional body; set ``force=true`` to cancel and restart.
        db:      Injected SQLite connection.

    Returns:
        HTTP 202 with the AnalysisJobResponse for the newly created (or existing) job.
    """
    job = AnalysisService.trigger_analysis(db, id, force=request.force or False)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return job

@router.get("/status", response_model=AnalysisJobResponse)
def poll_analysis_status(id: str, db: sqlite3.Connection = Depends(get_db)):
    """Return the latest analysis job record for a repository.

    Clients poll this endpoint while ``status == ANALYZING``.  The frontend
    WorkspacePage uses a 1.5-second interval timer for live progress updates.

    Returns HTTP 404 if no analysis job has ever been created for the repository.
    """
    cursor = db.cursor()
    cursor.execute("SELECT id FROM analysis_jobs WHERE repository_id = ? ORDER BY started_at DESC LIMIT 1", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"No analysis job found for repository '{id}'."}
        )
    job = AnalysisService.get_job_status(db, row["id"])
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job metadata not found."}
        )
    return job
