# Repolytic Architecture & Technical Blueprint

## 1. Overview & Core Purpose
**Repolytic** is a repository-aware intelligence and retrieval engine designed for the IBM Bob 2.0 Hackathon. It addresses developer context fragmentation by constructing a lightweight structural model of code repositories—tracking file hierarchy, code components (functions, classes, modules), and inter-component relationships (imports/exports and approximate symbol usage)—to power grounded, traceable AI responses and focused graph visualizations.

### The Pipeline
```
Repository Ingestion ──► Structure Extraction ──► Relationship Extraction ──► Search & Retrieval ──► Grounded AI Chat (with Traceability) & Focused Graph
```

---

## 2. System Architecture: Modular Monolith
To maximize performance, keep setup friction at zero, and avoid microservice orchestration overhead during hackathon execution, Repolytic is built as a **FastAPI Modular Monolith** in Python 3.11.

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

## 3. Core Functional Modules

### 3.1 Repository Ingestion & Boundary (`app.security.repository_boundary`)
- Enforces strict path traversal prevention using resolved absolute path verification against repository roots.
- Denies symlinks resolving outside the root boundary.
- Enforces file size limits (default 1 MB) and safety rules.

### 3.2 Analysis & Extraction (`app.analysis`)
- **Discovery (`discovery.py`)**: File tree traversal enforcing ignore lists (`.git`, `node_modules`, `dist`, `__pycache__`, binaries, secrets).
- **Structure Extractor (`structure.py`)**: Lightweight AST/regex parser for Python/JavaScript/TypeScript extracting functions, classes, and top-level modules with line ranges.
- **Relationship Extractor (`relationships.py`)**: Extracts file dependency edges (`IMPORTS`, `EXPORTS`) and approximate symbol usage (`USES`).

### 3.3 Retrieval Engine (`app.services.retrieval_service`)
- Combines lexical query relevance scoring with **1-hop relationship expansion**.
- Re-ranks candidates based on direct lexical match, exact symbol hits, and graph connectivity bonus.
- Implements a text-only baseline mode for comparative evaluation.

### 3.4 AI Answering & Traceability (`app.services.ai_service`)
- Assembles bounded context packages adhering to model token budgets.
- Disallows general hallucination by instructing the LLM to rely strictly on provided context excerpts.
- Performs **server-side Source ID validation** to ensure model citations map strictly to retrieved evidence.

### 3.5 Focused Graph Service (`app.services.graph_service`)
- Produces bounded 1-hop adjacency graph DTOs centered around selected focus nodes (files or components) or chat evidence nodes.

---

## 4. API Specification & Rules

All API endpoints reside under `/api/repositories`. Responses are formatted in JSON. Errors conform to the standardized error schema.

### Standard Error Schema
```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human readable error description",
    "details": {},
    "retryable": false,
    "requestId": "req_12345678"
  }
}
```

### Endpoints Matrix
| Method | Endpoint | Description | Request Body | Status Code |
|--------|----------|-------------|--------------|-------------|
| `POST` | `/api/repositories` | Register repository source | `{ "name": string, "sourceType": "local_path", "sourcePath": string }` | 201 Created |
| `GET`  | `/api/repositories/{id}` | Get repository status & metadata | - | 200 OK |
| `POST` | `/api/repositories/{id}/analyze` | Trigger one-shot analysis | `{ "force": boolean }` | 202 Accepted |
| `GET`  | `/api/repositories/{id}/status` | Poll analysis job progress | - | 200 OK |
| `GET`  | `/api/repositories/{id}/tree` | Fetch repository directory tree | - | 200 OK |
| `GET`  | `/api/repositories/{id}/files/{fileId}` | Fetch file excerpt and component breakdown | - | 200 OK |
| `POST` | `/api/repositories/{id}/search` | Query relationship-aware retrieval | `{ "query": string, "limit": 10, "relationshipAware": true }` | 200 OK |
| `POST` | `/api/repositories/{id}/chat` | Ask grounded AI question | `{ "question": string }` | 200 OK |
| `GET`  | `/api/repositories/{id}/graph` | Fetch focused 2D graph data | Query params: `nodeId`, `sourceIds` | 200 OK |

---

## 5. Security & Data Integrity Protocol
1. **No Path Traversal**: Path resolution prevents accessing any file outside the registered repository root.
2. **Secret Masking**: Common `.env` keys, API credentials, and private keys are scrubbed prior to storage and prompt assembly.
3. **Bounded Context**: Prompts are constrained to preventing prompt-injection attacks from untrusted repository text.
