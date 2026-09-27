# RepoScope — Repository Intelligence Engine

**RepoScope** is a repository-aware intelligence and retrieval backend that turns codebase file trees and dependency graphs into grounded, traceable AI context. Built as a proof-of-concept for the IBM Bob 2.0 Hackathon.

## Core Capabilities
- **One-Shot Repository Ingestion & Parsing**: Extract directory structure, code components (functions, classes, modules), and dependency edges (`IMPORTS`, `EXPORTS`, `USES`).
- **Relationship-Aware Retrieval**: Search codebase candidates using lexical relevance boosted by graph adjacency.
- **Grounded AI Answering with Source Traceability**: Produce structured answers where every claim is tied to verified file/line source ranges.
- **Focused Graph Generation**: Expose focused 2D node/edge relationship views.
- **Full-Stack Monolith**: FastAPI backend serves the compiled Vite/React frontend SPA as static files in production — single container, zero Nginx required.

## Repository Architecture & Structure
See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for full design blueprint.  
See [docs/api/API_CONTRACTS.md](docs/api/API_CONTRACTS.md) for frozen API route specifications.  
See [OWNERSHIP.md](OWNERSHIP.md) for team workstreams and responsibilities.

```
repo/
├── backend/            # FastAPI Backend Modular Monolith & Unit/Integration Tests
├── frontend/           # React + TypeScript + Vite SPA (explorer, chat, graph)
├── data/               # Local Repository Storage & Demo Fixtures
├── ai/                 # Prompts, Prompt Lab & Test Cases
├── bob_sessions/       # IBM Bob Session Logs & Screenshots Evidence
├── bob_tasks/          # IBM Bob Task Specifications & Task Notes
├── demo/               # Rehearsal Assets & Golden Demo Questions
└── docs/               # Architecture, API & Decision Documentation
```

---

## Running Locally (Development)

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

Backend API: http://localhost:8000  
Interactive docs: http://localhost:8000/docs

### Frontend (dev with HMR)
```bash
cd frontend
npm install
npm run dev
```
UI at http://localhost:5173 (proxies `/api` to port 8000).  
Open http://localhost:5173/?mock=1 for a guided tour using bundled fixture data (no backend needed).

### Running Tests
```bash
# All 395 tests (392 pass, 3 skipped)
pytest
```

---

## Deployment

### Option A — Docker Compose (Recommended)

Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env and set WATSONX_APIKEY and WATSONX_PROJECT_ID
```

Build and start (builds frontend + backend in a single image):
```bash
docker-compose up --build -d
```

App is available at **http://localhost:8000** (both API and UI served from the same port).

### Option B — Manual Docker

```bash
docker build -t reposcope .
docker run -p 8000:8000 \
  -e WATSONX_APIKEY=your_key \
  -e WATSONX_PROJECT_ID=your_project_id \
  -v reposcope_data:/app/data/index \
  reposcope
```

### Option C — Cloud / PaaS

The image is a self-contained Python 3.11 + Node 20 multi-stage build.  
Deploy to any container platform (Railway, Render, Fly.io, GCP Cloud Run, AWS ECS) by pointing it at the Dockerfile. The only required persistent volume is `/app/data/index` (for the SQLite DB).

**Required environment variables:**
| Variable | Required | Default |
|---|---|---|
| `WATSONX_APIKEY` | Yes (for AI chat) | — |
| `WATSONX_PROJECT_ID` | Yes (for AI chat) | — |
| `WATSONX_URL` | No | `https://us-south.ml.cloud.ibm.com` |
| `WATSONX_MODEL_ID` | No | `ibm/granite-13b-chat-v2` |
| `REPOSCOPE_ENV` | No | `development` |
| `REPOSCOPE_DB_PATH` | No | `data/index/reposcope.db` |
| `CORS_ORIGINS` | No | `["*"]` |

**Health check endpoint:** `GET /health`
