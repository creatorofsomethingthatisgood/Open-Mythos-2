#!/bin/bash
# Ultra-simple script to start chatting
# Just run: ./run_chat.sh

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              MYTHOS LOCAL - QUICK START                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check if we're in the right place
if [ ! -f "config.yaml" ]; then
    echo "❌ ERROR: Not in project directory!"
    echo "   Please cd to: ~/mythos_local/amd-vulkan-llm-project"
    exit 1
fi

# Activate venv
if [ ! -d "venv" ]; then
    echo "❌ ERROR: Virtual environment not found!"
    echo "   Please run ./setup.sh first"
    exit 1
fi

echo "✓ Found project files"
echo "✓ Activating virtual environment..."
source venv/bin/activate

echo ""
echo "Verifying configuration..."
python3 show_download_url.py

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting chat in 3 seconds..."
echo "  (The model will auto-download on first run - ~4.7GB)"
echo "  (This takes 5-10 minutes depending on your internet speed)"
echo ""
echo "  Press Ctrl+C now to cancel, or wait to continue..."
echo ""
sleep 3

python3 main.py --mode chat
