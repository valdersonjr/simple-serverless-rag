import os

import boto3

_client = None


def _get_client():
    """Factory: AOSS (SigV4) ou OpenSearch local (sem auth). Cached per process."""
    global _client
    if _client is not None:
        return _client

    from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

    endpoint = os.environ["OPENSEARCH_ENDPOINT"]
    auth_mode = os.getenv("OPENSEARCH_AUTH", "sigv4")

    if auth_mode == "local":
        raw = endpoint.replace("http://", "").replace("https://", "")
        host = raw.split(":")[0]
        port = int(raw.split(":")[1]) if ":" in raw else 9200
        _client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            use_ssl=False,
            verify_certs=False,
        )
        return _client

    credentials = boto3.Session().get_credentials()
    region = os.getenv("AWS_REGION", "us-east-1")
    auth = AWSV4SignerAuth(credentials, region, "aoss")
    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    _client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    return _client


def _index_mapping() -> dict:
    try:
        dims = int(os.environ.get("EMBEDDING_DIM", "1024"))
    except ValueError:
        dims = 1024

    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "text": {"type": "text"},
                "embedding": {"type": "knn_vector", "dimension": dims},
            },
        },
    }


def ensure_index(index: str) -> None:
    client = _get_client()
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_mapping())


def delete_index(index: str) -> None:
    client = _get_client()
    if client.indices.exists(index=index):
        client.indices.delete(index=index)


def reset_index(index: str) -> dict:
    delete_index(index)
    ensure_index(index)
    return {"reset": True, "index": index}


def delete_by_doc_id(index: str, doc_id: str) -> dict:
    client = _get_client()
    query = {"query": {"term": {"doc_id": doc_id}}}
    try:
        resp = client.delete_by_query(
            index=index,
            body=query,
            params={"refresh": "true", "conflicts": "proceed"},
        )
        return {"deleted": resp.get("deleted"), "took": resp.get("took")}
    except Exception as e:
        if "index_not_found" in str(e).lower():
            return {"deleted": 0, "reason": "index_not_found"}
        raise


def count_docs(index: str) -> dict:
    client = _get_client()
    try:
        resp = client.count(index=index)
        return {"count": resp.get("count")}
    except Exception as e:
        if "index_not_found" in str(e).lower():
            return {"count": 0, "reason": "index_not_found"}
        raise


def bulk_upsert_chunks(index: str, docs: list[dict]) -> dict:
    if not docs:
        return {"items": 0, "errors": False, "errors_sample": []}

    client = _get_client()
    ops: list[dict] = []
    for doc in docs:
        ops.append({"index": {"_index": index}})
        ops.append(doc)

    resp = client.bulk(body=ops, index=index)
    errors = bool(resp.get("errors"))
    errors_sample: list[dict] = []
    if errors:
        for item in (resp.get("items") or [])[:5]:
            op = next(iter(item))
            info = item[op]
            if "error" in info:
                errors_sample.append(
                    {"op": op, "status": info.get("status"), "error": info.get("error")}
                )
    return {"items": len(resp.get("items", [])), "errors": errors, "errors_sample": errors_sample}


def search_similar(index: str, embedding: list[float], top_k: int = 5) -> list[dict]:
    client = _get_client()
    resp = client.search(
        index=index,
        body={
            "size": top_k,
            "query": {"knn": {"embedding": {"vector": embedding, "k": top_k}}},
            "_source": ["text", "doc_id", "chunk_id", "chunk_index"],
        },
    )
    return [
        {
            "text": hit["_source"]["text"],
            "doc_id": hit["_source"]["doc_id"],
            "chunk_id": hit["_source"]["chunk_id"],
            "chunk_index": hit["_source"]["chunk_index"],
            "score": hit["_score"],
        }
        for hit in resp["hits"]["hits"]
    ]
