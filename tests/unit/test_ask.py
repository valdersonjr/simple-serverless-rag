import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules["opensearch"] = MagicMock()
sys.modules["embeddings"] = MagicMock()

_spec = importlib.util.spec_from_file_location("ask_app", os.path.join(_root, "ask/app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ask_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
_generate_mock = _mod._generate_mock
_generate_bedrock = _mod._generate_bedrock


_FAKE_CHUNKS = [{"text": "RAG é incrível", "doc_id": "doc1", "chunk_id": "doc1:00000", "chunk_index": 0, "score": 0.9}]


def test_missing_body():
    assert lambda_handler({}, None)["statusCode"] == 400


def test_invalid_json():
    assert lambda_handler({"body": "not-json"}, None)["statusCode"] == 400


def test_missing_question():
    assert lambda_handler({"body": '{"top_k": 3}'}, None)["statusCode"] == 400


def test_blank_question():
    assert lambda_handler({"body": '{"question": "   "}'}, None)["statusCode"] == 400


def test_invalid_top_k(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    resp = lambda_handler({"body": '{"question": "o que é RAG?", "top_k": "bad"}'}, None)
    assert resp["statusCode"] == 400


def test_mock_provider(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with patch.object(_mod, "embed_text", return_value=[0.1, 0.2]):
        with patch.object(_mod, "search_similar", return_value=_FAKE_CHUNKS):
            resp = lambda_handler({"body": '{"question": "o que é RAG?"}'}, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "answer" in body
    assert len(body["sources"]) == 1


def test_generate_mock_response():
    answer = _generate_mock("o que é RAG?", _FAKE_CHUNKS)
    assert "Mock" in answer
    assert "1 trecho" in answer


def test_generate_bedrock(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    fake_body = MagicMock()
    fake_body.read.return_value = json.dumps(
        {"content": [{"text": "Resposta via Bedrock"}]}
    ).encode()
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = {"body": fake_body}
    with patch("boto3.client", return_value=mock_client):
        result = _generate_bedrock("o que é RAG?", _FAKE_CHUNKS)
    assert result == "Resposta via Bedrock"
    call_kwargs = mock_client.invoke_model.call_args[1]
    assert call_kwargs["modelId"] == "anthropic.claude-3-haiku-20240307-v1:0"
