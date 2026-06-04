#!/usr/bin/env bash
# Copy everything you already downloaded into a portable folder (USB, another PC, fresh clone).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/offline-bundle}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

copy_tree() {
 local src="$1"
 local rel="$2"
 if [[ -d "$src" ]]; then
 mkdir -p "$DEST/$rel"
 rsync -a "$src/" "$DEST/$rel/"
 echo -e "${GREEN}${NC} $rel"
 return 0
 fi
 return 1
}

copy_file() {
 local src="$1"
 local rel="$2"
 if [[ -f "$src" ]]; then
 mkdir -p "$(dirname "$DEST/$rel")"
 if [[ -L "$src" ]]; then
 src="$(readlink -f "$src" 2>/dev/null || python3 -c "import os; print(os.path.realpath('$src'))")"
 fi
 echo " → $rel ($(du -sh "$src" | cut -f1))"
 rsync -a "$src" "$DEST/$rel"
 echo -e "${GREEN}${NC} $rel"
 return 0
 fi
 return 1
}

echo "==================================================================="
echo " Mythos -- export offline data"
echo "==================================================================="
echo ""
echo "Destination: $DEST"
echo ""

mkdir -p "$DEST"

# --- LLM (largest) ---
MODEL_NAME="Qwen2.5-7B-Instruct-Q4_K_M.gguf"
MODEL_SRC=""
for candidate in \
 "$ROOT/models/$MODEL_NAME" \
 "$HOME/.config/mythos/models/$MODEL_NAME" \
 "$DEST/models/$MODEL_NAME"; do
 if [[ -f "$candidate" ]]; then
 MODEL_SRC="$candidate"
 break
 fi
 if [[ -L "$candidate" ]]; then
 MODEL_SRC="$(readlink -f "$candidate" 2>/dev/null || true)"
 [[ -f "$MODEL_SRC" ]] && break
 MODEL_SRC=""
 fi
done

if [[ -n "$MODEL_SRC" && -f "$MODEL_SRC" ]]; then
 echo "Copying LLM (~4.5 GB)..."
 copy_file "$MODEL_SRC" "models/$MODEL_NAME"
else
 echo -e "${YELLOW} No GGUF model found -- run mythos model download first${NC}"
fi

# --- Embedding model cache (~87 MB) ---
HF_SRC=""
for candidate in \
 "$HOME/.config/mythos/cache/huggingface" \
 "$ROOT/.cache/huggingface"; do
 if [[ -d "$candidate/models--sentence-transformers--all-MiniLM-L6-v2" ]]; then
 HF_SRC="$candidate"
 break
 fi
done
if [[ -n "$HF_SRC" ]]; then
 echo "Copying Hugging Face cache (embeddings)..."
 copy_tree "$HF_SRC" "cache/huggingface"
else
 echo -e "${YELLOW} No embedding cache found (RAG will download once on first use)${NC}"
fi

# --- RAG index (use larger copy) ---
CHROMA_SRC=""
CHROMA_SIZE=0
for candidate in "$ROOT/chroma_db" "$HOME/.config/mythos/chroma_db"; do
 if [[ -d "$candidate" ]]; then
 sz="$(du -sk "$candidate" 2>/dev/null | cut -f1)"
 if [[ "${sz:-0}" -gt "$CHROMA_SIZE" ]]; then
 CHROMA_SRC="$candidate"
 CHROMA_SIZE="$sz"
 fi
 fi
done
if [[ -n "$CHROMA_SRC" ]]; then
 echo "Copying RAG index (chroma_db)..."
 copy_tree "$CHROMA_SRC" "chroma_db"
fi

# --- User config ---
mkdir -p "$DEST/config"
if [[ -f "$HOME/.config/mythos/mythos.yaml" ]]; then
 cp "$HOME/.config/mythos/mythos.yaml" "$DEST/config/mythos.yaml"
 echo -e "${GREEN}${NC} config/mythos.yaml"
elif [[ -f "$ROOT/config.yaml" ]]; then
 cp "$ROOT/config.yaml" "$DEST/config/mythos.yaml"
 echo -e "${GREEN}${NC} config/mythos.yaml (from repo)"
fi
if [[ -f "$HOME/.config/mythos/config.yaml" ]]; then
 cp "$HOME/.config/mythos/config.yaml" "$DEST/config/config.yaml"
 echo -e "${GREEN}${NC} config/config.yaml"
fi

# --- Optional: saved chats ---
if ls "$ROOT/conversations/"*.json &>/dev/null; then
 echo "Copying conversations..."
 copy_tree "$ROOT/conversations" "conversations"
fi

# --- Manifest ---
CREATED="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOTAL="$(du -sh "$DEST" | cut -f1)"
cat > "$DEST/README.txt" << EOF
Mythos offline bundle
Created: $CREATED
Total size: $TOTAL

Restore on a new machine:
 1. Clone Open-Mythos-2 and run ./setup-macos.sh (or ./setup.sh)
 2. ./scripts/mythos-import-data.sh "$(realpath "$DEST" 2>/dev/null || echo "$DEST")"
 3. ./mythos

Contents:
 models/ -- GGUF chat model (do not re-download)
 cache/ -- sentence-transformers embeddings for RAG
 chroma_db/ -- indexed documents (optional)
 config/ -- mythos.yaml + scan registry
 conversations/ -- saved chats (optional)
EOF

echo ""
echo -e "${GREEN}Export complete:${NC} $DEST ($TOTAL)"
echo "Copy this folder to USB or the other computer, then run mythos-import-data.sh"
