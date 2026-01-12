# Multi-stage build for Python 3.12
FROM python:3.12-slim as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Version info passed at build time
ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}

# Install runtime libs for opencv/tflite
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache /wheels/*

# Create a non-root user and setup directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /data /config /app/data/models && \
    chown -R appuser:appuser /app /data /config

COPY --chown=appuser:appuser . .

# Set environment variables
ENV DB_PATH=/data/speciesid.db
ENV MODEL_DIR=/app/data/models

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
