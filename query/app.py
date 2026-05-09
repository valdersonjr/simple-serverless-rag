import json
import os

from embeddings import embed_text
from opensearch import search_similar


def _resp(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event, context):
    body_raw = event.get("body") or ""
    if not body_raw:
        return _resp(400, {"error": "Body obrigatório"})

    try:
        payload = json.loads(body_raw)
    except Exception:
        return _resp(400, {"error": "Body inválido. Envie JSON."})

    query_text = payload.get("query")
    if not isinstance(query_text, str) or not query_text.strip():
        return _resp(400, {"error": "Campo obrigatório: query (string)"})

    try:
        top_k = int(payload.get("top_k", 5))
    except (TypeError, ValueError):
        return _resp(400, {"error": "top_k deve ser um inteiro"})

    try:
        index = os.environ["OPENSEARCH_INDEX"]
        embedding = embed_text(query_text)
        results = search_similar(index, embedding, top_k=top_k)
        return _resp(200, {"results": results, "count": len(results)})
    except Exception as e:
        return _resp(500, {"error": str(e)})
