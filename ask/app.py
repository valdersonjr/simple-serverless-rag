import json
import os

from embeddings import embed_text
from opensearch import search_similar

_SYSTEM_PROMPT = (
    "Você é um assistente que responde perguntas baseado exclusivamente nos trechos "
    "de documentos fornecidos. Se a resposta não estiver nos trechos, diga claramente "
    "que não encontrou informação suficiente nos documentos indexados."
)


def _build_context(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chunks))


def _generate_bedrock(question: str, chunks: list[dict]) -> str:
    import boto3

    model_id = os.environ.get("CLAUDE_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    region = os.environ.get("AWS_REGION", "us-east-1")
    user_text = f"TRECHOS DOS DOCUMENTOS:\n{_build_context(chunks)}\n\nPERGUNTA: {question}"
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_text}],
    }
    client = boto3.client("bedrock-runtime", region_name=region)
    resp = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode(),
    )
    data = json.loads(resp["body"].read())
    return data["content"][0]["text"]


def _generate_gemini(question: str, chunks: list[dict]) -> str:
    from google import genai

    user_text = f"TRECHOS DOS DOCUMENTOS:\n{_build_context(chunks)}\n\nPERGUNTA: {question}"
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash-lite")
    response = client.models.generate_content(
        model=model,
        contents=user_text,
        config={"system_instruction": _SYSTEM_PROMPT},
    )
    return response.text


def _generate_mock(question: str, chunks: list[dict]) -> str:
    return (
        f"[Mock] Pergunta recebida: '{question}'. "
        f"Encontrei {len(chunks)} trecho(s) relevante(s) nos documentos indexados. "
        "Configure LLM_PROVIDER=gemini e GEMINI_API_KEY para respostas reais."
    )


def _generate(question: str, chunks: list[dict]) -> str:
    provider = os.getenv("LLM_PROVIDER", "bedrock")
    if provider == "mock":
        return _generate_mock(question, chunks)
    if provider == "gemini":
        return _generate_gemini(question, chunks)
    return _generate_bedrock(question, chunks)


def ask(question: str, top_k: int = 5) -> dict:
    """Retrieve relevant chunks and generate an answer. Callable directly or via Lambda."""
    index = os.environ["OPENSEARCH_INDEX"]
    embedding = embed_text(question)
    chunks = search_similar(index, embedding, top_k=top_k)
    answer = _generate(question, chunks)
    return {
        "answer": answer,
        "sources": [
            {"doc_id": c["doc_id"], "chunk_index": c["chunk_index"], "text": c["text"]}
            for c in chunks
        ],
    }


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

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return _resp(400, {"error": "Campo obrigatório: question (string)"})

    try:
        top_k = int(payload.get("top_k", 5))
    except (TypeError, ValueError):
        return _resp(400, {"error": "top_k deve ser um inteiro"})

    try:
        return _resp(200, ask(question, top_k=top_k))
    except Exception as e:
        return _resp(500, {"error": str(e)})
