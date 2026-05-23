# Mythos Sentinel — Product CLI

Local security scanner customers install once, register code folders, and run scans from the terminal or CI.

## Install

```bash
pip install -e .          # from this repo
# or, when published:
# pip install mythos-sentinel
```

Requires Python 3.10+ and (for `--deep` only) a downloaded GGUF model.

## Customer workflow

```bash
# One-time setup
mythos init
mythos path add ~/projects/payments-api
mythos path add ~/projects/auth-service --label auth

# Instant static scan (seconds, no GPU)
mythos scan

# Single repo
mythos scan --path ~/projects/payments-api

# CI / JSON output
mythos scan --format json --severity high

# AI deep audit (local LLM, minutes)
mythos model download
mythos scan --deep --path ~/projects/payments-api
```

## Commands

| Command | Description |
|---------|-------------|
| `mythos init` | Create `~/.config/mythos/` |
| `mythos path add <dir>` | Register a codebase folder |
| `mythos path list` | Show registered folders |
| `mythos path remove <path\|id>` | Unregister |
| `mythos scan` | Static rules on all registered paths |
| `mythos scan --deep --path <dir>` | RAG + local LLM security audit |
| `mythos explore <dir>` | Preview indexable files |
| `mythos model download` | Fetch default GGUF model |
| `mythos status` | Config, paths, model status |

## Configuration

- **User registry:** `~/.config/mythos/config.yaml` — `scan_paths`, severity filters
- **LLM / RAG:** `~/.config/mythos/mythos.yaml` — model path, embeddings cache
- **Override home:** `export MYTHOS_HOME=/custom/config`

## What `mythos scan` detects (static)

Private keys, cloud credentials, hardcoded secrets, `eval`/`exec`, unsafe pickle/YAML, shell injection, weak TLS, permissive CORS, debug flags, webhook routes, `.env` in tree, and more.

Exit code `1` when **critical** or **high** findings exist — suitable for CI gates.

## Positioning

- **Free tier:** `mythos scan` (static, instant, offline)
- **Pro tier:** `mythos scan --deep` (local LLM, no data leaves the machine)
- **Enterprise:** custom rules, SARIF export, license key (future)
