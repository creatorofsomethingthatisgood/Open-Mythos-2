#!/bin/bash
set -e

echo "==================================================================="
echo " Mythos Local - macOS Setup (Apple Silicon / Intel)"
echo "==================================================================="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ "$(uname)" != "Darwin" ]]; then
 echo -e "${RED}This script is for macOS only. Use ./setup.sh on Linux.${NC}"
 exit 1
fi

ARCH="$(uname -m)"
echo "Detected: macOS $(sw_vers -productVersion) ($ARCH)"
echo ""

# Check for Python 3
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
 echo -e "${RED}Python 3 not found.${NC}"
 echo "Install with Homebrew: brew install python@3.13"
 exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo -e "${GREEN} Python $PYTHON_VERSION found${NC}"

# Install build dependencies via Homebrew if available
if command -v brew &> /dev/null; then
 echo ""
 echo "Installing build dependencies via Homebrew..."
 brew install cmake 2>/dev/null || brew upgrade cmake 2>/dev/null || true
 echo -e "${GREEN} Build tools ready${NC}"
else
 echo -e "${YELLOW}Homebrew not found. Using system tools.${NC}"
 echo "If the Metal build fails, install Homebrew and run: brew install cmake"
fi

# Recreate venv if it was created on another OS or Python version
RECREATE_VENV=0
if [ -d "venv" ]; then
 if [ ! -x "venv/bin/python" ] && [ ! -x "venv/bin/python3" ]; then
 echo -e "${YELLOW}Existing venv is from another platform -- recreating...${NC}"
 RECREATE_VENV=1
 elif [ -f "venv/pyvenv.cfg" ] && grep -q "/home/" venv/pyvenv.cfg 2>/dev/null; then
 echo -e "${YELLOW}Existing venv was created on Linux -- recreating for macOS...${NC}"
 RECREATE_VENV=1
 else
 echo "Virtual environment already exists."
 fi
fi

if [ $RECREATE_VENV -eq 1 ]; then
 rm -rf venv
fi

if [ ! -d "venv" ]; then
 echo ""
 echo "Creating Python virtual environment..."
 python3 -m venv venv
 echo -e "${GREEN} Virtual environment created${NC}"
fi

source venv/bin/activate

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/install-common.sh
source "$SCRIPT_DIR/scripts/install-common.sh"

echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

METAL_SUCCESS=0

if llama_cpp_import_ok; then
 echo -e "${GREEN} llama-cpp-python already installed (skipping rebuild)${NC}"
 if [[ "$ARCH" == "arm64" ]]; then
 METAL_SUCCESS=1
 fi
else
 echo ""
 echo "==================================================================="
 echo " Building llama-cpp-python with Metal GPU support..."
 echo " (First run only -- may take several minutes)"
 echo "==================================================================="
 echo ""

 if [[ "$ARCH" == "arm64" ]]; then
 echo "Attempting Metal build for Apple Silicon GPU acceleration..."
 if CMAKE_ARGS="-DGGML_METAL=on -DGGML_METAL_EMBED_LIBRARY=ON" \
 pip install llama-cpp-python --no-cache-dir 2>&1 | tee /tmp/metal_build.log; then
 if grep -qi "error" /tmp/metal_build.log; then
 echo -e "${YELLOW}Metal build completed with warnings -- trying prebuilt wheel...${NC}"
 pip uninstall -y llama-cpp-python 2>/dev/null || true
 pip install llama-cpp-python --no-cache-dir && METAL_SUCCESS=1
 else
 echo -e "${GREEN} Metal backend installed successfully${NC}"
 METAL_SUCCESS=1
 fi
 else
 echo -e "${YELLOW}Metal build failed -- trying prebuilt wheel...${NC}"
 pip install llama-cpp-python --no-cache-dir && METAL_SUCCESS=1
 fi
 else
 echo "Intel Mac detected -- installing CPU-optimized build..."
 pip install llama-cpp-python --no-cache-dir
 METAL_SUCCESS=0
 fi
fi

install_mythos_python_deps
run_mythos_init

echo ""
echo "Creating project directories..."
mkdir -p models prompts rag_docs conversations benchmarks lora
touch models/.gitkeep rag_docs/.gitkeep conversations/.gitkeep benchmarks/.gitkeep lora/.gitkeep
echo -e "${GREEN} Project directories created${NC}"

# Model download prompt
echo ""
echo "==================================================================="
echo " Model Download"
echo "==================================================================="
echo ""
USER_MODEL="$HOME/.config/mythos/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
if [ -f "$USER_MODEL" ] || [ -f "models/Qwen2.5-7B-Instruct-Q4_K_M.gguf" ]; then
 echo -e "${GREEN} Default model already present${NC}"
else
 echo "The default model (Qwen2.5-7B-Instruct-Q4_K_M) is approximately 4.5GB."
 read -p "Download model now? (y/n) " -n 1 -r
 echo
 if [[ $REPLY =~ ^[Yy]$ ]]; then
 python3 -c "
import sys
sys.path.insert(0, '.')
from engine.model_manager import ModelManager
manager = ModelManager()
try:
 manager.download_default()
 print('\n Model downloaded successfully')
except Exception as e:
 print(f'\n Model download failed: {e}')
 print('Download later with: ./mythos model download')
"
 else
 echo -e "${YELLOW}Skipping model download.${NC}"
 echo "Download later with: ./mythos model download"
 fi
fi

# Quick inference test
echo ""
echo "==================================================================="
echo " Testing Installation"
echo "==================================================================="
echo ""

if ls "$HOME/.config/mythos/models/"*.gguf models/*.gguf 2>/dev/null | head -1 | grep -q .; then
 python3 -c "
import sys
sys.path.insert(0, '.')
from engine.inference import InferenceEngine
try:
 engine = InferenceEngine()
 print('Engine loaded successfully!')
 result = engine.generate('Say hello in one short sentence.', max_tokens=30)
 print(f'Test response: {result}')
 print('\n Inference test passed!')
except Exception as e:
 print(f'\n Test failed: {e}')
 print('Check mythos.log for details.')
"
else
 echo -e "${YELLOW}No model found, skipping inference test.${NC}"
fi

echo ""
echo "==================================================================="
echo " Setup Complete!"
echo "==================================================================="
echo ""
chmod +x "$SCRIPT_DIR/mythos" 2>/dev/null || true
print_mythos_usage
if [[ "$ARCH" == "arm64" && $METAL_SUCCESS -eq 1 ]]; then
 echo -e "${GREEN}Apple GPU acceleration (Metal) is enabled!${NC}"
else
 echo -e "${YELLOW}Running in CPU mode.${NC}"
fi
echo ""
