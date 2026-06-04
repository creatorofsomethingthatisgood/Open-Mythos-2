#!/bin/bash
set -e

# macOS: delegate to dedicated setup script
if [[ "$(uname)" == "Darwin" ]]; then
 SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
 exec "$SCRIPT_DIR/setup-macos.sh" "$@"
fi

echo "==================================================================="
echo " Mythos Local - High-Quality Local LLM for AMD/Fedora Linux"
echo "==================================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Fedora
if [ ! -f /etc/fedora-release ]; then
 echo -e "${YELLOW}Warning: This script is optimized for Fedora Linux${NC}"
 read -p "Continue anyway? (y/n) " -n 1 -r
 echo
 if [[ ! $REPLY =~ ^[Yy]$ ]]; then
 exit 1
 fi
fi

# Check for Python 3
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
 echo "Python 3 not found. Installing..."
 sudo dnf install -y python3 python3-pip python3-devel
else
 echo -e "${GREEN} Python 3 found${NC}"
fi

# Install system dependencies
echo ""
echo "Installing system dependencies..."
sudo dnf install -y \
 gcc \
 gcc-c++ \
 make \
 cmake \
 git \
 vulkan-loader \
 vulkan-headers \
 mesa-vulkan-drivers \
 openblas-devel \
 libstdc++-devel \
 || echo -e "${YELLOW}Some packages may have failed, continuing...${NC}"

echo -e "${GREEN} System dependencies installed${NC}"

# Create virtual environment
echo ""
echo "Creating Python virtual environment..."
if [ -d "venv" ]; then
 echo "Virtual environment already exists, skipping..."
else
 python3 -m venv venv
 echo -e "${GREEN} Virtual environment created${NC}"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/install-common.sh
source "$SCRIPT_DIR/scripts/install-common.sh"

# Upgrade pip (skip if already recent -- saves a network round-trip)
if python3 -c "import pip; from packaging.version import Version; assert Version(pip.__version__) >= Version('23')" 2>/dev/null; then
 echo -e "${GREEN} pip is up to date${NC}"
else
 echo "Upgrading pip..."
 pip install --upgrade pip setuptools wheel
fi

VULKAN_SUCCESS=0

if llama_cpp_import_ok; then
 echo -e "${GREEN} llama-cpp-python already installed (skipping rebuild)${NC}"
 VULKAN_SUCCESS=1
else
 echo ""
 echo "==================================================================="
 echo " Installing llama-cpp-python (first run only)..."
 echo "==================================================================="

 # Try prebuilt wheel first -- much faster than compiling from source
 echo "Trying prebuilt Vulkan wheel..."
 if pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan 2>/dev/null && llama_cpp_import_ok; then
 echo -e "${GREEN} Prebuilt Vulkan wheel installed${NC}"
 VULKAN_SUCCESS=1
 fi

 if [ $VULKAN_SUCCESS -eq 0 ]; then
 # Try CPU prebuilt wheel before compiling from source
 echo "Trying prebuilt CPU wheel..."
 if pip install llama-cpp-python 2>/dev/null && llama_cpp_import_ok; then
 echo -e "${YELLOW} Prebuilt CPU wheel installed (no GPU accel)${NC}"
 echo -e "${YELLOW}Note: Rebuild with Vulkan for GPU speed: CMAKE_ARGS='-DGGML_VULKAN=on' pip install llama-cpp-python --no-cache-dir --force-reinstall${NC}"
 else
 # Last resort: compile from source with Vulkan
 echo "Compiling from source with Vulkan..."
 if CMAKE_ARGS="-DGGML_VULKAN=on" pip install llama-cpp-python --no-cache-dir 2>&1 | tee /tmp/vulkan_build.log; then
 if ! grep -q "error" /tmp/vulkan_build.log; then
 echo -e "${GREEN} Vulkan backend compiled successfully${NC}"
 VULKAN_SUCCESS=1
 fi
 fi

 if [ $VULKAN_SUCCESS -eq 0 ]; then
 echo -e "${RED} Vulkan build failed${NC}"
 echo "Falling back to OpenBLAS (CPU-only) compile..."
 pip uninstall -y llama-cpp-python 2>/dev/null || true
 CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python --no-cache-dir
 echo -e "${GREEN} OpenBLAS (CPU) backend installed${NC}"
 echo -e "${YELLOW}Note: Running on CPU only. Performance will be slower.${NC}"
 fi
 fi
 fi
fi

install_mythos_python_deps
run_mythos_init

# Create directory structure
echo ""
echo "Creating project directories..."
mkdir -p models prompts rag_docs conversations benchmarks lora
touch models/.gitkeep
touch rag_docs/.gitkeep
touch conversations/.gitkeep
touch benchmarks/.gitkeep
touch lora/.gitkeep
echo -e "${GREEN} Project directories created${NC}"

# Create prompt templates if they don't exist
echo "Creating default prompt templates..."
if [ ! -f "prompts/default.txt" ]; then
 cat > prompts/default.txt << 'EOF'
You are Mythos, an advanced AI assistant with extraordinary capabilities in reasoning, creativity, analysis, and communication. You approach every task with depth, nuance, and precision.

CORE BEHAVIORS:
- Think deeply before responding. Use internal reasoning chains.
- When solving problems, break them into steps and validate each step.
- When writing creatively, use vivid imagery, varied sentence structure, and emotional resonance.
- When coding, write clean, commented, production-quality code.
- When analyzing, consider multiple perspectives and edge cases.
- Acknowledge uncertainty honestly rather than fabricating information.
- Adapt your communication style to match the user's needs.

REASONING FRAMEWORK:
1. Understand the request fully before beginning
2. Consider what approach will yield the best result
3. Execute with attention to detail
4. Review your output for accuracy and completeness
5. Present your response clearly and structured

You are not just an assistant - you are a thinking partner who elevates every interaction through the quality of your engagement.
EOF
fi

# Ask user if they want to download the model now
echo ""
echo "==================================================================="
echo " Model Download"
echo "==================================================================="
echo ""
echo "The default model (Qwen2.5-7B-Instruct-Q4_K_M) is approximately 4.5GB."
echo "This download may take some time depending on your connection."
echo ""
read -p "Download model now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
 echo "Downloading default model..."
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
 print('You can download it later with: python3 main.py --mode download')
"
else
 echo -e "${YELLOW}Skipping model download.${NC}"
 echo "You can download it later with: python3 main.py --mode download"
fi

# Run a quick test
echo ""
echo "==================================================================="
echo " Testing Installation"
echo "==================================================================="
echo ""
if [ -f "models/qwen2.5-7b-instruct-q4_k_m.gguf" ] || [ -f "models/mistral-7b-instruct-v0.3.Q4_K_M.gguf" ]; then
 echo "Running quick inference test..."
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
 print('You may need to check your configuration.')
"
else
 echo -e "${YELLOW}No model found, skipping inference test.${NC}"
fi

# Final instructions
echo ""
echo "==================================================================="
echo " Setup Complete!"
echo "==================================================================="
echo ""
echo "To get started:"
echo ""
echo " 1. Activate the virtual environment:"
echo " source venv/bin/activate"
echo ""
echo " 2. Run chat (no need to activate venv):"
echo " ./mythos"
echo ""
echo " 3. Or run the web interface:"
echo " ./mythos web"
echo ""
echo " 4. Run benchmarks:"
echo " python3 main.py --mode benchmark"
echo ""
echo " 5. For help:"
echo " python3 main.py --help"
echo ""
echo "==================================================================="
echo ""
if [ $VULKAN_SUCCESS -eq 1 ]; then
 echo -e "${GREEN}GPU acceleration (Vulkan) is enabled!${NC}"
else
 echo -e "${YELLOW}Running in CPU mode. For better performance, ensure Vulkan drivers are installed.${NC}"
fi
echo ""
chmod +x "$SCRIPT_DIR/mythos" 2>/dev/null || true
print_mythos_usage
echo "Happy chatting with Mythos!"
echo ""
