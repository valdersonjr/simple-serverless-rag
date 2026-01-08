## simple-rag

Projeto **simples** de **RAG (Retrieval-Augmented Generation)** para permitir que usuários façam perguntas sobre **documentos proprietários** e recebam respostas **baseadas apenas nesses documentos**.

---

## Fluxo desejado

### Fluxo 1 — População do vetor (Ingestão)
- Documentos/textos são enviados para uma **AWS Lambda**
- A Lambda divide o conteúdo em **chunks** pequenos
- Cada chunk é convertido em um **embedding**
- Para múltiplos arquivos/chunks, o ideal é processar de forma **assíncrona** (fila + retries) e fazer **upsert por chunk** no OpenSearch
- Embeddings (e metadados) são salvos no **Amazon OpenSearch Serverless** (vector database)

### Fluxo 2 — Consulta (RAG)
- Usuário envia uma pergunta
- A pergunta é convertida em **embedding** (mesmo modelo do Fluxo 1)
- O sistema faz **busca por similaridade** no **Amazon OpenSearch Serverless**
- Recupera os **chunks mais relevantes**
- Injeta esses chunks no contexto do **LLM**
- O LLM é instruído a responder **somente com base no contexto recuperado**
- A resposta é retornada ao usuário

---

## Nota sobre AWS

Previsão de utilização:
- **API Gateway**
- **AWS Lambda**
- **Amazon OpenSearch Serverless**
- **IAM**
- **CloudWatch**


## O que construir:

- Deve-se ter um frontend simples com duas abas: uma para o envio dos arquivos para popular o banco. a outra para o envio das perguntas e também com um lugar para receber a resposta.
- Devemos ter também um backend simples (API) com dois endpoints:
  - `POST /ingest`: recebe texto/arquivo, faz chunking + embedding e indexa no OpenSearch (ou enfileira para processar assíncrono)
  - `POST /chat`: recebe a pergunta, faz embedding, busca no OpenSearch e chama o LLM para responder usando apenas o contexto retornado
- Uma **Lambda de ingestão** e uma **Lambda de consulta** (pode ser via API Gateway)
- Um índice no **Amazon OpenSearch Serverless** com suporte a **vector search**
- Permissões mínimas via **IAM** (API → Lambda → OpenSearch/LLM)
- Logs e métricas no **CloudWatch** para observar ingestões, erros e latência (por ultimo)