#!/bin/bash
# Ultra-simple script to start web UI
# Just run: ./run_web.sh

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║            MYTHOS LOCAL - WEB INTERFACE                      ║"
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
echo "Starting web interface in 3 seconds..."
echo "  • URL: http://localhost:7860"
echo "  • The model will auto-download on first run (~4.7GB)"
echo "  • Open your browser after the server starts"
echo ""
echo "  Press Ctrl+C now to cancel, or wait to continue..."
echo ""
sleep 3

echo "Starting server..."
python3 main.py --mode web
