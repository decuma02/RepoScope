"""
main.py — FastAPI application factory and entrypoint for RepoScope.

Responsibilities:
  - Creates and configures the FastAPI ``app`` instance.
  - Registers CORS middleware with origins read from ``settings.CORS_ORIGINS``.
  - Attaches a unified exception handler that normalises both HTTPException and
    unexpected Python exceptions into a consistent JSON error envelope.
  - Mounts the five feature routers (repositories, analysis, search, chat, graph)
    under the configured API prefix (default: ``/api/v1``).
  - In production (when ``frontend/dist`` is present), serves the compiled Vite
    SPA and its static assets so a single process handles both API and UI.

Vercel serverless entrypoint: ``api/index.py`` imports ``app`` from here.
Local dev: ``uvicorn backend.app.main:app --reload``
"""

import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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
    """Application lifespan handler.

    Runs ``init_db()`` on startup to create all SQLite tables if they do not
    exist yet (idempotent DDL).  No teardown logic is required.
    """
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

# CORS configuration
cors_origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False if "*" in cors_origins else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    """Global exception handler — normalises all errors to the standard envelope.

    HTTPException detail may be either a plain string or a structured dict
    with ``code``, ``message``, and ``details`` keys.  Unhandled Python
    exceptions become HTTP 500 responses with ``INTERNAL_ERROR`` codes.
    A unique ``requestId`` is generated for every error to aid log correlation.
    """
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
    """Liveness probe endpoint.

    Returns the running version, project name, and deployment environment.
    Used by Vercel health checks and monitoring tools.
    """
    return {"status": "ok", "version": settings.VERSION, "project": settings.PROJECT_NAME, "environment": settings.ENVIRONMENT}

app.include_router(repositories_router, prefix=settings.API_PREFIX)
app.include_router(analysis_router, prefix=settings.API_PREFIX)
app.include_router(search_router, prefix=settings.API_PREFIX)
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(graph_router, prefix=settings.API_PREFIX)

# Serve Frontend static assets in production if compiled dist folder exists
frontend_dist = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA catch-all route for production self-hosted deployments.

        Serves static assets directly when a matching file exists inside
        ``frontend/dist``.  All other paths return ``index.html`` so that
        React Router can handle client-side navigation.

        API, docs, and health paths are excluded and return 404 so they are
        never accidentally handled as SPA routes.

        Note: On Vercel this route is never hit because ``vercel.json`` handles
        static file serving and SPA fallback at the CDN/edge layer.
        """
        if (
            full_path.startswith("api/")
            or full_path == "health"
            or full_path.startswith("docs")
            or full_path.startswith("redoc")
            or full_path.startswith("openapi.json")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        target_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(target_path):
            return FileResponse(target_path)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Not Found")

