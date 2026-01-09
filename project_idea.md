## simple-rag — project idea

A **simple** **RAG (Retrieval‑Augmented Generation)** project to let users ask questions about **private/proprietary documents** and get answers **based only on those documents**.

---

## Desired flow

### Flow 1 — Vector population (Ingestion)

- Documents/text are sent to an **AWS Lambda**
- The Lambda splits the content into small **chunks**
- Each chunk is converted into an **embedding**
- For multiple files/chunks, the ideal is to process **asynchronously** (queue + retries) and do **chunk upserts** in OpenSearch
- Embeddings (and metadata) are stored in **Amazon OpenSearch Serverless** (vector database)

### Flow 2 — Query (RAG)

- The user sends a question
- The question is converted into an **embedding** (same model as Flow 1)
- The system performs **similarity search** in **Amazon OpenSearch Serverless**
- It retrieves the **most relevant chunks**
- It injects those chunks into the **LLM** context
- The LLM is instructed to answer **only using the retrieved context**
- The answer is returned to the user

---

## AWS note

Planned usage:
- **API Gateway**
- **AWS Lambda**
- **Amazon OpenSearch Serverless**
- **IAM**
- **CloudWatch**

---

## What to build

- A simple frontend with two tabs:
  - one to upload/send documents to populate the vector database
  - one to ask questions and display the answer
- A simple backend (API) with two endpoints:
  - `POST /ingest`: receives text/file, does chunking + embeddings and indexes into OpenSearch (or enqueues for async processing)
  - `POST /chat`: receives the question, embeds it, searches OpenSearch, and calls the LLM to answer using only the retrieved context
- An ingestion Lambda and a query Lambda (exposed via API Gateway)
- An **Amazon OpenSearch Serverless** index that supports vector search
- Minimal IAM permissions (API → Lambda → OpenSearch/LLM)
- Logs/metrics in CloudWatch to observe ingestion, errors, and latency (later)

---

## How to run (local)

### Prerequisites

- **SAM CLI** installed
- **Docker runtime** working via **Colima** (or Docker Desktop)
- AWS credentials configured (e.g. `aws configure --profile rag-test`)

### Container runtime (Colima)

If SAM complains it cannot find a container runtime, configure the Colima socket:

```bash
export DOCKER_HOST="unix:///Users/valdersonjunior/.colima/default/docker.sock"
```

### Environment variables (`env.json`)

We use `env.json` (gitignored) to pass env vars to `sam local`.

Important fields:
- **OpenSearch Serverless**:
  - `OPENSEARCH_ENDPOINT`
  - `OPENSEARCH_INDEX`
- **Bedrock (embeddings)**:
  - `BEDROCK_EMBEDDING_MODEL_ID` (e.g. `amazon.titan-embed-text-v2:0`)
  - `BEDROCK_EMBEDDING_DIM` (e.g. `1024`)

Notes:
- `env.json` is **not committed** (it is in `.gitignore`).
- Do **not** commit `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

### Build + start API locally

From the repository root:

```bash
sam build --use-container
sam local start-api --env-vars env.json --profile rag-test --region us-east-1
```

---

## Ingestion script (no curl)

This project uses `script/call_ingest.py` to call `/ingest`.

### Main command

```bash
python3 script/call_ingest.py --doc-id bachelor-tesis --text @documents/bachelor-tesis.txt --chunk-size 800 --persist
```

Important note:
- When `--persist` is used, the backend forces **embeddings to be enabled** (equivalent to `embed=true`).

### Available flags

- `--url`: endpoint URL (default: `http://127.0.0.1:3000/ingest`)
- `--doc-id`: document identifier (recommended)
- `--text`: literal text or `@path/to/file.txt`
- `--chunk-size`: chunk size (characters)
- `--persist`: persist to OpenSearch Serverless
- `--embed`: force `embed=true` (note: with `--persist`, embeddings are already required)

### Debug / admin (via script)

- **Show env vars visible to the Lambda** (without leaking secrets):

```bash
python3 script/call_ingest.py --debug-env
```

- **Count docs in the index** (`_count`):

```bash
python3 script/call_ingest.py --debug-count
```

- **Full index reset** (delete + recreate with vector mapping):

```bash
python3 script/call_ingest.py --reset-index
```

---

## Idempotency notes

- When persisting (`--persist`), the worker first deletes documents for that `doc_id` before re-indexing.
- This prevents duplication when you run ingestion multiple times with the same `--doc-id`.

---

## Queue (SQS) — async ingestion

In this phase, `POST /ingest` does **not** index directly. It **enqueues** a message to SQS and a worker (`IngestWorkerFunction`) consumes it to:

- chunking
- embeddings (Bedrock)
- delete-by-query by `doc_id` (avoid duplication)
- bulk index into OpenSearch Serverless

Behavior:
- `POST /ingest` returns **202** with `status: enqueued`
- processing happens in the background

Local vs AWS:
- Locally (`sam local start-api`) `/ingest` can send messages to a **real SQS queue in AWS** (if the stack is deployed).
- The worker can be tested via `sam local invoke IngestWorkerFunction` with an SQS event (or by deploying to AWS).