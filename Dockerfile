# ── Mythos Local — Docker Image ──────────────────────────────────────
# Fully local, offline AI that lives in your terminal.
# No API keys, no cloud, no limits.
#
# Build:
#   docker build -t mythos .
#
# Run (CPU):
#   docker run -it --rm mythos
#
# Run (GPU — NVIDIA):
#   docker run -it --rm --gpus all mythos
#
# Run with persistent config & models:
#   docker run -it --rm \
#     -v ~/.config/mythos:/root/.config/mythos \
#     -v ./models:/app/models \
#     mythos
#
# Web UI:
#   docker run -it --rm -p 7860:7860 mythos web --port 7860
# ─────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System deps for llama-cpp-python (CPU wheel)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY pyproject.toml ./
COPY requirements.txt ./
RUN pip install --no-cache-dir -e ".[web]" 2>/dev/null || \
    pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

# Copy the full project
COPY . .

# Install the project
RUN pip install --no-cache-dir -e ".[web]" 2>/dev/null || true

# Pre-create common directories
RUN mkdir -p /root/.config/mythos /app/models /app/conversations /app/rag_docs /app/chroma_db

# Default environment
ENV PYTHONUNBUFFERED=1
ENV MYTHOS_HOME=/root/.config/mythos

# ── GPU variant ──────────────────────────────────────────────────────
FROM base AS gpu
# Reinstall llama-cpp-python with CUDA support
RUN CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-cache-dir --force-reinstall \
    llama-cpp-python>=0.2.0 2>/dev/null || true

# ── Final stage ──────────────────────────────────────────────────────
FROM base

# Health check for the API server
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')" || exit 1

EXPOSE 7860

# Default: launch terminal chat. Override with: docker run mythos web
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "chat"]
