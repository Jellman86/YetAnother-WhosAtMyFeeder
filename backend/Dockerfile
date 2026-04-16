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
ARG APP_BRANCH=unknown
ARG TARGETARCH
ARG INTEL_GPU_APT_CHANNEL=noble/lts
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}
ENV APP_BRANCH=${APP_BRANCH}

# Install runtime libs for opencv/tflite and Intel iGPU OpenVINO acceleration.
# NVIDIA CUDA/cuDNN userspace for ONNX Runtime is installed via backend/requirements.txt;
# the host still needs NVIDIA Container Toolkit (or equivalent) for GPU passthrough.
# Debian 13 no longer ships the Intel NEO OpenCL/Level Zero runtime packages OpenVINO GPU needs,
# so we add Intel's graphics repo and install the userspace runtime stack explicitly.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gpg \
        libgl1 \
        libglib2.0-0 \
        sqlite3; \
    if [ "${TARGETARCH:-amd64}" = "amd64" ]; then \
        install -d -m 0755 /etc/apt/keyrings; \
        curl -fsSL --retry 5 --retry-delay 2 https://repositories.intel.com/gpu/intel-graphics.key \
            | gpg --dearmor -o /etc/apt/keyrings/intel-graphics.gpg; \
        echo "deb [signed-by=/etc/apt/keyrings/intel-graphics.gpg arch=amd64] https://repositories.intel.com/gpu/ubuntu ${INTEL_GPU_APT_CHANNEL} unified" \
            > /etc/apt/sources.list.d/intel-gpu.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            ocl-icd-libopencl1 \
            libze1 \
            libze-intel-gpu1 \
            intel-opencl-icd; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install from requirements so extras like onnxruntime-gpu[cuda,cudnn] remain active
# while still preferring the prebuilt local wheels we produced in the builder stage.
RUN pip install --no-cache-dir --find-links /wheels -r requirements.txt

# Create a non-root user and setup directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /data /config /app/data/models && \
    chown -R appuser:appuser /app /data /config

COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser download_model.py /app/download_model.py
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser locales /app/locales
COPY --chown=appuser:appuser migrations /app/migrations

# Set environment variables
ENV DB_PATH=/data/speciesid.db
ENV MODEL_DIR=/data/models
# OpenVINO (and related GPU runtimes) may write telemetry/shader cache under HOME/XDG paths.
# Compose overrides the container user to a numeric UID/GID, so default HOME can become `/`.
# Point caches/config to /tmp (writable, per-container) to avoid noisy warnings and failures.
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache
ENV XDG_CONFIG_HOME=/tmp/.config
ENV XDG_DATA_HOME=/tmp/.local/share

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
