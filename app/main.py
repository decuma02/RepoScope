import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.repositories import router as repositories_router
from app.api.analysis import router as analysis_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.graph import router as graph_router
from app.models.api import ErrorResponse, ErrorDetail

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database tables
    init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Repolytic Repository Intelligence & Grounded Retrieval Engine",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard Error Exception Handler
@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    req_id = f"req_{uuid.uuid4().hex[:12]}"

    if hasattr(exc, "status_code") and hasattr(exc, "detail") and isinstance(exc.detail, dict):
        status_code = exc.status_code
        error_code = exc.detail.get("code", "REQUEST_ERROR")
        message = exc.detail.get("message", "An error occurred processing the request.")
        details = exc.detail.get("details", {})
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

# Health check
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "version": settings.VERSION, "environment": settings.ENVIRONMENT}

# Include API Routers
app.include_router(repositories_router, prefix=settings.API_PREFIX)
app.include_router(analysis_router, prefix=settings.API_PREFIX)
app.include_router(search_router, prefix=settings.API_PREFIX)
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(graph_router, prefix=settings.API_PREFIX)
