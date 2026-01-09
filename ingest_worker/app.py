import json
import os

from opensearch_aoss import bulk_upsert_chunks, delete_by_doc_id, ensure_index
from bedrock_embeddings import embed_text


def chunk_text(text: str, chunk_size: int) -> list[str]:
    text = text or ""
    if chunk_size <= 0:
        return [text]
    return [
        text[i : i + chunk_size]
        for i in range(0, len(text), chunk_size)
        if text[i : i + chunk_size].strip()
    ]


def validate_env() -> None:
    if not os.environ.get("OPENSEARCH_ENDPOINT") or not os.environ.get("OPENSEARCH_INDEX"):
        raise RuntimeError("OPENSEARCH_ENDPOINT/OPENSEARCH_INDEX não configurados")


def build_docs(doc_id: str, chunks: list[str], embed: bool) -> list[dict]:
    docs = []
    for i, chunk in enumerate(chunks):
        doc = {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}:{i:05d}",
            "chunk_index": i,
            "text": chunk,
        }
        if embed:
            doc["embedding"] = embed_text(chunk)
        docs.append(doc)
    return docs


def process_job(job: dict) -> dict:
    doc_id = job.get("doc_id")
    text = job.get("text")
    chunk_size = int(job.get("chunk_size", 800))
    persist = bool(job.get("persist", False))
    embed = bool(job.get("embed", False))

    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("job.doc_id inválido")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("job.text inválido")

    # regra do projeto: se persistir, embeddings são obrigatórios
    if persist:
        embed = True

    endpoint = os.environ["OPENSEARCH_ENDPOINT"]
    index = os.environ["OPENSEARCH_INDEX"]

    chunks = chunk_text(text, chunk_size)
    docs = build_docs(doc_id, chunks, embed=embed)

    if not persist:
        return {"doc_id": doc_id, "persisted": False, "chunks": len(chunks), "embed": embed}

    # Só precisa de OpenSearch quando persistir
    validate_env()

    ensure_index(endpoint, index)
    clean = delete_by_doc_id(endpoint, index, doc_id)
    result = bulk_upsert_chunks(endpoint, index, docs)
    return {
        "doc_id": doc_id,
        "persisted": True,
        "chunks": len(chunks),
        "embed": embed,
        "clean": clean,
        "bulk": result,
    }


def lambda_handler(event, context):
    # SQS event
    records = event.get("Records", [])
    out = []
    for r in records:
        body = r.get("body") or "{}"
        job = json.loads(body)
        out.append(process_job(job))

    return {"processed": len(out), "items": out}
