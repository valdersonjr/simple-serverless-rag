import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock shared layer before loading the Lambda so its imports resolve to mocks
sys.modules["opensearch"] = MagicMock()

# Load with a unique name to avoid collision with other app.py files
_spec = importlib.util.spec_from_file_location("ingest_app", os.path.join(_root, "ingest/app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ingest_app"] = _mod
_spec.loader.exec_module(_mod)

parse_json_body = _mod.parse_json_body
validate_text = _mod.validate_text
make_doc_id = _mod.make_doc_id
get_doc_id = _mod.get_doc_id
get_chunk_size = _mod.get_chunk_size
lambda_handler = _mod.lambda_handler


def test_parse_json_body_valid():
    assert parse_json_body({"body": '{"text": "hello"}'}) == {"text": "hello"}


def test_parse_json_body_empty():
    assert parse_json_body({}) == {}


def test_parse_json_body_invalid_json():
    with pytest.raises(ValueError, match="Body inválido"):
        parse_json_body({"body": "not-json"})


def test_validate_text_ok():
    assert validate_text({"text": "hello"}) == "hello"


def test_validate_text_missing():
    with pytest.raises(ValueError, match="text"):
        validate_text({})


def test_validate_text_blank():
    with pytest.raises(ValueError, match="text"):
        validate_text({"text": "   "})


def test_make_doc_id_deterministic():
    assert make_doc_id("hello") == make_doc_id("hello")


def test_make_doc_id_different_texts():
    assert make_doc_id("hello") != make_doc_id("world")


def test_make_doc_id_prefix():
    assert make_doc_id("hello").startswith("doc_")


def test_get_doc_id_from_payload():
    assert get_doc_id({"doc_id": "my-id"}, "text") == "my-id"


def test_get_doc_id_generated():
    assert get_doc_id({}, "some text").startswith("doc_")


def test_get_chunk_size_default():
    assert get_chunk_size({}) == 800


def test_get_chunk_size_custom():
    assert get_chunk_size({"chunk_size": 400}) == 400


def test_get_chunk_size_invalid():
    with pytest.raises(ValueError, match="chunk_size"):
        get_chunk_size({"chunk_size": "abc"})


def test_lambda_handler_missing_text(monkeypatch):
    monkeypatch.setenv("INGEST_QUEUE_URL", "http://localhost:9324/queue/ingest-queue")
    resp = lambda_handler({"body": '{"doc_id": "test"}'}, None)
    assert resp["statusCode"] == 400


def test_lambda_handler_enqueues(monkeypatch):
    monkeypatch.setenv("INGEST_QUEUE_URL", "http://localhost:9324/queue/ingest-queue")
    with patch.object(_mod, "sqs") as mock_sqs:
        mock_sqs.send_message.return_value = {"MessageId": "abc123"}
        resp = lambda_handler({"body": '{"text": "hello world", "doc_id": "doc1"}'}, None)
    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body["status"] == "enqueued"
    assert body["doc_id"] == "doc1"
