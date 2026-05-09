import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock shared layer modules before loading the Lambda
sys.modules["opensearch"] = MagicMock()
sys.modules["embeddings"] = MagicMock()

_spec = importlib.util.spec_from_file_location("worker_app", os.path.join(_root, "ingest_worker/app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["worker_app"] = _mod
_spec.loader.exec_module(_mod)

chunk_text = _mod.chunk_text
build_docs = _mod.build_docs
process_job = _mod.process_job
lambda_handler = _mod.lambda_handler


def test_chunk_text_basic():
    assert chunk_text("hello world", chunk_size=5) == ["hello", " worl", "d"]


def test_chunk_text_empty():
    assert chunk_text("", chunk_size=100) == []


def test_chunk_text_none():
    assert chunk_text(None, chunk_size=100) == []


def test_chunk_text_zero_size_returns_full():
    assert chunk_text("hello", chunk_size=0) == ["hello"]


def test_chunk_text_filters_blank_chunks():
    chunks = chunk_text("aaaaa     ", chunk_size=5)
    assert all(c.strip() for c in chunks)


def test_build_docs_without_embed():
    with patch.object(_mod, "embed_text") as mock_embed:
        docs = build_docs("doc1", ["chunk a", "chunk b"], embed=False)
        mock_embed.assert_not_called()
    assert len(docs) == 2
    assert docs[0]["doc_id"] == "doc1"
    assert docs[0]["chunk_id"] == "doc1:00000"
    assert docs[1]["chunk_index"] == 1
    assert "embedding" not in docs[0]


def test_build_docs_with_embed():
    fake_vector = [0.1, 0.2, 0.3]
    with patch.object(_mod, "embed_text", return_value=fake_vector):
        docs = build_docs("doc1", ["chunk a"], embed=True)
    assert docs[0]["embedding"] == fake_vector


def test_process_job_no_persist(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    result = process_job({
        "doc_id": "doc1",
        "text": "hello world test",
        "chunk_size": 5,
        "persist": False,
        "embed": False,
    })
    assert result["persisted"] is False
    assert result["chunks"] > 0


def test_process_job_invalid_doc_id():
    with pytest.raises(ValueError, match="doc_id"):
        process_job({"doc_id": "", "text": "hello", "persist": False})


def test_process_job_invalid_text():
    with pytest.raises(ValueError, match="text"):
        process_job({"doc_id": "doc1", "text": "  ", "persist": False})


def test_lambda_handler_processes_records(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_INDEX", "test_index")
    event = {
        "Records": [
            {"body": json.dumps({
                "doc_id": "doc1",
                "text": "hello world",
                "chunk_size": 800,
                "persist": False,
                "embed": False,
            })}
        ]
    }
    result = lambda_handler(event, None)
    assert result["processed"] == 1
