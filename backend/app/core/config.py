"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = BASE_DIR / "logs"


class Settings(BaseSettings):
    """Strongly typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ────────────────────────────────────────────────
    app_name: str = "Policy DB Chatbot"
    app_env: str = "development"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    # ─── Security / JWT ─────────────────────────────────────────────
    secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ─── CORS ───────────────────────────────────────────────────────
    # Comma-separated list of allowed origins. Use "*" ONLY in dev.
    # Example: "http://localhost:5500,https://ask.latrobe.edu.au"
    cors_origins: str = "http://127.0.0.1:5500,http://localhost:5500"

    # ─── Security features ──────────────────────────────────────────
    # Toggle security headers middleware on/off.
    security_headers_enabled: bool = True
    # Toggle input/output validation filters.
    input_validation_enabled: bool = True

    # ─── Auth provider ──────────────────────────────────────────────
    auth_provider: str = "jwt"

    # ─── Auth0 (only required when auth_provider="auth0") ───────────
    auth0_domain: str = ""
    auth0_audience: str = ""
    auth0_issuer: str = ""
    auth0_allowed_domain: str = "latrobe.edu.au"

    # ─── Support contact (forgot-password reference) ────────────────
    support_email: str = "IT.Support@latrobe.edu.au"
    support_url: str = "https://www.latrobe.edu.au/it/contact-us"

    # ─── Database ───────────────────────────────────────────────────
    # SQLite is the default for local dev. Postgres is used via Docker.
    sqlite_db_path: Path = STORAGE_DIR / "app.db"

    # Postgres credentials (used by docker-compose only).
    postgres_user: str = "policy"
    postgres_password: str = "policy"
    postgres_db: str = "policy_db"

    @property
    def database_url(self) -> str:
        """
        Return the async database URL.

        Uses ``DATABASE_URL`` from the environment when set (e.g. inside
        Docker, pointing at Postgres). Falls back to a local SQLite file
        with an absolute path.
        """
        import os

        override = os.getenv("DATABASE_URL", "").strip()
        if override:
            return override

        return f"sqlite+aiosqlite:///{self.sqlite_db_path.as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list of origin strings."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    # ─── LLM Provider chain ─────────────────────────────────────────
    # Primary provider plus up to two fallbacks. Each is tried in order
    # when the previous one raises GenerationError.
    llm_provider: str = "deepseek"
    llm_fallback_enabled: bool = True
    llm_fallback_provider: str = "gemini"
    llm_fallback_provider_2: str = "claude"

    # ─── DeepSeek ───────────────────────────────────────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    # ─── Gemini ─────────────────────────────────────────────────────
    gemini_api_key: str = Field(min_length=1)
    gemini_generation_model: str = "gemini-3.6-flash"

    # ─── Claude (Anthropic) ─────────────────────────────────────────
    claude_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"

    # ─── Hugging Face ───────────────────────────────────────────────
    hf_token: str
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024

    # Optional path to a pre-downloaded local embedding model.
    # Only used by the optional LocalEmbeddingService.
    embedding_local_path: str = ""

    # ─── Qdrant ─────────────────────────────────────────────────────
    qdrant_mode: str = "local"
    qdrant_path: str = "./storage/qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "policy_chunks"

    # ─── Retrieval ──────────────────────────────────────────────────
    vector_top_k: int = 20
    lexical_top_k: int = 20
    rrf_k: int = 60
    final_context_chunks: int = 12

    # Max chunks from any single policy in the final context. Prevents
    # one policy from monopolising the retrieval window.
    max_chunks_per_policy: int = 2

    # ─── Context optimisation ───────────────────────────────────────
    # Long chunks (> chunk_long_threshold tokens) are compressed to
    # their first `chunk_long_threshold` tokens plus the last
    # `chunk_long_tail` tokens. Short chunks are sent untouched.
    # Preserves the opening rule + closing caveat while trimming
    # elaboration in the middle. Never drops a chunk entirely.
    chunk_long_threshold: int = 400
    chunk_long_tail: int = 100

    # Adaptive context window: send fewer chunks when retrieval
    # confidence is high (the tail chunks wouldn't be cited anyway),
    # send more when it's low (need the recall).
    context_by_confidence: bool = True

    # Conversation history budget in tokens. Sent turns fill this budget
    # (with a minimum of 3 turns and a maximum of `max_conversation_turns`).
    conversation_token_budget: int = 600

    # ─── Retrieval confidence & broadening ──────────────────────────
    # When the top fused retrieval score is below this threshold, the
    # pipeline triggers a broadening pass (one extra LLM call) to catch
    # queries that don't match any policy directly.
    retrieval_low_confidence_threshold: float = 0.12

    # Toggle the broadening pass entirely.
    query_broadening_enabled: bool = True

    # ─── Reranking ──────────────────────────────────────────────────
    reranking_enabled: bool = False
    reranking_bm25_weight: float = 0.4

    min_retrieval_score: float = 0.15
    min_generation_support: float = 0.60

    # ─── Query rewriting ────────────────────────────────────────────
    query_rewriting_enabled: bool = True

    # ─── Pipeline debug logging (verbose; only for dev) ────────────
    debug_pipeline: bool = False

    # ─── Limits ─────────────────────────────────────────────────────
    max_query_length: int = 2000
    max_conversation_turns: int = 8
    rate_limit_per_minute: int = 10

    # ─── Logging ────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = str((LOGS_DIR / "app.log").as_posix())

    # ─── Policy data ────────────────────────────────────────────────
    policy_jsonl_path: str = "data/raw/policies.jsonl"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
