import sqlite3
from typing import List, Dict, Any, Set
from backend.app.schemas.api import SearchRequest, SearchResponse, SearchResultItem, RelationshipEvidenceItem, RetrievalComparisonResponse
from backend.app.storage.boundary import RepositoryBoundaryValidator

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

        cursor.execute("SELECT source_path FROM repositories WHERE id = ?", (repo_id,))
        repo_row = cursor.fetchone()
        if not repo_row:
            return SearchResponse(results=[], relationships=[])

        repo_root = repo_row["source_path"]
        query_terms = [t.lower() for t in request.query.split() if len(t) >= 2]

        if not query_terms:
            return SearchResponse(results=[], relationships=[])

        cursor.execute("SELECT * FROM files WHERE repository_id = ?", (repo_id,))
        file_rows = cursor.fetchall()

        cursor.execute("SELECT * FROM components WHERE repository_id = ?", (repo_id,))
        comp_rows = cursor.fetchall()

        seed_file_ids: Set[str] = set()
        file_scores: Dict[str, float] = {}
        # Maps file_id -> best matching chunk row (most query terms matched)
        best_chunks: Dict[str, Any] = {}

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

        # Content-chunk matching: query content_chunks scoped to repo, match terms case-insensitively
        like_clauses = " OR ".join(["LOWER(text) LIKE ?"] * len(query_terms))
        like_params = [f"%{term}%" for term in query_terms]
        cursor.execute(
            f"SELECT * FROM content_chunks WHERE repository_id = ? AND ({like_clauses})",
            [repo_id] + like_params,
        )
        chunk_rows = cursor.fetchall()

        for chunk in chunk_rows:
            chunk_text_lower = chunk["text"].lower()
            term_count = sum(1 for term in query_terms if term in chunk_text_lower)
            if term_count == 0:
                continue
            fid = chunk["file_id"]
            # Content score: +1.0 per matched query term found in chunk.
            # Raw accumulation here; final score cap (1.0) is applied at result-build time.
            content_score = float(term_count)
            file_scores[fid] = file_scores.get(fid, 0.0) + content_score
            seed_file_ids.add(fid)
            # Keep best chunk: most terms matched; tie-break by ROWID (first inserted / lowest id)
            prev = best_chunks.get(fid)
            if prev is None:
                best_chunks[fid] = (term_count, chunk)
            elif term_count > prev[0]:
                best_chunks[fid] = (term_count, chunk)

        relationship_evidence: List[RelationshipEvidenceItem] = []
        expanded_file_ids: Set[str] = set(seed_file_ids)
        # Maps file_id -> maximum confidence-weighted relationship bonus applied to that file.
        # Used so that SearchResultItem.relationshipBonus reflects actual weighted bonuses,
        # not a hard-coded constant.
        file_rel_bonus: Dict[str, float] = {}

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
                # Confidence-weighted relationship bonus: confidence * 0.4
                rel_score = (r["confidence"] or 0.0) * 0.4

                if src_id in seed_file_ids and r["target_type"] == "file":
                    expanded_file_ids.add(tgt_id)
                    file_scores[tgt_id] = file_scores.get(tgt_id, 0.0) + rel_score
                    file_rel_bonus[tgt_id] = max(file_rel_bonus.get(tgt_id, 0.0), rel_score)
                elif tgt_id in seed_file_ids and r["source_type"] == "file":
                    expanded_file_ids.add(src_id)
                    file_scores[src_id] = file_scores.get(src_id, 0.0) + rel_score
                    file_rel_bonus[src_id] = max(file_rel_bonus.get(src_id, 0.0), rel_score)

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

        results: List[SearchResultItem] = []

        for f in file_rows:
            if f["id"] not in expanded_file_ids:
                continue

            base_score = file_scores.get(f["id"], 0.1)
            is_seed = f["id"] in seed_file_ids
            rel_bonus = file_rel_bonus.get(f["id"], 0.0)
            final_score = min(1.0, base_score + rel_bonus)

            # Use matching chunk for excerpt/lines if available; otherwise fall back to first 25 lines
            chunk_entry = best_chunks.get(f["id"])
            if chunk_entry is not None:
                _, best_chunk = chunk_entry
                excerpt = best_chunk["text"]
                start_line = best_chunk["start_line"]
                end_line = best_chunk["end_line"]
            else:
                full_path = RepositoryBoundaryValidator.resolve_safe_path(repo_root, f["path"])
                excerpt = ""
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='replace') as fp:
                        excerpt = "".join(fp.readlines()[:25])
                except Exception:
                    excerpt = "// Unable to read snippet"
                start_line = 1
                end_line = min(25, 200)

            results.append(
                SearchResultItem(
                    sourceId=f"src_{f['id']}",
                    fileId=f["id"],
                    filePath=f["path"],
                    score=round(final_score, 2),
                    lexicalScore=round(base_score, 2),
                    relationshipBonus=round(rel_bonus, 2),
                    startLine=start_line,
                    endLine=end_line,
                    excerpt=excerpt,
                    relevanceReason="Direct query match" if is_seed else "Graph 1-hop relationship match"
                )
            )

        results.sort(key=lambda x: (x.score, x.lexicalScore), reverse=True)
        limit = request.limit or 10

        return SearchResponse(
            results=results[:limit],
            relationships=relationship_evidence[:15]
        )

    @staticmethod
    def compare_retrieval(conn: sqlite3.Connection, repo_id: str, query: str) -> RetrievalComparisonResponse:
        rel_req = SearchRequest(query=query, limit=10, relationshipAware=True)
        base_req = SearchRequest(query=query, limit=10, relationshipAware=False)

        rel_res = RetrievalService.search(conn, repo_id, rel_req)
        base_res = RetrievalService.search(conn, repo_id, base_req)

        rel_ids = {r.fileId for r in rel_res.results}
        base_ids = {b.fileId for b in base_res.results}
        discovered_by_graph = rel_ids - base_ids

        summary = (
            f"Relationship-aware retrieval discovered {len(discovered_by_graph)} additional file(s) via graph "
            f"adjacency expansion that plain-text keyword matching missed."
        )

        return RetrievalComparisonResponse(
            query=query,
            relationshipAwareResults=rel_res.results,
            textOnlyBaselineResults=base_res.results,
            graphExpandedFilesCount=len(discovered_by_graph),
            differentiationSummary=summary
        )
