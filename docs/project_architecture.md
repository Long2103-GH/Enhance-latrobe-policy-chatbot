# System Architecture & Integration

## 1. Executive Summary
This project resolves the complexity of navigating extensive university documentation. By employing a Retrieval-Augmented Generation (RAG) framework, the chatbot mitigates AI hallucinations, ensuring that every response provided to La Trobe University students and staff is explicitly backed by official source material.

## 2. Decoupled Client-Server Architecture
The project strictly separates the user interface from the intelligence engine, communicating via RESTful API endpoints.

### 2.1 Frontend Client
The frontend tracks conversation history (budgeted to approximately 600 tokens per session) and manages distinct user flows. It renders policy citations dynamically, allowing users to verify the exact document clause driving the chatbot's answer.

### 2.2 Backend Services
The FastAPI backend orchestrates the heavy lifting. Requests pass through a middleware layer that enforces rate limits before reaching the `rag/` module. Here, the user's intent is processed, vectorized, and queried against the Qdrant database. The retrieved context is formatted and sent to the LLM chain, producing a grounded response.

## 3. Data Flow Overview
1.  **Ingestion:** Raw policies (`policies.jsonl`) are chunked. Long segments undergo head/tail compression to retain critical context.
2.  **Query & Retrieval:** User prompts are vectorized. The system executes a hybrid vector-lexical search to compile the context window.
3.  **Generation:** The LLM evaluates the context alongside the conversation history (capped at 8 multi-turn interactions) to formulate a response.
4.  **Delivery:** The response and its corresponding citations are validated against Pydantic schemas and returned to the frontend UI.

## 4. Deployment & Orchestration
The entire application stack is containerized. Docker Compose synchronizes the execution of the FastAPI web server, the PostgreSQL relational database (for user data), and the Qdrant vector database (for policy embeddings), ensuring absolute parity between the development and production environments.
