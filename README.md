# La Trobe University Policy DB Chatbot

A full-stack **Retrieval-Augmented Generation (RAG)** chatbot for answering questions about **La Trobe University policies**.

The system combines a web-based frontend with a FastAPI backend, hybrid semantic + lexical retrieval, reranking, large language model (LLM) generation, citation validation, authenticated user-scoped conversations, and security-focused backend infrastructure.

> **Academic project:** Capstone prototype for CSE3CAP.

> **Not an official La Trobe University service (until it gets approval from the authority)**

---

## Table of Contents

* [Project Overview](#project-overview)
* [Problem Statement](#problem-statement)
* [Key Features](#key-features)
* [System Architecture](#system-architecture)
* [RAG Pipeline](#rag-pipeline)
* [Technology Stack](#technology-stack)
* [Project Repository Structure](#project-repository-structure)
* [Prerequisites](#prerequisites)
* [Required API Keys and Secrets](#required-api-keys-and-secrets)
* [Getting Started](#getting-started)

  * [1. Clone the Repository](#1-clone-the-repository)
  * [2. Configure the Backend Environment](#2-configure-the-backend-environment)
  * [3. Install Backend Dependencies](#3-install-backend-dependencies)
  * [4. Create the Database](#4-create-the-database)
  * [5. Build the Policy Retrieval Index](#5-build-the-policy-retrieval-index)
  * [6. Start the Backend](#6-start-the-backend)
  * [7. Start the Frontend](#7-start-the-frontend)
* [Swagger UI and API Testing](#swagger-ui-and-api-testing)
* [Docker](#docker)
* [Authentication](#authentication)
* [Using the Application](#using-the-application)
* [Policy Data and Ingestion](#policy-data-and-ingestion)
* [Evaluation and Testing](#evaluation-and-testing)
* [API Overview](#api-overview)
* [Security and Reliability](#security-and-reliability)
* [Development Workflow](#development-workflow)
* [Environment and Generated Files](#environment-and-generated-files)
* [Project Limitations](#project-limitations)
* [Future Improvements](#future-improvements)
* [Academic and Data Usage Notice](#academic-and-data-usage-notice)
* [License](#license)

---

# Project Overview

The **La Trobe University Policy DB Chatbot** provides a conversational interface over a collection of La Trobe University policy and procedure documents, with tailored interaction pathways for different user groups (students vs. staff).

Instead of manually searching through large policy documents, a user can ask a natural-language question and receive a generated answer explicitly supported by relevant policy sources. 

The system:

1. Accepts a natural-language question.
2. Optionally rewrites the query.
3. Searches the policy knowledge base using semantic and lexical retrieval.
4. Combines retrieval results using Reciprocal Rank Fusion (RRF).
5. Reranks the retrieved candidates.
6. Builds a grounded generation prompt.
7. Generates an answer using the configured LLM provider.
8. Validates citations against retrieved evidence.
9. Returns the answer together with its supporting sources.
10. Stores the conversation for the authenticated user.

The application is designed around **grounded generation**, meaning the answer is strictly based on retrieved policy evidence rather than relying on the language model's general knowledge, mitigating the risk of AI hallucinations.

---

# Problem Statement

University policies and procedures can be lengthy, distributed across multiple documents, and difficult to search efficiently. 

Users may need answers to questions such as:

* What are the grounds for special consideration?
* How much personal leave can a continuing staff member accrue?
* What is the process for purchasing research equipment?
* What should be checked when a student cannot access a Learning Portal subject site?

Traditional keyword search may return documents without directly explaining the answer or identifying the most relevant passages. This project addresses the problem through a conversational RAG system that retrieves relevant policy evidence and uses that evidence to generate structured answers with citations.

---

# Key Features

## RAG and Knowledge Retrieval

* Hybrid semantic and lexical retrieval.
* Vector search using **Qdrant**.
* Lexical search using **SQLite FTS5**.
* Reciprocal Rank Fusion (RRF).
* Candidate reranking before generation.
* Query rewriting.
* Policy-aware text chunking.
* Citation tracking and validation.
* No-evidence handling.
* Grounding and escalation safeguards.

## AI Generation

The backend supports multiple LLM providers through provider adapters:

* **DeepSeek** — primary generation provider.
* **Google Gemini** — fallback generation provider.
* **Anthropic Claude** — fallback generation provider.

The provider abstraction allows the generation layer to switch providers without changing the rest of the application architecture.

## Conversations

* Authenticated user-scoped conversations.
* Conversation creation and retrieval.
* Conversation renaming.
* Conversation deletion.
* Persistent server-side conversation history.
* Last selected conversation ID retained locally by the frontend.

## Frontend

The frontend is a lightweight vanilla HTML/CSS/JavaScript application with:

* Ask La Trobe branding.
* Responsive chat interface.
* Multiple layouts.
* Light, dark, and system themes.
* Conversation history sidebar.
* Suggested questions.
* Streaming-style response display.
* Copy and regenerate actions.
* Stop generation.
* Voice input where supported by the browser.
* Markdown rendering.
* Sanitized HTML output.
* Citation cards linking to policy sources.
* Settings panel.
* Conversational handling of natural responses.

## Backend Reliability and Security

* JWT authentication.
* Authentication provider abstraction.
* Auth0 support.
* Mock authentication for controlled testing.
* Request validation.
* Rate limiting.
* Security headers.
* Structured application logging.
* Rotating log files.
* Typed API errors.
* RAG guardrails.
* Citation validation.
* User-scoped conversation access.
* Docker deployment configuration.
* Nginx reverse-proxy configuration.

---

# System Architecture

At a high level:

```text
                         ┌─────────────────────────┐
                         │       Web Browser       │
                         │                         │
                         │   Ask La Trobe          │
                         │      Frontend           │
                         └────────────┬────────────┘
                                      │
                                      │ HTTP / JSON
                                      ▼
                         ┌─────────────────────────┐
                         │       FastAPI API       │
                         │                         │
                         │   Auth / Chat / Convos  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │       RAG Service       │
                         │                         │
                         │ Query → Retrieve →      │
                         │ Rerank → Generate →     │
                         │ Validate → Audit        │
                         └────────────┬────────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  │                   │                   │
                  ▼                   ▼                   ▼
          ┌──────────────┐   ┌──────────────┐   ┌────────────────┐
          │    Qdrant    │   │  SQLite FTS5 │   │  LLM Providers │
          │  Vector DB   │   │   Lexical    │   │  DeepSeek      │
          │              │   │   Retrieval  │   │  Gemini        │
          └──────────────┘   └──────────────┘   │  Claude        │
                                                └────────────────┘
                                                         │
                                                         ▼
                                      ┌─────────────────────────┐
                                      │   Citation Validation   │
                                      │   + Guardrails + Audit  │
                                      └─────────────────────────┘
```

---

# RAG Pipeline

The main RAG flow is:

```text
User Question
      │
      ▼
Input Validation
      │
      ▼
Query Rewriting
      │
      ├───────────────┐
      ▼               ▼
Vector Retrieval   Lexical Retrieval
(Qdrant)            (SQLite FTS5)
      │               │
      └───────┬───────┘
              ▼
      Reciprocal Rank Fusion
              │
              ▼
          Reranking
              │
              ▼
     Context / Prompt Build
              │
              ▼
        LLM Generation
              │
              ▼
      Citation Validation
              │
        ┌─────┴─────┐
        ▼           ▼
     Valid       Insufficient
        │           │
        ▼           ▼
  Final Answer   Escalation /
  + Citations    No-Evidence Response
```

## Why hybrid retrieval?

Semantic retrieval is useful when the user's wording differs from the wording used in the source document.

Lexical retrieval is useful when exact terminology, policy titles, section names, identifiers, or specific phrases matter.

Using both approaches provides complementary retrieval signals.

## Why reranking?

Initial retrieval intentionally produces a broader candidate set. Reranking then prioritises the most relevant chunks before they are supplied to the generation layer.

## Why citation validation?

The system should not assume that a citation generated by an LLM is automatically valid. Citation validation checks generated references against the evidence retrieved from the policy knowledge base.

---

# Technology Stack

## Frontend

* HTML5
* CSS3
* Vanilla JavaScript
* `marked` for Markdown parsing
* `DOMPurify` for sanitization
* Browser Fetch API
* Browser Web Speech API where supported

The frontend has **no Node.js build pipeline** and can be served directly as static files.

## Backend

* Python
* FastAPI
* Uvicorn
* Pydantic
* SQLAlchemy 2.x
* Async SQLAlchemy
* SQLite for local development
* PostgreSQL-compatible deployment configuration
* Qdrant
* SQLite FTS5
* JWT authentication
* Auth0 integration support
* DeepSeek / Gemini / Claude provider adapters

## AI / Retrieval

* Hugging Face embedding infrastructure
* `BAAI/bge-m3`
* 1024-dimensional embeddings
* Qdrant vector retrieval
* SQLite FTS5 lexical retrieval
* Reciprocal Rank Fusion
* Reranking
* RAG citation validation

## Infrastructure

* Docker
* Docker Compose
* Nginx
* Rotating application logs

---

# 📂 Project Repository Structure

The following represents the project working-directory structure.

Some directories and files are generated locally or intentionally ignored by Git. They may therefore not appear in a fresh clone until the application is configured and executed.

```text
📂 Project Repository Structure

├── backend                                      # FastAPI backend, database and RAG engine
│   ├── _pending                                 # Experimental or pending implementations
│   │   └── embedding_service_local.py
│   ├── app                                      # Main backend application package
│   │   ├── api                                  # HTTP API layer
│   │   │   ├── routes                             # API endpoint modules
│   │   │   │   ├── __init__.py
│   │   │   │   ├── admin.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── conversations.py
│   │   │   │   └── health.py
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py                   # Shared FastAPI dependencies
│   │   │   └── router.py                          # API route registration
│   │   ├── auth                                 # Authentication abstraction
│   │   │   ├── providers                        # Authentication provider implementations
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth0.py
│   │   │   │   ├── jwt.py
│   │   │   │   └── mock.py
│   │   │   ├── __init__.py
│   │   │   ├── base.py                            # Auth provider interface
│   │   │   └── factory.py                         # Auth provider selection
│   │   ├── core                                 # Configuration, security, logging and limits
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── core_logging.py
│   │   │   ├── exceptions.py
│   │   │   ├── rate_limit.py
│   │   │   ├── security.py
│   │   │   └── security_filters.py
│   │   ├── db                                   # Database engine, models and repositories
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   └── repositories.py
│   │   ├── middleware                            # HTTP security middleware
│   │   │   ├── __init__.py
│   │   │   └── security_headers.py
│   │   ├── rag                                 # RAG data models, chunking and scoring
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py
│   │   │   ├── citation.py
│   │   │   ├── models.py
│   │   │   └── scoring.py
│   │   ├── schemas                              # Pydantic request and response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── common.py
│   │   │   ├── conversation.py
│   │   │   └── policy.py
│   │   ├── services                             # Application business logic and RAG services
│   │   │   ├── providers                        # LLM provider adapters
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── claude_provider.py
│   │   │   │   ├── deepseek_provider.py
│   │   │   │   └── gemini_provider.py
│   │   │   ├── __init__.py
│   │   │   ├── audit_service.py                 # Audit events and traceability
│   │   │   ├── auth_service.py                  # Authentication business logic
│   │   │   ├── conversation_service.py          # Conversation management
│   │   │   ├── embedding_service.py             # Embedding generation
│   │   │   ├── embedding_service_local.py       # Local sentence-transformers embedding backend
│   │   │   ├── generation_service.py            # LLM generation orchestration
│   │   │   ├── ingestion_service.py             # Policy ingestion pipeline
│   │   │   ├── lexical_store.py                 # SQLite FTS5 retrieval
│   │   │   ├── prompt_service.py                # Prompt and context construction
│   │   │   ├── query_rewriter.py                # Query rewriting
│   │   │   ├── rag_service.py                   # End-to-end RAG orchestration
│   │   │   ├── reranking_service.py             # Retrieval candidate reranking
│   │   │   ├── retrieval_service.py             # Hybrid retrieval orchestration
│   │   │   ├── validation_service.py            # Answer and citation validation
│   │   │   └── vector_store.py                  # Qdrant vector retrieval
│   │   ├── utils                                # Shared utility functions
│   │   │   ├── __init__.py
│   │   │   ├── hashing.py
│   │   │   └── text.py
│   │   ├── __init__.py
│   │   └── main.py                              # FastAPI application entry point
│   ├── data                                    # Policy, evaluation and generated data
│   │   ├── evaluation                          # RAG evaluation datasets
│   │   │   ├── expected_answers.json
│   │   │   └── questions.json
│   │   ├── processed                           # Processed policy data
│   │   ├── raw                                # Source policy data and collection tools
│   │   │   ├── get_raw_policies                # Policy collection utilities
│   │   │   │   ├── crawl_latrobe_policies.py
│   │   │   │   └── requirements.txt
│   │   │   ├── policies.jsonl                  # Main policy dataset
│   │   │   └── policies_summary.csv            # Derived summary data
│   │   └── test_artifacts                      # Test-only generated artifacts
│   │       └── seed_credentials.csv
│   ├── deploy                                  # Deployment configuration and documentation
│   │   ├── nginx.conf
│   │   └── README.md
│   ├── logs                                    # Runtime application logs
│   │   └── app.log
│   ├── policy_db_chatbot.egg-info              # Generated Python package metadata
│   │   ├── dependency_links.txt
│   │   ├── PKG-INFO
│   │   ├── SOURCES.txt
│   │   └── top_level.txt
│   ├── scripts                                 # Database, ingestion, indexing and evaluation commands
│   │   ├── __init__.py
│   │   ├── create_database.py
│   │   ├── evaluate_rag.py
│   │   ├── export_test_credentials.py
│   │   ├── ingest_policies.py
│   │   ├── rebuild_index.py
│   │   ├── seed_production_db.py
│   │   └── seed_users.py
│   ├── storage                                 # Local database and Qdrant storage
│   │   ├── qdrant                              # Local Qdrant data
│   │   │   ├── collection
│   │   │   │   └── policy_chunks
│   │   │   │       └── storage.sqlite
│   │   │   └── meta.json
│   │   ├── qdrant_test                         # Test Qdrant data
│   │   │   └── meta.json
│   │   └── app.db                              # Local application database
│   ├── tests                                   # Automated backend tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_chunker.py
│   │   ├── test_citations.py
│   │   ├── test_health.py
│   │   ├── test_rag_guardrails.py
│   │   └── test_retrieval.py
│   ├── docker-compose.dev.yml                  # Development container stack
│   ├── docker-compose.yml                      # Deployment-oriented container stack
│   ├── Dockerfile                              # Backend container image
│   ├── Makefile                                # Backend development commands
│   ├── pyproject.toml                          # Python project and tool configuration
│   ├── README.md                               # Backend-specific documentation
│   └── requirements.txt                        # Backend Python dependencies
├── frontend                                  # Static browser-based Ask La Trobe client
│   ├── app                                   # Frontend application modules
│   │   ├── api.js                              # Backend API client
│   │   ├── chat.js                             # Chat controller and request handling
│   │   ├── composer.js                         # Question input and controls
│   │   ├── config.js                           # Frontend runtime configuration
│   │   ├── main.js                             # Frontend bootstrap and render loop
│   │   ├── markdown.js                         # Markdown and citation rendering
│   │   ├── settings.js                         # Settings panel
│   │   ├── store.js                            # Frontend application state
│   │   ├── theme.js                            # Theme management
│   │   └── thread.js                           # Chat thread rendering
│   ├── assets                                # Static images and branding
│   │   ├── favicon.ico
│   │   └── latrobe-logo.png
│   ├── styles                                # Frontend styling
│   │   ├── base.css
│   │   ├── components.css
│   │   ├── layouts.css
│   │   └── tokens.css
│   └── index.html                            # Frontend entry page
└── README.md                                # Project-level documentation
```

---

# Prerequisites

For local development, install:

* Git
* Python 3.11 or later
* A modern web browser
* Docker Desktop, if Docker is being used

The frontend itself does **not** require Node.js or `npm`.

You will also need credentials for the external services used by the backend.

---

# Required API Keys and Secrets

The frontend contains **no API keys or provider secrets**.

All provider credentials and backend secrets belong in:

```text
backend/.env
```

The repository includes:

```text
backend/.env.example
```

as the configuration template.

## 1. DeepSeek API Key — required for the primary LLM

DeepSeek is configured as the **main generation provider**.

You need a DeepSeek API key from your DeepSeek account.

Configure the corresponding DeepSeek API-key variable in:

```text
backend/.env
```

The exact variable name should match the `DEEPSEEK_*` entry provided in `backend/.env.example`.

Without a valid DeepSeek credential, the primary generation provider cannot make LLM requests.

---

## 2. Google Gemini API Key — required if Gemini fallback is enabled

Gemini is configured as the **first fallback generation provider**.

You need a Google Gemini API key if your configured provider chain can fall back to Gemini.

Configure the corresponding Gemini API-key variable in:

```text
backend/.env
```

The exact variable name should match the `GEMINI_*` entry provided in `backend/.env.example`.

The configured Gemini generation model is controlled separately through the generation-model setting.

---

## 3. Anthropic API Key — required if Claude fallback is enabled

Claude is configured as the **second fallback generation provider**.

You need an Anthropic API key if your configured provider chain can fall back to Claude.

Configure the corresponding Anthropic API-key variable in:

```text
backend/.env
```

The exact variable name should match the `ANTHROPIC_*` entry provided in `backend/.env.example`.

---

## 4. Hugging Face Token — optional (not required for inference)

The project uses BAAI/bge-m3 for embeddings, running locally via ```sentence-transformers```. The model weights are downloaded once from the public Hugging Face model hub (~2.3 GB) and cached on disk. The download is free and does not require a token.

Set ```HF_TOKEN``` in ```backend/.env``` only if you want to avoid anonymous download rate limits. Leave it empty if you don't have one.

No Inference API is used at query time. All embeddings run offline on the local CPU.



The embedding configuration uses a **1024-dimensional** vector representation.

---

## 5. JWT Secret — required for JWT authentication

The backend signs and validates JWT access tokens.

A strong random secret must be configured for the JWT signing key in:

```text
backend/.env
```

Use the JWT-secret variable defined by:

```text
backend/.env.example
```

Do not use a weak example value in a real deployment.

For local development, each developer should generate and use their own secret.

---

## 6. Auth0 credentials — only when Auth0 authentication is selected

Auth0 is optional.

When the backend is configured to use the Auth0 provider, the required Auth0 domain, audience, client configuration and related settings must be supplied in:

```text
backend/.env
```

When JWT authentication is being used locally, Auth0 credentials are not required.

---

## 7. Qdrant credentials — only for remote Qdrant deployments

For the local Qdrant mode used during development, the project stores Qdrant data locally and does not require a hosted Qdrant API key.

If the backend is configured for a remote Qdrant deployment, configure:

* Qdrant URL
* Qdrant API key

through the Qdrant environment variables defined in:

```text
backend/.env.example
```

---

## Credential summary

| Service          | Purpose                  | Required?                                                        |
| ---------------- | ------------------------ | ---------------------------------------------------------------- |
| DeepSeek         | Primary LLM generation   | Yes for primary provider                                         |
| Google Gemini    | LLM fallback             | Required when Gemini fallback is enabled                         |
| Anthropic Claude | LLM fallback             | Required when Claude fallback is enabled                         |
| Hugging Face     | Embedding model access   | Required for embedding generation where authentication is needed |
| JWT secret       | Local JWT authentication | Yes for JWT authentication                                       |
| Auth0            | External authentication  | Only when Auth0 provider is selected                             |
| Qdrant API key   | Hosted Qdrant            | Only for remote Qdrant mode                                      |

**Always use `backend/.env.example` as the authoritative list of environment-variable names.**

Never commit:

```text
backend/.env
```

or any other file containing API keys, passwords, tokens, or signing secrets.

---

# Getting Started

## 1. Clone the Repository

```bash
git clone https://github.com/durbAr404/LaTrobe-University-Policy-DB-Chatbot.git
cd LaTrobe-University-Policy-DB-Chatbot
```

Verify the repository:

```bash
git status
```

---

## 2. Configure the Backend Environment

Move into the backend directory:

```bash
cd backend
```

Create the environment file:

### Windows Git Bash

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Open:

```text
backend/.env
```

and enter your required API keys and secrets.

At minimum, make sure the credentials required by your selected LLM provider, embedding service, and authentication provider are configured.

---

## 3. Install Backend Dependencies

Create a virtual environment:

```bash
python -m venv .venv
```

### Windows Git Bash

```bash
source .venv/Scripts/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 4. Create the Database

From the `backend/` directory:

```bash
python -m scripts.create_database
```

For local development, the project uses SQLite through the configured database URL.

The resulting database file is local runtime data and is not intended for source control.

---

## 5. Build the Policy Retrieval Index

The main policy dataset is:

```text
backend/data/raw/policies.jsonl
```

If `backend/data/raw/policies.jsonl` is not available in your local checkout, collect the policy data first by running the policy crawler:

```bash
python backend/data/raw/get_raw_policies/crawl_latrobe_policies.py
```

Build the retrieval index:

```bash
python -m scripts.ingest_policies
```

The ingestion pipeline:

1. Loads policy data.
2. Normalises text.
3. Splits policies into retrieval chunks.
4. Generates embeddings.
5. Stores vector data in Qdrant.
6. Builds the SQLite FTS5 lexical index.

The initial run can take longer because the embedding model may need to be downloaded and initialized.

### Rebuild the index

When policy data or indexing configuration changes:

```bash
python -m scripts.rebuild_index
```

---

## 6. Start the Backend

From `backend/`:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend:

```text
http://127.0.0.1:8000
```

API base:

```text
http://127.0.0.1:8000/api/v1
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

ReDoc:

```text
http://127.0.0.1:8000/redoc
```

OpenAPI JSON:

```text
http://127.0.0.1:8000/openapi.json
```

---

## 7. Start the Frontend

Open a second terminal from the repository root.

The frontend is static and does not require a build process.

```bash
python -m http.server 5500 --directory frontend
```

Open:

```text
http://127.0.0.1:5500
```

When running locally on `localhost` or `127.0.0.1`, the frontend is configured to use:

```text
http://127.0.0.1:8000/api/v1
```

---

# Swagger UI and API Testing

FastAPI provides an interactive API testing interface through Swagger UI.

Once the backend is running, open:

```text
http://127.0.0.1:8000/docs
```

Swagger UI allows developers to inspect the available endpoints, schemas, parameters and responses and send requests directly to the running backend.

## Recommended API testing flow

### 1. Check the health endpoint

Open the health endpoint in Swagger and use:

```text
Try it out
```

then:

```text
Execute
```

This verifies that the API is running.

---

### 2. Test authentication

Use:

```text
POST /api/v1/auth/login
```

Click:

```text
Try it out
```

Enter the test user's credentials and execute the request.

A successful login returns an access token.

---

### 3. Authorize protected endpoints

After receiving a token, use the Swagger **Authorize** control if it is exposed by the generated OpenAPI security scheme.

Enter the bearer token in the format expected by the Swagger security dialog, typically:

```text
Bearer <access_token>
```

After authorizing, protected endpoints can be tested directly from Swagger UI.

---

### 4. Test the current user endpoint

Use:

```text
GET /api/v1/auth/me
```

This verifies that the token is valid and identifies the authenticated user.

---

### 5. Test the chat endpoint

Use:

```text
POST /api/v1/chat
```

The endpoint accepts the user's question together with the conversation context and optional conversation ID.

A typical request structure is:

```json
{
  "query": "What are the grounds for approving a special consideration request?",
  "conversation": [],
  "conversation_id": null
}
```

The exact request and response schema displayed in Swagger is authoritative for the current backend implementation.

A successful response can include:

* generated answer
* policy citations
* grounding status
* confidence
* escalation status
* disclaimer
* request ID
* conversation ID

---

### 6. Test conversation endpoints

Swagger can also be used to test:

```text
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}
```

These endpoints allow developers to verify conversation creation, retrieval, renaming, deletion and user-level access control.

---

### 7. Test error handling

Swagger is also useful for checking expected error responses, including:

* `400` class validation errors
* `401` unauthorised requests
* `404` missing resources
* `429` rate limiting
* other structured API failures

Swagger therefore provides a convenient way to validate the backend independently of the frontend.

---

# Docker

Docker is provided for containerised backend development and deployment.

From `backend/`:

## Development stack

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Deployment-oriented stack

```bash
docker compose up --build
```

Stop the deployment stack:

```bash
docker compose down
```

Stop the development stack:

```bash
docker compose -f docker-compose.dev.yml down
```

For deployment-specific information:

```text
backend/deploy/README.md
```

---

# Authentication

The backend separates authentication from application logic through an authentication-provider abstraction.

Supported implementations include:

* JWT
* Auth0
* Mock authentication

The active provider is selected through backend configuration.

For JWT authentication, the general flow is:

```text
User credentials
      ↓
POST /auth/login
      ↓
JWT access token
      ↓
Authorization: Bearer <token>
      ↓
Protected API endpoints
```

The backend enforces user-scoped conversation access.

---

# Using the Application

A typical application flow is:

```text
1. Open the frontend
        ↓
2. Sign in
        ↓
3. Ask a policy question
        ↓
4. Backend validates the request
        ↓
5. Query is processed for retrieval
        ↓
6. Hybrid retrieval finds relevant policy evidence
        ↓
7. Candidates are reranked
        ↓
8. LLM generates a grounded answer
        ↓
9. Citations are validated
        ↓
10. Answer + citations are returned
        ↓
11. Conversation is stored server-side
```

The frontend supports:

* starting a new enquiry
* reopening previous conversations
* renaming conversations
* deleting conversations
* changing layout
* changing theme
* copying answers
* regenerating answers
* stopping generation
* suggested questions
* voice input where supported

---

# Policy Data and Ingestion

The primary policy dataset is:

```text
backend/data/raw/policies.jsonl
```

Policy collection tools are under:

```text
backend/data/raw/get_raw_policies/
```

The crawler is:

```text
backend/data/raw/get_raw_policies/crawl_latrobe_policies.py
```

## Ingestion flow

```text
Raw Policy Documents
        ↓
Normalisation
        ↓
Policy Chunking
        ↓
Content Hashing / Metadata
        ↓
Embedding Generation
        ↓
Qdrant Vector Index
        +
SQLite FTS5 Lexical Index
        ↓
Ready for Hybrid Retrieval
```

## Qdrant

Qdrant stores policy embeddings and associated metadata for semantic retrieval.

## SQLite FTS5

SQLite FTS5 stores searchable policy text for lexical retrieval.

## Derived files

`policies_summary.csv` is a derived local summary file and is intentionally excluded from source control.

---

# Evaluation and Testing

Automated backend tests are located under:

```text
backend/tests/
```

Run the full test suite:

```bash
pytest
```

The test suite covers areas including:

* authentication
* policy chunking
* citation validation
* health endpoints
* RAG guardrails
* retrieval

## RAG Evaluation

Evaluation inputs are stored under:

```text
backend/data/evaluation/
```

Run:

```bash
python -m scripts.evaluate_rag
```

Evaluation datasets can be updated through:

```text
backend/data/evaluation/questions.json
backend/data/evaluation/expected_answers.json
```

---

# API Overview

The backend API is versioned under:

```text
/api/v1
```

## Authentication

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

## Chat

```text
POST /api/v1/chat
```

## Conversations

```text
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}
```

## Health

```text
GET /api/v1/health
```

For the complete request and response schemas, use Swagger UI:

```text
http://127.0.0.1:8000/docs
```

---

# Security and Reliability

The project includes several controls intended to make the prototype closer to a production-style backend.

## Authentication and authorisation

* JWT authentication.
* Authentication-provider abstraction.
* Auth0 support.
* User-scoped conversation access.
* Protected API endpoints.

## API protection

* Request validation.
* Rate limiting.
* Structured API errors.
* Request IDs.
* Security response headers.

## RAG safeguards

* Hybrid evidence retrieval.
* Candidate reranking.
* Citation validation.
* Grounding checks.
* Explicit no-evidence handling.
* Escalation when sufficient evidence is unavailable.

## Frontend security

Markdown generated by the backend is sanitised through DOMPurify before being inserted into the document.

Citation links are handled with safe link attributes including:

```text
rel="noopener noreferrer"
```

## Logging

The backend uses application logging and rotating log files.

Runtime logs should remain local and must not contain credentials or secrets.

---

# Development Workflow

The repository is intended to be developed collaboratively.

A recommended branch model is:

```text
main
 │
 ├── feature/backend-...
 ├── feature/frontend-...
 ├── feature/rag-...
 └── feature/...
```

Typical workflow:

```bash
git checkout main
git pull origin main
git checkout -b feature/my-change
```

After making changes:

```bash
git status
git diff --check
pytest
```

Then:

```bash
git add <files>
git commit -m "feat(component): describe the change"
git push -u origin feature/my-change
```

Open a pull request and merge into `main` after review.

Avoid direct commits to `main` during normal team development.

---

# Environment and Generated Files

The repository intentionally excludes local, generated and sensitive files such as:

```text
.env
storage/
logs/
*.db
*.sqlite
__pycache__/
.venv/
node_modules/
reports/
test artifacts
generated package metadata
temporary files
```

These files are environment-specific or generated at runtime.

A fresh clone should therefore recreate its local environment by:

1. Creating `backend/.env`.
2. Supplying required credentials.
3. Installing dependencies.
4. Creating the database.
5. Building the retrieval indexes.
6. Starting the backend.
7. Starting the frontend.

---

# Project Limitations

This is a **student capstone prototype**, not a production university information system.

Important limitations include:

* Policy coverage depends on the available dataset.
* Retrieval quality depends on chunking, embeddings, ranking and reranking.
* LLM responses can still contain errors even when grounded.
* Citation validation does not guarantee that every generated statement is correct.
* External LLM providers may impose rate limits or service restrictions.
* Voice input depends on browser support and permissions.
* The frontend currently stores the JWT in browser local storage, which is a known client-side security trade-off.
* Production deployment would require stronger secret management, monitoring, backups, incident handling, infrastructure hardening and operational controls.

For important policy decisions, users should verify the answer against the authoritative policy source.

---

# Future Improvements

Potential extensions include:

* stronger authentication and session management
* secure HTTP-only cookie-based sessions
* more comprehensive RAG evaluation
* stronger citation entailment validation
* direct backend streaming
* advanced reranking models
* policy version tracking
* incremental ingestion
* document change detection
* richer observability and tracing
* CI/CD automation
* automated dependency and security scanning
* production-grade secret management
* comprehensive browser end-to-end testing
* stronger administrative access control
* managed cloud deployment

---

# Academic and Data Usage Notice

This repository was developed as a university capstone project for **CSE3CAP**.

The included policy dataset is provided for the project's intended private academic use under the project's authorised data-sharing arrangements.

The dataset and application should not be redistributed beyond the permissions governing the project.

The application is **not an official La Trobe University service** and must not be represented as one.

---

# Project Components

## Backend

Located in:

```text
backend/
```

Responsible for:

* authentication
* API endpoints
* database operations
* conversation persistence
* policy ingestion
* hybrid retrieval
* reranking
* LLM generation
* citation validation
* audit logging
* security controls

Backend-specific documentation:

```text
backend/README.md
```

## Frontend

Located in:

```text
frontend/
```

Responsible for:

* user interface
* authentication screens
* chat experience
* conversation navigation
* settings
* themes and layouts
* markdown rendering
* citation presentation
* API communication

---

# Quick Start

## Backend

```bash
cd backend

python -m venv .venv
source .venv/Scripts/activate

pip install -r requirements.txt

cp .env.example .env

python -m scripts.create_database
python -m scripts.ingest_policies

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Frontend

From the repository root, open a second terminal:

```bash
python -m http.server 5500 --directory frontend
```

Then open:

```text
http://127.0.0.1:5500
```

## API Documentation

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

ReDoc:

```text
http://127.0.0.1:8000/redoc
```

OpenAPI schema:

```text
http://127.0.0.1:8000/openapi.json
```

---

# License

This project is an academic capstone project.

Unless a separate license file is added to the repository, no additional open-source redistribution rights should be assumed for the project source code or included policy data.

