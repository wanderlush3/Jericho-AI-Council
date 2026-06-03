# Jericho — AI Council

[![Ko-fi](https://img.shields.io/badge/Support%20this%20project-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/stifle23649) [![Discord](https://img.shields.io/badge/Join%20the%20community-Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/sMCs5fg3W)

> *An AI city where LLM agents collaboratively govern, build worlds, and evolve characters through democratic processes and an emergent economy.*

---

## What is Jericho?

Jericho is an **AI council simulator** — a living world governed by nine AI personas who debate proposals, pass laws, manage an economy, create characters, and build locations. You orchestrate everything from a sleek web dashboard while the council members argue, vote, and evolve on their own.

The key idea: a **Python orchestrator** handles all the heavy lifting (file I/O, API calls, state management) while agents interact purely through natural language. No fragile tool-calling — just structured prompts in, natural responses out.

```
You trigger an action → Orchestrator sends prompts → Agents respond → Everything is persisted
```

**Powered by** [OpenRouter](https://openrouter.ai/), [Mancer](https://mancer.tech/), and [LM Studio](https://lmstudio.ai/) — use cloud models, local models, or mix both.

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- API key for [OpenRouter](https://openrouter.ai/) and/or [Mancer](https://mancer.tech/)

### Install & Launch

```bash
# Clone and enter the project
git clone https://github.com/wanderlush3/Jericho-AI-Council.git jericho
cd jericho

# Create a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# Install
pip install -e ".[dev]"

# Launch the web dashboard
jericho web
```

Open **http://127.0.0.1:8080** in your browser. Configure API keys from the **Settings** page — no `.env` file editing required. Keys are encrypted at rest.

> **Windows users:** Just double-click `start.bat` to do everything automatically.
>
> **macOS / Linux users:** Run `chmod +x start.sh && ./start.sh` for the same one-click experience.

---

## The Council

Nine specialized AI personas govern Jericho. Each has a unique role, personality, and expertise. Council membership is fully customizable — rename members, swap models, upload custom avatars, or promote characters to the council.

| Member | Role | What They Do |
|--------|------|-------------|
| **Sage** | Ethics Advisor | Safety, values, long-term consequences |
| **Spark** | Creative Director | Novel ideas, unconventional approaches |
| **Logic** | Systems Analyst | Consistency, structure, edge cases |
| **Echo** | Historian | Memory, precedent, institutional knowledge |
| **Forge** | Character Builder | Identity design, personality crafting |
| **Lens** | Quality Reviewer | Critique, refinement, standards |
| **Pulse** | Community Advocate | User impact, accessibility, empathy |
| **Drift** | Devil's Advocate | Contrarian perspectives, stress-testing |
| **Anchor** | Moderator | Consensus building, tiebreaking |

Profiles are YAML files you can edit from the dashboard, including avatar upload with a zoom/pan framing editor.

---

## Features

### 🏛️ Governance

- **Proposals** — Create proposals, trigger AI discussion rounds, then let the council vote. Full lifecycle: `draft → open → under_review → decided`
- **Voting** — Quorum checks, configurable thresholds (default 60%), human veto power, reputation-weighted votes
- **Laws** — Draft, activate, and archive laws. Laws are conditionally injected into AI context only when relevant
- **Council Sessions** — Open-ended deliberation where the council discusses whatever's on their mind
- **Council Expansion** — Propose and vote on adding new members, or promote characters directly

### 🎭 Characters

- **Collaborative Design** — Multi-phase workflow where council members co-create characters (concept → traits → backstory → prompt → review)
- **Character Evolution** — Propose changes to existing characters, voted on by the council. Full version history with visual diff timeline
- **TavernCard Export** — Export any character as a TavernCard v2 PNG
- **Auto-Memory Creation** — New characters automatically get their own memory space

### 🌍 World Building

- **Locations** — Hierarchical location system with features, lore, coordinates, and parent/child relationships
- **Items** — Full item lifecycle with multi-owner tracking, property system, and custom LLM injection text (with 24h TTL for consumables)
- **Stores** — Commerce system with inventory, Obelisk pricing, and treasury-integrated purchasing
- **Gift Giving** — Dedicated gifting interface with item selector, owner/recipient pickers, reputation previews, and gift history timeline

### 🗺️ Exploration & Stories

- **Visual Exploration** — "Look Around" at locations with hero images, scene galleries, and hierarchical navigation
- **Feature-Centric Movement** — Stateful exploration with clickable feature cards, progress tracking, guided and imaginative modes (LLM-driven discovery beyond known features)
- **Explore Participants** — Add up to 10 council members and/or characters to exploration with full context injection
- **Explore Chat** — Interactive round-based discussions within exploration scenes via SSE streaming
- **Illustrated Stories** — LLM-narrated stories with inline generated illustrations, organized as Story → Chapter → Scene
- **Story Chat** — Interactive discussions within story scenes with participants

### 💬 Communication

- **Human-to-AI Chat** — Talk directly to any council member with your user profile injected as context
- **AI-to-AI Chat** — Orchestrate conversations between council members
- **Multi-Party Chat** — Autonomous multi-member conversations with sequential turn-taking
- **Presence System (SilentPassa)** — `[PRESENT]`/`[SILENCE]` display wrappers with toggleable UI
- **Response Timers** — Live pulsing timer during generation with permanent duration badges
- **Tasks** — Assign narrative tasks to council members/characters with SSE streaming. Supports standard, gift, and purchase task types

### 💰 Economy — The Obelisk

Three-tier currency: **Gold** (🥇) → **Silver** (🥈) → **Bronze** (🥉), each at 100:1 conversion.

- **Treasury** — Accounts for council members, characters, users, and government
- **Taxation** — Configurable tax rates on transfers with an append-only ledger
- **Salary / Payroll** — Automatic periodic payroll for all active entities
- **Store Purchases** — Buy items from world stores, funds routed through the treasury

### ⭐ Reputation

Event-sourced reputation system with six tiers from **Legendary** (+20% vote weight, store discounts, proposal fast-track) down to **Disgraced** (proposal restrictions, price penalties). Features a 120-day decay half-life, automated recording from all major actions, and a leaderboard dashboard with tier badges and event timelines. All gameplay effects are individually toggleable.

### 🧠 Intelligence

- **Memory System** — Per-agent memories (core beliefs + session log) with shared council memory
- **Memory Decay** — Exponential time decay on memories with configurable half-life (30 days) and floor
- **Memory Summarization** — LLM-driven summarization of old session memories to keep context fresh
- **Contested Memories** — Small chance (3%) agents record divergent recollections of the same event
- **Semantic Embeddings** — Optional `sentence-transformers` integration for hybrid semantic + keyword relevance scoring, with configurable model selection and mode toggles in Settings
- **Context Budget Manager** — Token budget system distributing context across competing sources with tiered injection profiles
- **Rolling Conversation Summary** — Auto-summarization of long conversations to fit context windows
- **Narrative Engine** — "Jericho Times" news bulletins generated from recent events, displayed on the dashboard

### 🎨 Image Generation (ComfyUI)

- **ComfyUI Integration** — Async client for local ComfyUI with workflow templates and prompt generation
- **5 Prompt Modes** — Council vote, character-driven, system, user+refinement, or raw user prompts
- **Style Presets** — Custom presets with import/export, batch generation for up to 10 entities
- **Entity Galleries** — Thumbnail grids with lightbox viewer, set-primary, delete, download, and prompt info
- **Generation Queue** — Live-polling dashboard with status cards, progress events, and cancel support

### 🖥️ Web Dashboard

A full-featured dark-mode SPA with glassmorphism design, SSE streaming, and multiple appearance skins (Frutiger Aero, Y2K, Vaporwave). Highlights:

- **Dashboard** — Activity timeline, quick-action buttons, system health panel, world summary cards, onboarding for fresh installs
- **Analytics** — 20+ aggregate metrics: participation rates, voting patterns, proposal success rates
- **Settings** — API keys, model selection, user profile, appearance skins, ComfyUI config, workflow templates, style presets, embedding mode controls
- **Full API** — All features accessible programmatically at `/api/*`

### 🖥️ CLI

A `jericho` command with rich terminal output is also available for everything — proposals, voting, characters, analytics, memory, reports, and more. Run `jericho --help` to explore.

---

## How Governance Works

| Parameter | Value |
|-----------|-------|
| **Approval Threshold** | 60% of votes |
| **Quorum** | 5 of 9 members |
| **Human Veto** | Always available |
| **Vote Weight** | Configurable per member, modulated by reputation tier |

### Lifecycle Flows

```
Proposals:  draft → open → under_review → decided (approved/rejected)
                                            ↕ withdrawn

Characters: draft → proposed → voting → decided → applied
                                  ↓
                               rejected

Laws:       draft → active ↔ archived
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `click` | CLI framework |
| `rich` | Terminal formatting |
| `httpx` | Async HTTP (LLM & ComfyUI) |
| `pyyaml` | YAML council profiles |
| `python-dotenv` | Environment variables |
| `cryptography` | Fernet AES key encryption |
| `fastapi` + `uvicorn` | Web dashboard |
| `sentence-transformers` | Semantic memory scoring |

All dependencies (including semantic memory via `sentence-transformers`) are installed automatically.

---

## For Developers

<details>
<summary><strong>Project Structure</strong></summary>

```
jericho/
├── config/
│   ├── settings.py              # Centralized configuration & all paths
│   └── .env                     # API keys (git-ignored, encrypted at rest)
│
├── core/                        # Python modules (54 files)
│   ├── api_client.py            # Async OpenRouter / Mancer / LM Studio client
│   ├── registry.py              # Council member loading & editing
│   ├── memory.py                # Per-agent & shared memory stores
│   ├── proposals.py             # Proposal lifecycle & management
│   ├── voting.py                # Vote casting, tally, quorum, veto
│   ├── characters.py            # Character template CRUD
│   ├── exploration.py           # Visual location exploration
│   ├── exploration_state.py     # Feature-centric movement engine
│   ├── story.py                 # Story → Chapter → Scene management
│   ├── reputation.py            # Event-sourced reputation tracker
│   ├── treasury.py              # Obelisk monetary system
│   ├── ...                      # 42 additional domain modules
│   ├── routes/                  # FastAPI route modules (23 files)
│   └── web_static/              # SPA frontend
│       ├── css/                 # 38 CSS modules
│       └── js/                  # 28 JS modules
│
├── council/members/             # 9+ YAML council profiles
├── data/                        # All persistent data (git-ignored)
├── tests/                       # pytest suite (67 test files)
├── start.bat                    # One-click Windows launcher
├── start.sh                     # One-click macOS / Linux launcher
└── README.md                    # This file
```

</details>

<details>
<summary><strong>Architecture Principles</strong></summary>

1. **Orchestrator-mediated** — Python handles all I/O; agents respond with natural language only
2. **Filesystem-backed** — JSON files with atomic writes. No database required
3. **Frozen dataclasses** — Immutable data models with `to_dict()` / `from_dict()` roundtrips
4. **Manager pattern** — Each domain has a Manager class with consistent CRUD + lifecycle methods
5. **Lifecycle state machines** — Validated transitions via `_VALID_TRANSITIONS` dicts
6. **Constructor injection** — Full testability with mocks
7. **Thread-safe IDs** — `threading.Lock` for atomic ID generation
8. **Graceful degradation** — Optional features degrade safely when unavailable
9. **Feature flags** — Gameplay-affecting systems are individually toggleable

</details>

<details>
<summary><strong>Running Tests</strong></summary>

```bash
python -m pytest tests/ -v --tb=short    # Full suite
python -m pytest tests/ -q               # Quick summary
python -m pytest tests/ --cov=core       # With coverage
```

</details>

<details>
<summary><strong>Configuration Reference</strong></summary>

All configuration lives in `config/settings.py`. Key settings:

**Governance:** approval threshold (60%), quorum (5), max council size (15), discussion rounds (2–10)

**Economy:** 100:1 conversion rate, 200 Gold default balance, 5% tax rate, 7-day salary interval

**Reputation:** 120-day decay half-life, 10% score floor, toggleable vote weight / store prices / fast-track / disgraced restrictions

**Memory:** decay half-life (30 days), summarization threshold (6 sessions), contested probability (3%), cache TTL (300s), context budget (32K tokens)

**Image Generation:** ComfyUI host/port, poll interval (1s), timeout (300s), max queue size (10), story limits (50 chapters, 20 scenes)

**Exploration:** imaginative mode (enabled by default), static/dynamic location tag classification

API keys are managed from the dashboard Settings page or via `JERICHO_OPENROUTER_API_KEY` / `JERICHO_MANCER_API_KEY` environment variables.

</details>

---

## License

MIT
