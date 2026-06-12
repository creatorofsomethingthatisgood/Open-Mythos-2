# Contributing to Mythos

Thanks for your interest! We welcome contributions of all kinds - bug fixes,
features, documentation, prompts, and tests.

## Quick Start

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/Open-Mythos-2.git`
3. **Setup**: `./setup.sh` (Linux) or `./setup-macos.sh` (macOS)
4. **Create a branch**: `git checkout -b feature/your-idea`
5. **Make changes** and test them
6. **Submit a PR** against `main`

## Development Setup

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev,web]"

# Run the test suite
pytest tests/ -v

# Launch the terminal chat
python main.py
```

## Code Style

- Python 3.10+ — use type hints, f-strings, and `pathlib.Path`
- Follow PEP 8 with 4-space indentation
- Keep functions focused; prefer small, composable modules
- Use `logging` instead of `print()` in engine code
- Use `rich` for terminal output in CLI/UI code

## Pull Request Guidelines

- **One feature per PR** — keep it focused
- **Add tests** for new functionality (even basic smoke tests help)
- **Update docs** — README.md, docstrings, and inline comments
- **No breaking changes** without a deprecation period
- **Lint your code**: `pytest tests/ -v` and manual testing

## Project Structure

```
engine/          Core logic (inference, RAG, memory, security scanning)
ui/              Terminal and web interfaces
mythos_cli/      CLI commands (scan, fix, init, model, etc.)
prompts/         System prompt templates
tests/           Test suite
scripts/         Helper scripts (RAG indexing, data import/export)
```

## Adding Features

### New Chat Command
Add your handler in `ui/terminal_ui.py` → `handle_command()` method.
Follow the existing pattern: `elif cmd == "/yourcmd": ...`

### New CLI Subcommand
Add an `_cmd_*` function in `mythos_cli/main.py` and register it
in `build_parser()`.

### New Prompt Template
Create `prompts/your_template.txt` and it becomes available via
`/persona your_template` in chat.

### New Engine Module
Add your file under `engine/`, import in `ui/terminal_ui.py`
or `engine/api_server.py` as needed.

## Reporting Bugs

1. Run `mythos doctor` and include the output
2. Include your OS, Python version, and model name
3. Paste the full error traceback
4. Describe steps to reproduce

## Feature Requests

Open an issue with the label `enhancement`. Include:
- The problem it solves
- Proposed interface (command, config key, etc.)
- Any alternatives you considered

## Security Vulnerabilities

For security issues, please email the maintainer directly instead of
opening a public issue. Include:
- The vulnerability type (injection, path traversal, etc.)
- The affected component and version
- Steps to reproduce

## License

By contributing, you agree that your code will be released into the
[Apache License 2.0](LICENSE).
