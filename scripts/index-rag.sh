#!/usr/bin/env bash
# Index documents into Mythos RAG (ChromaDB).
# Usage:
#   ./scripts/index-rag.sh              # uses rag.docs_dir from config.yaml
#   ./scripts/index-rag.sh /path/to/code
#   ./scripts/index-rag.sh ~/projects/myapp

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCS_PATH="${1:-}"

if [[ -n "$DOCS_PATH" ]]; then
  if [[ ! -d "$DOCS_PATH" ]]; then
    echo "Not a directory: $DOCS_PATH" >&2
    exit 1
  fi
  echo "Exploring: $DOCS_PATH"
  python main.py --mode rag-explore --path "$DOCS_PATH"
  echo ""
  echo "Indexing: $DOCS_PATH"
  python main.py --mode rag-index --path "$DOCS_PATH"
else
  DOCS_DIR="$(python -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('rag',{}).get('docs_dir','rag_docs'))")"
  if [[ ! -d "$DOCS_DIR" ]]; then
    echo "Missing $DOCS_DIR/ -- create it, copy docs, or pass a path:" >&2
    echo "  ./scripts/index-rag.sh /path/to/your/code" >&2
    exit 1
  fi
  python main.py --mode rag-explore
  echo ""
  python main.py --mode rag-index
fi

echo ""
echo "Done. Start chat and enable RAG:"
echo "  python main.py --mode chat"
echo "  /rag on"
