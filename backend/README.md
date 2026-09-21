# La Trobe Policy DB Chatbot — Backend

Production-oriented FastAPI backend for the La Trobe University Policy DB Chatbot.

The backend implements a retrieval-augmented generation (RAG) pipeline that retrieves relevant policy content, generates an answer using an LLM provider, validates citations and grounding, and records audit information.

## Architecture

```text
Frontend
   │
   │ HTTP / JSON
   ▼
Nginx
   │
   ▼
FastAPI
   │
   ├── Authentication
   │     ├── JWT
   │     ├── Auth0
   │     └── Mock (tests)
   │
   ├── RAG Pipeline
   │     ├── Query rewriting
   │     ├── Embedding generation
   │     ├── Vector retrieval
   │     ├── Lexical retrieval
   │     ├── Reciprocal Rank Fusion
   │     ├── Reranking
   │     ├── LLM generation
   │     └── Citation / grounding validation
   │
   ├── PostgreSQL / SQLite
   │     ├── Users
   │     ├── Conversations
   │     ├── Messages
   │     └── Audit events
   │
   ├── Redis
   │     └── Rate limiting / supporting infrastructure
   │
   └── Qdrant
         └── Policy vector index
```

## Technology Stack

| Area                 | Technology               |
| -------------------- | ------------------------ |
| API                  | FastAPI                  |
| Language             | Python 3.12+             |
| ORM                  | SQLAlchemy 2.x           |
| Development database | SQLite                   |
| Production database  | PostgreSQL               |
| Vector database      | Qdrant                   |
| Lexical search       | SQLite FTS5              |
| Embeddings           | BAAI/bge-m3              |
| Reranking            | BM25-based reranking     |
| LLM providers        | DeepSeek, Gemini, Claude |
| Authentication       | JWT / Auth0 / Mock       |
| Rate limiting        | SlowAPI                  |
| Reverse proxy        | Nginx                    |
| Containerization     | Docker / Docker Compose  |
| Testing              | Pytest / pytest-asyncio  |
| Linting              | Ruff                     |
| Type checking        | MyPy                     |

## Project Structure

```text
backend/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   ├── dependencies.py
│   │   └── router.py
│   ├── auth/
│   │   ├── providers/
│   │   ├── base.py
│   │   └── factory.py
│   ├── core/
│   ├── db/
│   ├── middleware/
│   ├── rag/
│   ├── schemas/
│   ├── services/
│   └── main.py
│
├── data/
│   ├── evaluation/
│   ├── processed/
│   └── raw/
│
├── deploy/
├── scripts/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.dev.yml
├── requirements.txt
└── pyproject.toml
```

## Local Development

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
source .venv/Scripts/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create the local environment file:

```bash
cp .env.example .env
```

Then update `.env` with the credentials and settings required for the selected authentication and LLM providers.

Never commit `.env` or real API credentials.

### 4. Run the API directly

```bash
uvicorn app.main:app --reload
```

The API runs on:

```text
http://127.0.0.1:8000
```

During development, interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Docker Development

The development Compose configuration starts the API and Qdrant with development-oriented settings and hot reload.

```bash
docker compose -f docker-compose.dev.yml up --build
```

Stop the services with:

```bash
docker compose -f docker-compose.dev.yml down
```

## Production Deployment

The production Compose configuration provides:

```text
FastAPI
PostgreSQL
Redis
Qdrant
```

Start the stack with:

```bash
docker compose up -d --build
```

The API container is exposed on port `8000` for the host-level Nginx reverse proxy.

Nginx serves the frontend and forwards `/api/` requests to the FastAPI container.

Production configuration should use:

* `APP_ENV=production`
* `DEBUG=false`
* strong secret keys
* production LLM credentials
* production database credentials
* a remote or containerized Qdrant instance
* HTTPS through Nginx

Do not use the test-user seeding or test-credential export scripts as part of production deployment.

## Database Initialization

Create the application database tables using:

```bash
python -m scripts.create_database
```

For a Docker deployment:

```bash
docker compose exec api python -m scripts.create_database
```

The application uses SQLite during local development and PostgreSQL in the production Compose environment.

## Policy Ingestion

Policy source documents are stored under:

```text
data/raw/policies.jsonl
```

To ingest the policy collection and build the retrieval indexes:

```bash
python -m scripts.ingest_policies
```

The ingestion pipeline:

```text
Policy JSONL
    │
    ▼
Chunking
    │
    ├──► Embeddings ──► Qdrant
    │
    └──► Lexical index ──► SQLite FTS5
```

The local Qdrant index is generated under application storage and is intentionally excluded from Git.

The raw policy dataset is the source of truth. Generated vector indexes should be rebuilt rather than committed to the repository.

## Rebuilding the Retrieval Index

To rebuild the vector and lexical indexes:

```bash
python -m scripts.rebuild_index
```

Use this when policy data or retrieval configuration changes and the existing index needs to be regenerated.

## Evaluation

Evaluation questions and expected answers are stored under:

```text
data/evaluation/
```

Run the RAG evaluation harness with:

```bash
python -m scripts.evaluate_rag
```

Evaluation may call external embedding and LLM services depending on the configured providers.

Generated reports are written to the ignored `reports/` directory.

## Test Suite

Run the complete test suite with:

```bash
pytest
```

The project is configured to collect coverage automatically.

A coverage threshold is enforced through `pyproject.toml`.

The tests mock external embedding, generation, vector, and lexical services so the core test suite can run without requiring live external AI services.

## Authentication

The backend supports multiple authentication providers through the provider factory.

### JWT

Local JWT authentication is intended for development and environments where the application manages passwords directly.

Passwords are hashed using Argon2id.

### Auth0

Auth0 provides external identity management and RS256 JWT verification using Auth0 JWKS.

The backend mirrors authenticated users into the local database using the Auth0 subject identifier as the external identifier.

### Mock

The mock provider is intended for automated tests only.

It must not be enabled in production.

Select the provider through the configured `AUTH_PROVIDER` setting.

## Security

The backend includes multiple security controls:

* Argon2id password hashing
* JWT authentication
* Auth0 JWT verification
* role-based authorization
* request validation
* prompt-injection and XSS filtering
* request IDs for tracing
* rate limiting
* security response headers
* strict CORS allowlisting
* user-scoped conversation access
* citation validation
* grounding checks
* generic unexpected-error responses that do not expose internal exceptions
* non-root Docker runtime user

Secrets are supplied through environment variables and are not embedded in the application image.

## Important Local Files

The following files and directories are intentionally ignored by Git:

```text
.env
storage/
logs/
reports/
__pycache__/
*.db
*.sqlite
test_artifacts/
_pending/
```

Test credential exports are written to:

```text
data/test_artifacts/seed_credentials.csv
```

This file contains plaintext passwords and must never be committed or distributed outside the intended development/testing team.

## Useful Commands

Run tests:

```bash
pytest
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Create database:

```bash
python -m scripts.create_database
```

Ingest policies:

```bash
python -m scripts.ingest_policies
```

Rebuild indexes:

```bash
python -m scripts.rebuild_index
```

Run evaluation:

```bash
python -m scripts.evaluate_rag
```

Start development Docker stack:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Start production Docker stack:

```bash
docker compose up -d --build
```

## Development Notes

The backend is designed around dependency injection and service separation so that authentication, retrieval, generation, validation, and persistence components can be tested independently.

The RAG pipeline is intentionally hybrid: semantic retrieval and lexical retrieval are combined before reranking so that both conceptual similarity and exact policy terminology can contribute to the final evidence set.

Generated answers must remain grounded in retrieved policy evidence. When sufficient evidence cannot be established, the backend returns a non-grounded response and marks the interaction for escalation rather than presenting unsupported policy information as fact.
