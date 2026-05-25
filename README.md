<img width="845" height="372" alt="Screenshot from 2026-05-24 20-57-50" src="https://github.com/user-attachments/assets/8e3b6a5b-117a-41c6-afbb-394e5cb8c023" />
<div align="center">
<pre>
                  ██████╗ ██████╗ ███████╗███╗   ██╗
                 ██╔═══██╗██╔══██╗██╔════╝████╗  ██║
                 ██║   ██║██████╔╝█████╗  ██╔██╗ ██║
                 ██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║
                 ╚██████╔╝██║     ███████╗██║ ╚████║
                  ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝
███╗   ███╗██╗   ██╗████████╗██╗  ██╗ ██████╗ ███████╗       ██████╗
████╗ ████║╚██╗ ██╔╝╚══██╔══╝██║  ██║██╔═══██╗██╔════╝       ╚════██╗
██╔████╔██║ ╚████╔╝    ██║   ███████║██║   ██║███████╗  █████╗ █████╔╝
██║╚██╔╝██║  ╚██╔╝     ██║   ██╔══██║██║   ██║╚════██║  ╚════╝██╔═══╝
██║ ╚═╝ ██║   ██║      ██║   ██║  ██║╚██████╔╝███████║       ███████╗
╚═╝     ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝       ╚══════╝
</pre>

> *"From the void of computation, a new oracle speaks — no gods, no cloud, only the terminal."*

<br>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=22&pause=1000&color=FFD700&center=true&vCenter=true&width=700&lines=The+Oracle+runs+in+your+terminal.;No+API.+No+cloud.+No+gods.;Pure+local+AI+power.;OpenMythos-2+has+awakened." alt="Typing SVG" />

<br>

[![npm published](https://img.shields.io/npm/v/open-mythos-2?style=for-the-badge&label=npm&color=cb3837)](https://www.npmjs.com/package/open-mythos-2)
[![License: MIT](https://img.shields.io/badge/License-MIT-gold?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0.5-blueviolet?style=for-the-badge)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2)
[![No API Required](https://img.shields.io/badge/No%20API-Required-darkgreen?style=for-the-badge&logo=gnubash&logoColor=white)]()
[![Runs in Terminal](https://img.shields.io/badge/Runs%20In-Terminal-black?style=for-the-badge&logo=windowsterminal&logoColor=white)]()
[![Open Source](https://img.shields.io/badge/Open-Source-orange?style=for-the-badge&logo=opensourceinitiative&logoColor=white)]()
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)]()
[![Stargazers repo roster for @creatorofsomethingthatisgood/Open-Mythos-2](https://reporoster.com/stars/creatorofsomethingthatisgood/Open-Mythos-2)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/stargazers)
[![Forkers repo roster for @creatorofsomethingthatisgood/Open-Mythos-2](https://reporoster.com/forks/creatorofsomethingthatisgood/Open-Mythos-2)](https://github.com/creatorofsomethingthatisgood/Open-Mythos-2/network/members)

</div>
---

## ⚡ What is OpenMythos-2?

**OpenMythos-2** is a fully **local**, **offline** AI that lives and breathes inside your terminal. Inspired by the ancient myths of oracles, gods, and forgotten wisdom — it brings the power of intelligent conversation and reasoning directly to your command line, with **zero API keys**, **zero cloud dependency**, and **zero limits**.

Like Prometheus stealing fire from the gods, OpenMythos-2 brings the fire of AI to every machine.

---

## 🏛️ Features

| ✨ Feature | 📖 Description |
|---|---|
| ⚡ **No API Required** | Fully local — nothing ever leaves your machine |
| 🖥️ **Terminal Native** | Built from the ground up for the command line |
| 🧠 **Intelligent Reasoning** | Context-aware, multi-turn conversations |
| 🌑 **Offline First** | Works anywhere — planes, bunkers, the underworld |
| 🔱 **Mythos Persona** | Answers in the voice of an ancient, wise oracle |
| 🪶 **Lightweight** | Minimal dependencies, blazing fast startup |
| 🔓 **Open Source** | Fully transparent and community-driven |
| 🛡️ **Private by Design** | Your conversations are yours alone |
| 🔄 **RML (Reinforcement ML)** | Learns from your feedback and adapts — edits system prompt and generation params to match your preferences | when command is /rml on

## 🌊 The Myth Behind the Machine

The name draws from **mythos** (μῦθος) — the ancient Greek word for *story*, *legend*, and *the spoken word of truth*. OpenMythos-2 embodies that spirit: a storyteller, reasoner, and companion that runs **entirely on your machine**, with no external gods (servers) to pray to.

---

## 🚀 Getting Started

### Prerequisites

- Python `3.10+`
- `pip`
- A terminal (bash, zsh, PowerShell, cmd)

### 🔱 Installation

<details>
<summary><strong>Option 1 — Git Clone (recommended)</strong></summary>

```bash
# Clone the sacred repository
git clone https://github.com/creatorofsomethingthatisgood/Open-Mythos-2.git

# Enter the temple
cd Open-Mythos-2

# One-time setup (macOS or Linux)
./setup-macos.sh # or ./setup.sh on Linux

# Then chat (no `source venv` needed)
./mythos
./mythos model download # once per machine (~4.5 GB → ~/.config/mythos/)

# Move your downloads to another PC (no re-download):
./scripts/mythos-export-data.sh # creates offline-bundle/ (~4.5 GB)
# On the new machine after setup:
./scripts/mythos-import-data.sh ./offline-bundle
```

</details>

<details>
<summary><strong>Option 2 — npm (npx)</strong></summary>

```bash
# Two-command install & run — no manual clone needed
sudo npm install open-mythos-2@2.0.0
or 
sudo npm install -g open-mythos-2 

# Download the model (~4.5 GB, first time only)
mythos model download

# Start chatting
mythos
```

> **Note:** The npm package wraps the same setup and Python backend under the hood. Node.js 18+ and Python 3.10+ are required. The first `npx` or `mythos` run will automatically set up the virtual environment and dependencies if they aren't already present.

</details>

<details>
<summary><strong>Option 3 — pnpm</strong></summary>

```bash
sudo pnpm install open-mythos-2@2.0.0

> **Note:** [pnpm](https://pnpm.io/) is a fast, disk-efficient package manager. The package wraps the same setup and Python backend under the hood. Node.js 18+ and Python 3.10+ are required. The first run will automatically set up the virtual environment and dependencies if they aren't already present.

</details>


---

## 🔄 RML — Reinforcement Machine Learning

RML is a feedback-driven self-improvement loop that learns your preferences over time and adapts Mythos to match. It does **two things automatically**:

### 1. Edits the System Prompt

When a category accumulates enough negative feedback, RML injects a concrete behavioral hint directly into the system prompt. These learned hints tell Mythos how to adjust its style — for example:

- **Accuracy** hint: *"Prioritize accuracy over creativity. Double-check facts. If unsure, say so."*
- **Conciseness** hint: *"Be concise. Get to the answer quickly; elaborate only when asked."*
- **Clarity** hint: *"Use headers, bullet points, short paragraphs. Avoid jargon without explanation."*
- **Code quality** hint: *"Write production-quality code: type hints, docstrings, error handling."*
- **Security** hint: *"Apply security best practices: input validation, no hardcoded secrets."*
- **Completeness** hint: *"Be thorough. Address all parts of the question. Don't skip edge cases."*

Hints are **removed automatically** when the category's score recovers — so the system prompt is always a live reflection of what you actually prefer.

### 2. Adjusts Generation Parameters

RML also tweaks `temperature`, `top_p`, and `repeat_penalty` behind the scenes:

- High accept rate → temperature nudges **up** (more creative/confident)
- High rejections/edits → temperature nudges **down** (more conservative/precise)
- Many interrupts → `repeat_penalty` increases slightly

All adjustments are bounded by `max_param_offset` (default 0.3) so nothing swings wildly.

### Feedback Signals RML Collects

| Signal | Strength | Trigger |
|--------|----------|---------|
| Explicit good | +2.0 | `/rml good` |
| Explicit bad | −2.0 | `/rml bad` |
| Implicit positive | +1.0 | You say "thanks", "perfect", "works", etc. |
| Implicit negative | −1.0 | You say "wrong", "try again", "mistake", etc. |
| Edit penalty | −1.0 | You rewrite Mythos' output |
| Interrupt penalty | −0.5 | You Ctrl+C during generation |

### Commands

```
/rml on          Enable RML
/rml off         Disable RML
/rml good        Mark last response as good (explicit +2)
/rml bad         Mark last response as bad (explicit -2)
/rml stats       Show what RML has learned (scores, hints, param adjustments)
/rml reset       Wipe all learned preferences and start fresh
```

### Config (`config.yaml`)

```yaml
rml:
  enabled: false          # Turn on with /rml on in chat
  learning_rate: 0.05     # 0.01 = slow, 0.2 = fast
  max_param_offset: 0.3   # Max drift from base temperature/top_p
  hint_threshold: 3.0     # Negative score before a hint is injected
```

Preferences persist in `~/.config/mythos/rml_preferences.json` across sessions.

Thank you for the star if you gave one.
We love supporters

