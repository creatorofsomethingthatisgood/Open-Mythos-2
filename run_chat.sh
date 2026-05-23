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
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "   Please run ./setup-macos.sh first"
    else
        echo "   Please run ./setup.sh first"
    fi
    exit 1
fi

echo "✓ Found project files"
if [ ! -x "./mythos" ] && [ ! -x "venv/bin/mythos" ]; then
    echo "❌ mythos CLI not installed. Run ./setup-macos.sh or ./setup.sh first"
    exit 1
fi

chmod +x ./mythos 2>/dev/null || true

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting chat..."
echo "  Model path: ~/.config/mythos/models/ (download once with ./mythos model download)"
echo ""

exec ./mythos chat
