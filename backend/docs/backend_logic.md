# Backend Architecture & RAG Pipeline

This document details the backend mechanics powering the chatbot, built on an asynchronous FastAPI architecture with stringent Pydantic data validation.

## 1. RAG & Retrieval Engine
The system processes official university policy documents into chunks, storing them in a Qdrant vector database.
*   **Embeddings:** Text chunks are vectorized using Hugging Face's `BAAI/bge-m3` model (1024 dimensions).
*   **Hybrid Search:** Queries trigger both a vector search and a BM25 lexical search. Reciprocal Rank Fusion (RRF) merges these results, passing the top 12 chunks to the LLM context window.
*   **Adaptive Context:** If retrieval confidence drops below `0.12`, the system automatically broadens the query to capture peripheral policy details.

## 2. Multi-Tiered LLM Chain
To ensure maximum uptime for staff and students, the generation phase uses a tiered approach:
1.  **DeepSeek (`deepseek-flash`):** The primary generation model.
2.  **Gemini (`gemini-3.6-flash`):** First automated fallback.
3.  **Claude (`claude-haiku-4-5`):** Final redundancy layer.

## 3. Directory Structure (`app/`)
*   `api/`: Central router, dependency injection, and endpoint definitions.
*   `auth/`: JWT authentication and user validation logic (via `python-jose` and `argon2-cffi`).
*   `db/`: Relational database connections (SQLAlchemy) for conversation state management.
*   `middleware/`: Request interception and rate limiting (capped at 10 requests/minute via `slowapi`).
*   `rag/`: The core document chunking and vector retrieval logic.
*   `schemas/`: Pydantic models enforcing strict I/O validation.

## 4. Testing Protocols
Robust asynchronous testing is implemented via `pytest` and `pytest-asyncio`. Core test coverage includes document chunking (`test_chunker.py`), retrieval accuracy (`test_retrieval.py`), and citation guardrails (`test_citations.py`).
