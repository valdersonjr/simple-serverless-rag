import json
import os
from typing import List

import boto3


def get_region() -> str:
    return os.environ.get("AWS_REGION") or boto3.session.Session().region_name or "us-east-1"


def get_model_id() -> str:
    model_id = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID")
    if not model_id:
        raise RuntimeError("BEDROCK_EMBEDDING_MODEL_ID não configurado")
    return model_id


def get_dimensions() -> int:
    # Titan Text Embeddings V2 suporta 1024 (padrão), 512, 256
    dims = os.environ.get("BEDROCK_EMBEDDING_DIM", "1024")
    try:
        return int(dims)
    except Exception as e:
        raise RuntimeError("BEDROCK_EMBEDDING_DIM deve ser inteiro") from e


def embed_text(text: str) -> List[float]:
    """Gera embedding para um texto usando Amazon Bedrock (Titan Text Embeddings V2)."""
    client = boto3.client("bedrock-runtime", region_name=get_region())

    body = {
        "inputText": text,
        "dimensions": get_dimensions(),
        "normalize": True,
    }

    resp = client.invoke_model(
        modelId=get_model_id(),
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8"),
    )

    raw = resp["body"].read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw else {}

    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"Resposta inesperada do Bedrock embeddings: {data}")
    return embedding
