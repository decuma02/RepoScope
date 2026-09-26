import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.database import get_db
from app.models.api import AnalysisTriggerRequest, AnalysisJobResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/repositories/{id}", tags=["Analysis"])

@router.post("/analyze", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(id: str, request: AnalysisTriggerRequest = AnalysisTriggerRequest(), db: sqlite3.Connection = Depends(get_db)):
    job = AnalysisService.trigger_analysis(db, id, force=request.force or False)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": f"Repository with id '{id}' not found."}
        )
    return job

@router.get("/status", response_model=AnalysisJobResponse)
def poll_analysis_status(id: str, db: sqlite3.Connection = Depends(get_db)):
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
