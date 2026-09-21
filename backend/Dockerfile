# =============================================================================
# Stage 1: Build dependencies
# =============================================================================
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps needed to compile some Python packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtualenv we can copy later.
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r requirements.txt


# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

# Runtime-only system deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the app.
RUN groupadd --system app && \
    useradd --system --gid app --home /app --shell /sbin/nologin app

# Copy the virtualenv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy application code.
WORKDIR /app
COPY --chown=app:app . .

# Ensure writable dirs exist for the non-root user.
RUN mkdir -p /app/storage /app/logs && \
    chown -R app:app /app/storage /app/logs

USER app

EXPOSE 8000

# Healthcheck that verifies the API is responding.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# Start the API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]