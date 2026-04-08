FROM node:20 AS ui-builder

WORKDIR /ui

ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ARG APP_BRANCH=unknown
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}
ENV APP_BRANCH=${APP_BRANCH}

COPY apps/ui/package.json apps/ui/package-lock.json ./
RUN npm install --legacy-peer-deps

COPY apps/ui/ .
RUN npm run build

FROM python:3.12-slim AS backend-builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ARG APP_BRANCH=unknown
ARG INTEL_GPU_APT_CHANNEL=noble/lts
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}
ENV APP_BRANCH=${APP_BRANCH}

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gpg \
        libgl1 \
        libglib2.0-0 \
        nginx \
        sqlite3 \
        tini; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL --retry 5 --retry-delay 2 https://repositories.intel.com/gpu/intel-graphics.key \
        | gpg --dearmor -o /etc/apt/keyrings/intel-graphics.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/intel-graphics.gpg arch=amd64] https://repositories.intel.com/gpu/ubuntu ${INTEL_GPU_APT_CHANNEL} unified" \
        > /etc/apt/sources.list.d/intel-gpu.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        intel-opencl-icd \
        libze-intel-gpu1 \
        libze1 \
        ocl-icd-libopencl1; \
    rm -rf /var/lib/apt/lists/*

# CUDA/cuDNN userspace for ONNX Runtime is installed via backend/requirements.txt.
# The host still needs NVIDIA Container Toolkit (or equivalent) to provide GPU passthrough.

COPY --from=backend-builder /wheels /wheels
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --find-links /wheels -r /app/requirements.txt

RUN useradd -m -u 1000 appuser && \
    mkdir -p /config /data /app/data/models && \
    chown -R appuser:appuser /app /config /data /usr/share/nginx/html

COPY --from=ui-builder /ui/dist /usr/share/nginx/html
COPY backend/alembic.ini /app/alembic.ini
COPY backend/download_model.py /app/download_model.py
COPY backend/app /app/app
COPY backend/locales /app/locales
COPY backend/migrations /app/migrations
COPY docker/monolith/nginx-main.conf /etc/nginx/nginx.conf
COPY docker/monolith/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/monolith/entrypoint.sh /usr/local/bin/yawamf-entrypoint.sh
COPY docker/monolith/healthcheck.sh /usr/local/bin/yawamf-healthcheck.sh

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
