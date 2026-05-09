import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the real opensearch module from file, bypassing any sys.modules mock
sys.modules.setdefault("opensearchpy", MagicMock())
_spec = importlib.util.spec_from_file_location("_real_opensearch", os.path.join(_root, "shared/opensearch.py"))
os_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(os_module)


@pytest.fixture(autouse=True)
def reset_client():
    os_module._client = None
    yield
    os_module._client = None


def _make_mock_client(hits=None):
    client = MagicMock()
    if hits is None:
        hits = []
    client.search.return_value = {"hits": {"hits": hits}}
    return client


def _make_hit(idx: int, score: float = 0.9) -> dict:
    return {
        "_score": score,
        "_source": {
            "text": f"chunk {idx}",
            "doc_id": "doc1",
            "chunk_id": f"doc1:{idx:05d}",
            "chunk_index": idx,
        },
    }


class TestSearchSimilar:
    def test_size_equals_top_k(self):
        """search body must include size=top_k so results are never silently truncated."""
        mock_client = _make_mock_client([_make_hit(i) for i in range(15)])
        os_module._client = mock_client

        os_module.search_similar("my-index", [0.1] * 4, top_k=15)

        body = mock_client.search.call_args.kwargs["body"]
        assert body["size"] == 15, "size must match top_k to avoid silent truncation"

    def test_size_matches_k_in_knn(self):
        """k inside the knn clause and top-level size must be equal."""
        mock_client = _make_mock_client([_make_hit(0)])
        os_module._client = mock_client

        os_module.search_similar("my-index", [0.1] * 4, top_k=7)

        body = mock_client.search.call_args.kwargs["body"]
        assert body["size"] == body["query"]["knn"]["embedding"]["k"]

    def test_returns_mapped_fields(self):
        """Result dicts contain all expected fields including score."""
        mock_client = _make_mock_client([_make_hit(0, score=0.75)])
        os_module._client = mock_client

        results = os_module.search_similar("my-index", [0.1] * 4, top_k=1)

        assert len(results) == 1
        r = results[0]
        assert r["text"] == "chunk 0"
        assert r["doc_id"] == "doc1"
        assert r["chunk_id"] == "doc1:00000"
        assert r["chunk_index"] == 0
        assert r["score"] == 0.75


class TestClientCaching:
    def test_client_reused_across_calls(self, monkeypatch):
        """_get_client must not create a new object on every call."""
        monkeypatch.setenv("OPENSEARCH_ENDPOINT", "http://localhost:9200")
        monkeypatch.setenv("OPENSEARCH_AUTH", "local")

        mock_opensearch_cls = MagicMock()
        mock_instance = MagicMock()
        mock_opensearch_cls.return_value = mock_instance

        opensearchpy_mock = MagicMock()
        opensearchpy_mock.OpenSearch = mock_opensearch_cls

        with patch.dict(sys.modules, {"opensearchpy": opensearchpy_mock}):
            c1 = os_module._get_client()
            c2 = os_module._get_client()
            c3 = os_module._get_client()

        assert c1 is c2 is c3
        mock_opensearch_cls.assert_called_once()
