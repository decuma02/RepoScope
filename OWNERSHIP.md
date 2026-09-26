# RepoScope - IBM Bob 2.0 Hackathon Team Ownership & Workstreams

## Member 1: Backend Infrastructure & Repository Intelligence
- Repository ingestion pipeline (`backend/app/services/ingestion`)
- Code structure extraction (`backend/app/services/structure`)
- Relationship mining engine (`backend/app/services/relationships`)
- SQLite storage & boundary security (`backend/app/storage`, `backend/app/core`)
- REST APIs for repository discovery & analysis (`backend/app/api/repositories.py`, `analysis.py`)

## Member 2: Retrieval, Context Assembly & Watsonx AI Integration
- Relationship-aware search & ranking engine (`backend/app/services/retrieval`)
- Bounded context package assembly (`backend/app/services/context`)
- IBM Watsonx / Granite LLM integration (`backend/app/services/ai`)
- Grounded prompt engineering & system instructions (`ai/prompts/`)
- Server-side source ID validation & traceability contracts

## Member 3: Frontend Interface & Visualization
- Repository Selector & Workspace Shell (`frontend/src/pages/`, `frontend/src/components/`)
- Explorer View & Bounded Source Code Viewer
- Grounded AI Chat Window & Source Citation Evidence Panel
- Interactive Focused 2D Graph Visualizer (`frontend/src/components/graph/`)
- Demo fixtures & mock API client integration (`frontend/src/fixtures/`)

## Integration & Rehearsal (All Members)
- Shared Pydantic / TypeScript data contracts (`backend/app/schemas/api.py`, `frontend/src/types/reposcope.ts`)
- API contract documentation (`docs/api/API_CONTRACTS.md`)
- Golden questions test suite & live rehearsal runs (`backend/tests/golden/`, `demo/`)
