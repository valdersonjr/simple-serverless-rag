import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "shared"))
sys.path.insert(0, str(_root / "ask"))

os.environ.setdefault("OPENSEARCH_ENDPOINT", "http://localhost:9200")
os.environ.setdefault("OPENSEARCH_INDEX", "rag_chunks_local")
os.environ.setdefault("OPENSEARCH_AUTH", "local")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_DIM", "384")
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_MODEL_ID", "gemini-2.5-flash-lite")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")

from app import ask  # noqa: E402

st.set_page_config(page_title="RAG Chat", page_icon="🔍", layout="centered")
st.title("🔍 RAG Chat")
st.caption("Perguntas respondidas com base nos documentos indexados.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📄 {len(msg['sources'])} fonte(s) usada(s)"):
                for s in msg["sources"]:
                    st.markdown(f"**{s['doc_id']}** — chunk {s['chunk_index']}")
                    st.text(s["text"][:300] + ("..." if len(s["text"]) > 300 else ""))

if question := st.chat_input("Faça uma pergunta sobre os documentos..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Buscando e gerando resposta..."):
            try:
                result = ask(question)
                st.markdown(result["answer"])
                if result.get("sources"):
                    with st.expander(f"📄 {len(result['sources'])} fonte(s) usada(s)"):
                        for s in result["sources"]:
                            st.markdown(f"**{s['doc_id']}** — chunk {s['chunk_index']}")
                            st.text(s["text"][:300] + ("..." if len(s["text"]) > 300 else ""))
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result.get("sources", []),
                })
            except Exception as e:
                st.error(f"Erro: {e}")
