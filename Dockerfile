# syntax=docker/dockerfile:1.7

# node:22 (LTS) satisfies the vite 8 / vitest 4 engine floor (^20.19 || >=22.12).
FROM node:22 AS ui-builder

WORKDIR /ui

ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ARG APP_BRANCH=unknown
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}
ENV APP_BRANCH=${APP_BRANCH}

COPY apps/ui/package.json apps/ui/package-lock.json ./
RUN set -eux; \
    npm ci --include=dev --include=optional --legacy-peer-deps; \
    if ! node -e "require('lightningcss')"; then \
        npm ci --include=dev --include=optional --legacy-peer-deps; \
    fi; \
    node -e "require('lightningcss')"

COPY apps/ui/ .
RUN npm run build

FROM python:3.12-slim AS backend-builder

WORKDIR /app

ARG RUNTIME_FLAVOR=full
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --chmod=0755 docker/runtime-flavor.sh /usr/local/bin/yawamf-runtime-flavor
COPY backend/requirements*.txt /requirements/
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN runtime_arch="${TARGETARCH:-amd64}"; \
    provider_requirements="$(yawamf-runtime-flavor requirements "$RUNTIME_FLAVOR" "$runtime_arch")"; \
    pip wheel --no-cache-dir --wheel-dir /wheels \
        -r /requirements/requirements-base.txt \
        -r "/requirements/$provider_requirements"

FROM python:3.12-slim

WORKDIR /app

ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ARG APP_BRANCH=unknown
ARG TARGETARCH
ARG RUNTIME_FLAVOR=full
ARG INTEL_GPU_APT_CHANNEL=noble/lts
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}
ENV APP_BRANCH=${APP_BRANCH}
ENV YAWAMF_IMAGE_FLAVOR=${RUNTIME_FLAVOR}

LABEL io.yawamf.image.flavor="${RUNTIME_FLAVOR}"

COPY --chmod=0755 docker/runtime-flavor.sh /usr/local/bin/yawamf-runtime-flavor

RUN set -eux; \
    runtime_arch="${TARGETARCH:-amd64}"; \
    yawamf-runtime-flavor validate "$RUNTIME_FLAVOR" "$runtime_arch"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gpg \
        libgl1 \
        libglib2.0-0 \
        nginx \
        sqlite3 \
        tini \
        zlib1g; \
    if yawamf-runtime-flavor needs-intel-runtime "$RUNTIME_FLAVOR" "$runtime_arch"; then \
        install -d -m 0755 /etc/apt/keyrings; \
        curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 https://repositories.intel.com/gpu/intel-graphics.key \
            | gpg --dearmor -o /etc/apt/keyrings/intel-graphics.gpg; \
        echo "deb [signed-by=/etc/apt/keyrings/intel-graphics.gpg arch=amd64] https://repositories.intel.com/gpu/ubuntu ${INTEL_GPU_APT_CHANNEL} unified" \
            > /etc/apt/sources.list.d/intel-gpu.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            intel-opencl-icd \
            libze-intel-gpu1 \
            libze1 \
            ocl-icd-libopencl1; \
        # Intel NPU ("AI Boost") driver for the OpenVINO `intel_npu` provider on
        # Core Ultra. These are NOT in the intel-graphics apt repo, so install the
        # release .debs (firmware + Level-Zero driver + compiler). This pinned version
        # is hardware-validated on Quark with OpenVINO 2026.2.1. Checksums bind the
        # image to the reviewed assets; an incomplete Intel runtime fails the build.
        NPU_VER=1.17.0.20250508-14912879441; \
        NPU_REL=https://github.com/intel/linux-npu-driver/releases/download/v1.17.0; \
        ( cd /tmp \
          && for p in intel-fw-npu intel-driver-compiler-npu intel-level-zero-npu; do \
                 curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
                     -O "${NPU_REL}/${p}_${NPU_VER}_ubuntu24.04_amd64.deb"; \
             done \
          && echo "cebbac7bdb56eb72529b8060bb1601afdcd4e90f2e5c29018b5ceaff98b7c63c  intel-fw-npu_${NPU_VER}_ubuntu24.04_amd64.deb" | sha256sum -c - \
          && echo "24309e17063e94729330ae9c02c5f2ea8ca5c27cdb067303e4e26ad1f4656a13  intel-driver-compiler-npu_${NPU_VER}_ubuntu24.04_amd64.deb" | sha256sum -c - \
          && echo "07ee5332d0523661f5b3cec69593197fecc95439c8a9a401905e05cb7690097b  intel-level-zero-npu_${NPU_VER}_ubuntu24.04_amd64.deb" | sha256sum -c - \
          && apt-get install -y --no-install-recommends \
                 ./intel-fw-npu_*.deb \
                 ./intel-driver-compiler-npu_*.deb \
                 ./intel-level-zero-npu_*.deb \
          && rm -f /tmp/*.deb ); \
    fi; \
    rm -rf /var/lib/apt/lists/*

# CUDA/cuDNN userspace for ONNX Runtime is installed by the CUDA/full provider requirements.
# The host still needs NVIDIA Container Toolkit (or equivalent) to provide GPU passthrough.

COPY backend/requirements*.txt /requirements/
RUN --mount=type=bind,from=backend-builder,source=/wheels,target=/wheels,ro \
    runtime_arch="${TARGETARCH:-amd64}"; \
    provider_requirements="$(yawamf-runtime-flavor requirements "$RUNTIME_FLAVOR" "$runtime_arch")"; \
    pip install --no-cache-dir --no-index --find-links /wheels \
        -r /requirements/requirements-base.txt \
        -r "/requirements/$provider_requirements"; \
    rm -rf /requirements

RUN useradd -m -u 1000 appuser && \
    mkdir -p /config /data /app/data/models && \
    chown -R appuser:appuser /app /config /data /usr/share/nginx/html

COPY --from=ui-builder /ui/dist /usr/share/nginx/html
COPY backend/alembic.ini /app/alembic.ini
COPY backend/download_model.py /app/download_model.py
COPY backend/app /app/app
COPY backend/scripts /app/scripts
COPY backend/locales /app/locales
COPY backend/migrations /app/migrations
COPY docker/monolith/nginx-main.conf /etc/nginx/nginx.conf
COPY docker/monolith/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/monolith/entrypoint.sh /usr/local/bin/yawamf-entrypoint.sh
COPY docker/monolith/healthcheck.sh /usr/local/bin/yawamf-healthcheck.sh

# Every image must be able to classify on first start, including an offline Pi.
# Pin the upstream Coral test-data revision and verify every downloaded byte.
# The sidecar is checked in and contract-tested against the canonical registry,
# so a mutable GitHub Release asset cannot make an otherwise reproducible build fail.
RUN set -eux; \
    coral_revision=104342d2d3480b3e66203073dac24f4e2dbb4c41; \
    coral_base="https://raw.githubusercontent.com/google-coral/test_data/${coral_revision}"; \
    curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
        -o /app/app/assets/model.tflite \
        "${coral_base}/mobilenet_v2_1.0_224_inat_bird_quant.tflite"; \
    curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 \
        -o /app/app/assets/labels.txt \
        "${coral_base}/inat_bird_labels.txt"; \
    echo "350fcd8cf1df1560060d464595dfed8b174b05792788052896004848d9ad04f9  /app/app/assets/model.tflite" | sha256sum -c -; \
    echo "a16108dfe3f8daff015b87a97ab6a17e717b9b1bccd719f6d8f747746d7b9277  /app/app/assets/labels.txt" | sha256sum -c -

ENV DB_PATH=/data/speciesid.db
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache
ENV XDG_CONFIG_HOME=/tmp/.config
ENV XDG_DATA_HOME=/tmp/.local/share
ENV NGINX_PORT=8080

RUN chown -R appuser:appuser /app /usr/share/nginx/html && \
    chmod -R go+rX /app /usr/share/nginx/html && \
    chmod 0644 /etc/nginx/nginx.conf && \
    chmod 0644 /etc/nginx/conf.d/default.conf && \
    chmod 0755 /usr/local/bin/yawamf-entrypoint.sh /usr/local/bin/yawamf-healthcheck.sh

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=10s --start-period=15s --retries=6 \
    CMD /usr/local/bin/yawamf-healthcheck.sh || exit 1

ENTRYPOINT ["tini", "--", "/usr/local/bin/yawamf-entrypoint.sh"]
