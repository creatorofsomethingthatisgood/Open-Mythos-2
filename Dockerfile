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
# - HEALTHCHECK probes /api/health every 30s (active in --mode web)
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
#
# Pull llama-cpp-python from abetlen's prebuilt CPU wheel index instead of
# compiling from source. Source-builds the CPU-only wheel take 15-25 min,
# burn the CPU at full parallelism, and have been observed to fail with a
# g++ ICE on heat-stressed build hosts. The prebuilt index serves
# manylinux wheels for python 3.10/3.11/3.12 directly. PyPI is kept as
# the primary index so every other dep resolves normally.
COPY requirements.txt pyproject.toml ./
RUN pip install \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
        -r requirements.txt

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
    MYTHOS_HOME=/home/mythos/.config/mythos \
    MYTHOS_HOST=127.0.0.1

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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health')" || exit 1

# Default: terminal chat. Override on `docker run`, for example:
#   docker run -it --rm -p 7860:7860 mythos --mode web
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "chat"]
