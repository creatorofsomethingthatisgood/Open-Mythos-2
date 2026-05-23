# Shared install helpers — source from setup-macos.sh / setup.sh
# Idempotent: safe to re-run; skips downloads when already installed.

install_mythos_python_deps() {
    echo ""
    echo "Installing Mythos package (skips packages already satisfied)..."
    pip install -e ".[web]"
    echo -e "${GREEN}✓ Mythos CLI registered (venv/bin/mythos)${NC}"
}

llama_cpp_import_ok() {
    python3 -c "from llama_cpp import Llama" 2>/dev/null
}

mythos_cli_ok() {
    python3 -c "import mythos_cli" 2>/dev/null
}

run_mythos_init() {
    echo ""
    echo "Initializing user config (~/.config/mythos)..."
    python3 -m mythos_cli.main init 2>/dev/null || python3 -c "
from mythos_cli.config_store import init_config
init_config(quiet=True)
print('✓ User config ready')
"
}

print_mythos_usage() {
    local root
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    echo ""
    echo "To start chatting (no need to activate venv each time):"
    echo ""
    echo "  cd \"$root\""
    echo "  ./mythos              # or: ./mythos chat"
    echo "  ./mythos web          # web UI"
    echo ""
    echo "Optional — mythos from any directory after opening a new terminal:"
    echo "  export PATH=\"$root/venv/bin:\$PATH\""
    echo ""
    echo "Models and Hugging Face cache live in ~/.config/mythos/ (not re-downloaded per clone)."
    echo "Download the LLM once:  ./mythos model download"
    echo ""
}
