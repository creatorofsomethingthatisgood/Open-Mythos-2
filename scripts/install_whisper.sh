#!/usr/bin/env bash
# install_whisper.sh -- Build whisper.cpp with Vulkan backend for AMD GPUs
#
# Usage:
# ./scripts/install_whisper.sh # base.en model (142 MB, fast)
# ./scripts/install_whisper.sh small # small.en model (466 MB, better accuracy)
# ./scripts/install_whisper.sh large # large-v3 model (3 GB, best accuracy)
#
# Prerequisites:
# - Vulkan SDK / Mesa Vulkan drivers (amdvlk or radv)
# - cmake, gcc/gcc-c++ or clang, git
#
# After install, add to config.yaml:
# voice:
# enabled: true
# whisper_bin: "whisper-cli"
# model: "models/ggml-base.en.bin"
#
# Then use /voice in the Open-Mythos-2 terminal UI.

set -euo pipefail

MODEL_SIZE="${1:-base}"
INSTALL_DIR="${HOME}/.local/share/whisper.cpp"
WHISPER_REPO="https://github.com/ggerganov/whisper.cpp"

# Map model size arg to actual model name
case "$MODEL_SIZE" in
 base) GGML_MODEL="ggml-base.en.bin" ;;
 small) GGML_MODEL="ggml-small.en.bin" ;;
 medium) GGML_MODEL="ggml-medium.en.bin" ;;
 large) GGML_MODEL="ggml-large-v3.bin" ;;
 *) echo "Unknown model size: $MODEL_SIZE (use: base, small, medium, large)" >&2; exit 1 ;;
esac

echo "==> whisper.cpp installer for AMD (Vulkan backend)"
echo " Model: $GGML_MODEL"
echo " Install dir: $INSTALL_DIR"
echo ""

# Check prerequisites 

check_cmd() {
 if ! command -v "$1" &>/dev/null; then
 echo "ERROR: $1 not found. Install: $2" >&2
 exit 1
 fi
}

check_cmd git "sudo apt install git"
check_cmd cmake "sudo apt install cmake"

# Check for Vulkan
if ! vulkaninfo &>/dev/null 2>&1; then
 echo "WARNING: vulkaninfo not found or failed."
 echo " For AMD GPUs on Linux, install:"
 echo " sudo apt install mesa-vulkan-drivers vulkan-tools"
 echo " Or for AMDVLK:"
 echo " sudo apt install amdvlk"
 echo ""
 echo "Continuing anyway -- build may fail without Vulkan drivers."
fi

# Clone or update 

if [ -d "$INSTALL_DIR/.git" ]; then
 echo "==> Updating existing whisper.cpp clone..."
 cd "$INSTALL_DIR"
 git pull --ff-only 2>/dev/null || {
 echo "WARNING: git pull failed. Using existing checkout."
 }
else
 echo "==> Cloning whisper.cpp..."
 mkdir -p "$INSTALL_DIR"
 git clone --depth 1 "$WHISPER_REPO" "$INSTALL_DIR"
 cd "$INSTALL_DIR"
fi

# Build with Vulkan 

echo "==> Building whisper.cpp with Vulkan backend (GGML_VULKAN=1)..."
cmake -B build \
 -DGGML_VULKAN=1 \
 -DCMAKE_BUILD_TYPE=Release \
 -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"

cmake --build build --config Release -j"$(nproc 2>/dev/null || echo 4)"

echo "==> Build complete."

# Download model 

MODEL_DIR="$INSTALL_DIR/models"
mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_DIR/$GGML_MODEL" ]; then
 echo "==> Model $GGML_MODEL already exists, skipping download."
else
 echo "==> Downloading $GGML_MODEL..."
 cd "$MODEL_DIR"
 bash "$INSTALL_DIR/models/download-ggml-model.sh" \
 "$(echo "$GGML_MODEL" | sed 's/ggml-//;s/\.bin$//')"
fi

# Install binary to PATH 

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

WHISPER_CLI="$INSTALL_DIR/build/bin/whisper-cli"
if [ ! -f "$WHISPER_CLI" ]; then
 # Some builds put it in bin/Release/
 WHISPER_CLI="$INSTALL_DIR/build/bin/Release/whisper-cli"
fi

if [ -f "$WHISPER_CLI" ]; then
 ln -sf "$WHISPER_CLI" "$BIN_DIR/whisper-cli"
 echo "==> Linked whisper-cli -> $BIN_DIR/whisper-cli"
else
 echo "ERROR: whisper-cli binary not found after build." >&2
 echo " Looked in: $INSTALL_DIR/build/bin/" >&2
 exit 1
fi

# Verify 

echo ""
echo "==> Verification:"
echo " whisper-cli: $(command -v whisper-cli 2>/dev/null || echo 'NOT IN PATH')"
echo " Model: $MODEL_DIR/$GGML_MODEL"
echo " Size: $(du -h "$MODEL_DIR/$GGML_MODEL" | cut -f1)"
echo ""

# Quick smoke test
if command -v whisper-cli &>/dev/null; then
 echo " whisper-cli --help (first 3 lines):"
 whisper-cli --help 2>&1 | head -3 || true
fi

echo ""
echo "==> Done! Update your config.yaml:"
echo ""
echo " voice:"
echo " enabled: true"
echo " model: \"$MODEL_DIR/$GGML_MODEL\""
echo ""
echo " Then use /voice in the terminal UI."
