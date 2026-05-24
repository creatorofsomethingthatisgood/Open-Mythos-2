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
| `mythos fix --path <dir>` | Preview safe auto-fixes (dry-run) |
| `mythos fix --path <dir> --apply` | Apply line-level fixes (use git; no `.bak`) |
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

## Auto-fix (`mythos fix`)

Applies **deterministic** patches for patterns that are safe to change without understanding business logic:

- `yaml.load` → `yaml.safe_load`
- `verify=False` → `verify=True` (and similar TLS flags)
- Wildcard CORS `*` → placeholder origin (edit the domain)
- Obvious `DEBUG=true` / development flags → production-safe defaults

**Not auto-fixed** (review in chat or manually): hardcoded secrets, `eval`/`exec`, `shell=True`, SQL string building, webhooks, `.env` files.

In terminal chat:

```text
/file ~/projects/my-api
/fix ~/projects/my-api
```

Chat scans findings, shows a rewrite warning, and asks before overwriting **full files** (no `.bak` — use git).

### Fix while chatting (no `/fix` required)

In `./mythos` or `mythos chat`:

```text
/system security_fix
/file ~/projects/my-api
fix the vulnerabilities in ~/projects/my-api
```

Or in one message:

```text
fix vulns in file:///Users/you/projects/my-api/handlers/auth.py
```

What happens:

1. **Static scan** (preview only — no partial line edits in chat).
2. **Rewrite warning** + confirmation (terminal: `y/n`; web: enable “Allow full-file rewrite”).
3. The assistant replies with **`<<<MYTHOS_PATCH path="...">>>` blocks** containing the **entire file**.

Disable in `config.yaml`: `chat.fix.enabled: false`.

**File edit access** (on by default after restart):

- Reads paths like `'/Users/you/project'` (quotes supported) or `/Users/you/project`
- Remembers the last path when you say `fix` or `rewrite` alone
- Writes full files only after you confirm (`chat.fix.auto_write_patches: false` by default)
- Settings live in `~/.config/mythos/mythos.yaml` under `chat:` (added automatically on next `mythos` start)

### Rewrite file on disk (MYTHOS_PATCH only)

```text
/rewrite '/Users/you/projects/my-api/app/api/routes/verification.py'
```

This uses a dedicated patch prompt, retries until the model outputs valid `<<<MYTHOS_PATCH>>>`, then writes the **complete file** (no `.bak` — use git).

`/system security_audit` finds issues but does **not** write files. For edits use `/system security_fix` or `/rewrite`.

## Positioning

- **Free tier:** `mythos scan` (static, instant, offline)
- **Pro tier:** `mythos scan --deep` (local LLM, no data leaves the machine)
- **Enterprise:** custom rules, SARIF export, license key (future)
