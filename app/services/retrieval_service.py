import sqlite3
from typing import List, Dict, Any, Set
from app.models.api import SearchRequest, SearchResponse, SearchResultItem, RelationshipEvidenceItem
from app.security.repository_boundary import RepositoryBoundaryValidator

class RetrievalService:
    """
    Relationship-aware retrieval engine.
    1. Lexical seed matching across file paths, symbol names, and excerpts.
    2. 1-hop graph relationship expansion (IMPORTS, EXPORTS, USES).
    3. Re-ranking candidates based on graph adjacency and evidence quality.
    """

    @staticmethod
    def search(conn: sqlite3.Connection, repo_id: str, request: SearchRequest) -> SearchResponse:
        cursor = conn.cursor()

        # Fetch repo root
        cursor.execute("SELECT source_path FROM repositories WHERE id = ?", (repo_id,))
        repo_row = cursor.fetchone()
        if not repo_row:
            return SearchResponse(results=[], relationships=[])

        repo_root = repo_row["source_path"]
        query_terms = [t.lower() for t in request.query.split() if len(t) >= 2]

        if not query_terms:
            return SearchResponse(results=[], relationships=[])

        # Step 1: Lexical Candidate Seeds
        cursor.execute("SELECT * FROM files WHERE repository_id = ?", (repo_id,))
        file_rows = cursor.fetchall()

        cursor.execute("SELECT * FROM components WHERE repository_id = ?", (repo_id,))
        comp_rows = cursor.fetchall()

        seed_file_ids: Set[str] = set()
        file_scores: Dict[str, float] = {}

        for f in file_rows:
            f_path_lower = f["path"].lower()
            score = 0.0
            for term in query_terms:
                if term in f_path_lower:
                    score += 0.5
            if score > 0:
                file_scores[f["id"]] = score
                seed_file_ids.add(f["id"])

        for c in comp_rows:
            c_name_lower = c["name"].lower()
            for term in query_terms:
                if term in c_name_lower:
                    file_scores[c["file_id"]] = file_scores.get(c["file_id"], 0.0) + 0.8
                    seed_file_ids.add(c["file_id"])

        # Step 2: 1-hop Relationship Expansion
        relationship_evidence: List[RelationshipEvidenceItem] = []
        expanded_file_ids: Set[str] = set(seed_file_ids)

        if request.relationshipAware and seed_file_ids:
            cursor.execute(
                f"""
                SELECT * FROM relationships
                WHERE repository_id = ? AND (source_id IN ({','.join(['?']*len(seed_file_ids))}) OR target_id IN ({','.join(['?']*len(seed_file_ids))}))
                """,
                [repo_id] + list(seed_file_ids) + list(seed_file_ids)
            )
            rel_rows = cursor.fetchall()

            for r in rel_rows:
                src_id = r["source_id"]
                tgt_id = r["target_id"]
                rel_type = r["type"]

                # Expand adjacency
                if src_id in seed_file_ids and r["target_type"] == "file":
                    expanded_file_ids.add(tgt_id)
                    file_scores[tgt_id] = file_scores.get(tgt_id, 0.0) + 0.4
                elif tgt_id in seed_file_ids and r["source_type"] == "file":
                    expanded_file_ids.add(src_id)
                    file_scores[src_id] = file_scores.get(src_id, 0.0) + 0.4

                # Build Evidence Item
                relationship_evidence.append(
                    RelationshipEvidenceItem(
                        relationshipId=r["id"],
                        sourcePath=src_id,
                        targetPath=tgt_id,
                        type=rel_type,
                        confidence=r["confidence"],
                        sourceLine=r["source_line"]
                    )
                )

        # Step 3: Candidate Merge, Excerpt Generation & Re-Ranking
        results: List[SearchResultItem] = []

        for f in file_rows:
            if f["id"] not in expanded_file_ids:
                continue

            base_score = file_scores.get(f["id"], 0.1)
            is_seed = f["id"] in seed_file_ids
            rel_bonus = 0.4 if (is_seed and request.relationshipAware) else 0.0
            final_score = min(1.0, base_score + rel_bonus)

            # Read bounded snippet
            full_path = RepositoryBoundaryValidator.resolve_safe_path(repo_root, f["path"])
            excerpt = ""
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as fp:
                    excerpt = "".join(fp.readlines()[:25])
            except Exception:
                excerpt = "// Unable to read snippet"

            results.append(
                SearchResultItem(
                    sourceId=f"src_{f['id']}",
                    fileId=f["id"],
                    filePath=f["path"],
                    score=round(final_score, 2),
                    lexicalScore=round(base_score, 2),
                    relationshipBonus=round(rel_bonus, 2),
                    startLine=1,
                    endLine=min(25, 200),
                    excerpt=excerpt,
                    relevanceReason="Direct query match" if is_seed else "Graph 1-hop relationship match"
                )
            )

        # Sort by final score descending
        results.sort(key=lambda x: x.score, reverse=True)
        limit = request.limit or 10

        return SearchResponse(
            results=results[:limit],
            relationships=relationship_evidence[:15]
        )
