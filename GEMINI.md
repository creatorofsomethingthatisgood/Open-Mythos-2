# Open-Mythos-2: The Terminal Oracle

Open-Mythos-2 is a fully **local, offline AI** designed for intelligent conversation, autonomous tool use, and security auditing directly from your terminal. Built with a focus on privacy and efficiency, it requires **zero API keys** and **zero cloud dependency**, running entirely on your local hardware.

## 🚀 Project Overview

- **Purpose:** Provide a private, high-performance local AI assistant and security scanner.
- **Core Technologies:** 
    - **Inference:** Python-based engine leveraging `llama-cpp-python` for GGUF model support.
    - **CLI/UI:** Rich-powered terminal interface and Gradio-based web UI.
    - **Security:** Static and AI-powered (deep) security scanners.
    - **Intelligence Features:** RAG (Retrieval-Augmented Generation), RML (Reinforcement Machine Learning), Cross-Session Memory, and Autonomous Agent (Operative Mode).
- **Architecture:** 
    - `mythos_cli/`: CLI entry points and management tools.
    - `engine/`: Core logic for inference, memory, RAG, agent loops, and feedback engines.
    - `ui/`: Implementation of the terminal and web interfaces.
    - `prompts/`: Structured system instructions for various specialized modes (coding, security, roleplay, etc.).

## 🛠 Building and Running

### Prerequisites
- Python 3.10+
- C++ Build Tools (for `llama-cpp-python` compilation)
- Optional: `espeak-ng` (for TTS), `whisper-cli` (for voice input)

### Setup
The project provides several platform-specific setup scripts:
- **Linux:** `bash setup.sh`
- **macOS:** `./setup-macos.sh`
- **Windows:** `.\setup-windows.ps1`

Alternatively, you can install as an editable package:
```bash
pip install -e .
```

### Key Commands
- **Start Chat:** `mythos` or `mythos chat`
- **Download Model:** `mythos model download`
- **Autonomous Agent:** `mythos agent "task description"`
- **Security Scan:** `mythos scan --path <dir>` (Add `--deep` for AI audit)
- **Auto-Fix:** `mythos fix --path <dir> --apply`
- **Web UI:** `mythos web --port 7860`
- **Doctor (Diagnostics):** `mythos doctor`

## 📜 Development Conventions

### Coding Style
- **Verification First:** The project emphasizes a "Verify 5 Times" principle (Logic, Edge Cases, Bugs, Optimization, Security).
- **Type Safety:** Uses Python type hints for clarity and maintainability.
- **Defensive Programming:** Rigorous input validation and error handling, especially in `engine/agent.py` and `ui/terminal_ui.py`.
- **Documentation:** Maintain clear docstrings for functions and classes.

### Testing
- **Framework:** `pytest` is the preferred testing framework.
- **Run Tests:** `pytest tests/`
- **Verification:** Always run `python3 -m py_compile <file>` to check for syntax errors after modifications.

### Agent & Tool Use
- **Safety Tiers:** `safe`, `elevated`, and `unleashed` tiers control tool access levels.
- **Sandbox:** All file operations should stay within the configured sandbox directory.
- **Confirmation:** Destructive actions or writes require explicit user confirmation unless in `unleashed` mode.

## 🏛 Specialized Modes
Open-Mythos-2 supports various "System Modes" via prompt injection:
- `coding`: ELITE 5-pass verification mode.
- `security_fix`: Default mode for finding and fixing vulnerabilities using `MYTHOS_PATCH` blocks.
- `analytical`: Deep reasoning and analysis.
- `operative`: The autonomous agent loop capable of using terminal tools.

## ⚡ Performance Optimizations

Open-Mythos-2 includes a V-native core for maximum performance. While the primary interface is Python, performance-critical tasks can be delegated to pre-compiled V binaries.

### V-Native Fast Mode
- **Zero Startup Overhead:** The V binary starts in <5ms, compared to ~1.2s for the Python interpreter.
- **Native Inference Loop:** Eliminates the Python GIL and `llama-cpp-python` overhead for smoother token streaming.
- **Fast Static Scanner:** Native regex engine handles large codebases 10-50x faster than Python.
- **Parallel Downloader:** Native orchestrator with 16 parallel connections for maximum bandwidth utilization.

### Usage
To use the V-native engine, build it first:
```bash
cd mythos-v
make prod
```

Then use the `--fast` flag with standard commands:
- `mythos chat --fast` - Launch chat with microseconds startup and native streaming.
- `mythos scan --fast` - Scan large directories in seconds.
- `mythos model download` - Automatically uses the V downloader if built.

---
*Open-Mythos-2: No API. No cloud. No gods. Pure local power.*
