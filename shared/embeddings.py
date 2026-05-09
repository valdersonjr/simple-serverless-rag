import json
import os

import boto3


def get_embedding_dim() -> int:
    try:
        return int(os.environ.get("EMBEDDING_DIM", "1024"))
    except ValueError as e:
        raise RuntimeError("EMBEDDING_DIM must be an integer") from e


def embed_text(text: str) -> list[float]:
    provider = os.getenv("EMBEDDING_PROVIDER", "bedrock")
    if provider == "local":
        return _embed_local(text)
    if provider == "fastembed":
        return _embed_fastembed(text)
    if provider == "mock":
        return _embed_mock(text)
    return _embed_bedrock(text)


def _embed_bedrock(text: str) -> list[float]:
    region = os.environ.get("AWS_REGION") or boto3.session.Session().region_name or "us-east-1"
    model_id = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID")
    if not model_id:
        raise RuntimeError("BEDROCK_EMBEDDING_MODEL_ID não configurado")

    client = boto3.client("bedrock-runtime", region_name=region)
    body = {"inputText": text, "dimensions": get_embedding_dim(), "normalize": True}

    resp = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode(),
    )
    data = json.loads(resp["body"].read())
    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"Resposta inesperada do Bedrock: {data}")
    return embedding


def _embed_local(text: str) -> list[float]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers não instalado. Execute: pip install sentence-transformers"
        ) from e
    # all-MiniLM-L6-v2 → 384 dims. Certifique-se de que EMBEDDING_DIM=384 no env local.
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text, normalize_embeddings=True).tolist()


def _embed_fastembed(text: str) -> list[float]:
    try:
        from fastembed import TextEmbedding
    except ImportError as e:
        raise RuntimeError("fastembed não instalado. Execute: pip install fastembed") from e
    model_name = os.getenv("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")
    model = TextEmbedding(model_name)
    result = list(model.embed([text]))
    return result[0].tolist()


def _embed_mock(text: str) -> list[float]:
    """Vetores determinísticos baseados no hash do texto — para testes locais sem ML."""
    import hashlib
    import random

    dim = get_embedding_dim()
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
    norm = sum(x**2 for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]
