import hashlib
import json
import os

from bedrock_embeddings import embed_text
from opensearch_aoss import bulk_upsert_chunks, count_docs, ensure_index, reset_index, delete_by_doc_id


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


def should_persist(payload: dict) -> bool:
    if isinstance(payload.get("persist"), bool):
        return bool(payload.get("persist"))
    return bool(os.environ.get("OPENSEARCH_ENDPOINT") and os.environ.get("OPENSEARCH_INDEX"))


def should_embed(payload: dict) -> bool:
    if isinstance(payload.get("embed"), bool):
        return bool(payload.get("embed"))
    return False

def validate_bedrock_config() -> None:
    # Quando embeddings são obrigatórios, essas env vars precisam existir.
    if not os.environ.get("BEDROCK_EMBEDDING_MODEL_ID"):
        raise RuntimeError("BEDROCK_EMBEDDING_MODEL_ID não configurado")
    # Dim tem default no bedrock_embeddings, mas mantemos aqui para rastreabilidade
    if not os.environ.get("BEDROCK_EMBEDDING_DIM"):
        os.environ["BEDROCK_EMBEDDING_DIM"] = "1024"



def get_opensearch_config() -> tuple[str, str]:
    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    index = os.environ.get("OPENSEARCH_INDEX")
    if not endpoint or not index:
        raise RuntimeError("OPENSEARCH_ENDPOINT/OPENSEARCH_INDEX não configurados")
    return endpoint, index


def build_chunk_docs(doc_id: str, chunks: list[str], embed: bool) -> list[dict]:
    docs: list[dict] = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}:{i:05d}"
        doc = {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "chunk_index": i,
            "text": chunk,
        }
        if embed:
            doc["embedding"] = embed_text(chunk)
        docs.append(doc)
    return docs




def clean_existing_doc(doc_id: str) -> dict:
    # Remove documentos antigos desse doc_id antes de reindexar (evita duplicação).
    endpoint, index = get_opensearch_config()
    try:
        # Garante que o índice existe antes do delete_by_query (primeira ingestão).
        ensure_index(endpoint, index)
        return {"cleaned": True, "result": delete_by_doc_id(endpoint, index, doc_id)}
    except Exception as e:
        return {"cleaned": False, "error": str(e)}
def persist_docs(docs: list[dict]) -> dict:
    endpoint, index = get_opensearch_config()
    ensure_index(endpoint, index)
    result = bulk_upsert_chunks(endpoint, index, docs)
    return {"persisted": True, **result}


def debug_count() -> dict:
    endpoint, index = get_opensearch_config()
    data = count_docs(endpoint, index)
    return {"index": index, **data}


def debug_env() -> dict:
    # Retorna apenas informações seguras (sem vazar secrets).
    ak = os.environ.get("AWS_ACCESS_KEY_ID")
    return {
        "AWS_REGION": os.environ.get("AWS_REGION"),
        "has_AWS_ACCESS_KEY_ID": bool(ak),
        "AWS_ACCESS_KEY_ID_suffix": (ak[-4:] if ak else None),
        "has_AWS_SECRET_ACCESS_KEY": bool(os.environ.get("AWS_SECRET_ACCESS_KEY")),
        "has_AWS_SESSION_TOKEN": bool(os.environ.get("AWS_SESSION_TOKEN")),
        "OPENSEARCH_ENDPOINT": os.environ.get("OPENSEARCH_ENDPOINT"),
        "OPENSEARCH_INDEX": os.environ.get("OPENSEARCH_INDEX"),
        "BEDROCK_EMBEDDING_MODEL_ID": os.environ.get("BEDROCK_EMBEDDING_MODEL_ID"),
        "BEDROCK_EMBEDDING_DIM": os.environ.get("BEDROCK_EMBEDDING_DIM"),
    }


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
    #   - persist: bool (opcional)
    #   - embed: bool (opcional; se true, gera embeddings via Bedrock por chunk)
    #   - debug: "count" | "env" (opcional)

    try:
        payload = parse_json_body(event)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    if payload.get("debug") == "reset-index":
        try:
            endpoint, index = get_opensearch_config()
            info = reset_index(endpoint, index)
            return _resp(200, {"ok": True, "reset": info})
        except Exception as e:
            return _resp(500, {"ok": False, "error": str(e)})

    if payload.get("debug") == "count":
        try:
            return _resp(200, {"ok": True, "count": debug_count()})
        except Exception as e:
            return _resp(500, {"ok": False, "error": str(e)})

    if payload.get("debug") == "env":
        return _resp(200, {"ok": True, "env": debug_env()})

    try:
        text = validate_text(payload)
        doc_id = get_doc_id(payload, text)
        chunk_size = get_chunk_size(payload)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    chunks = chunk_text(text, chunk_size)
    persist_requested = should_persist(payload)
    embed = should_embed(payload)
    # Regra do projeto: se vai persistir no OpenSearch, embeddings são obrigatórios.
    if persist_requested:
        embed = True

    if embed:
        try:
            validate_bedrock_config()
        except Exception as e:
            return _resp(500, {"error": f"Config Bedrock inválida: {e}"})

    try:
        docs = build_chunk_docs(doc_id, chunks, embed=embed)
    except Exception as e:
        return _resp(500, {"error": f"Falha ao gerar embeddings: {e}"})

    persist_info: dict = {"persisted": False}
    if persist_requested:
        clean_info = clean_existing_doc(doc_id)
        try:
            persist_info = persist_docs(docs)
            persist_info["clean_before"] = clean_info
        except Exception as e:
            persist_info = {"persisted": False, "error": str(e), "clean_before": clean_info}

    return _resp(
        202,
        {
            "status": "received",
            "doc_id": doc_id,
            "chars": len(text),
            "chunk_size": chunk_size,
            "chunks_count": len(chunks),
            "embed": embed,
            "chunks_preview": chunks[:3],
            "chunk_ids_preview": [d["chunk_id"] for d in docs[:3]],
            "persist": persist_info,
        },
    )
