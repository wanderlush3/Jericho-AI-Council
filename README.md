# Jericho — AI Council

> *An AI city where LLM agents collaboratively govern, build worlds, and evolve characters through democratic processes and an emergent economy.*

---

## Overview

Jericho is a **human-orchestrated AI council system** where LLM agents (powered by [OpenRouter](https://openrouter.ai/), [Mancer](https://mancer.tech/), and [LM Studio](https://lmstudio.ai/) APIs) work together to govern a living world. Council members debate proposals, pass laws, manage a monetary economy, create characters and locations, and design items — all through democratic governance with human oversight.

The key architectural principle is simple: the **Python orchestrator** handles all filesystem operations and API calls while agents interact purely through structured natural language. Agents never need tool access or filesystem capabilities — this design sidesteps LLM tool-use reliability problems entirely.

```
Human triggers action → Orchestrator sends structured prompts →
Agents respond naturally → Orchestrator persists everything
```

---

## The Council

Nine specialized AI personas form the council. Each member has a defined role, personality, and area of expertise. Council membership is fully customizable — members can be renamed, re-modeled, and new members can be promoted from the character roster.

| Member     | Role              | Specialty                                  | Provider    |
|------------|-------------------|--------------------------------------------|-------------|
| **Sage**   | Ethics Advisor    | Safety, values, long‑term consequences     | OpenRouter  |
| **Spark**  | Creative Director | Novel ideas, unconventional approaches     | OpenRouter  |
| **Logic**  | Systems Analyst   | Consistency, structure, edge cases         | OpenRouter  |
| **Echo**   | Historian         | Memory, precedent, institutional knowledge | Mancer      |
| **Forge**  | Character Builder | Identity design, personality crafting      | OpenRouter  |
| **Lens**   | Quality Reviewer  | Critique, refinement, standards            | OpenRouter  |
| **Pulse**  | Community Advocate| User impact, accessibility, empathy        | Mancer      |
| **Drift**  | Devil's Advocate  | Contrarian perspectives, stress‑testing    | OpenRouter  |
| **Anchor** | Moderator         | Consensus building, tiebreaking            | OpenRouter  |

Council member profiles are defined as YAML files in `council/members/`. Each profile includes personality traits, specialties, and a full system prompt. Profiles are editable directly from the web dashboard, including custom avatar upload with zoom/pan framing.

---

## Features

Jericho ships with **79 implemented features** organized across ten domains, plus a narrative engine, semantic embeddings, image generation pipeline, reputation system, and a comprehensive web dashboard:

### Core Infrastructure
- **API Client** — Unified async client for OpenRouter, Mancer & LM Studio with retry, rate limiting, structured response parsing
- **Council Registry** — Load, list, validate, and edit YAML council member profiles with avatar management
- **Memory System** — Per‑agent memories (core beliefs + session log) and shared council memory (decisions + narrative history)
- **Manager Cache** — Centralized singleton cache for all manager instances, reducing redundant filesystem I/O across route modules
- **Shared Utilities** — Atomic file writes, common helpers
- **Embedding Provider** — Optional semantic text embeddings via `sentence-transformers` for advanced relevance scoring (falls back to keyword Jaccard similarity when unavailable)
- **Thread-Safe ID Generation** — Atomic `threading.Lock`-protected sequential ID generation across all 14 manager classes, preventing collisions under concurrent access

### Governance
- **Proposal System** — Create, review, and track proposals with lifecycle state machine (`draft → open → under_review → decided`)
- **Voting Engine** — Cast votes, tally results, quorum/threshold checks, human veto power, robust last-match vote parsing
- **Discussion Rounds** — Structured multi‑agent deliberation on proposals before voting
- **Council Expansion** — Propose and vote on adding new council members via governance system
- **Council Promotion** — Promote active characters to council membership directly from the web UI
- **Law System** — Structured law lifecycle (`draft → active ↔ archived`) with bidirectional reinstatement, linked to the proposal system
- **Council Sessions** — Open‑ended deliberation sessions with proposal handoff capability

### Reputation System
- **Reputation Infrastructure** — Event-sourced reputation tracker with immutable JSONL event records, on-demand score computation, and 120-day decay half-life
- **Reputation Tiers** — Six tiers (Legendary, Distinguished, Respected, Neutral, Dubious, Disgraced) with configurable default stances per entity
- **Automated Recording** — Hooks into voting, proposals, gifts, discussions, and sessions for automatic reputation event generation
- **Gameplay Effects** — Reputation-based vote weight modulation, store price adjustments, proposal fast-tracking, and disgraced entity restrictions (all toggleable via feature flags)
- **Reputation Dashboard** — Frontend leaderboard, entity detail views, event timelines, and tier badges

### Character System
- **Character Templates** — Structured format for AI character definitions with traits, backstory, and prompts
- **Collaborative Design** — Multi‑phase workflow where council members co‑create characters (concept → traits → backstory → prompt → review)
- **Character Evolution** — Propose and vote on modifications to existing characters via governance
- **Prompt Evolution History** — Visual timeline of how characters changed over council decisions with version diff engine
- **TavernCard PNG Export** — Embed character data in TavernCard v2 PNG format

### World Building
- **World Locations** — Hierarchical location system with features, lore, coordinates, and parent/child relationships (`draft → active → archived`)
- **World Items** — Item creation, lifecycle management, property system, multi-owner tracking, and LLM context injection
- **World Stores** — Commerce system with inventory CRUD, pricing in Obelisk currency, and treasury-integrated purchasing
- **Gift Giving** — Transfer item ownership between users, characters, and council members with auto-generated chat records

### Economy (The Obelisk)
- **Treasury System** — Three‑tier currency (Gold, Silver, Bronze at 100:1 conversion) with accounts for council members, characters, users, and government
- **Taxation System** — Configurable tax rates, account type exemptions, and append-only event ledger; tax collected on transfers
- **Salary / Payroll** — Automatic periodic payroll that credits council members, users, and active characters at configurable intervals

### Intelligence
- **Memory Influence** — Memories affect agent responses via context injection with relevance scoring (Jaccard keyword + optional semantic embeddings)
- **Context Budget Manager** — Global token budget system that distributes context window allocation across competing injection sources
- **Tiered Injection Profiles** — Priority-based context injection (persona → memories → world → extras) with configurable byte limits per tier
- **Rolling Conversation Summary** — Automatic summarization of long conversation histories to fit within context windows
- **Conditional Law Injection** — Laws injected into LLM context only when relevant to the current topic
- **Narrative Engine** — Template-driven "Jericho Times" news bulletins generated from recent in-world events, displayed on the dashboard with auto-cycling ticker
- **Session Analytics** — Participation rates, voting patterns, proposal success rates, member activity, and 20+ aggregate metrics

### Communication
- **Agent‑to‑Agent Chat** — Orchestrator‑mediated conversations between council members
- **Human‑to‑Agent Chat** — Direct conversations with individual council members, with user description context injection
- **Multi‑Party AI Chat** — Autonomous multi-member conversations with sequential turn-taking
- **Presence Wrappers (SilentPassa)** — `[PRESENT]`/`[SILENCE]` display wrappers for chat messages with toggleable UI
- **Chat Response Timers** — Per-message response time tracking with live pulsing timer during generation and permanent duration badges
- **Absent Response Handling** — Graceful handling of chat participants who don't respond
- **Task System** — Assign tasks to council members/characters with automated multi-round narrative execution via SSE streaming

### Image Generation (ComfyUI Integration)
- **ComfyUI Client** — Async HTTP client for the local ComfyUI API (queue workflows, poll status, download images via `/view`)
- **Image Manager** — Filesystem-backed entity image storage organized by entity type/ID with metadata, primary image flags, and serve/retrieve operations
- **Prompt Generation Engine** — Multi-mode LLM-driven prompt construction (5 modes: council vote, character, system, user+refinement, raw user) with style presets
- **ComfyUI Settings & Templates Web UI** — Connection config, drag-and-drop JSON template upload, placeholder preview, per-entity-type resolution settings
- **Entity Image Galleries** — Thumbnail grids on character/location/item/store detail pages with lightbox viewer, set-primary, delete, download, and prompt info tooltips
- **Generation Pipeline & Progress UI** — End-to-end generation flow with prompt mode selector modal, SSE real-time progress events, auto-gallery refresh, and cancel support
- **Custom Style Presets & Queue Dashboard** — User-defined style preset CRUD (import/export), batch generation for up to 10 entities, live-polling queue dashboard with status cards
- **Per-Entity-Type Workflow Templates** — Assign default ComfyUI workflows per entity type with smart fallback chain (explicit → entity_type match → first available)

### Exploration & Stories
- **Exploration Image Galleries** — Visual location exploration with "Look Around" scene generation, hero image overlays, scene gallery strips, and hierarchical location navigation (parent/children/siblings)
- **Explore Participant System** — Add up to 10 council members and/or characters to exploration experiences with full context injection (persona, beliefs, memories, traits, laws, locations, items)
- **Explore Chat** — Interactive round-based chat within exploration scenes; participants discuss locations via SSE streaming with round management and narration injection
- **Story Illustration System** — LLM-narrated story segments with inline generated illustrations; hierarchical Story → Chapter → Scene management with immersive book-like reader UI
- **Story Participant System** — Add up to 10 participants to narration and illustration with shared `_build_participant_context()` infrastructure
- **Story Chat** — Interactive round-based chat within story scenes; council members and characters discuss scenes via SSE streaming with 5-round limits and inline chat UI

### User Interfaces
- **CLI Interface** — Click‑based `jericho` command with rich subcommands
- **Rich Terminal Dashboard** — Beautiful terminal output with tables, panels, and status colours
- **Web Dashboard** — Full-featured browser SPA with FastAPI backend, dark mode, glassmorphism design, and theming
- **Sidebar Accordion Navigation** — Collapsible section headers with chevron indicators, CSS transitions, and localStorage persistence
- **Governance Reports** — Export council activity as structured Markdown documents
- **Secure API Key Management** — Web-based API key configuration with Fernet AES encryption at rest
- **Appearance Skins** — Multiple UI themes including default dark mode, Frutiger Aero, Y2K, and Vaporwave
- **Evolution Traits Display** — Active evolution traits shown in council member badges and detail views
- **LM Studio Provider Badge** — Provider badge support for locally-hosted LM Studio models

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- API keys for [OpenRouter](https://openrouter.ai/) and/or [Mancer](https://mancer.tech/)

### Installation

```bash
# 1. Clone the repository
git clone <repo-url> jericho
cd jericho

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Optional: install embedding support
pip install -e ".[embeddings]"

# 5. Launch the web dashboard
jericho web
```

API keys can be configured directly from the web dashboard's **Settings** page — no need to manually edit `.env` files. Keys are encrypted at rest with Fernet (AES).

### One‑Click Start (Windows)

A `start.bat` file is provided in the project root. Double‑click it or run from a terminal:

```batch
start.bat
```

This will activate the virtual environment (creating one if needed), install dependencies, and launch the web dashboard at **http://127.0.0.1:8080**.

---

## Web Dashboard

Launch the browser‑based dashboard:

```bash
jericho web
```

Then open **http://127.0.0.1:8080** in your browser. The dashboard provides a dark‑mode SPA with:

### Navigation Sections

| Section | Views |
|---------|-------|
| **Overview** | Dashboard (stats, Jericho Times news ticker), Analytics (20+ metrics) |
| **Governance** | Proposals (create, discuss, vote via AI), Votes, Council Sessions, Laws, Reputation (leaderboard, tiers) |
| **Characters** | Character templates, Memories (per-member beliefs/events), Evolution (timeline, diff), Tasks |
| **World** | Chat (human-to-AI, AI-to-AI, multi-party), Explore, Stories, Locations, Items, Stores, Treasury, Taxation |
| **AI Image** | Generation Queue (live-polling status cards) |
| **Configuration** | Settings (API keys, models, user profile, appearance skins, ComfyUI config, workflow templates, style presets) |

### Key Capabilities

- **SSE Streaming** — Real-time AI responses in chat, proposal discussions, and image generation progress
- **Proposal Lifecycle** — Full governance flow: create → AI discussion rounds → AI voting → decision
- **Avatar System** — Upload and frame custom avatars for council members with zoom/pan editor
- **Reputation System** — Event-sourced leaderboards, tier badges, automated recording, gameplay effects
- **Treasury Management** — View accounts, credit/debit, transfer funds, initialize defaults
- **Store Commerce** — Create stores, manage inventory, purchase items with Obelisk currency
- **Gift Giving** — Transfer item ownership between entities with auto-generated chat records
- **Task Execution** — Assign and execute tasks with SSE-streamed narrative responses
- **Image Generation** — Generate & manage images for any entity via ComfyUI (5 prompt modes, style presets, batch generation, queue monitoring)
- **Exploration Mode** — Visual "Look Around" at locations with hero images, scene galleries, participant selection, and interactive chat
- **Story System** — Create illustrated stories with LLM narration, inline image generation, participant context, and interactive scene chat
- **Appearance Themes** — Default dark mode, Frutiger Aero (glossy Y2K), and more via Settings
- **Response Time Tracking** — Live timer and duration badges on chat messages for monitoring AI model performance

The backend API is also available directly at `/api/*` for programmatic access.

---

## CLI Reference

After installation, the `jericho` command is available:

```
jericho status                      # Project overview — counts and status
jericho council list                # List all council members
jericho council show <name>         # Show details for a council member

jericho proposals list [--status X] # List proposals (filter by status/category/author)
jericho proposals show <id>         # Show proposal details and reviews
jericho proposals create            # Create a new proposal

jericho vote list [--status X]      # List vote records
jericho vote show <proposal_id>     # Show vote details and tally
jericho vote cast                   # Cast a vote on a proposal
jericho vote veto <proposal_id>     # Exercise human veto power

jericho characters list [--status X]  # List character templates
jericho characters show <id>          # Show character details
jericho characters export <id>        # Export character as YAML

jericho analytics overview          # Aggregate analytics report
jericho analytics member <name>     # Analytics for a specific member

jericho memory beliefs <member>     # View a member's core beliefs
jericho memory recent <member>      # View recent memory entries

jericho history timeline <char_id>  # Character evolution timeline
jericho history diff <id1> <id2>    # Diff two character versions
jericho history list                # List all character lineages

jericho expansion list              # List expansion proposals
jericho expansion show <id>         # Show expansion detail

jericho report generate [--save]    # Generate governance report (Markdown)
jericho report list                 # List saved reports

jericho web                         # Launch the web dashboard (port 8080)
```

---

## Governance Model

The council governs through a democratic process with built‑in safeguards:

| Parameter             | Value          |
|-----------------------|----------------|
| **Approval Threshold**| 60% of votes   |
| **Quorum**            | 5 of 9 members |
| **Human Veto**        | Always available on any decision |
| **Vote Weight**       | Configurable per member (default: 1), modulated by reputation tier |

### Proposal Lifecycle

```
draft → open → under_review → decided
  ↓                              ↑ ↓
  └──── withdrawn ←──────────────┘ └─→ (approved / rejected)
```

### Character Evolution Lifecycle

```
draft → proposed → voting → decided → applied
                     ↓
                  rejected
```

### Law Lifecycle

```
draft → active ↔ archived
```

Laws can be reactivated from archived status, allowing for temporary suspension and reinstatement.

### Reputation Tiers

| Tier | Score Range | Effects |
|------|-------------|---------|
| **Legendary** | ≥ 200 | +20% vote weight, −10% store prices, proposal fast-track |
| **Distinguished** | 100–199 | +10% vote weight, −5% store prices |
| **Respected** | 50–99 | +5% vote weight |
| **Neutral** | 0–49 | No modifiers (default) |
| **Dubious** | −25 to −1 | −10% vote weight |
| **Disgraced** | ≤ −26 | Cannot author proposals, +15% store prices |

Reputation is event-sourced with a 120-day decay half-life and a 10% score floor. All gameplay effects are independently toggleable via feature flags.

---

## Economy — The Obelisk

Jericho uses a three‑tier currency system called the **Obelisk**:

| Tier | Symbol | Conversion |
|------|--------|------------|
| **Gold** | 🥇 | 1 Gold = 100 Silver = 10,000 Bronze |
| **Silver** | 🥈 | 1 Silver = 100 Bronze |
| **Bronze** | 🥉 | Base unit |

### Account Types

| Type | Default Balance | Salary |
|------|----------------|--------|
| **Council Member** | 200 Gold | 200 Gold / 7 days |
| **User** | 200 Gold | 200 Gold / 7 days |
| **Character** | 200 Gold | 100 Gold / 7 days |
| **Government** | 1,000 Gold | Tax revenue |

### Taxation

Transfers between non-government accounts are taxed at a configurable rate (default 5%). Tax is collected from the recipient and credited to the government treasury. Government accounts are exempt.

### Stores

World stores list items for sale with Obelisk pricing. Purchases route funds from buyer to store owner (or government if no owner) via the treasury transfer system. Store types include: general, blacksmith, alchemist, enchanter, tavern, and custom.

---

## Project Structure

```
jericho/
├── config/
│   ├── settings.py            # Centralized configuration & all paths
│   ├── .env.example           # API key template
│   └── .env                   # Your API keys (git-ignored, encrypted at rest)
│
├── core/                      # All Python modules (53 files)
│   ├── api_client.py          # Async OpenRouter / Mancer / LM Studio client
│   ├── api_keys.py            # Fernet-encrypted API key management
│   ├── registry.py            # Council member loading, validation, editing
│   ├── memory.py              # Per-agent & shared memory stores
│   ├── memory_influence.py    # Relevance scoring & context injection
│   ├── embeddings.py          # Semantic embedding provider (optional)
│   ├── proposals.py           # Proposal lifecycle & management
│   ├── voting.py              # Vote casting, tally, quorum, veto, prompt/parser
│   ├── laws.py                # Law system (draft/active/archived)
│   ├── law_filter.py          # Conditional law injection logic
│   ├── session.py             # Council session orchestrator
│   ├── council_session.py     # Open-ended deliberation sessions
│   ├── discussion.py          # Multi-agent proposal discussions
│   ├── agent_chat.py          # Agent-to-agent conversations
│   ├── human_chat.py          # Human-to-agent conversations
│   ├── chat_helpers.py        # Shared chat utility functions
│   ├── chat_streaming.py      # SSE streaming for chat responses
│   ├── characters.py          # Character template CRUD & lifecycle
│   ├── character_design.py    # Collaborative multi-phase design
│   ├── character_evolution.py # Governance-backed character modifications
│   ├── evolution_history.py   # Version chain & diff engine
│   ├── council_expansion.py   # Add new council members via governance
│   ├── locations.py           # World location management
│   ├── items.py               # World item management (multi-owner, gifting)
│   ├── stores.py              # World store & commerce system
│   ├── treasury.py            # Obelisk monetary system
│   ├── taxation.py            # Tax policy, collection, & ledger
│   ├── salary.py              # Automatic payroll system
│   ├── reputation.py          # Event-sourced reputation tracker
│   ├── reputation_hooks.py    # Automated reputation event recording
│   ├── reputation_effects.py  # Gameplay modifiers from reputation tiers
│   ├── tasks.py               # Task assignment & execution
│   ├── narrative_engine.py    # Template-driven news bulletins
│   ├── analytics.py           # Read-only analytics engine (20+ metrics)
│   ├── reports.py             # Markdown report generator
│   ├── png_embed.py           # TavernCard v2 PNG embedding
│   ├── context_builder.py     # Participant context assembly engine
│   ├── context_budget.py      # Global token budget manager
│   ├── injection_profiles.py  # Tiered context injection profiles
│   ├── conversation_summary.py # Rolling conversation summarization
│   ├── comfyui_client.py      # ComfyUI HTTP client & workflow templates
│   ├── image_manager.py       # Entity image storage & metadata
│   ├── prompt_builder.py      # Multi-mode prompt generation & style presets
│   ├── generation_pipeline.py # End-to-end image generation orchestrator
│   ├── template_assignments.py # Per-entity-type workflow defaults
│   ├── exploration.py         # Visual location exploration & scenes
│   ├── story.py               # Story → Chapter → Scene management
│   ├── manager_cache.py       # Centralized singleton cache for managers
│   ├── cli.py                 # Click CLI entry point
│   ├── dashboard.py           # Rich terminal renderer
│   ├── web_api.py             # Thin FastAPI compositor (~145 lines)
│   ├── utils.py               # Shared utilities (atomic writes)
│   ├── routes/                # Backend route modules (22 files + helpers)
│   │   ├── _helpers.py        # Shared cross-module helpers
│   │   ├── council.py         # /api/council endpoints
│   │   ├── proposals.py       # /api/proposals endpoints
│   │   ├── characters.py      # /api/characters endpoints
│   │   ├── chat.py            # /api/chat endpoints
│   │   ├── sessions.py        # /api/sessions endpoints
│   │   ├── votes.py           # /api/votes endpoints
│   │   ├── evolutions.py      # /api/evolutions endpoints
│   │   ├── explore.py         # /api/explore endpoints
│   │   ├── stories.py         # /api/stories endpoints
│   │   ├── generation.py      # /api/generate endpoints
│   │   ├── settings.py        # /api/settings endpoints
│   │   ├── locations.py       # /api/locations endpoints
│   │   ├── items.py           # /api/items endpoints
│   │   ├── stores.py          # /api/stores endpoints
│   │   ├── treasury.py        # /api/treasury endpoints
│   │   ├── memories.py        # /api/memories endpoints
│   │   ├── laws.py            # /api/laws endpoints
│   │   ├── images.py          # /api/images endpoints
│   │   ├── tasks.py           # /api/tasks endpoints
│   │   ├── reputation.py      # /api/reputation endpoints
│   │   └── status.py          # /api/status endpoint
│   └── web_static/            # SPA frontend
│       ├── index.html         # HTML shell with accordion nav sidebar
│       ├── css/               # 35 CSS modules (~10,000 lines)
│       │   ├── tokens.css     # Design tokens (:root variables)
│       │   ├── base.css       # Reset & base styles
│       │   ├── layout.css     # Layout + sidebar
│       │   ├── skins.css      # Theme skins (Frutiger Aero, Y2K, Vaporwave)
│       │   └── [feature].css  # Per-feature styles (council, chat, explore, reputation, etc.)
│       └── js/                # 27 JS modules (~14,300 lines)
│           ├── core.js        # api(), navigateTo(), renderView(), showToast()
│           ├── dashboard.js   # renderDashboard(), narrative banner
│           ├── council.js     # renderCouncil(), renderCouncilDetail()
│           ├── explore.js     # renderExplore(), participant selection, chat
│           ├── stories.js     # renderStories(), reader, scene chat
│           ├── reputation.js  # renderReputation(), leaderboard, event timeline
│           └── ...            # 21 additional feature modules
│
├── council/
│   ├── members/               # 9+ YAML profiles
│   └── avatars/               # Uploaded avatar PNGs + metadata
│
├── data/                      # All persistent data (git-ignored)
│   ├── proposals/             # P-XXXX.json
│   ├── votes/                 # V-P-XXXX.json
│   ├── characters/            # CH-XXXX.json
│   ├── character_designs/     # CD-XXXX.json
│   ├── character_evolutions/  # EV-XXXX.json
│   ├── council_expansions/    # EX-XXXX.json
│   ├── council_sessions/      # CS-XXXX.json
│   ├── discussions/           # D-XXXX.json
│   ├── conversations/         # C-XXXX.json / H-XXXX.json
│   ├── laws/                  # LAW-XXXX.json
│   ├── locations/             # LOC-XXXX.json
│   ├── items/                 # ITEM-XXXX.json
│   ├── stores/                # STORE-XXXX.json
│   ├── tasks/                 # TK-XXXX.json
│   ├── treasury/              # ACCT-*.json
│   ├── reputation/            # {member|character}_name.jsonl event logs
│   ├── memories/              # Per-agent & shared memory
│   ├── reports/               # Generated Markdown reports
│   ├── prompts/               # Character & system prompts
│   ├── comfyui/               # ComfyUI config, templates, presets
│   │   ├── templates/         # TPL-XXXX.json workflow templates
│   │   ├── presets/           # PST-XXXX.json custom style presets
│   │   └── template_assignments.json
│   ├── images/                # Generated & uploaded images
│   │   └── {entity_type}/
│   │       └── {entity_id}/   # Per-entity image files + images.json
│   ├── exploration/           # Exploration scene metadata
│   └── stories/               # ST-XXXX.json story files
│
├── tests/                     # 3,797 tests (pytest)
│   ├── conftest.py            # Shared fixtures & manager cache invalidation
│   ├── test_integration.py    # Cross-module integration tests
│   └── test_*.py              # 66 per-module test suites
│
├── features.json              # Feature backlog tracker (79 features)
├── claude.md                  # AI assistant coding guidelines
├── LICENSE                    # MIT license
├── pyproject.toml             # Project config & dependencies
├── start.bat                  # One-click launcher (Windows)
└── README.md                  # This file
```

---

## Running Tests

```bash
# Full test suite
python -m pytest tests/ -v --tb=short

# Quick summary
python -m pytest tests/ -q

# With coverage
python -m pytest tests/ --cov=core --cov-report=term-missing
```

The full suite of **3,797 tests** should pass in approximately 90–100 seconds.

---

## Configuration

All configuration is centralized in `config/settings.py`:

### Governance

| Setting                    | Default        | Description                                    |
|----------------------------|----------------|------------------------------------------------|
| `APPROVAL_THRESHOLD`       | 0.60           | 60% of votes must be "for" to approve          |
| `QUORUM_MINIMUM`           | 5              | Minimum voters for a valid decision            |
| `MAX_COUNCIL_SIZE`         | 15             | Upper limit for council expansion              |
| `DEFAULT_DISCUSSION_ROUNDS`| 2              | Default rounds per discussion                  |
| `MAX_DISCUSSION_ROUNDS`    | 10             | Maximum discussion rounds                      |

### Economy

| Setting                         | Default        | Description                              |
|---------------------------------|----------------|------------------------------------------|
| `OBELISK_CONVERSION_RATE`       | 100            | Bronze per Silver, Silver per Gold       |
| `OBELISK_DEFAULT_BALANCE`       | 200 Gold       | Starting balance for new accounts        |
| `OBELISK_GOVERNMENT_BALANCE`    | 1,000 Gold     | Initial government treasury              |
| `TAX_DEFAULT_RATE`              | 0.05           | 5% tax on non-exempt transfers           |
| `SALARY_INTERVAL_DAYS`          | 7              | Days between payroll runs                |
| `SALARY_COUNCIL_USER_AMOUNT`    | 200            | Gold per payroll for council/user        |
| `SALARY_CHARACTER_AMOUNT`       | 100            | Gold per payroll for active characters   |

### Reputation

| Setting                         | Default        | Description                              |
|---------------------------------|----------------|------------------------------------------|
| `REPUTATION_DECAY_HALF_LIFE_DAYS` | 120          | Days for event score to decay by 50%     |
| `REPUTATION_DECAY_FLOOR`       | 0.10           | Minimum decay multiplier (10%)           |
| `REPUTATION_VOTE_WEIGHT_ENABLED` | `True`        | Enable vote weight modulation by tier    |
| `REPUTATION_STORE_PRICES_ENABLED` | `True`       | Enable store price adjustments by tier   |
| `REPUTATION_FAST_TRACK_ENABLED` | `True`         | Enable proposal fast-tracking by tier    |
| `REPUTATION_RESTRICT_DISGRACED` | `True`         | Restrict actions for disgraced entities  |

### API & Server

| Setting                    | Default        | Description                                    |
|----------------------------|----------------|------------------------------------------------|
| `API_MAX_RETRIES`          | 3              | API call retry attempts                        |
| `API_TIMEOUT_SECONDS`      | 120            | API call timeout                               |
| `WEB_PORT`                 | 8080           | Web dashboard port                             |

### Memory & Intelligence

| Setting                              | Default   | Description                                   |
|--------------------------------------|-----------|-----------------------------------------------|
| `MEMORY_INFLUENCE_MAX_MEMORIES`      | 10        | Max session memories in context injection      |
| `MEMORY_INFLUENCE_MAX_BELIEFS`       | 5         | Max core beliefs in context injection          |
| `MEMORY_INFLUENCE_MIN_RELEVANCE`     | 0.1       | Minimum relevance score threshold              |
| `MEMORY_INFLUENCE_BELIEF_BOOST`      | 1.5       | Score multiplier for core beliefs              |
| `NARRATIVE_MAX_BULLETINS`            | 10        | Max news bulletins on dashboard                |
| `NARRATIVE_MAX_AGE_DAYS`             | 30        | Event age window for narrative generation      |
| `EMBEDDING_MODEL_NAME`              | `all-MiniLM-L6-v2` | Sentence-transformers model (optional) |

### Image Generation (ComfyUI)

| Setting                              | Default             | Description                                   |
|--------------------------------------|---------------------|-----------------------------------------------|
| `COMFYUI_DEFAULT_HOST`               | `127.0.0.1`         | ComfyUI server address (local only)           |
| `COMFYUI_DEFAULT_PORT`               | `8188`              | ComfyUI server port                           |
| `COMFYUI_MAX_QUEUE_SIZE`             | 10                  | Maximum concurrent generation jobs in queue   |
| `STORY_MAX_CHAPTERS`                 | 50                  | Maximum chapters per story                    |
| `STORY_MAX_SCENES_PER_CHAPTER`       | 20                  | Maximum scenes per chapter                    |

ComfyUI connection and workflow templates can be configured from the web dashboard **Settings → ComfyUI** tab.

API keys are managed from the web dashboard Settings page or via environment variables:
- `JERICHO_OPENROUTER_API_KEY`
- `JERICHO_MANCER_API_KEY`

---

## Dependencies

| Package            | Purpose                              |
|--------------------|--------------------------------------|
| `click`            | CLI framework                        |
| `rich`             | Terminal formatting (tables, panels) |
| `httpx`            | Async HTTP client for LLM & ComfyUI  |
| `pyyaml`           | YAML parsing for council profiles    |
| `python-dotenv`    | Environment variable loading         |
| `cryptography`     | Fernet AES encryption for API keys   |
| `fastapi`          | Web dashboard backend                |
| `uvicorn`          | ASGI server for FastAPI              |

**Optional:** `sentence-transformers` (install via `pip install -e ".[embeddings]"`) for semantic embedding-based memory relevance scoring.

**Dev dependencies:** `pytest`, `pytest-asyncio`, `pytest-cov`

---

## Architecture Principles

1. **Orchestrator-mediated** — The Python backend handles all filesystem I/O and API calls. Agents respond with structured natural language only.
2. **Filesystem-backed** — All data is stored as JSON files with atomic writes (temp + rename). No database required.
3. **Frozen dataclasses** — All data models are immutable frozen dataclasses with `to_dict()` / `from_dict()` roundtrip serialization.
4. **Manager pattern** — Each domain has a Manager class (e.g., `ProposalManager`, `CharacterManager`, `StoreManager`) with consistent CRUD + lifecycle methods.
5. **Lifecycle state machines** — All entities follow validated state transitions via `_VALID_TRANSITIONS` dicts.
6. **Constructor injection** — Managers accept dependencies via constructor for full testability with mocks.
7. **Thread-safe IDs** — All managers use `threading.Lock` for atomic ID generation, preventing collisions under concurrent access.
8. **Graceful degradation** — Optional features (embeddings, individual managers) degrade gracefully when unavailable. Reputation hooks never break primary workflows.
9. **Feature flags** — Gameplay-affecting systems (reputation effects) are individually toggleable without code changes.

---

## License

MIT
