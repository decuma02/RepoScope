import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.api.repositories import router as repositories_router
from backend.app.api.analysis import router as analysis_router
from backend.app.api.search import router as search_router
from backend.app.api.chat import router as chat_router
from backend.app.api.graph import router as graph_router
from backend.app.schemas.api import ErrorResponse, ErrorDetail

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="RepoScope Repository Intelligence & Grounded Retrieval Engine",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    req_id = f"req_{uuid.uuid4().hex[:12]}"

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        if isinstance(exc.detail, dict):
            error_code = exc.detail.get("code", "REQUEST_ERROR")
            message = exc.detail.get("message", "An error occurred processing the request.")
            details = exc.detail.get("details", {})
        else:
            error_code = "HTTP_ERROR"
            message = str(exc.detail)
            details = {}
    else:
        status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        error_code = "INTERNAL_ERROR" if status_code == 500 else "REQUEST_FAILED"
        message = str(exc) if str(exc) else "An unexpected error occurred."
        details = {}

    error_payload = ErrorResponse(
        error=ErrorDetail(
            code=error_code,
            message=message,
            details=details,
            retryable=(status_code in [502, 503, 504]),
            requestId=req_id
        )
    )
    return JSONResponse(status_code=status_code, content=error_payload.model_dump())

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "version": settings.VERSION, "project": settings.PROJECT_NAME, "environment": settings.ENVIRONMENT}

app.include_router(repositories_router, prefix=settings.API_PREFIX)
app.include_router(analysis_router, prefix=settings.API_PREFIX)
app.include_router(search_router, prefix=settings.API_PREFIX)
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(graph_router, prefix=settings.API_PREFIX)
