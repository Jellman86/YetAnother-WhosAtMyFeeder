# syntax=docker/dockerfile:1.7

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

# Install the full compatibility runtime. The legacy split backend is not
# receiving provider-specific image variants before its v3 removal.
COPY requirements*.txt /requirements/
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    -r /requirements/requirements-base.txt \
    -r /requirements/requirements-provider-full.txt

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
ENV YAWAMF_IMAGE_FLAVOR=full

LABEL io.yawamf.image.flavor="full"

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
        sqlite3 \
        zlib1g; \
    if [ "${TARGETARCH:-amd64}" = "amd64" ]; then \
        install -d -m 0755 /etc/apt/keyrings; \
        curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 https://repositories.intel.com/gpu/intel-graphics.key \
            | gpg --dearmor -o /etc/apt/keyrings/intel-graphics.gpg; \
        echo "deb [signed-by=/etc/apt/keyrings/intel-graphics.gpg arch=amd64] https://repositories.intel.com/gpu/ubuntu ${INTEL_GPU_APT_CHANNEL} unified" \
            > /etc/apt/sources.list.d/intel-gpu.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            ocl-icd-libopencl1 \
            libze1; \
        # Intel's apt channel stops at compute-runtime 25.18 with IGC 2.11, built for Ubuntu 24.04. On this
        # Debian 13 base its kernel compiler crashed intermittently (glibc longjmp check, segfaults) whenever
        # OpenVINO compiled a model for the iGPU: five of eight models could not be verified on Intel GPU.
        # Compute-runtime 26.35 with IGC 2.41.5 compiled every model cold and matched the CPU's answers on
        # Quark. IGC 2.x installs into /usr/local/lib, hence ldconfig. The loader (libze1) and the OpenCL
        # ICD loader still come from the channel above.
        COMPUTE_VER=26.35.39758.10; \
        IGC_VER=2.41.5; \
        IGC_BUILD=22716; \
        GMM_VER=22.10.0; \
        COMPUTE_REL="https://github.com/intel/compute-runtime/releases/download/${COMPUTE_VER}"; \
        IGC_REL="https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VER}"; \
        ( cd /tmp \
          && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                 -O "${IGC_REL}/intel-igc-core-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
          && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                 -O "${IGC_REL}/intel-igc-opencl-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
          && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                 -O "${COMPUTE_REL}/intel-opencl-icd_${COMPUTE_VER}-0_amd64.deb" \
          && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                 -O "${COMPUTE_REL}/libze-intel-gpu1_${COMPUTE_VER}-0_amd64.deb" \
          && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                 -O "${COMPUTE_REL}/libigdgmm12_${GMM_VER}_amd64.deb" \
          && echo "0a6e64a663ae65a0fa02d6912ae3b6b37cf85b90c21cc423fd9fef70aaf4f628  intel-igc-core-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" | sha256sum -c - \
          && echo "779e1b9e88098eb25711e9a8f67c2752665bad22f134aa40ed5649f6e1b87058  intel-igc-opencl-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" | sha256sum -c - \
          && echo "61712caaddeba3d38e4f79e2a0fb23fea25596ca2d72c3144c6eea2331ec4301  intel-opencl-icd_${COMPUTE_VER}-0_amd64.deb" | sha256sum -c - \
          && echo "c19a641b953d55aebbf1d51bec364a84bf629f985e02fbbe6dc70224c0e88470  libze-intel-gpu1_${COMPUTE_VER}-0_amd64.deb" | sha256sum -c - \
          && echo "6031a63d6e8a12ce61c14efc15f2c8e727061286e3820b8594e6d00615e04d54  libigdgmm12_${GMM_VER}_amd64.deb" | sha256sum -c - \
          && apt-get install -y --no-install-recommends \
                 "./intel-igc-core-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
                 "./intel-igc-opencl-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
                 "./libigdgmm12_${GMM_VER}_amd64.deb" \
                 "./intel-opencl-icd_${COMPUTE_VER}-0_amd64.deb" \
                 "./libze-intel-gpu1_${COMPUTE_VER}-0_amd64.deb" \
          && rm -f \
                 "/tmp/intel-igc-core-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
                 "/tmp/intel-igc-opencl-2_${IGC_VER}+${IGC_BUILD}_amd64.deb" \
                 "/tmp/libigdgmm12_${GMM_VER}_amd64.deb" \
                 "/tmp/intel-opencl-icd_${COMPUTE_VER}-0_amd64.deb" \
                 "/tmp/libze-intel-gpu1_${COMPUTE_VER}-0_amd64.deb" ); \
        ldconfig; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY requirements*.txt /requirements/
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels,ro \
    pip install --no-cache-dir --no-index --find-links /wheels \
        -r /requirements/requirements-base.txt \
        -r /requirements/requirements-provider-full.txt; \
    rm -rf /requirements

# Create a non-root user and setup directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /data /config /app/data/models && \
    chown -R appuser:appuser /app /data /config

COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser alembic_catalog.ini /app/alembic_catalog.ini
COPY --chown=appuser:appuser download_model.py /app/download_model.py
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser locales /app/locales
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser migrations_catalog /app/migrations_catalog
COPY --chown=appuser:appuser scripts /app/scripts

# Build the seed species catalogue so the split image seeds first start the
# same way the monolith does; an existing empty catalogue is also replaced by
# this seed on upgrade.
RUN python /app/scripts/build_species_catalog_seed.py \
        --reference /app/app/assets/species_reference.db \
        --output /app/app/assets/species_catalog_seed.db && \
    chown appuser:appuser /app/app/assets/species_catalog_seed.db /app/app/assets/species_catalog_seed.db.sha256

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
