# syntax=docker/dockerfile:1.7
# ── Mythos Local — Docker Image ──────────────────────────────────────
# Fully local, offline AI in your terminal. No API keys, no cloud.
#
# Build:
#   docker build -t mythos .
#
# Run (terminal chat — REQUIRES -it):
#   docker run -it --rm mythos
#
# Run (web UI on http://localhost:7860):
#   docker run -it --rm -p 7860:7860 mythos --mode web
#
# Persistent config and models (recommended; volumes survive --rm):
#   docker run -it --rm \
#     -v "$HOME/.config/mythos:/home/mythos/.config/mythos" \
#     -v "$(pwd)/models:/app/models" \
#     mythos
#
# Notes:
#   - Runs as a non-root user (uid 1000, gid 1000). If your host uid
#     differs, pass `--user $(id -u):$(id -g)` so mounted volumes stay
#     writable.
#   - This image is CPU-only. GPU support needs a CUDA base image
#     (e.g. nvidia/cuda:12.4.1-devel-ubuntu22.04) and rebuilding
#     llama-cpp-python with -DGGML_CUDA=on — out of scope here.
#   - No HEALTHCHECK is defined: the default entrypoint is interactive
#     and serves no HTTP endpoint. Add one in your compose /
#     orchestration layer if you run --mode web in production.
# ─────────────────────────────────────────────────────────────────────

ARG PYTHON_VERSION=3.11.9
ARG DEBIAN_RELEASE=bookworm

# ── Builder stage: full toolchain for compiling llama-cpp-python ─────
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

# Self-contained venv at a fixed path so we can copy it whole into runtime.
RUN python -m venv /opt/mythos-venv
ENV PATH="/opt/mythos-venv/bin:${PATH}"
RUN pip install --upgrade pip setuptools wheel

WORKDIR /app

# Dependency layer: only invalidated when manifests change.
COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

# Source layer.
COPY . .

# Install the project itself into the venv. --no-deps because the
# previous step already installed every transitive dependency.
RUN pip install --no-deps ".[web]"

# ── Runtime stage: slim image, no build tools ────────────────────────
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/mythos-venv/bin:${PATH}" \
    MYTHOS_HOME=/home/mythos/.config/mythos

# libgomp1 is needed at runtime by llama-cpp-python (OpenMP threading).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. UID 1000 matches the default user on most Linux hosts,
# which keeps mounted volumes writable without --user juggling.
RUN groupadd --gid 1000 mythos \
    && useradd --uid 1000 --gid mythos --create-home --shell /bin/bash mythos

# Copy the prebuilt venv and the project source from the builder.
COPY --from=builder /opt/mythos-venv /opt/mythos-venv
COPY --from=builder --chown=mythos:mythos /app /app

WORKDIR /app

# Directories the app writes to. Pre-create + chown so a non-root user
# can use them without needing write access to /app at runtime.
RUN mkdir -p \
        /home/mythos/.config/mythos \
        /app/models \
        /app/conversations \
        /app/rag_docs \
        /app/chroma_db \
    && chown -R mythos:mythos /home/mythos /app

USER mythos

EXPOSE 7860

# Default: terminal chat. Override on `docker run`, for example:
#   docker run -it --rm -p 7860:7860 mythos --mode web
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "chat"]
