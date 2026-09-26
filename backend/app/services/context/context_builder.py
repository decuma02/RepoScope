from typing import List, Dict, Any
from backend.app.schemas.api import SearchResultItem, RelationshipEvidenceItem

class ContextBuilder:
    """
    Assembles bounded AI context packages and source maps from retrieval candidates.
    """

    @staticmethod
    def build_context_package(
        query: str,
        repo_name: str,
        results: List[SearchResultItem],
        relationships: List[RelationshipEvidenceItem],
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        context_items = []
        total_estimated_tokens = 0

        for r in results:
            item = {
                "sourceId": r.sourceId,
                "filePath": r.filePath,
                "startLine": r.startLine,
                "endLine": r.endLine,
                "content": r.excerpt
            }
            estimated = len(r.excerpt.split()) + 15
            if total_estimated_tokens + estimated > max_tokens:
                break
            context_items.append(item)
            total_estimated_tokens += estimated

        rel_evidence = [
            {
                "relationshipId": rel.relationshipId,
                "source": rel.sourcePath,
                "target": rel.targetPath,
                "type": rel.type
            }
            for rel in relationships[:10]
        ]

        return {
            "query": query,
            "repositoryName": repo_name,
            "context": context_items,
            "relationships": rel_evidence,
            "tokenEstimate": total_estimated_tokens
        }
