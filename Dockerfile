# syntax=docker/dockerfile:1.6
#
# filefy - Web-Based File Manager
# Multi-stage Dockerfile producing a small, production-ready image.
#

# ---------- Builder stage ----------
FROM python:3.12-slim AS builder

ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="filefy" \
      org.opencontainers.image.description="FileFy - Modern Cloud File Manager" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Pymmdrza/filefy"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project sources and build a wheel
COPY . /build
RUN pip install --upgrade pip build \
    && python -m build --wheel --outdir /build/dist

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FILEFY_HOST=0.0.0.0 \
    FILEFY_PORT=5000 \
    FILEFY_DIR=/data

# Create non-root user and the data directory
RUN groupadd --system --gid 1000 filefy \
    && useradd --system --uid 1000 --gid filefy --home-dir /home/filefy --create-home filefy \
    && mkdir -p /data \
    && chown -R filefy:filefy /data

# Install the wheel built in the previous stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install /tmp/*.whl \
    && rm -f /tmp/*.whl

# Pre-install the 'cloudflared' binary using the bundled installer so the
# --tunnel feature works out-of-the-box without any manual intervention
# from the user. The installer uses the standard library only, so no
# extra Python packages are required at this point.
RUN filefy-install-cloudflared --no-package-manager \
    && cloudflared --version

WORKDIR /data
USER filefy

EXPOSE 5000

# Simple healthcheck: ensure the HTTP server is responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:'+os.environ.get('FILEFY_PORT','5000')+'/'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=3).status < 500 else 1)" || exit 1

# Use the shell form so environment variables are expanded at runtime,
# while still allowing extra arguments via `docker run ... <args>`.
ENTRYPOINT ["sh", "-c", "exec filefy --host \"$FILEFY_HOST\" --port \"$FILEFY_PORT\" --directory \"$FILEFY_DIR\" \"$@\"", "--"]
