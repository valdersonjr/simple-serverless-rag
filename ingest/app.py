import hashlib
import json
import os

from opensearch_aoss import bulk_upsert_chunks, count_docs, ensure_index


def chunk_text(text: str, chunk_size: int) -> list[str]:
    text = text or ""
    if chunk_size <= 0:
        return [text]
    return [
        text[i : i + chunk_size]
        for i in range(0, len(text), chunk_size)
        if text[i : i + chunk_size].strip()
    ]


def make_doc_id(text: str) -> str:
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()
    return f"doc_{digest[:12]}"


def parse_json_body(event: dict) -> dict:
    body_raw = event.get("body") or ""
    if not body_raw:
        return {}
    try:
        return json.loads(body_raw)
    except Exception as e:
        raise ValueError("Body inválido. Envie JSON.") from e


def validate_text(payload: dict) -> str:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Campo obrigatório: text (string).")
    return text


def get_doc_id(payload: dict, text: str) -> str:
    doc_id = payload.get("doc_id")
    if isinstance(doc_id, str) and doc_id.strip():
        return doc_id
    return make_doc_id(text)


def get_chunk_size(payload: dict) -> int:
    chunk_size = payload.get("chunk_size", 800)
    try:
        return int(chunk_size)
    except Exception as e:
        raise ValueError("chunk_size deve ser um número inteiro.") from e


def build_chunk_docs(doc_id: str, chunks: list[str]) -> list[dict]:
    docs: list[dict] = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}:{i:05d}"
        docs.append(
            {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "chunk_index": i,
                "text": chunk,
            }
        )
    return docs


def should_persist(payload: dict) -> bool:
    if isinstance(payload.get("persist"), bool):
        return bool(payload.get("persist"))
    return bool(os.environ.get("OPENSEARCH_ENDPOINT") and os.environ.get("OPENSEARCH_INDEX"))


def get_opensearch_config() -> tuple[str, str]:
    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    index = os.environ.get("OPENSEARCH_INDEX")
    if not endpoint or not index:
        raise RuntimeError("OPENSEARCH_ENDPOINT/OPENSEARCH_INDEX não configurados")
    return endpoint, index


def persist_chunks(docs: list[dict]) -> dict:
    endpoint, index = get_opensearch_config()
    ensure_index(endpoint, index)
    result = bulk_upsert_chunks(endpoint, index, docs)
    return {"persisted": True, **result}


def debug_count() -> dict:
    endpoint, index = get_opensearch_config()
    data = count_docs(endpoint, index)
    return {"index": index, **data}


def _resp(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event, context):
    # POST /ingest
    # Body JSON:
    #   - text: string (obrigatório)
    #   - doc_id: string (opcional, recomendado)
    #   - chunk_size: int (opcional; padrão 800)
    #   - persist: bool (opcional; se true tenta salvar no OpenSearch Serverless)
    #   - debug: "count" (opcional; retorna _count do índice para validar ingestão)

    try:
        payload = parse_json_body(event)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    if payload.get("debug") == "count":
        try:
            return _resp(200, {"ok": True, "count": debug_count()})
        except Exception as e:
            return _resp(500, {"ok": False, "error": str(e)})

    try:
        text = validate_text(payload)
        doc_id = get_doc_id(payload, text)
        chunk_size = get_chunk_size(payload)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    chunks = chunk_text(text, chunk_size)
    docs = build_chunk_docs(doc_id, chunks)

    persist_info: dict = {"persisted": False}
    if should_persist(payload):
        try:
            persist_info = persist_chunks(docs)
        except Exception as e:
            persist_info = {"persisted": False, "error": str(e)}

    return _resp(
        202,
        {
            "status": "received",
            "doc_id": doc_id,
            "chars": len(text),
            "chunk_size": chunk_size,
            "chunks_count": len(chunks),
            "chunks_preview": chunks[:3],
            "chunk_ids_preview": [d["chunk_id"] for d in docs[:3]],
            "persist": persist_info,
        },
    )
