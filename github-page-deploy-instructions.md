# GitHub Pages Deployment — Assessment & Instructions

A practical guide for deploying the Open-Mythos-2 web frontend to GitHub Pages (free tier). Read the **assessment** first — there's a real architectural mismatch you should understand before doing the work.

---

## 1. Assessment

### What's in `src/` today

| Piece | What it is |
|---|---|
| `src/main.tsx` | React 19 entry point. |
| `src/App.tsx` | Main chat UI shell (~530 lines). |
| `src/api.ts` | All HTTP calls — hardcoded `const API_BASE = "/api"`. Hits `/api/chat`, `/api/prompt`, `/api/clear`, `/api/export`, `/api/save`, `/api/rag-upload`. |
| `src/components/` | `ChatArea`, `InputBar`, `CommandPalette`, `SettingsPanel`, `CodeBlock`, `ThinkingBlock`, `ExportModal`, `QuickActions`, `ModeSelector`, `StatusBar`. |
| `src/index.css` | Tailwind v4 styles. |
| `index.html` | Single root div + `/src/main.tsx` script tag. |

Build toolchain (from `package.json` + `vite.config.ts`):

- **Vite 7** + `@vitejs/plugin-react` + `@tailwindcss/vite` + **`vite-plugin-singlefile`**.
- `vite build` produces a self-contained `dist/index.html` with all JS and CSS **inlined** (no separate asset files thanks to `vite-plugin-singlefile`).

### How the current architecture is supposed to work

```
[ Browser ]  ──HTTP──>  [ Vercel serverless fn /api/index.ts ]  ──HTTP──>  [ Local Python FastAPI on port 7860 ]
                              ^                                                       ^
                              |                                                       |
                              Reads MYTHOS_BACKEND env var                            engine/api_server.py
```

The `api/index.ts` Vercel function is a thin **proxy** that forwards `/api/*` to the user's locally-running Python backend (default `http://localhost:7860`). It exists because Vercel can run server-side code; that's how `vercel.json` is wired (`{ "framework": "vite", "rewrites": [{ "source": "/api/:path*", "destination": "/api/:path*" }] }`).

### Why GitHub Pages is **not a drop-in replacement**

GitHub Pages serves **static files only** — no serverless functions, no proxies, no environment variables for runtime config. If you deploy the current frontend to GH Pages as-is:

- The HTML, CSS, and React app **load fine**.
- The first `fetch('/api/prompt?name=...')` on app init returns **404** (no such route on Pages).
- Every chat send returns 404 too.
- The user sees the UI but the chat is dead.

There is no way to make `/api/*` work on GH Pages without changing the frontend code. **GitHub Pages requires either**:

1. **Option A — static demo only**: ship the UI as a non-functional preview / landing page. Zero code changes. Honest about what it does.
2. **Option B — configurable backend URL**: small code change (~10 lines) so the frontend points at a user-configurable backend URL instead of `/api`. The user runs Mythos locally on `:7860`, exposes it (CORS already permissive — `engine/api_server.py:62` sets `allow_origins=["*"]`), and types the URL into a settings field on the deployed site.
3. **Option C — in-browser WASM inference**: out of scope. Would need a different model and a different runtime (llama.cpp WASM build, web-llm, etc.) — a separate, large project.

### Existing alternative the project already supports

`vercel.json` is fully wired and `api/index.ts` already exists. **The path of least resistance for a hosted chat is Vercel, not GitHub Pages** — both are free for public projects, but Vercel runs the proxy you need. If you only deploy to Pages, expect to add Option B or live with Option A.

### Cost & limits (GitHub Pages free tier)

- Free for **public** repositories (private repos need GitHub Pro/Team/Enterprise).
- Soft limits: **1 GB site size**, **100 GB/month bandwidth**, **10 builds/hour**.
- Custom domain supported (free), automatic HTTPS via Let's Encrypt.
- Build time per deploy: ~1–2 min for this project.

### Verdict

For the lowest-friction path that actually shows the UI: **Option A + a banner explaining that chat needs a local backend.** Pair the README with a link back to the npm/Docker install instructions. If you want functional chat from the hosted page, do Option B (it's small).

---

## 2. Step-by-step instructions

These instructions cover **Option A (static-only deploy, no code changes)** and **Option B (configurable backend URL)**. Pick one; the GH Actions workflow and repo settings are identical for both.

### Step 0 — Prerequisites

- You're an admin or owner of the `Open-Mythos-2` repo (you need Pages settings access).
- The repo is **public**, or you have GitHub Pro/Team/Enterprise.
- You can push to `main` or open PRs that get merged.

### Step 1 — Enable GitHub Pages with "GitHub Actions" as source

1. Go to `https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/settings/pages`.
2. Under **Build and deployment → Source**, select **GitHub Actions**.
3. (Don't pick "Deploy from a branch" — that mode is for pre-built static files in a branch. We're building via Actions.)

That's it for now. No save button — the choice is persisted.

### Step 2 — Add the deploy workflow

Create the file `.github/workflows/deploy-pages.yml` with the contents below. Commit + push.

```yaml
name: Deploy to GitHub Pages

on:
  # Auto-deploy on push to main
  push:
    branches: [main]
  # Allow manual trigger from the Actions tab
  workflow_dispatch:

# Required permissions for the Pages deployment
permissions:
  contents: read
  pages: write
  id-token: write

# Only one Pages deploy at a time; cancel any in-progress when a new one starts
concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Build site
        run: npm run build
        env:
          # Required when serving from https://<user>.github.io/Open-Mythos-2/
          # so Vite uses /Open-Mythos-2/ as the base path. See Step 3.
          VITE_BASE: "/Open-Mythos-2/"
          # Option B only — point the frontend at the user's local backend.
          # Leave unset for Option A.
          # VITE_API_BASE: "http://localhost:7860/api"

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### Step 3 — Tell Vite about the GH Pages base path

The site will live at `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/` — note the `/Open-Mythos-2/` segment. Vite has to know that base, otherwise asset URLs go wrong (mostly cosmetic with `vite-plugin-singlefile`, but the favicon and any future static imports break).

Edit `vite.config.ts`:

```ts
import path from "path";
import { fileURLToPath } from "url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  // Use VITE_BASE if set (CI), otherwise '/' for local dev
  base: process.env.VITE_BASE ?? "/",
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
```

This is the **only mandatory change for Option A**. Local `npm run dev` and `npm run build` still produce a root-served build; the CI deploy gets `/Open-Mythos-2/`.

### Step 4a — Option A: static demo only (no further changes)

You're done. Push the workflow file + `vite.config.ts` change to `main`. The Actions tab will show the deploy job; once green, the site is live at:

```
https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/
```

The UI loads, but every API call will fail with a 404 / "Failed to fetch" error. Users will see whatever fallback the React app shows — currently a banner saying "Backend unreachable" (rendered from `src/App.tsx` around line 67).

**Recommended**: add a visible note to the deployed page so users know it's a static demo. The lowest-impact way is a banner in `App.tsx` gated on `import.meta.env.VITE_BASE` (i.e., "you're looking at the GH Pages demo — chat is offline; for a working chat, install the npm package or run the Docker image"). That's a small UI tweak, not a backend change.

### Step 4b — Option B: configurable backend URL

This is the path to a **functional chat** from the deployed page. Two minor edits.

**1. Make `API_BASE` configurable** — edit `src/api.ts`:

```ts
import type { Message, Settings } from "./types";

// Build-time default. Override at runtime by setting
// localStorage.MYTHOS_API_BASE on the deployed site.
const DEFAULT_API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    const override = window.localStorage.getItem("MYTHOS_API_BASE");
    if (override) return override.replace(/\/$/, "");
  }
  return DEFAULT_API_BASE;
}

const API_BASE_LAZY = () => getApiBase();
```

Then replace every `${API_BASE}` template literal in this file with `${API_BASE_LAZY()}`. (One-line search-and-replace.)

**2. Set the build-time default in the workflow** — un-comment the `VITE_API_BASE` line in `.github/workflows/deploy-pages.yml` (Step 2). Example value for a user who runs Mythos locally on port 7860:

```yaml
VITE_API_BASE: "http://localhost:7860/api"
```

**3. (Recommended) Add a settings input** — let users override the backend URL from the deployed page without rebuilding. Anywhere in `src/components/SettingsPanel.tsx` add an `<input>` bound to `localStorage.MYTHOS_API_BASE`. The `getApiBase()` helper above already reads from there.

**4. Mythos backend's CORS is already permissive** — `engine/api_server.py:60-66` sets `allow_origins=["*"]`, so a browser at `https://...github.io` can call `http://localhost:7860/api/...` directly. Caveat: **mixed content** rules in browsers block `https → http` calls. Users will need either:
- a browser flag (Chrome: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`), or
- a tunnel like `cloudflared tunnel` / `ngrok` to expose `localhost:7860` over HTTPS, or
- run the GH Pages site from `http://...` (not possible — GH Pages forces HTTPS).

The cloudflared-tunnel path is probably the realistic one. Document it in the README.

### Step 5 — Trigger the first deploy

After committing the workflow + `vite.config.ts` change (+ optionally the `api.ts` change for Option B), either:

- Push to `main` — the workflow triggers automatically, or
- Go to **Actions → Deploy to GitHub Pages → Run workflow** for a manual trigger.

The first run takes ~2 min (npm install dominates). Subsequent runs are faster thanks to `actions/setup-node@v4`'s npm cache.

### Step 6 — Verify

1. **Actions tab**: the workflow shows two green checks (`build`, `deploy`).
2. **Deployment URL**: the `deploy` job prints the URL it deployed to in its output.
3. **Open the URL**: `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/` should render the app.
4. **DevTools → Network**: open the page and watch for `/api/*` requests:
   - Option A: they will 404. UI loads, chat dead. Expected.
   - Option B: with backend running + CORS reachable, they return 200. Type into chat and check for a model reply.

### Step 7 (optional) — Custom domain

If you own a domain (e.g., `mythos.example.com`):

1. In your DNS provider, add a `CNAME` record from `mythos` → `creatorofsomethingthatisgood.github.io`.
2. In **Settings → Pages → Custom domain**, enter `mythos.example.com`. Click Save.
3. Wait for DNS propagation (minutes to an hour). GitHub will provision a Let's Encrypt cert automatically.
4. Tick **Enforce HTTPS**.
5. **Update `VITE_BASE`** in the workflow from `/Open-Mythos-2/` back to `/` — at a custom domain root, the base is `/`.

### Step 8 (optional) — Branch protection for the Pages source

If `main` is the source for deploys, consider adding branch protection on `main` so only reviewed PRs land:

1. **Settings → Branches → Add rule**
2. Branch name pattern: `main`
3. Tick **Require a pull request before merging**, **Require status checks** (point at the build job).

---

## 3. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Workflow fails with "Resource not accessible by integration" | Missing Pages permissions on the workflow. | Verify `permissions:` block (Step 2) includes `pages: write` + `id-token: write`. |
| Workflow fails with "Get Pages site failed" | Pages source not set to "GitHub Actions". | Redo Step 1. |
| Deployed page is blank, console shows 404 for `/Open-Mythos-2/assets/index-XXX.js` | `vite-plugin-singlefile` is bundling everything inline — should not request external assets. If you see this, the plugin isn't activating; check `vite.config.ts` includes `viteSingleFile()`. | Confirm `plugins: [react(), tailwindcss(), viteSingleFile()]`. |
| 404 for the page itself (`/Open-Mythos-2/`) | Wrong base path or trailing-slash issue. | Make sure `VITE_BASE` ends with `/` and matches the repo name exactly. |
| Mixed-content blocked in browser | HTTPS Pages calling HTTP backend (Option B). | Tunnel backend over HTTPS (cloudflared/ngrok), or document the browser flag workaround. |
| `npm ci` fails on `tar@^7.5.15` or similar | `package-lock.json` out of sync with `package.json`. | Run `npm install` locally, commit the regenerated lockfile. |
| Build is much larger than expected (>5 MB) | `vite-plugin-singlefile` inlines assets; large images / fonts blow up the HTML. | Audit `src/` for binary imports; offload large assets to a CDN. |
| Chat says "Backend unreachable" (Option B) | Local Mythos backend not running, or CORS / mixed-content failure. | Run `python main.py --mode web` locally (port 7860); use cloudflared tunnel if accessing via HTTPS. |

---

## 4. Quick reference

**Files this introduces / changes:**

| File | Option A | Option B |
|---|---|---|
| `.github/workflows/deploy-pages.yml` | new | new |
| `vite.config.ts` | edit (add `base`) | edit (add `base`) |
| `src/api.ts` | no change | edit (~10 lines) |
| `src/components/SettingsPanel.tsx` | no change | optional edit (backend URL input) |
| `src/App.tsx` | optional banner | optional banner |

**Site URL:** `https://creatorofsomethingthatisgood.github.io/Open-Mythos-2/`

**Build command CI runs:** `npm ci && npm run build` with `VITE_BASE=/Open-Mythos-2/`

**Deploy trigger:** push to `main` (or manual via Actions tab).

**Rollback:** re-run a previous workflow from the Actions tab, or revert the bad commit on `main`.

---

## 5. What I'd actually recommend

1. **If goal is "have a public URL for screenshots / npm landing page" → Option A.** ~15 min of work. Honest banner. Done.
2. **If goal is "let people try Mythos from a browser without installing" → Vercel, not Pages.** The existing `vercel.json` + `api/index.ts` already work; users still need to run the Python backend locally (the Vercel function proxies to `localhost:7860`), but the wiring is in place. Add a `vercel deploy` button to the README and you're done.
3. **If you really want GH Pages + functional chat → Option B + cloudflared tunnel.** Documented above. Most setup work falls on the end user.
4. **In-browser WASM inference** is interesting but a separate project — not GH Pages work.
