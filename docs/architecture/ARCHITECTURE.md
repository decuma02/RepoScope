# RepoScope Architecture & Technical Blueprint

## 1. Overview & Core Purpose
**RepoScope** is a repository-aware intelligence and retrieval engine designed for the IBM Bob 2.0 Hackathon. It addresses developer context fragmentation by constructing a lightweight structural model of code repositories—tracking file hierarchy, code components (functions, classes, modules), and inter-component relationships (imports/exports and approximate symbol usage)—to power grounded, traceable AI responses and focused graph visualizations.

### The Pipeline
```
Repository Ingestion ──► Structure Extraction ──► Relationship Extraction ──► Search & Retrieval ──► Grounded AI Chat (with Traceability) & Focused Graph
```

---

## 2. System Architecture: Modular Monolith
To maximize performance, keep setup friction at zero, and avoid microservice orchestration overhead during hackathon execution, RepoScope is built as a **FastAPI Modular Monolith** in Python 3.11.

```
                    ┌────────────────────────────────────────────────────────┐
                    │                      REST API Layer                    │
                    │         (FastAPI Routers + Standard Error Handler)     │
                    └───────────────────────────┬────────────────────────────┘
                                                │
         ┌───────────────────┬──────────────────┼───────────────────┬───────────────────┐
         ▼                   ▼                  ▼                   ▼                   ▼
┌──────────────────┐ ┌───────────────┐ ┌──────────────────┐ ┌────────────────┐ ┌─────────────────┐
│ Repository &     │ │ Analysis      │ │ Retrieval        │ │ Grounded AI    │ │ Graph Query     │
│ Boundary Service │ │ Orchestrator  │ │ Engine           │ │ & Context      │ │ Service         │
└────────┬─────────┘ └───────┬───────┘ └────────┬─────────┘ └───────┬────────┘ └────────┬────────┘
         │                   │                  │                   │                   │
         └───────────────────┴──────────────────┼───────────────────┴───────────────────┘
                                                ▼
                                   ┌─────────────────────────┐
                                   │  SQLite / Local Store   │
                                   └─────────────────────────┘
```

---

## 3. Directory Layout Alignment
```
repo/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   ├── structure/
│   │   │   ├── relationships/
│   │   │   ├── retrieval/
│   │   │   ├── context/
│   │   │   ├── ai/
│   │   │   └── graph/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── storage/
│   │   ├── core/
│   │   └── main.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── golden/
├── frontend/
├── data/
├── ai/
├── bob_sessions/
├── bob_tasks/
├── demo/
└── docs/
```
