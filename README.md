# Repolytic - Repository Intelligence Engine (IBM Bob 2.0 Hackathon)

Repolytic is a repository intelligence and relationship-aware retrieval backend that turns codebase file trees and dependency graphs into grounded, traceable AI context.

## Core Features
- **One-Shot Repository Ingestion & Parsing**: Extract directory structure, code components (functions, classes, modules), and dependency edges (`IMPORTS`, `EXPORTS`, `USES`).
- **Relationship-Aware Retrieval**: Search codebase candidates using lexical relevance boosted by graph adjacency.
- **Grounded AI Answering with Source Traceability**: Produce structured answers where every claim is tied to verified file/line source ranges.
- **Focused Graph Generation**: Expose focused 2D node/edge relationship views.
- **FastAPI Modular Monolith**: Zero-dependency overhead, high performance, fully asynchronous REST API.

## Architecture
See [ARCHITECTURE.md](file:///d:/git/akhil_repo_list/work/RepoScope/ARCHITECTURE.md) for full design blueprint, domain models, and API specifications.

## Running Locally

### 1. Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional)

### 2. Quickstart with Python
```bash
python -m venv venv
# On Windows: venv\Scripts\activate
# On Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Quickstart with Docker
```bash
docker build -t repolytic-backend .
docker run -p 8000:8000 repolytic-backend
```
Or via docker-compose:
```bash
docker-compose up --build
```
