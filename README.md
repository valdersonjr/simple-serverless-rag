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


---

## Como rodar (local)

### Pré-requisitos

- **SAM CLI** instalado
- **Docker runtime** funcionando via **Colima** (ou Docker Desktop)
- Credenciais AWS configuradas (ex.: `aws configure --profile rag-test`)

### Container runtime (Colima)

Se em um terminal novo o SAM reclamar que não acha runtime de container, configure o socket do Colima:

```bash
export DOCKER_HOST="unix:///Users/valdersonjunior/.colima/default/docker.sock"
```

### Variáveis de ambiente (env.json)

Usamos `env.json` (gitignored) para passar env vars para o `sam local`.

Arquivo: `env.json`

Campos mais importantes:
- **OpenSearch Serverless**:
  - `OPENSEARCH_ENDPOINT`
  - `OPENSEARCH_INDEX`
- **Bedrock (embeddings)**:
  - `BEDROCK_EMBEDDING_MODEL_ID` (ex.: `amazon.titan-embed-text-v2:0`)
  - `BEDROCK_EMBEDDING_DIM` (ex.: `1024`)

Observação:
- O arquivo `env.json` **não vai para o git** (está no `.gitignore`).
- **Não** comite `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.

### Build e start da API

Na raiz do projeto:

```bash
sam build --use-container
sam local start-api --env-vars env.json --profile rag-test --region us-east-1
```

---

## Script de ingestão (sem curl)

O projeto usa o script `script/call_ingest.py` para chamar o endpoint `/ingest`.

### Comandos principais

- **Ingest (com persistência no AOSS)**:

```bash
python3 script/call_ingest.py --doc-id bachelor-tesis --text @documents/bachelor-tesis.txt --chunk-size 800 --persist
```

Observação importante:
- Quando `--persist` é usado, o backend força **embeddings obrigatórios** (equivalente a `embed=true`).

### Flags disponíveis

- **`--url`**: URL do endpoint (default: `http://127.0.0.1:3000/ingest`)
- **`--doc-id`**: identificador do documento (recomendado)
- **`--text`**: texto literal ou `@caminho/arquivo.txt`
- **`--chunk-size`**: tamanho do chunk (em caracteres)
- **`--persist`**: persiste no OpenSearch Serverless
- **`--embed`**: força `embed=true` (observação: com `--persist`, embeddings já são obrigatórios)

### Debug / Admin (via script)

- **Ver env vars que a Lambda está enxergando** (sem vazar secrets):

```bash
python3 script/call_ingest.py --debug-env
```

- **Contar docs no índice** (`_count`):

```bash
python3 script/call_ingest.py --debug-count
```

- **Reset total do índice** (zera tudo e recria com mapping vetorial):

```bash
python3 script/call_ingest.py --reset-index
```

---

## Observações sobre idempotência

- Ao persistir (`--persist`), a Lambda tenta **apagar documentos existentes daquele `doc_id`** antes de reindexar.
- Isso evita duplicação quando você roda o ingest mais de uma vez com o mesmo `--doc-id`.
