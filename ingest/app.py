import hashlib
import json
import os

import boto3

sqs = boto3.client("sqs")


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


def make_doc_id(text: str) -> str:
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()
    return f"doc_{digest[:12]}"


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


def enqueue_job(job: dict) -> dict:
    queue_url = os.environ.get("INGEST_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("INGEST_QUEUE_URL não configurado")
    resp = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(job, ensure_ascii=False),
    )
    return {"message_id": resp.get("MessageId")}


def _resp(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event, context):
    try:
        payload = parse_json_body(event)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    try:
        text = validate_text(payload)
        doc_id = get_doc_id(payload, text)
        chunk_size = get_chunk_size(payload)
    except ValueError as e:
        return _resp(400, {"error": str(e)})

    job = {
        "doc_id": doc_id,
        "text": text,
        "chunk_size": chunk_size,
        "persist": bool(payload.get("persist", False)),
        "embed": bool(payload.get("embed", False)),
    }

    try:
        info = enqueue_job(job)
        return _resp(202, {"status": "enqueued", "doc_id": doc_id, "chunk_size": chunk_size, **info})
    except Exception as e:
        return _resp(500, {"status": "error", "error": str(e)})
