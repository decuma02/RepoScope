# RepoScope REST API Specification & Contracts

All endpoints are prefixed with `/api`. Data payloads are strictly JSON.

## Frozen API Matrix

| Method | Endpoint | Purpose | Request Body | Response DTO | Status |
|--------|----------|---------|--------------|--------------|--------|
| `POST` | `/api/repositories` | Register repository source | `{ "name": "...", "sourceType": "local_path", "sourcePath": "..." }` | `RepositoryResponse` | 201 Created |
| `GET`  | `/api/repositories/{id}` | Get repository status & metadata | - | `RepositoryResponse` | 200 OK |
| `POST` | `/api/repositories/{id}/analyze` | Start one-shot background analysis | `{ "force": false }` | `AnalysisJobResponse` | 202 Accepted |
| `GET`  | `/api/repositories/{id}/status` | Poll analysis job progress | - | `AnalysisJobResponse` | 200 OK |
| `GET`  | `/api/repositories/{id}/tree` | Get repository directory tree | - | `TreeResponse` | 200 OK |
| `GET`  | `/api/repositories/{id}/files/{fileId}` | Get file excerpt and components | - | `FileDetailResponse` | 200 OK |
| `POST` | `/api/repositories/{id}/search` | Run relationship-aware retrieval | `{ "query": "...", "limit": 10, "relationshipAware": true }` | `SearchResponse` | 200 OK |
| `POST` | `/api/repositories/{id}/chat` | Answer grounded AI question | `{ "question": "..." }` | `ChatResponse` | 200 OK |
| `GET`  | `/api/repositories/{id}/graph` | Get focused 2D graph DTO | Query: `nodeId`, `sourceIds` | `GraphResponse` | 200 OK |

## Standard Error Format
```json
{
  "error": {
    "code": "INVALID_REPOSITORY",
    "message": "Repository path does not exist",
    "details": {},
    "retryable": false,
    "requestId": "req_12345678"
  }
}
```
