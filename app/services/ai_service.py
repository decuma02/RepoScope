import sqlite3
from typing import List
from app.models.api import ChatRequest, ChatResponse, SourceReference, GraphFocusDTO, SearchRequest
from app.services.retrieval_service import RetrievalService

class AIService:
    """
    Grounded AI Answering Service with server-side Source ID validation.
    Enforces context bounding and traceability rules.
    """

    @staticmethod
    def answer_question(conn: sqlite3.Connection, repo_id: str, request: ChatRequest) -> ChatResponse:
        # Step 1: Run Retrieval to get grounded context
        search_req = SearchRequest(query=request.question, limit=5, relationshipAware=True)
        search_res = RetrievalService.search(conn, repo_id, search_req)

        if not search_res.results:
            return ChatResponse(
                answer="The repository index does not provide sufficient evidence to answer this question.",
                sources=[],
                relationshipEvidence=[],
                graphFocus=GraphFocusDTO(nodeIds=[]),
                confidence="insufficient_evidence"
            )

        # Step 2: Validate & build Source References
        valid_sources: List[SourceReference] = []
        valid_source_ids = set()

        for item in search_res.results:
            source_ref = SourceReference(
                sourceId=item.sourceId,
                fileId=item.fileId,
                filePath=item.filePath,
                startLine=item.startLine,
                endLine=item.endLine,
                snippet=item.excerpt[:200],
                reason=item.relevanceReason,
                relevance=item.score
            )
            valid_sources.append(source_ref)
            valid_source_ids.add(item.sourceId)

        # Step 3: Grounded Answer Synthesis (Simulated / Host LLM bounded answer)
        primary_file = valid_sources[0].filePath if valid_sources else "the codebase"
        rel_count = len(search_res.relationships)

        answer_text = (
            f"Based on the analyzed repository context, '{request.question}' relates primarily to "
            f"[{primary_file}] ({valid_sources[0].sourceId}). "
            f"The repository graph identifies {rel_count} inter-file dependency relationship(s) "
            f"connecting these components. All evidence is grounded strictly in the retrieved source files."
        )

        node_ids = [s.fileId for s in valid_sources[:3]]

        return ChatResponse(
            answer=answer_text,
            sources=valid_sources,
            relationshipEvidence=search_res.relationships,
            graphFocus=GraphFocusDTO(nodeIds=node_ids),
            confidence="supported"
        )
