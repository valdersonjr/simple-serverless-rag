import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def get_region() -> str:
    return os.environ.get("AWS_REGION") or boto3.session.Session().region_name or "us-east-1"


def _sign_headers(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> dict[str, str]:
    session = boto3.session.Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("Credenciais AWS não encontradas (AWS creds não disponíveis no runtime).")

    frozen = creds.get_frozen_credentials()
    req = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(frozen, "aoss", get_region()).add_auth(req)
    return dict(req.headers.items())


def aoss_request(
    method: str,
    endpoint: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> tuple[int, str]:
    endpoint = endpoint.rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    url = f"{endpoint}{path}"

    parsed = urllib.parse.urlparse(url)
    base_headers = headers.copy() if headers else {}

    # SigV4: Host e hash do payload ajudam a evitar Forbidden por assinatura inválida.
    payload = body or b""
    base_headers.setdefault("Host", parsed.netloc)
    base_headers.setdefault("x-amz-content-sha256", hashlib.sha256(payload).hexdigest())

    signed_headers = _sign_headers(method, url, body, base_headers)

    req = urllib.request.Request(url, data=body, headers=signed_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        return e.code, body_txt


def ensure_index(endpoint: str, index: str) -> None:
    status, _ = aoss_request("HEAD", endpoint, f"/{index}")
    if status == 200:
        return
    if status not in (404,):
        raise RuntimeError(f"Falha ao checar índice: HTTP {status}")

    mapping = {
        "mappings": {
            "properties": {
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "text": {"type": "text"},
            }
        }
    }

    body = json.dumps(mapping).encode("utf-8")
    status, resp = aoss_request(
        "PUT",
        endpoint,
        f"/{index}",
        body=body,
        headers={"content-type": "application/json"},
    )
    if status not in (200, 201):
        raise RuntimeError(f"Falha ao criar índice: HTTP {status}: {resp}")


def count_docs(endpoint: str, index: str) -> dict:
    status, resp = aoss_request("GET", endpoint, f"/{index}/_count")
    if status != 200:
        raise RuntimeError(f"Falha no _count: HTTP {status}: {resp}")
    return json.loads(resp) if resp else {}


def build_bulk_index_ops(index: str, docs: Iterable[dict]) -> bytes:
    """
    Monta NDJSON para /_bulk.

    Importante: no OpenSearch Serverless (AOSS), o uso de Document ID ("_id")
    pode ser rejeitado (400: Document ID is not supported...).
    Por isso, indexamos sem _id e guardamos chunk_id como campo dentro do documento.
    """
    lines: list[str] = []
    for doc in docs:
        lines.append(json.dumps({"index": {"_index": index}}, ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _extract_bulk_errors(parsed: dict, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    for item in parsed.get("items", []) or []:
        # item é algo como: {"index": {"_id":..., "status":..., "error":...}}
        op = next(iter(item.keys()), None)
        if not op:
            continue
        info = item.get(op) or {}
        if "error" in info:
            out.append({"op": op, "_id": info.get("_id"), "status": info.get("status"), "error": info.get("error")})
            if len(out) >= limit:
                break
    return out


def bulk_upsert_chunks(endpoint: str, index: str, docs: list[dict]) -> dict:
    if not docs:
        return {"items": 0, "errors": False, "errors_sample": []}

    body = build_bulk_index_ops(index, docs)
    status, resp = aoss_request(
        "POST",
        endpoint,
        f"/{index}/_bulk",
        body=body,
        headers={"content-type": "application/x-ndjson"},
        timeout=60,
    )
    if status not in (200, 201):
        raise RuntimeError(f"Falha no bulk upsert: HTTP {status}: {resp}")

    parsed = json.loads(resp) if resp else {}
    errors = bool(parsed.get("errors"))
    return {
        "items": len(parsed.get("items", [])),
        "errors": errors,
        "errors_sample": _extract_bulk_errors(parsed, limit=5) if errors else [],
    }
