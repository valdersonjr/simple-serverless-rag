# Beginner-friendly guide — what this project is and how to use it

## Project idea (vision)

For the original project vision/spec and the planned flows, see `project_idea.md`.

## Proposed (abstract) architecture

![Abstract architecture proposal](assets/abstract-architecture.png)

## Status

- **Flow 1 (Ingestion)**: ✅ implemented (API Gateway → Lambda → SQS → Worker → Bedrock embeddings → OpenSearch Serverless)
- **Flow 2 (Query/RAG)**: 🚧 in progress (chat endpoint + retrieval + LLM answer)

## What this project does (in 1 minute)

This project is a **RAG** (Retrieval‑Augmented Generation). In simple terms:

- You **send a text/document** to the system.
- The system **splits the text into smaller pieces** (“chunks”).
- It turns each piece into a big “number list” (a **vector**, called an **embedding**) that represents the meaning of the text.
- Those chunks + vectors are stored in a “smart search database” (**OpenSearch Serverless**).

Later (Flow 2, still in progress), you would ask questions and the system would search the most relevant chunks to answer based on them.

---

## How Flow 1 works (step by step)

When you call `POST /ingest`:

1) **API Gateway** receives the HTTP request.
2) The **`IngestFunction`** Lambda validates the JSON and places a message into a queue (**SQS**).
3) The queue (**SQS**) stores the work and retries automatically. If it fails too many times, it goes to the **DLQ**.
4) The **`IngestWorkerFunction`** Lambda reads the message and processes it:
   - splits the text into chunks
   - generates embeddings via **Bedrock**
   - writes into **OpenSearch Serverless (AOSS)**

That’s why `/ingest` responds quickly with **`status: enqueued`** (the rest happens in the background).

---

## “Each part” (what each thing is)

- **API Gateway**: the HTTP “front door” (`/ingest`).
- **`IngestFunction` Lambda**: receives the request and **enqueues** it (does not do the heavy work).
- **SQS (queue)**: async processing queue.
- **DLQ**: “error queue” (messages that failed multiple times).
- **`IngestWorkerFunction` Lambda**: does the heavy work (chunk + embedding + indexing).
- **Bedrock**: AWS service that generates embeddings.
- **OpenSearch Serverless (AOSS)**: stores the chunks and embeddings for search.

---

## How to use it (AWS — simplest way)

You need to have deployed the stack and have the **`IngestApiUrl`** output.

### 1) Ingest a text file

Example using a simple Lorem Ipsum text:

```bash
curl -X POST "<IngestApiUrl>" \
  -H "content-type: application/json" \
  -d '{
    "doc_id": "lorem-ipsum",
    "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
    "chunk_size": 200,
    "persist": true
  }'
```

Expected response (example):

- `status: enqueued`
- `message_id`: the SQS message id

### 2) Check if the worker processed it

```bash
sam logs -n IngestWorkerFunction --stack-name simple-serveless-rag --tail --profile rag-test --region us-east-1
```

If you see an error, it’s usually AOSS/Bedrock permissions or configuration.

---

## Proof it works (screenshots)

### Deployment outputs (API + queues)

![CloudFormation outputs (IngestApiUrl, QueueUrl, DLQUrl)](assets/deploy.png)

### Worker processing logs (no errors)

![IngestWorkerFunction logs (START/END/REPORT)](assets/queue-log.png)

### Vector DB has documents (OpenSearch `_count`)

![OpenSearch Serverless index count (_count > 0)](assets/chunk-count-vdb.png)

---

## What does “it worked” mean?

You know Flow 1 is working when:

- `POST /ingest` returns `status: enqueued`
- the worker does not keep failing/retrying
- you can confirm there are documents in the index (e.g. `_count > 0`)

---

## Common issues (simple explanations)

- **Queue does not exist** (`NonExistentQueue`): the system is trying to use a queue that wasn’t created/deployed, or the queue URL is wrong.
- **AOSS 403**: the Lambda is not allowed to access OpenSearch Serverless (you need a Data Access Policy allowing the role).
- **SSL error in local Python**: your Python doesn’t trust the certificate; you can fix it with `certifi` (when running local commands).

