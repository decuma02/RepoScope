"""
Focused unit tests for ContextBuilder.

Covers:
  1.  Empty results → sources list is empty.
  2.  Source fields are preserved: sourceId, filePath, startLine, endLine, snippet.
  3.  Score (relevance) is preserved on each source.
  4.  Results are packed in the order supplied (retrieval order maintained).
  5.  Token budget enforced — items that exceed the limit are excluded.
  6.  A single large item that fits exactly at the budget boundary is included.
  7.  Relationship evidence is included and capped at max_relationships.
  8.  Relationship evidence preserves: relationshipId, source, target, type, confidence, sourceLine.
  9.  Excerpt whitespace is stripped before becoming snippet.
  10. build_source_map returns correct sourceId → SourceReference mapping.
  11. build_source_map for empty results returns empty dict.
  12. tokenEstimate reflects items actually packed (not all results).
  13. componentName is passed through when present.
  14. componentName defaults to None when absent.
  15. Results with zero-length excerpts do not crash and contribute only metadata tokens.

All tests are pure-Python — no SQLite, no network, no filesystem.
"""
import pytest
from backend.app.schemas.api import SearchResultItem, RelationshipEvidenceItem
from backend.app.services.context.context_builder import ContextBuilder, _estimate_tokens
from backend.app.models.domain import RelationshipType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    source_id="src_f1",
    file_id="f1",
    file_path="src/foo.py",
    start_line=1,
    end_line=30,
    excerpt="def foo(): pass",
    score=0.9,
    lexical_score=0.9,
    rel_bonus=0.0,
    reason="Direct query match",
    component_name=None,
) -> SearchResultItem:
    return SearchResultItem(
        sourceId=source_id,
        fileId=file_id,
        filePath=file_path,
        componentName=component_name,
        score=score,
        lexicalScore=lexical_score,
        relationshipBonus=rel_bonus,
        startLine=start_line,
        endLine=end_line,
        excerpt=excerpt,
        relevanceReason=reason,
    )


def _make_rel(
    rel_id="rel1",
    source_path="src/a.py",
    target_path="src/b.py",
    rel_type=RelationshipType.IMPORTS,
    confidence=0.95,
    source_line=10,
) -> RelationshipEvidenceItem:
    return RelationshipEvidenceItem(
        relationshipId=rel_id,
        sourcePath=source_path,
        targetPath=target_path,
        type=rel_type,
        confidence=confidence,
        sourceLine=source_line,
    )


# ---------------------------------------------------------------------------
# Test 1: Empty results → empty sources
# ---------------------------------------------------------------------------

def test_empty_results_gives_empty_sources():
    pkg = ContextBuilder.build_context_package(
        query="auth",
        repo_name="myrepo",
        results=[],
        relationships=[],
    )
    assert pkg["sources"] == []
    assert pkg["tokenEstimate"] == 0


# ---------------------------------------------------------------------------
# Test 2: Source fields are preserved
# ---------------------------------------------------------------------------

def test_source_fields_preserved():
    result = _make_result(
        source_id="src_abc",
        file_path="lib/auth.py",
        start_line=5,
        end_line=40,
        excerpt="def authenticate(token): ...",
    )
    pkg = ContextBuilder.build_context_package("auth", "repo", [result], [])

    assert len(pkg["sources"]) == 1
    src = pkg["sources"][0]
    assert src["sourceId"] == "src_abc"
    assert src["filePath"] == "lib/auth.py"
    assert src["startLine"] == 5
    assert src["endLine"] == 40
    assert src["snippet"] == "def authenticate(token): ..."


# ---------------------------------------------------------------------------
# Test 3: Score (relevance) is preserved
# ---------------------------------------------------------------------------

def test_score_preserved():
    result = _make_result(score=0.72)
    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])
    assert pkg["sources"][0]["relevance"] == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# Test 4: Packing order follows input order
# ---------------------------------------------------------------------------

def test_packing_preserves_input_order():
    r1 = _make_result(source_id="src_f1", file_id="f1", score=0.9, excerpt="first chunk")
    r2 = _make_result(source_id="src_f2", file_id="f2", score=0.8, excerpt="second chunk")
    r3 = _make_result(source_id="src_f3", file_id="f3", score=0.5, excerpt="third chunk")

    pkg = ContextBuilder.build_context_package("q", "repo", [r1, r2, r3], [])

    ids = [s["sourceId"] for s in pkg["sources"]]
    assert ids == ["src_f1", "src_f2", "src_f3"]


# ---------------------------------------------------------------------------
# Test 5: Token budget enforced — items beyond budget are excluded
# ---------------------------------------------------------------------------

def test_token_budget_excludes_items():
    # Each item has a 400-char excerpt → ~100 tokens + 30 metadata = ~130 tokens each
    long_excerpt = "x" * 400
    r1 = _make_result(source_id="src_f1", file_id="f1", excerpt=long_excerpt)
    r2 = _make_result(source_id="src_f2", file_id="f2", excerpt=long_excerpt)
    r3 = _make_result(source_id="src_f3", file_id="f3", excerpt=long_excerpt)

    tokens_per_item = _estimate_tokens(long_excerpt)
    # Budget allows only 2 items
    budget = tokens_per_item * 2

    pkg = ContextBuilder.build_context_package("q", "repo", [r1, r2, r3], [], max_tokens=budget)

    assert len(pkg["sources"]) == 2
    source_ids = {s["sourceId"] for s in pkg["sources"]}
    assert "src_f1" in source_ids
    assert "src_f2" in source_ids
    assert "src_f3" not in source_ids


# ---------------------------------------------------------------------------
# Test 6: Single large item that exactly fits at boundary is included
# ---------------------------------------------------------------------------

def test_item_exactly_at_boundary_is_included():
    excerpt = "a" * 400
    tokens = _estimate_tokens(excerpt)
    result = _make_result(excerpt=excerpt)

    pkg = ContextBuilder.build_context_package("q", "repo", [result], [], max_tokens=tokens)

    assert len(pkg["sources"]) == 1
    assert pkg["tokenEstimate"] == tokens


# ---------------------------------------------------------------------------
# Test 7: Relationship evidence is capped at max_relationships
# ---------------------------------------------------------------------------

def test_relationships_capped():
    rels = [_make_rel(rel_id=f"rel{i}", source_path=f"a{i}.py", target_path=f"b{i}.py")
            for i in range(20)]
    pkg = ContextBuilder.build_context_package("q", "repo", [], rels, max_relationships=5)

    assert len(pkg["relationships"]) == 5


# ---------------------------------------------------------------------------
# Test 8: Relationship evidence fields are preserved
# ---------------------------------------------------------------------------

def test_relationship_fields_preserved():
    rel = _make_rel(
        rel_id="rel42",
        source_path="src/alpha.py",
        target_path="src/beta.py",
        rel_type=RelationshipType.IMPORTS,
        confidence=0.88,
        source_line=17,
    )
    pkg = ContextBuilder.build_context_package("q", "repo", [], [rel])

    assert len(pkg["relationships"]) == 1
    r = pkg["relationships"][0]
    assert r["relationshipId"] == "rel42"
    assert r["source"] == "src/alpha.py"
    assert r["target"] == "src/beta.py"
    assert r["type"] == RelationshipType.IMPORTS
    assert r["confidence"] == pytest.approx(0.88)
    assert r["sourceLine"] == 17


# ---------------------------------------------------------------------------
# Test 9: Excerpt whitespace is stripped
# ---------------------------------------------------------------------------

def test_excerpt_whitespace_stripped():
    result = _make_result(excerpt="  \n  def foo(): pass  \n  ")
    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])
    assert pkg["sources"][0]["snippet"] == "def foo(): pass"


# ---------------------------------------------------------------------------
# Test 10: build_source_map correct mapping
# ---------------------------------------------------------------------------

def test_build_source_map_correct():
    r1 = _make_result(source_id="src_f1", file_id="f1", file_path="a.py")
    r2 = _make_result(source_id="src_f2", file_id="f2", file_path="b.py")

    smap = ContextBuilder.build_source_map([r1, r2])

    assert "src_f1" in smap
    assert "src_f2" in smap
    assert smap["src_f1"].filePath == "a.py"
    assert smap["src_f2"].filePath == "b.py"


# ---------------------------------------------------------------------------
# Test 11: build_source_map for empty results returns empty dict
# ---------------------------------------------------------------------------

def test_build_source_map_empty():
    smap = ContextBuilder.build_source_map([])
    assert smap == {}


# ---------------------------------------------------------------------------
# Test 12: tokenEstimate matches items actually packed
# ---------------------------------------------------------------------------

def test_token_estimate_matches_packed_items():
    excerpt = "def example_function(): return True"
    result = _make_result(excerpt=excerpt)
    expected_tokens = _estimate_tokens(excerpt)

    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])

    assert pkg["tokenEstimate"] == expected_tokens


# ---------------------------------------------------------------------------
# Test 13: componentName is passed through when present
# ---------------------------------------------------------------------------

def test_component_name_passed_through():
    result = _make_result(component_name="AuthManager")
    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])
    assert pkg["sources"][0]["componentName"] == "AuthManager"


# ---------------------------------------------------------------------------
# Test 14: componentName defaults to None when absent
# ---------------------------------------------------------------------------

def test_component_name_defaults_to_none():
    result = _make_result(component_name=None)
    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])
    assert pkg["sources"][0]["componentName"] is None


# ---------------------------------------------------------------------------
# Test 15: Zero-length excerpt does not crash
# ---------------------------------------------------------------------------

def test_zero_length_excerpt_does_not_crash():
    result = _make_result(excerpt="")
    pkg = ContextBuilder.build_context_package("q", "repo", [result], [])

    assert len(pkg["sources"]) == 1
    assert pkg["sources"][0]["snippet"] == ""
    # Only metadata tokens counted for empty excerpt
    assert pkg["tokenEstimate"] == _estimate_tokens("")
