import json
import os

from embeddings import embed_text
from opensearch import bulk_upsert_chunks, delete_by_doc_id, ensure_index


def chunk_text(text: str, chunk_size: int) -> list[str]:
    text = text or ""
    if chunk_size <= 0:
        return [text]
    return [
        text[i : i + chunk_size]
        for i in range(0, len(text), chunk_size)
        if text[i : i + chunk_size].strip()
    ]


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

    if persist:
        embed = True

    chunks = chunk_text(text, chunk_size)
    docs = build_docs(doc_id, chunks, embed=embed)

    if not persist:
        return {"doc_id": doc_id, "persisted": False, "chunks": len(chunks), "embed": embed}

    index = os.environ["OPENSEARCH_INDEX"]
    ensure_index(index)
    clean = delete_by_doc_id(index, doc_id)
    result = bulk_upsert_chunks(index, docs)
    return {
        "doc_id": doc_id,
        "persisted": True,
        "chunks": len(chunks),
        "embed": embed,
        "clean": clean,
        "bulk": result,
    }


def lambda_handler(event, context):
    records = event.get("Records", [])
    out = []
    for r in records:
        body = r.get("body") or "{}"
        job = json.loads(body)
        out.append(process_job(job))
    return {"processed": len(out), "items": out}
