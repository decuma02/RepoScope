# RepoScope - Repository Intelligence Engine (IBM Bob 2.0 Hackathon)

**RepoScope** is a repository-aware intelligence and retrieval backend that turns codebase file trees and dependency graphs into grounded, traceable AI context. Built as a proof-of-concept for the IBM Bob 2.0 Hackathon.

## Core Capabilities
- **One-Shot Repository Ingestion & Parsing**: Extract directory structure, code components (functions, classes, modules), and dependency edges (`IMPORTS`, `EXPORTS`, `USES`).
- **Relationship-Aware Retrieval**: Search codebase candidates using lexical relevance boosted by graph adjacency.
- **Grounded AI Answering with Source Traceability**: Produce structured answers where every claim is tied to verified file/line source ranges.
- **Focused Graph Generation**: Expose focused 2D node/edge relationship views.
- **FastAPI Modular Monolith**: Zero-dependency overhead, high performance, fully asynchronous REST API.

## Repository Architecture & Structure
See [docs/architecture/ARCHITECTURE.md](file:///d:/git/akhil_repo_list/work/RepoScope/docs/architecture/ARCHITECTURE.md) for full design blueprint.
See [docs/api/API_CONTRACTS.md](file:///d:/git/akhil_repo_list/work/RepoScope/docs/api/API_CONTRACTS.md) for frozen API route specifications.
See [OWNERSHIP.md](file:///d:/git/akhil_repo_list/work/RepoScope/OWNERSHIP.md) for team workstreams and responsibilities.

```
repo/
├── backend/            # FastAPI Backend Modular Monolith & Unit/Integration Tests
├── frontend/           # React + TypeScript + Vite workspace (explorer, chat, graph)
├── data/               # Local Repository Storage & Demo Fixtures
├── ai/                 # Prompts, Prompt Lab & Test Cases
├── bob_sessions/       # IBM Bob Session Logs & Screenshots Evidence
├── bob_tasks/          # IBM Bob Task Specifications & Task Notes
├── demo/               # Rehearsal Assets & Golden Demo Questions
└── docs/               # Architecture, API & Decision Documentation
```

## Running Locally

### 1. Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional)

### 2. Quickstart with Python
```bash
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

### 3. Running Backend Tests
```bash
python -m pytest backend/tests -v
```

### 4. Frontend (Vite + React)
```bash
cd frontend
npm install
npm run dev
```
The UI runs at http://localhost:5173 and proxies `/api` to the backend on port 8000.
Open http://localhost:5173/?mock=1 to tour the workspace with bundled fixtures when the API is down.

### 5. Quickstart with Docker
```bash
docker build -t reposcope-backend .
docker run -p 8000:8000 reposcope-backend
```
Or via docker-compose:
```bash
docker-compose up --build
```
