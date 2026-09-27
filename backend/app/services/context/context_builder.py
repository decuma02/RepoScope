from typing import List, Dict, Any
from backend.app.schemas.api import SearchResultItem, RelationshipEvidenceItem, SourceReference

# Rough token estimate: 1 token ≈ 4 characters (conservative)
_CHARS_PER_TOKEN = 4
# Per-item overhead for metadata fields (sourceId, filePath, lines, reason) ≈ 30 tokens
_ITEM_METADATA_TOKENS = 30


def _estimate_tokens(text: str) -> int:
    """Cheap character-based token estimate (no external dependencies)."""
    return max(1, len(text) // _CHARS_PER_TOKEN) + _ITEM_METADATA_TOKENS


class ContextBuilder:
    """
    Assembles a bounded, AI-ready context package from retrieval results.

    Responsibilities:
    - Accept SearchResultItem / RelationshipEvidenceItem from RetrievalService unchanged.
    - Map each result to a SourceReference (the canonical AI-facing contract).
    - Pack items in score order until the token budget is exhausted.
    - Attach relationship evidence (capped) for graph-aware answers.
    - Return a plain dict ready to be handed to any AI service.
    """

    @staticmethod
    def build_context_package(
        query: str,
        repo_name: str,
        results: List[SearchResultItem],
        relationships: List[RelationshipEvidenceItem],
        max_tokens: int = 4000,
        max_relationships: int = 10,
    ) -> Dict[str, Any]:
        """
        Build a compact, token-bounded context package.

        Parameters
        ----------
        query:            The original user query string.
        repo_name:        Human-readable repository name for provenance.
        results:          Ordered retrieval results (highest score first).
        relationships:    Relationship evidence items from the same search.
        max_tokens:       Hard token budget; items are skipped once exceeded.
        max_relationships: Maximum relationship evidence items to include.

        Returns
        -------
        dict with keys:
            query, repositoryName, sources (list of SourceReference dicts),
            relationships (list of evidence dicts), tokenEstimate.
        """
        sources: List[SourceReference] = []
        total_tokens = 0

        # Results arrive pre-ranked by RetrievalService; respect that order.
        for item in results:
            snippet = item.excerpt.strip() if item.excerpt else ""
            item_tokens = _estimate_tokens(snippet)

            if total_tokens + item_tokens > max_tokens:
                # Budget exhausted — stop adding items.
                break

            ref = SourceReference(
                sourceId=item.sourceId,
                fileId=item.fileId,
                filePath=item.filePath,
                componentName=item.componentName,
                startLine=item.startLine,
                endLine=item.endLine,
                snippet=snippet,
                reason=item.relevanceReason,
                relevance=item.score,
            )
            sources.append(ref)
            total_tokens += item_tokens

        rel_evidence = [
            {
                "relationshipId": rel.relationshipId,
                "source": rel.sourcePath,
                "target": rel.targetPath,
                "type": rel.type,
                "confidence": rel.confidence,
                "sourceLine": rel.sourceLine,
            }
            for rel in relationships[:max_relationships]
        ]

        return {
            "query": query,
            "repositoryName": repo_name,
            "sources": [s.model_dump() for s in sources],
            "relationships": rel_evidence,
            "tokenEstimate": total_tokens,
        }

    @staticmethod
    def build_source_map(results: List[SearchResultItem]) -> Dict[str, SourceReference]:
        """
        Build a lookup map from sourceId → SourceReference for citation validation.

        Useful for AI services that need to validate model-cited source IDs against
        the retrieved set before including them in a response.
        """
        source_map: Dict[str, SourceReference] = {}
        for item in results:
            snippet = item.excerpt.strip() if item.excerpt else ""
            ref = SourceReference(
                sourceId=item.sourceId,
                fileId=item.fileId,
                filePath=item.filePath,
                componentName=item.componentName,
                startLine=item.startLine,
                endLine=item.endLine,
                snippet=snippet,
                reason=item.relevanceReason,
                relevance=item.score,
            )
            source_map[item.sourceId] = ref
        return source_map
