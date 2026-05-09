import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules["opensearch"] = MagicMock()
sys.modules["embeddings"] = MagicMock()

_spec = importlib.util.spec_from_file_location("query_app", os.path.join(_root, "query/app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["query_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler


def test_query_missing_body():
    assert lambda_handler({}, None)["statusCode"] == 400


def test_query_missing_query_field():
    assert lambda_handler({"body": '{"top_k": 3}'}, None)["statusCode"] == 400


def test_query_invalid_json():
    assert lambda_handler({"body": "not-json"}, None)["statusCode"] == 400


def test_query_returns_results(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    fake = [{"text": "t", "doc_id": "doc1", "chunk_id": "doc1:00000", "chunk_index": 0, "score": 0.9}]
    with patch.object(_mod, "embed_text", return_value=[0.1, 0.2]):
        with patch.object(_mod, "search_similar", return_value=fake):
            resp = lambda_handler({"body": '{"query": "what is ML?", "top_k": 3}'}, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 1
    assert body["results"][0]["doc_id"] == "doc1"


def test_query_invalid_top_k(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    resp = lambda_handler({"body": '{"query": "hello", "top_k": "bad"}'}, None)
    assert resp["statusCode"] == 400
