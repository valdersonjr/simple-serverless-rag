import hashlib
import json


def chunk_text(text: str, chunk_size: int) -> list[str]:
    # Divide o texto em chunks de tamanho fixo (por caracteres).
    text = text or ""
    if chunk_size <= 0:
        return [text]
    return [
        text[i : i + chunk_size]
        for i in range(0, len(text), chunk_size)
        if text[i : i + chunk_size].strip()
    ]


def make_doc_id(text: str) -> str:
    # Gera um doc_id determinístico quando o cliente não envia.
    # (Útil para teste; para updates, prefira enviar doc_id fixo.)
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()
    return f"doc_{digest[:12]}"


def lambda_handler(event, context):
    # POST /ingest
    # Body JSON esperado:
    #   - text: string (obrigatório)
    #   - doc_id: string (opcional, recomendado)
    #   - chunk_size: int (opcional; padrão 800)
    #
    # Nesta etapa:
    # - faz chunking simples (tamanho fixo)
    # - gera chunk_index e chunk_id (para upsert/idempotência)
    # - ainda sem embeddings e sem OpenSearch

    try:
        body_raw = event.get("body") or ""
        payload = json.loads(body_raw) if body_raw else {}
    except Exception:
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "Body inválido. Envie JSON."}, ensure_ascii=False),
        }

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "Campo obrigatório: text (string)."}, ensure_ascii=False),
        }

    doc_id = payload.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        doc_id = make_doc_id(text)

    chunk_size = payload.get("chunk_size", 800)
    try:
        chunk_size = int(chunk_size)
    except Exception:
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "chunk_size deve ser um número inteiro."}, ensure_ascii=False),
        }

    chunks = chunk_text(text, chunk_size)

    chunk_ids = [f"{doc_id}:{i:05d}" for i in range(len(chunks))]

    return {
        "statusCode": 202,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "status": "received",
                "doc_id": doc_id,
                "chars": len(text),
                "chunk_size": chunk_size,
                "chunks_count": len(chunks),
                "chunks_preview": chunks[:3],
                "chunk_ids_preview": chunk_ids[:3],
            },
            ensure_ascii=False,
        ),
    }
