"""
Focused unit tests for the watsonx AI integration in AIService.

All external I/O is mocked:
  - RetrievalService.search      → returns controlled SearchResponse fixtures
  - sqlite3.Connection           → lightweight MagicMock (dict-row capable)
  - _get_iam_token               → returns a fake bearer token
  - httpx.post                   → returns a fake watsonx response

No real credentials, network calls, or database required.

Test coverage:
  1.  No retrieval results → returns insufficient_evidence response.
  2.  Watsonx credentials missing → returns unconfigured response with sources.
  3.  Successful watsonx call → answer comes from model, confidence=supported.
  4.  Watsonx HTTP error → confidence=error, graceful error message.
  5.  IAM token exchange failure → confidence=error, graceful error message.
  6.  _build_prompt includes question, sourceId, filePath, system rules.
  7.  _build_prompt includes relationship evidence.
  8.  _build_prompt renders (none) when no sources present.
  9.  _call_watsonx sends correct model_id and project_id.
  10. _call_watsonx returns stripped generated text.
  11. Source list in response is bounded by ContextBuilder token budget.
  12. Relationship evidence in response is capped at 10 items.
"""

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.domain import RelationshipType
from backend.app.schemas.api import (
    ChatRequest,
    RelationshipEvidenceItem,
    SearchResponse,
    SearchResultItem,
)
from backend.app.services.ai.ai_service import (
    AIService,
    _build_prompt,
    _call_watsonx,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_result(
    source_id: str = "src_f1",
    file_id: str = "f1",
    file_path: str = "src/foo.py",
    start_line: int = 1,
    end_line: int = 30,
    excerpt: str = "def foo(): pass",
    score: float = 0.9,
) -> SearchResultItem:
    return SearchResultItem(
        sourceId=source_id,
        fileId=file_id,
        filePath=file_path,
        score=score,
        lexicalScore=score,
        relationshipBonus=0.0,
        startLine=start_line,
        endLine=end_line,
        excerpt=excerpt,
        relevanceReason="direct match",
    )


def _make_rel(
    rel_id: str = "rel1",
    source_path: str = "src/a.py",
    target_path: str = "src/b.py",
) -> RelationshipEvidenceItem:
    return RelationshipEvidenceItem(
        relationshipId=rel_id,
        sourcePath=source_path,
        targetPath=target_path,
        type=RelationshipType.IMPORTS,
        confidence=0.9,
        sourceLine=5,
    )


def _make_conn(repo_name: str = "TestRepo") -> MagicMock:
    """Return a mock sqlite3.Connection whose cursor returns repo name rows."""
    conn = MagicMock(spec=sqlite3.Connection)
    cursor = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, key: repo_name if key == "name" else None
    row.__bool__ = lambda self: True
    cursor.fetchone.return_value = row
    conn.cursor.return_value = cursor
    return conn


def _watsonx_ok_response(text: str = "Here is the answer.") -> MagicMock:
    """Fake successful httpx response from watsonx text generation."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"results": [{"generated_text": f"  {text}  "}]}
    return resp


def _iam_ok_response(token: str = "fake-iam-token") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"access_token": token}
    return resp


# ---------------------------------------------------------------------------
# Test 1: No retrieval results → insufficient_evidence
# ---------------------------------------------------------------------------

def test_no_results_returns_insufficient_evidence():
    conn = _make_conn()
    with patch(
        "backend.app.services.ai.ai_service.RetrievalService.search",
        return_value=SearchResponse(results=[], relationships=[]),
    ):
        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="what?"))

    assert resp.confidence == "insufficient_evidence"
    assert resp.sources == []
    assert "sufficient" in resp.answer.lower()


# ---------------------------------------------------------------------------
# Test 2: Credentials missing → unconfigured, but sources still present
# ---------------------------------------------------------------------------

def test_missing_credentials_returns_unconfigured():
    result = _make_result()
    conn = _make_conn()
    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=[result], relationships=[]),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
    ):
        mock_settings.WATSONX_APIKEY = ""
        mock_settings.WATSONX_PROJECT_ID = "proj"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 8000
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="auth?"))

    assert resp.confidence == "unconfigured"
    assert "credentials" in resp.answer.lower()
    assert len(resp.sources) >= 1


# ---------------------------------------------------------------------------
# Test 3: Successful watsonx call → answer from model, confidence=supported
# ---------------------------------------------------------------------------

def test_successful_watsonx_call():
    result = _make_result()
    conn = _make_conn()
    expected_answer = "The foo function does X."

    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=[result], relationships=[]),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
        patch("backend.app.services.ai.ai_service.httpx.post") as mock_post,
    ):
        mock_settings.WATSONX_APIKEY = "real-key"
        mock_settings.WATSONX_PROJECT_ID = "proj-id"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 8000
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        # First call = IAM token, second call = watsonx generation
        mock_post.side_effect = [
            _iam_ok_response(),
            _watsonx_ok_response(expected_answer),
        ]

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="what is foo?"))

    assert resp.confidence == "supported"
    assert resp.answer == expected_answer
    assert len(resp.sources) == 1


# ---------------------------------------------------------------------------
# Test 4: Watsonx HTTP error → confidence=error
# ---------------------------------------------------------------------------

def test_watsonx_http_error_returns_error_confidence():
    import httpx as _httpx

    result = _make_result()
    conn = _make_conn()

    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=[result], relationships=[]),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
        patch("backend.app.services.ai.ai_service.httpx.post") as mock_post,
    ):
        mock_settings.WATSONX_APIKEY = "real-key"
        mock_settings.WATSONX_PROJECT_ID = "proj-id"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 8000
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        # IAM succeeds, watsonx call raises HTTP error
        mock_post.side_effect = [
            _iam_ok_response(),
            _httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock()),
        ]

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="auth?"))

    assert resp.confidence == "error"
    assert "error" in resp.answer.lower()


# ---------------------------------------------------------------------------
# Test 5: IAM token failure → confidence=error
# ---------------------------------------------------------------------------

def test_iam_failure_returns_error_confidence():
    import httpx as _httpx

    result = _make_result()
    conn = _make_conn()

    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=[result], relationships=[]),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
        patch("backend.app.services.ai.ai_service.httpx.post") as mock_post,
    ):
        mock_settings.WATSONX_APIKEY = "bad-key"
        mock_settings.WATSONX_PROJECT_ID = "proj-id"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 8000
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        mock_post.side_effect = _httpx.HTTPStatusError(
            "401", request=MagicMock(), response=MagicMock()
        )

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="auth?"))

    assert resp.confidence == "error"


# ---------------------------------------------------------------------------
# Test 6: _build_prompt includes question, sourceId, filePath, system rules
# ---------------------------------------------------------------------------

def test_build_prompt_includes_question_and_source():
    context_package = {
        "query": "what is foo?",
        "repositoryName": "MyRepo",
        "sources": [
            {
                "sourceId": "src_abc",
                "filePath": "src/foo.py",
                "startLine": 1,
                "endLine": 20,
                "snippet": "def foo(): pass",
            }
        ],
        "relationships": [],
    }
    prompt = _build_prompt("what is foo?", context_package)

    assert "what is foo?" in prompt
    assert "src_abc" in prompt
    assert "src/foo.py" in prompt
    assert "UNTRUSTED DATA" in prompt
    assert "NEVER invent" in prompt
    assert "insufficient" in prompt


# ---------------------------------------------------------------------------
# Test 7: _build_prompt includes relationship evidence
# ---------------------------------------------------------------------------

def test_build_prompt_includes_relationships():
    context_package = {
        "query": "deps?",
        "repositoryName": "MyRepo",
        "sources": [],
        "relationships": [
            {
                "relationshipId": "rel1",
                "source": "src/a.py",
                "target": "src/b.py",
                "type": RelationshipType.IMPORTS,
                "confidence": 0.9,
                "sourceLine": 3,
            }
        ],
    }
    prompt = _build_prompt("deps?", context_package)

    assert "src/a.py" in prompt
    assert "src/b.py" in prompt
    assert "IMPORTS" in prompt or "imports" in prompt.lower()


# ---------------------------------------------------------------------------
# Test 8: _build_prompt renders (none) when no sources
# ---------------------------------------------------------------------------

def test_build_prompt_renders_none_for_empty_sources():
    context_package = {
        "query": "q",
        "repositoryName": "Repo",
        "sources": [],
        "relationships": [],
    }
    prompt = _build_prompt("q", context_package)

    assert "(none)" in prompt


# ---------------------------------------------------------------------------
# Test 9: _call_watsonx sends correct model_id and project_id
# ---------------------------------------------------------------------------

def test_call_watsonx_sends_correct_payload():
    with (
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
        patch("backend.app.services.ai.ai_service.httpx.post") as mock_post,
    ):
        mock_settings.WATSONX_APIKEY = "key"
        mock_settings.WATSONX_PROJECT_ID = "proj-123"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        mock_post.side_effect = [
            _iam_ok_response(),
            _watsonx_ok_response("answer"),
        ]

        _call_watsonx("test prompt")

    # Inspect the second call (watsonx generation)
    gen_call = mock_post.call_args_list[1]
    payload = gen_call.kwargs.get("json") or gen_call.args[1] if len(gen_call.args) > 1 else gen_call.kwargs["json"]
    assert payload["model_id"] == "ibm/granite-13b-chat-v2"
    assert payload["project_id"] == "proj-123"
    assert payload["input"] == "test prompt"


# ---------------------------------------------------------------------------
# Test 10: _call_watsonx returns stripped generated text
# ---------------------------------------------------------------------------

def test_call_watsonx_strips_whitespace():
    with (
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
        patch("backend.app.services.ai.ai_service.httpx.post") as mock_post,
    ):
        mock_settings.WATSONX_APIKEY = "key"
        mock_settings.WATSONX_PROJECT_ID = "proj"
        mock_settings.WATSONX_MODEL_ID = "ibm/granite"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.CHAT_TIMEOUT_SECONDS = 30

        mock_post.side_effect = [
            _iam_ok_response(),
            _watsonx_ok_response("  padded answer  "),
        ]

        result = _call_watsonx("prompt")

    # _watsonx_ok_response wraps with extra spaces; _call_watsonx must strip
    assert result == "padded answer"


# ---------------------------------------------------------------------------
# Test 11: Source list in response bounded by token budget
# ---------------------------------------------------------------------------

def test_sources_bounded_by_token_budget():
    # 10 results each with a large excerpt — only a subset should fit
    results = [
        _make_result(
            source_id=f"src_{i}",
            file_id=f"f{i}",
            excerpt="x" * 2000,  # ~500 tokens each
        )
        for i in range(10)
    ]
    conn = _make_conn()

    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=results, relationships=[]),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
    ):
        mock_settings.WATSONX_APIKEY = ""  # trigger unconfigured path
        mock_settings.WATSONX_PROJECT_ID = ""
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 1000  # tight budget → only ~1-2 items
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="q?"))

    # With 2000-char excerpts (~530 tokens each) and a 1000-token budget,
    # at most 1 item fits.
    assert len(resp.sources) <= 2


# ---------------------------------------------------------------------------
# Test 12: Relationship evidence capped at 10 items
# ---------------------------------------------------------------------------

def test_relationship_evidence_capped_at_10():
    result = _make_result()
    rels = [_make_rel(rel_id=f"rel{i}") for i in range(20)]
    conn = _make_conn()

    with (
        patch(
            "backend.app.services.ai.ai_service.RetrievalService.search",
            return_value=SearchResponse(results=[result], relationships=rels),
        ),
        patch("backend.app.services.ai.ai_service.settings") as mock_settings,
    ):
        mock_settings.WATSONX_APIKEY = ""
        mock_settings.WATSONX_PROJECT_ID = ""
        mock_settings.WATSONX_MODEL_ID = "ibm/granite-13b-chat-v2"
        mock_settings.WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
        mock_settings.MAX_CONTEXT_TOKENS = 8000
        mock_settings.CHAT_TIMEOUT_SECONDS = 60

        resp = AIService.answer_question(conn, "repo1", ChatRequest(question="deps?"))

    assert len(resp.relationshipEvidence) <= 10
