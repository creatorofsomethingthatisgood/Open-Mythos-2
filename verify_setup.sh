#!/bin/bash
# Comprehensive setup verification script

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           MYTHOS LOCAL - SETUP VERIFICATION                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check we're in the right directory
if [ ! -f "config.yaml" ]; then
    echo "❌ ERROR: config.yaml not found in current directory"
    echo "   Please run this from the project root:"
    echo "   cd ~/mythos_local/amd-vulkan-llm-project"
    exit 1
fi

echo "✓ Found config.yaml in current directory"
echo ""

# Check virtual environment
if [ ! -d "venv" ]; then
    echo "❌ ERROR: Virtual environment not found"
    echo "   Please run ./setup.sh first"
    exit 1
fi

echo "✓ Virtual environment exists"
echo ""

# Activate venv
source venv/bin/activate

echo "✓ Virtual environment activated"
echo ""

# Check config content
echo "Checking config.yaml content..."
if grep -q "bartowski/Qwen2.5-7B-Instruct-GGUF" config.yaml; then
    echo "✓ Config uses correct bartowski repo"
else
    echo "❌ ERROR: Config is not using bartowski repo"
    echo "   Expected: bartowski/Qwen2.5-7B-Instruct-GGUF"
    echo "   Found:"
    grep "repo_id" config.yaml | head -1
    exit 1
fi

echo ""
echo "Running Python config debug..."
python3 debug_config.py

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  VERIFICATION COMPLETE                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Everything looks good! Now you can:"
echo ""
echo "1. Download the model:"
echo "   python3 test_download.py"
echo ""
echo "2. Start chatting:"
echo "   python3 main.py --mode chat"
echo ""
