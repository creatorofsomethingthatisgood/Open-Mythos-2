# GitHub Pages Deployment — Assessment & Instructions

**Scope (corrected):** The GitHub Pages site is a **public landing / reference page** — project description, badges, fork & star rosters, attribution, contribution pointer. It is **not** a deployed copy of the interactive chat UI. The React app under `src/` and the serverless proxy under `api/` continue to target **Vercel**, where the chat can actually call a backend; GH Pages serves a static, theme-rendered version of the README plus optional extra pages.

---

## 1. Assessment

### What we have that's relevant

| Asset | Role on GH Pages |
| --- | --- |
| `README.md` | The landing page. Already has the ASCII banner, badges, stars/forks roster, feature table, install instructions, command reference, supporter shoutout. Render this with a Jekyll theme and the site is essentially done. |
| `src/` (React) | **Not deployed to Pages.** Stays for Vercel. |
| `api/index.ts` (Vercel serverless) | **Not deployed to Pages.** Stays for Vercel. |
| `vercel.json` | **Not deployed to Pages.** Stays for Vercel. |
| `LICENSE` (Unlicense) | Linked from the badge; Jekyll picks it up automatically. |

### Why this is much easier than I first wrote

GitHub Pages has built-in Jekyll rendering for the README. You don't need a workflow, a Node build, Vite, or any code changes. **Settings → Pages → Source → "Deploy from a branch" → `main` / root** does ~95 % of the work; picking a theme finishes it.

### What works out of the box from the current README

- Markdown headings, lists, tables, blockquotes — fine.
- `<div align="center">`, `<details>` / `<summary>`, `<img>` tags — fine (kramdown allows HTML).
- `https://img.shields.io/...` badges — fine, they're images.
- `https://reporoster.com/stars/...` and `.../forks/...` rosters — fine, also images.
- `https://readme-typing-svg.demolab.com/...` animated SVG — fine.

### What needs a small touch

- The repo's banner image URL points to `user-attachments/assets/...` which is a private GitHub asset and **may not render anonymously on the Pages domain.** Replace with a committed file under `assets/` or `docs/assets/` if it breaks.
- One stray double-pipe (`||`) in the feature table (from a recent merge) renders an empty left column. Cosmetic; one-line fix in README.
- ASCII banner inside `<pre>` is fine in monospace but the Jekyll theme controls the font — pick a theme that uses a monospace `<pre>` style (Cayman, Hacker, Slate all do).

### Cost (GitHub Pages free tier)

- Free for **public** repos. (Private repos need Pro/Team/Enterprise.)
- 1 GB site size, 100 GB/month bandwidth, 10 builds/hour — none of which we'll get near with a README site.
- Custom domain free, HTTPS automatic via Let's Encrypt.

### Verdict

Use the **"Deploy from a branch"** mode (not "GitHub Actions"). README.md becomes the index. Pick a theme. Optionally add an "Attribution" and "Contributing" page under `/docs`. ~15 minutes of work.

---

## 2. Step-by-step instructions

### Step 0 — Prerequisites

- You're an admin or owner of `creatorofsomethingthatisgood/Open-Mythos-2`.
- Repo is public (it is).
- `README.md` is in the repo root (it is).

### Step 1 — Enable Pages with branch-deploy

1. Go to `https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/settings/pages`.
2. Under **Build and deployment → Source**, pick **Deploy from a branch**.
3. Under **Branch**, pick `main` and `/ (root)`. Save.

GitHub will queue an initial build using the **default Jekyll theme** (Primer). Within ~30 seconds the page is live at:

```text
https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/
```

If you stop here, you already have a working landing page. The rest is polish.

### Step 2 — Pick a theme

Two ways. Either works.

**Option A — Theme chooser UI (fastest).**

1. Same Pages settings page. Scroll to **Theme**.
2. Click **Choose a theme**. Pick one (suggestions below).
3. GitHub commits a `_config.yml` to `main` automatically and rebuilds.

**Option B — Hand-write `_config.yml`** (if you want more control or you don't want the chooser to push an extra commit).

Create `_config.yml` in the repo root:

```yaml
# GitHub Pages site configuration
title: Open Mythos-2
description: Fully local, offline AI that lives in your terminal. No API keys, no cloud, no limits.
theme: jekyll-theme-cayman          # see suggestions below
show_downloads: false                # set true to show "Download .zip / .tar.gz" buttons
google_analytics:                    # optional, leave blank
plugins:
  - jekyll-relative-links            # converts ./docs/foo.md links to .html
  - jekyll-default-layout
  - jekyll-titles-from-headings
relative_links:
  enabled: true
  collections: false
include:
  - README.md
exclude:
  - src/
  - api/
  - engine/
  - mythos_cli/
  - ui/
  - tests/
  - scripts/
  - models/
  - benchmarks/
  - lora/
  - rag_docs/
  - conversations/
  - chroma_db/
  - .test-venv/
  - venv/
  - node_modules/
  - Dockerfile
  - .dockerignore
  - package.json
  - package-lock.json
  - pnpm-lock.yaml
  - pnpm-workspace.yaml
  - vite.config.ts
  - tsconfig.json
  - vercel.json
  - "*.sh"
  - "*.ps1"
  - "*.txt"
```

The `exclude:` list keeps Jekyll from trying to render source code as pages and from blowing up the build with non-markdown files.

**Theme suggestions for this project:**

| Theme | Vibe | Why it suits Mythos |
| --- | --- | --- |
| `jekyll-theme-cayman` | Clean, modern, dark accent | Default-feeling, plays nicely with the centered ASCII banner. |
| `jekyll-theme-hacker` | Green-on-black terminal | On-brand for a terminal-AI project. The ASCII banner will look great. |
| `jekyll-theme-slate` | Minimal, dark sidebar | Good for readability; understated. |
| `jekyll-theme-midnight` | Dark, blueprint feel | Matches the "Mythos / mystical" tone. |
| `jekyll-theme-architect` | Clean, light, well-typed | Best for users who want a "documentation" feel rather than a "manifesto" feel. |

My pick: **`jekyll-theme-hacker`** — it matches the project's terminal-first identity and renders the ASCII banner well.

### Step 3 — (Optional) Add attribution & contribution pages

Create a small `docs/` folder for pages that don't belong in the README.

```text
docs/
├── attribution.md
└── contributing.md
```

**`docs/attribution.md`** — your "attribution ladder":

```markdown
---
title: Attribution & Credits
---

# Attribution

## Maintainer

- **[@creatorofsomethingthatisgood](https://github.com/creatorofsomethingthatisgood)** — project lead

## Contributors

See the full list at [Contributors](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/graphs/contributors).

<!-- Optional: contrib.rocks image -->
[![Contributors](https://contrib.rocks/image?repo=creatorofsomethingthatisgood/Open-Mythos-2)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/graphs/contributors)

## Built on the shoulders of

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — local LLM inference
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — Python bindings
- [Qwen2.5](https://huggingface.co/Qwen) — default model family
- [bartowski](https://huggingface.co/bartowski) — GGUF quantizations
- [Hugging Face Hub](https://huggingface.co) — model distribution
- [ChromaDB](https://github.com/chroma-core/chroma) — RAG vector store
- [sentence-transformers](https://github.com/UKPLab/sentence-transformers) — embeddings
- [Gradio](https://www.gradio.app) — web UI
- [Rich](https://github.com/Textualize/rich) — terminal UI
- [React](https://react.dev) + [Vite](https://vite.dev) + [Tailwind](https://tailwindcss.com) — web frontend

## Supporters & stars

[![Stargazers](https://reporoster.com/stars/creatorofsomethingthatisgood/Open-Mythos-2)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/stargazers)

[![Forkers](https://reporoster.com/forks/creatorofsomethingthatisgood/Open-Mythos-2)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/network/members)

---

[← Back to project](../)
```

**`docs/contributing.md`** — point at the existing CONTRIBUTING.md (which was added in commit `15f27c2`):

```markdown
---
title: Contributing
---

# Contributing to Open Mythos-2

See the full guide in [CONTRIBUTING.md](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/blob/main/CONTRIBUTING.md).

## Quick links

- [Open an issue](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/issues/new)
- [Browse open PRs](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/pulls)
- [Discussions](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/discussions)

[← Back to project](../)
```

These pages will be reachable at:

- `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/docs/attribution.html`
- `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/docs/contributing.html`

Add a small "Project pages" section near the top of the README so the landing page links to them:

```markdown
**Pages:** [Attribution](docs/attribution.md) · [Contributing](docs/contributing.md) · [Issues](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/issues)
```

### Step 4 — (Optional) Custom domain

1. In your DNS provider, create either:
   - `CNAME` → `creatorofsomethingthatisgood.github.io` (for a subdomain like `mythos.example.com`), or
   - 4× `A` records pointing the apex domain to `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`.
2. Pages settings → **Custom domain** → enter the domain → Save.
3. GitHub creates a `CNAME` file in the repo root and provisions HTTPS via Let's Encrypt (~10 min).
4. Tick **Enforce HTTPS**.

### Step 5 — Verify

1. Open `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/`.
2. Check that:
   - ASCII banner renders in monospace.
   - Badges (npm, license, version) load.
   - Stars / forks rosters load (they take a few seconds — `reporoster.com` is third-party).
   - `<details>` install blocks expand.
3. Click the `docs/attribution.md` link from the README. It should resolve to `/Open-Mythos-2/docs/attribution.html` (thanks to `jekyll-relative-links` in `_config.yml`).
4. Pages tab → most recent deploy shows a green check.

### Step 6 — Keep it fresh

The site rebuilds **automatically** every time you push to `main`. No workflow file needed. To trigger a manual rebuild:

- Repo → **Actions → pages-build-deployment → Run workflow**, or
- Push an empty commit: `git commit --allow-empty -m "rebuild pages" && git push`.

---

## 3. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| README image at top (`user-attachments/assets/...`) is broken | GitHub-hosted user attachment URLs sometimes require auth referrer. | Commit the image under `assets/banner.png` and link to it with a relative path. |
| Stars / forks rosters slow to load | `reporoster.com` is a third-party rendering service. | Acceptable — they cache for 24 h. Or self-host with `contrib.rocks` style images. |
| Code blocks look broken in Jekyll output | Jekyll uses Rouge syntax highlighter, not GitHub's. | Most languages work; specify them as ` ```bash `, ` ```yaml `, etc. (you already do). |
| Empty left column in the Features table | A merge introduced lines starting with `\|\|` instead of `\|`. | Edit README.md, replace `\|\|` with `\|`. One-line fix. |
| `404` on `https://.../Open-Mythos-2/docs/attribution.html` | `jekyll-relative-links` plugin not enabled, or the `.md` file lacks frontmatter. | Add `relative_links` block to `_config.yml` (shown in Step 2) and ensure each `.md` page starts with `---\ntitle: ...\n---`. |
| Pages deploys but shows the raw README without theme | `_config.yml` missing or has wrong `theme:` value. | Use one of the supported themes (Step 2). Check spelling — `jekyll-theme-hacker`, not `hacker`. |
| Pages build fails with a Liquid error | Some text in README uses `{{ }}` or `{% %}` syntax that Jekyll's Liquid parser tries to interpret. | Wrap that text in `{% raw %}...{% endraw %}` blocks. |
| Custom domain says "domain not properly configured" | DNS hasn't propagated, or CNAME points at the wrong target. | Wait 10 min; verify with `dig +short mythos.example.com`. |

---

## 4. Quick reference

**Files this introduces (all minimal):**

| File | Purpose | Required? |
| --- | --- | --- |
| `_config.yml` | Theme + Jekyll plugins + exclude list | Recommended (auto-created by theme chooser if you skip writing it) |
| `docs/attribution.md` | Attribution ladder page | Optional |
| `docs/contributing.md` | Pointer to CONTRIBUTING.md | Optional |
| `assets/banner.png` | Self-hosted banner if user-attachments URL breaks | Only if needed |

**Files this does NOT touch:**

- `src/` (React app — stays for Vercel)
- `api/index.ts` (serverless proxy — stays for Vercel)
- `vercel.json`, `vite.config.ts`, `package.json` — all unchanged
- `Dockerfile`, `.dockerignore` — unrelated to Pages
- The Python backend — unrelated to Pages

**Site URL:** `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/`

**Pages source:** `main` branch, `/` (root). README.md is the index.

**Rebuild trigger:** any push to `main`.

**Rollback:** revert the offending commit on `main`. Pages rebuilds within ~30 s.

---

## 5. What stays where

| Surface | Target | Why |
| --- | --- | --- |
| **Public landing / attribution / reference** (this doc) | **GitHub Pages**, free, README-driven Jekyll | Static, public, free, automatic. |
| **Interactive chat UI** (`src/`) | **Vercel** (or self-hosted) | Needs the `api/index.ts` serverless proxy to reach the user's local Python backend. GH Pages can't host it. |
| **Terminal chat / scanner** (`mythos_cli`, `engine`, `ui/terminal_ui.py`) | npm install / Docker / `setup.sh` | Runs on user's machine. |
| **Web UI for chat** (`ui/web_ui.py` Gradio) | User's localhost on port 7860 | Started with `mythos web`. |

Each surface has its own deploy path; nothing overlaps.
