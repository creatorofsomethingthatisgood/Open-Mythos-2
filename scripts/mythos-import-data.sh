#!/usr/bin/env bash
# Restore a portable bundle into ~/.config/mythos (after fresh setup).
set -euo pipefail

SRC="${1:-}"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "Usage: $0 /path/to/offline-bundle"
  echo "  Default: ./offline-bundle in the repo"
  exit 1
fi

SRC="$(cd "$SRC" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${MYTHOS_HOME:-$HOME/.config/mythos}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "==================================================================="
echo "  Mythos — import offline data"
echo "==================================================================="
echo ""
echo "From: $SRC"
echo "To:   $HOME_DIR"
echo ""

mkdir -p "$HOME_DIR"/{models,cache,huggingface,chroma_db,conversations,rag_docs}

if [[ -d "$SRC/models" ]]; then
  echo "Installing models..."
  rsync -a "$SRC/models/" "$HOME_DIR/models/"
  echo -e "${GREEN}✓${NC} models"
fi

if [[ -d "$SRC/cache/huggingface" ]]; then
  echo "Installing embedding cache..."
  mkdir -p "$HOME_DIR/cache"
  rsync -a "$SRC/cache/huggingface/" "$HOME_DIR/cache/huggingface/"
  echo -e "${GREEN}✓${NC} cache/huggingface"
fi

if [[ -d "$SRC/chroma_db" ]]; then
  echo "Installing RAG index..."
  rsync -a "$SRC/chroma_db/" "$HOME_DIR/chroma_db/"
  echo -e "${GREEN}✓${NC} chroma_db"
fi

if [[ -f "$SRC/config/mythos.yaml" ]]; then
  cp "$SRC/config/mythos.yaml" "$HOME_DIR/mythos.yaml"
  echo -e "${GREEN}✓${NC} mythos.yaml"
fi

if [[ -f "$SRC/config/config.yaml" ]]; then
  cp "$SRC/config/config.yaml" "$HOME_DIR/config.yaml"
  echo -e "${GREEN}✓${NC} config.yaml"
fi

if [[ -d "$SRC/conversations" ]]; then
  rsync -a "$SRC/conversations/" "$ROOT/conversations/"
  mkdir -p "$HOME_DIR/conversations"
  rsync -a "$SRC/conversations/" "$HOME_DIR/conversations/"
  echo -e "${GREEN}✓${NC} conversations"
fi

# Ensure paths in mythos.yaml point at user home (not old machine paths)
if [[ -f "$HOME_DIR/mythos.yaml" ]]; then
  python3 << PY
from pathlib import Path
import yaml

home = Path("$HOME_DIR")
path = home / "mythos.yaml"
cfg = yaml.safe_load(path.read_text()) or {}
model = cfg.setdefault("model", {})
name = model.get("filename", "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
model["path"] = str(home / "models" / name)
rag = cfg.setdefault("rag", {})
rag["persist_dir"] = str(home / "chroma_db")
rag["hf_cache_dir"] = str(home / "cache" / "huggingface")
mem = cfg.setdefault("memory", {})
mem["conversations_dir"] = str(home / "conversations")
path.write_text(yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False))
print("Patched mythos.yaml paths for this machine")
PY
else
  echo -e "${YELLOW}No mythos.yaml in bundle — run: ./mythos init${NC}"
fi

echo ""
echo -e "${GREEN}Import complete.${NC} Start chat: cd \"$ROOT\" && ./mythos"
