# La Trobe University Policy DB Chatbot

A full-stack Retrieval-Augmented Generation (RAG) chatbot for answering questions about **La Trobe University policies, procedures, and internal documentation**.

The system combines a browser-based frontend with a FastAPI backend, hybrid semantic + lexical retrieval, reranking, large language model generation, citation validation, authenticated user-scoped conversations, and security-focused backend infrastructure.

> **Academic project:** Student capstone prototype for CSE3PIT.
> **Not an official La Trobe University service.**

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
* [Getting Started](#getting-started)

  * [1. Clone the Repository](#1-clone-the-repository)
  * [2. Configure the Backend](#2-configure-the-backend)
  * [3. Install Backend Dependencies](#3-install-backend-dependencies)
  * [4. Create the Database](#4-create-the-database)
  * [5. Prepare the Policy Index](#5-prepare-the-policy-index)
  * [6. Start the Backend](#6-start-the-backend)
  * [7. Start the Frontend](#7-start-the-frontend)
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

## Project Overview

The **La Trobe University Policy DB Chatbot** provides a conversational interface over a collection of La Trobe University policy and procedure documents.

Instead of requiring a user to manually search through large numbers of documents, the system:

1. Accepts a natural-language question.
2. Searches the policy knowledge base using multiple retrieval methods.
3. Combines and reranks the most relevant evidence.
4. Generates an answer using an LLM.
5. Validates the generated citations against retrieved evidence.
6. Returns the answer together with its supporting policy sources.
7. Stores conversations on the backend so authenticated users can return to previous enquiries.

The application is designed around **grounded generation**, meaning answers should be based on retrieved policy evidence rather than relying solely on the language model's general knowledge.

---

## Problem Statement

University policies and procedures can be lengthy, distributed across multiple documents, and difficult to search efficiently.

Typical users may need to answer questions such as:

* What are the grounds for special consideration?
* How much personal leave can a continuing staff member accrue?
* What is the process for purchasing research equipment?
* What should be checked when a student cannot access a Learning Portal subject site?

Traditional keyword search can return many results without explaining the answer in context.

This project addresses that problem by providing a conversational RAG interface that retrieves relevant policy evidence and uses that evidence to generate a structured answer with citations.

---

## Key Features

### RAG and Knowledge Retrieval

* Hybrid semantic and lexical retrieval.
* Vector search using **Qdrant**.
* Lexical search using **SQLite FTS5**.
* Reciprocal Rank Fusion (RRF) for combining retrieval results.
* Candidate reranking before generation.
* Query rewriting support.
* Policy-aware chunking.
* Citation tracking and validation.
* No-evidence handling and escalation behaviour.

### AI Generation

The backend includes provider adapters for:

* Google Gemini
* Anthropic Claude
* DeepSeek

The provider abstraction allows the generation layer to support multiple LLM backends without changing the rest of the RAG pipeline.

### Conversations

* Authenticated, user-scoped conversations.
* Conversation creation and retrieval.
* Conversation renaming.
* Conversation deletion.
* Persistent server-side conversation history.
* Last selected conversation ID retained locally by the frontend.

### Frontend

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
* Non-question shortcut responses for common greetings, acknowledgements, and help requests.

### Backend Reliability and Security

* JWT authentication.
* Auth provider abstraction with JWT, Auth0, and mock providers.
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

## System Architecture

At a high level:

```text
                         ┌─────────────────────────┐
                         │       Web Browser       │
                         │                         │
                         │  Ask La Trobe Frontend  │
                         └────────────┬────────────┘
                                      │
                                      │ HTTP / JSON
                                      ▼
                         ┌─────────────────────────┐
                         │       FastAPI API       │
                         │                         │
                         │ Auth / Chat / Convos    │
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
                     ┌────────────────┼────────────────┐
                     │                │                │
                     ▼                ▼                ▼
              ┌────────────┐  ┌────────────┐  ┌──────────────┐
              │   Qdrant   │  │ SQLite FTS │  │  LLM Provider│
              │ Vector DB   │  │  Lexical   │  │ Gemini/      │
              │             │  │  Retrieval │  │ Claude/      │
              └────────────┘  └────────────┘  │ DeepSeek     │
                                              └──────────────┘
                                                     
                                      ▼
                         ┌─────────────────────────┐
                         │   Citation Validation   │
                         │   + Guardrails + Audit  │
                         └─────────────────────────┘
```

---

## RAG Pipeline

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

### Why hybrid retrieval?

Semantic retrieval is useful when the user's wording differs from the wording in the source document.

Lexical retrieval is useful when exact terminology, policy titles, section names, identifiers, or specific phrases matter.

Using both approaches provides complementary retrieval signals.

### Why reranking?

Initial retrieval intentionally produces a broader candidate set. Reranking then prioritises the most relevant chunks before the language model receives the final context.

### Why citation validation?

The system should not treat an LLM-generated citation as trustworthy merely because the model produced it. Citation validation checks the generated references against the retrieved policy evidence.

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
* Optional Auth0 integration
* Gemini / Claude / DeepSeek provider adapters

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

The following is the project working-directory structure. Some directories such as local storage, logs, generated package metadata, and test artifacts are generated or ignored and therefore may not exist in a fresh Git clone until the project is run.

```text
📂 Project Repository Structure

├── backend                                      # FastAPI backend and RAG engine
│   ├── _pending                                 # Experimental or pending backend implementations
│   │   └── embedding_service_local.py
│   ├── app                                      # Main backend application package
│   │   ├── api                                  # HTTP API layer and route definitions
│   │   │   ├── routes                              # Individual API endpoint modules
│   │   │   │   ├── __init__.py
│   │   │   │   ├── admin.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── conversations.py
│   │   │   │   └── health.py
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py                  # Shared FastAPI dependencies
│   │   │   └── router.py                         # API router registration
│   │   ├── auth                                  # Authentication abstraction layer
│   │   │   ├── providers                         # Authentication provider implementations
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth0.py
│   │   │   │   ├── jwt.py
│   │   │   │   └── mock.py
│   │   │   ├── __init__.py
│   │   │   ├── base.py                            # Auth provider interface
│   │   │   └── factory.py                         # Provider selection
│   │   ├── core                                  # Configuration, security, logging and limits
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── core_logging.py
│   │   │   ├── exceptions.py
│   │   │   ├── rate_limit.py
│   │   │   ├── security.py
│   │   │   └── security_filters.py
│   │   ├── db                                    # Database engine, models and repositories
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   └── repositories.py
│   │   ├── middleware                             # HTTP security middleware
│   │   │   ├── __init__.py
│   │   │   └── security_headers.py
│   │   ├── rag                                  # Core RAG data structures and ranking logic
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py
│   │   │   ├── citation.py
│   │   │   ├── models.py
│   │   │   └── scoring.py
│   │   ├── schemas                               # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── common.py
│   │   │   ├── conversation.py
│   │   │   └── policy.py
│   │   ├── services                              # Business logic and RAG services
│   │   │   ├── providers                         # LLM provider adapters
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── claude_provider.py
│   │   │   │   ├── deepseek_provider.py
│   │   │   │   └── gemini_provider.py
│   │   │   ├── __init__.py
│   │   │   ├── audit_service.py                  # Audit events and traceability
│   │   │   ├── auth_service.py                   # Authentication-related business logic
│   │   │   ├── conversation_service.py           # Conversation management
│   │   │   ├── embedding_service.py              # Text embedding generation
│   │   │   ├── generation_service.py             # LLM generation orchestration
│   │   │   ├── ingestion_service.py              # Policy ingestion pipeline
│   │   │   ├── lexical_store.py                  # SQLite FTS5 retrieval
│   │   │   ├── prompt_service.py                 # Prompt/context construction
│   │   │   ├── query_rewriter.py                 # Query rewriting
│   │   │   ├── rag_service.py                    # End-to-end RAG orchestration
│   │   │   ├── reranking_service.py              # Candidate reranking
│   │   │   ├── retrieval_service.py              # Hybrid retrieval orchestration
│   │   │   ├── validation_service.py             # Answer/citation validation
│   │   │   └── vector_store.py                   # Qdrant vector retrieval
│   │   ├── utils                                 # Small shared utilities
│   │   │   ├── __init__.py
│   │   │   ├── hashing.py
│   │   │   └── text.py
│   │   ├── __init__.py
│   │   └── main.py                              # FastAPI application entry point
│   ├── data                                    # Policy, evaluation and generated data
│   │   ├── evaluation                           # RAG evaluation inputs and expected results
│   │   │   ├── expected_answers.json
│   │   │   └── questions.json
│   │   ├── processed                           # Processed policy data
│   │   ├── raw                                # Source policy dataset and crawler
│   │   │   ├── get_raw_policies                # Policy collection/crawling utilities
│   │   │   │   ├── crawl_latrobe_policies.py
│   │   │   │   └── requirements.txt
│   │   │   ├── policies.jsonl                  # Main policy source dataset
│   │   │   └── policies_summary.csv            # Derived local summary file
│   │   └── test_artifacts                      # Test-only generated artifacts
│   │       └── seed_credentials.csv
│   ├── deploy                                  # Deployment configuration and notes
│   │   ├── nginx.conf
│   │   └── README.md
│   ├── logs                                    # Runtime application logs (generated/ignored)
│   │   └── app.log
│   ├── policy_db_chatbot.egg-info              # Python package metadata (generated/ignored)
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
│   ├── storage                                 # Local databases and Qdrant storage (generated/ignored)
│   │   ├── qdrant                              # Local Qdrant data
│   │   │   ├── collection
│   │   │   │   └── policy_chunks
│   │   │   │       └── storage.sqlite
│   │   │   └── meta.json
│   │   ├── qdrant_test                         # Test Qdrant data
│   │   │   └── meta.json
│   │   └── app.db                              # Local application database
│   ├── tests                                   # Automated backend test suite
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
│   ├── Makefile                                # Backend development shortcuts
│   ├── pyproject.toml                          # Python project/tool configuration
│   ├── README.md                               # Backend-specific documentation
│   └── requirements.txt                        # Backend Python dependencies
├── frontend                                   # Browser-based Ask La Trobe client
│   ├── app                                    # Frontend application modules
│   │   ├── api.js                              # Backend API client
│   │   ├── chat.js                             # Chat request/controller logic
│   │   ├── composer.js                          # Input composer and controls
│   │   ├── config.js                            # Frontend runtime configuration
│   │   ├── main.js                              # Application bootstrap/render loop
│   │   ├── markdown.js                          # Markdown and citation rendering
│   │   ├── settings.js                          # Settings panel
│   │   ├── shortcuts.js                         # Non-question shortcut matching
│   │   ├── store.js                             # Frontend application state
│   │   ├── theme.js                             # Theme management
│   │   └── thread.js                            # Chat thread rendering
│   ├── assets                                  # Static branding assets
│   │   ├── favicon.ico
│   │   └── latrobe-logo.png
│   ├── styles                                  # Application CSS
│   │   ├── base.css
│   │   ├── components.css
│   │   ├── layouts.css
│   │   └── tokens.css
│   └── index.html                              # Frontend entry page
└── README.md                                  # Project-level documentation
```

---

# Prerequisites

For local development, install:

* Git
* Python 3.11 or later
* A modern web browser
* Docker Desktop, if using Docker

An API credential for the configured embedding/LLM providers may also be required depending on the selected environment configuration.

The frontend itself does **not** require Node.js or `npm`.

---

# Getting Started

## 1. Clone the Repository

```bash
git clone https://github.com/durbAr404/latrobe-university-policy-db-chatbot-TEAM-VectorBot.git
cd latrobe-university-policy-db-chatbot-TEAM-VectorBot
```

Verify the repository:

```bash
git status
```

A clean clone should report that the working tree is clean.

---

## 2. Configure the Backend

Move into the backend directory:

```bash
cd backend
```

Create the environment file from the committed template:

```bash
cp .env.example .env
```

On Windows PowerShell, the equivalent is:

```powershell
Copy-Item .env.example .env
```

Open `backend/.env` and configure the values required for your environment.

Typical configuration includes:

* application environment
* database connection
* JWT configuration
* authentication provider settings
* embedding model settings
* Hugging Face credentials where required
* LLM provider credentials
* Qdrant configuration
* retrieval settings
* logging settings

### Important

Never commit:

```text
.env
.env.* 
```

Secrets must remain local or be supplied through the deployment environment.

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

From the `backend` directory:

```bash
python -m scripts.create_database
```

This creates the local application database using the configured database URL.

For local development the project is configured to use SQLite.

---

## 5. Prepare the Policy Index

The repository contains the policy dataset under:

```text
backend/data/raw/policies.jsonl
```

Run the ingestion pipeline:

```bash
python -m scripts.ingest_policies
```

The ingestion process prepares policy content for retrieval by:

* loading the policy dataset
* normalising and chunking content
* generating embeddings
* storing vector representations in Qdrant
* building the lexical FTS5 index
* generating the metadata required by the retrieval layer

The first ingestion run may take longer because embedding models may need to be downloaded and initialized.

### Rebuild the index

When the underlying policy dataset or indexing configuration changes:

```bash
python -m scripts.rebuild_index
```

---

## 6. Start the Backend

From `backend/`:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will then be available at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive documentation is available at:

```text
http://127.0.0.1:8000/docs
```

The API root used by the frontend is:

```text
http://127.0.0.1:8000/api/v1
```

---

## 7. Start the Frontend

Open a second terminal from the repository root.

The frontend is static, so it does not require a build step.

For example:

```bash
python -m http.server 5500 --directory frontend
```

Open:

```text
http://127.0.0.1:5500
```

The frontend automatically uses the local backend API when running on `localhost` or `127.0.0.1`.

---

# Docker

Docker is provided for containerised backend development and deployment.

From the `backend/` directory:

### Development stack

```bash
docker compose -f docker-compose.dev.yml up --build
```

### Deployment-oriented stack

```bash
docker compose up --build
```

To stop the containers:

```bash
docker compose down
```

To stop the development stack:

```bash
docker compose -f docker-compose.dev.yml down
```

For deployment-specific information, see:

```text
backend/deploy/README.md
```

The deployment configuration includes Nginx and containerised backend infrastructure.

---

# Authentication

The backend separates authentication from the rest of the application through an authentication provider abstraction.

Supported provider implementations include:

* JWT
* Auth0
* Mock authentication for controlled development/testing scenarios

The active provider is selected through backend configuration.

The frontend communicates with authenticated endpoints using a bearer token.

The backend enforces user-scoped access to conversations, meaning a user's conversation data belongs to that authenticated user rather than being shared globally.

---

# Using the Application

A typical user flow is:

```text
1. Open the frontend
        ↓
2. Sign in
        ↓
3. Ask a policy question
        ↓
4. Backend validates the request
        ↓
5. Hybrid retrieval finds relevant policy evidence
        ↓
6. Candidates are reranked
        ↓
7. LLM generates a grounded answer
        ↓
8. Citations are validated
        ↓
9. Answer + citations are returned
        ↓
10. Conversation is stored server-side
```

The interface supports:

* starting a new enquiry
* reopening previous conversations
* renaming conversations
* deleting conversations
* changing layout
* changing theme
* copying answers
* regenerating answers
* stopping an in-progress generation
* using suggested questions
* voice input where supported

---

# Policy Data and Ingestion

The primary policy dataset is:

```text
backend/data/raw/policies.jsonl
```

The policy collection tooling is under:

```text
backend/data/raw/get_raw_policies/
```

The crawler is:

```text
backend/data/raw/get_raw_policies/crawl_latrobe_policies.py
```

The ingestion pipeline transforms policy content into retrieval-ready representations.

### Main stages

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

### Index stores

**Qdrant**

Stores vector embeddings and metadata for semantic retrieval.

**SQLite FTS5**

Stores searchable policy text for lexical retrieval.

### Data files

`policies_summary.csv` is a derived summary file and is intentionally excluded from source control.

---

# Evaluation and Testing

The backend includes automated tests under:

```text
backend/tests/
```

Run the complete test suite from `backend/`:

```bash
pytest
```

Useful test areas include:

* authentication
* policy chunking
* citation validation
* health endpoints
* RAG guardrails
* retrieval

### RAG evaluation

Evaluation inputs are stored under:

```text
backend/data/evaluation/
```

Run the evaluation script:

```bash
python -m scripts.evaluate_rag
```

The evaluation dataset can be extended through:

```text
backend/data/evaluation/questions.json
backend/data/evaluation/expected_answers.json
```

---

# API Overview

The backend exposes versioned API routes under:

```text
/api/v1
```

Main areas include:

### Authentication

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

### Chat

```text
POST /api/v1/chat
```

The chat endpoint accepts the current question, conversation context, and optional conversation ID, then returns the generated answer and supporting metadata.

### Conversations

```text
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}
```

### Health

```text
GET /api/v1/health
```

For the complete API schema, start the backend and open:

```text
http://127.0.0.1:8000/docs
```

---

# Security and Reliability

The project includes several defensive controls intended to make the prototype closer to a production-style backend.

### Authentication and authorisation

* JWT-based authentication.
* Provider abstraction for Auth0 and other providers.
* User-scoped conversation access.
* Protected API endpoints.

### API protection

* Request validation.
* Rate limiting.
* Structured API errors.
* Request IDs for traceability.
* Security response headers.

### RAG safeguards

* Hybrid evidence retrieval.
* Candidate reranking.
* Citation validation.
* Grounding checks.
* Explicit no-evidence handling.
* Escalation when sufficient evidence is not available.

### Frontend security

Markdown responses are sanitised through DOMPurify before HTML insertion.

External citation links are restricted to supported URI schemes and opened with:

```text
rel="noopener noreferrer"
```

### Logging

The backend uses structured application logging and rotating log files.

Runtime logs are local/generated artifacts and should not be committed.

---

# Development Workflow

This repository is intended to be developed collaboratively.

A recommended workflow is:

```text
main
 │
 ├── feature/backend-...
 ├── feature/frontend-...
 ├── feature/rag-...
 └── feature/...
```

Each developer should:

1. Pull the latest `main`.
2. Create a feature branch.
3. Make focused changes.
4. Run the relevant tests.
5. Review the diff.
6. Commit with a descriptive message.
7. Push the feature branch.
8. Open a pull request.
9. Merge into `main` after review.

Example:

```bash
git checkout main
git pull origin main

git checkout -b feature/improve-retrieval
```

After development:

```bash
git status
git diff --check
pytest
git add <files>
git commit -m "feat(rag): improve retrieval ranking"
git push -u origin feature/improve-retrieval
```

Avoid committing directly to `main` for normal team development.

---

# Environment and Generated Files

The repository intentionally excludes local and sensitive files such as:

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

These files are environment-specific, generated, or potentially sensitive.

A fresh clone should therefore be expected to recreate local runtime state by:

1. creating `.env`
2. installing dependencies
3. creating the database
4. preparing the vector/lexical indexes
5. starting the application

---

# Project Limitations

This is a **student capstone prototype**, not a production university information system.

Important limitations include:

* Policy content is dependent on the dataset available to the project.
* Retrieval quality depends on chunking, embeddings, ranking and reranking quality.
* LLM responses can still contain errors even when grounded.
* Citation validation reduces unsupported references but does not guarantee that every generated statement is correct.
* External LLM providers may have rate limits, availability constraints, or model-specific behaviour.
* Browser voice input depends on browser capabilities and permissions.
* The frontend currently stores the JWT in browser local storage, which is a known client-side security trade-off for this prototype.
* Production deployment requires proper secret management, monitoring, infrastructure hardening, backups, and operational controls beyond this academic prototype.

For policy decisions with real-world consequences, users should verify important information against the authoritative source policy.

---

# Future Improvements

Potential extensions include:

* stronger authentication and session management
* secure HTTP-only cookie-based sessions
* more comprehensive automated RAG evaluation
* improved citation entailment checks
* streaming directly from the backend
* more advanced reranking models
* better policy version tracking
* incremental ingestion
* document change detection
* richer observability and tracing
* CI/CD pipelines
* automated dependency and security scanning
* production-grade secret management
* comprehensive end-to-end browser testing
* stronger access-control administration
* deployment to managed cloud infrastructure

---

# Academic and Data Usage Notice

This repository was developed as a university capstone project.

The included policy dataset is provided for the project's intended private academic use under the project's authorised data-sharing arrangements.

The dataset and application should not be redistributed beyond the permissions governing the project.

The application is not an official La Trobe University service and should not be represented as one.

---

# Project Components

The repository contains two primary applications:

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
* themes/layouts
* markdown rendering
* citation presentation
* API communication

---

# Quick Start

For experienced developers, the shortest local setup is:

### Terminal 1 — Backend

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

### Terminal 2 — Frontend

From the repository root:

```bash
python -m http.server 5500 --directory frontend
```

Then open:

```text
http://127.0.0.1:5500
```

Backend API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# License

This project is an academic capstone project.

Unless a separate license file is added to the repository, no additional open-source redistribution rights should be assumed for the project source code or included policy data.

```

Use that as the **root `README.md`**. One important distinction is intentional: the structure you supplied includes local/generated directories such as `storage`, `logs`, `policy_db_chatbot.egg-info`, and ignored files such as `seed_users.py`; the README now explicitly explains that those may not exist in a fresh clone.
```
