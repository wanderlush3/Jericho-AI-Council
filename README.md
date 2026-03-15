# Jericho — AI Council

> *An AI city where LLM agents collaboratively design and evolve AI characters through democratic governance.*

---

## Overview

Jericho is a **human-orchestrated AI council system** where 9 LLM agents (powered by [OpenRouter](https://openrouter.ai/) and [Mancer](https://mancer.tech/) APIs) work together to design, debate, and refine AI character prompts. The council operates through proposals, structured discussions, and democratic voting — creating a living governance system that evolves over time.

The key architectural principle is simple: the **Python orchestrator** handles all filesystem operations and API calls while agents interact purely through structured natural language. Agents never need tool access or filesystem capabilities — this design sidesteps LLM tool‑use reliability problems entirely.

```
Human triggers action → Orchestrator sends structured prompts →
Agents respond naturally → Orchestrator persists everything
```

---

## The Council

Nine specialized AI personas form the council. Each member has a defined role, personality, and area of expertise:

| Member     | Role              | Specialty                                  | Provider    |
|------------|-------------------|--------------------------------------------|-------------|
| **Sage**   | Ethics Advisor    | Safety, values, long‑term consequences     | OpenRouter  |
| **Spark**  | Creative Director | Novel ideas, unconventional approaches     | OpenRouter  |
| **Logic**  | Systems Analyst   | Consistency, structure, edge cases         | OpenRouter  |
| **Echo**   | Historian         | Memory, precedent, institutional knowledge | Mancer      |
| **Forge**  | Character Builder | Identity design, personality crafting      | OpenRouter  |
| **Lens**   | Quality Reviewer  | Critique, refinement, standards            | Mancer      |
| **Pulse**  | Community Advocate| User impact, accessibility, empathy        | Mancer      |
| **Drift**  | Devil's Advocate  | Contrarian perspectives, stress‑testing    | OpenRouter  |
| **Anchor** | Moderator         | Consensus building, tiebreaking            | OpenRouter  |

Council member profiles are defined as YAML files in `council/members/`. Each profile includes personality traits, specialties, and a full system prompt.

---

## Features

Jericho ships with 22 implemented features organized in six tiers:

### Core Infrastructure
- **API Client** — Unified async client for OpenRouter & Mancer with retry, rate limiting, structured response parsing
- **Council Registry** — Load, list, and validate YAML council member profiles
- **Memory System** — Per‑agent memories (core beliefs + session log) and shared council memory
- **Shared Utilities** — Atomic file writes, common helpers

### Governance
- **Proposal System** — Create, review, and track proposals with lifecycle state machine (`draft → open → under_review → decided`)
- **Voting Engine** — Cast votes, tally results, quorum/threshold checks, human veto power
- **Discussion Rounds** — Structured multi‑agent deliberation on proposals before voting
- **Council Expansion** — Propose and vote on adding new council members

### Communication
- **Agent‑to‑Agent Chat** — Orchestrator‑mediated conversations between council members
- **Human‑to‑Agent Chat** — Direct conversations with individual council members
- **Council Sessions** — Full session lifecycle: briefing, activity, summary, and memory persistence

### Character System
- **Character Templates** — Structured format for AI character definitions with traits, backstory, and prompts
- **Collaborative Design** — Multi‑phase workflow where council members co‑create characters
- **Character Evolution** — Propose and vote on modifications to existing characters via governance
- **Prompt Evolution History** — Visual timeline of how characters changed over council decisions

### Intelligence
- **Memory Influence** — Memories affect agent responses via context injection with relevance scoring
- **Session Analytics** — Participation rates, voting patterns, proposal success rates, member activity

### User Interfaces
- **CLI Interface** — Click‑based `jericho` command with rich subcommands
- **Rich Terminal Dashboard** — Beautiful terminal output with tables, panels, and status colours
- **Web Dashboard** — Browser‑based SPA with FastAPI backend (dark‑mode, glassmorphism design)
- **Governance Reports** — Export council activity as structured Markdown documents
- **Integration Test Suite** — 1,318 tests with cross‑module integration coverage

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

# 4. Set up API keys
copy config\.env.example config\.env
# Edit config\.env with your API keys:
#   JERICHO_OPENROUTER_API_KEY=sk-or-...
#   JERICHO_MANCER_API_KEY=...

# 5. Verify setup
jericho status
```

### One‑Click Start (Windows)

A `start.bat` file is provided in the project root. Double‑click it or run from a terminal:

```batch
start.bat
```

This will activate the virtual environment (creating one if needed), install dependencies, and launch the web dashboard at **http://127.0.0.1:8080**.

---

## CLI Reference

After installation, the `jericho` command is available with the following subcommands:

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

## Web Dashboard

Launch the browser‑based dashboard:

```bash
jericho web
```

Then open **http://127.0.0.1:8080** in your browser. The dashboard provides a dark‑mode SPA with views for:

- **Dashboard** — Overview with member, proposal, vote, and character counts
- **Council** — Member list and detail views
- **Proposals** — Browse proposals with status filtering
- **Votes** — Vote records with visual approval bars
- **Characters** — Character templates with trait displays
- **Analytics** — Aggregate statistics and participation data

The backend API is also available directly at `/api/*` for programmatic access.

---

## Governance Model

The council governs through a democratic process with built‑in safeguards:

| Parameter             | Value          |
|-----------------------|----------------|
| **Approval Threshold**| 60% of votes   |
| **Quorum**            | 5 of 9 members |
| **Human Veto**        | Always available on any decision |
| **Vote Weight**       | Equal (1 per member) |

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

---

## Session Protocol

Each AI council session follows a structured five‑phase loop:

1. **Context Load** — Read memories, pending proposals, recent history
2. **Council Briefing** — Each participant receives context via API call; memories are injected based on relevance scoring
3. **Activity Phase** — Propose, discuss, vote, design characters, or chat
4. **Record** — Orchestrator persists all outputs to the filesystem
5. **Summary** — Each member provides session takeaways; summary written to shared memory

---

## Project Structure

```
jericho/
├── config/
│   ├── settings.py            # Centralized configuration & paths
│   ├── .env.example           # API key template
│   └── .env                   # Your API keys (git-ignored)
│
├── core/                      # All Python modules
│   ├── api_client.py          # Async OpenRouter / Mancer client
│   ├── registry.py            # Council member loading & validation
│   ├── memory.py              # Per-agent & shared memory stores
│   ├── memory_influence.py    # Relevance scoring & context injection
│   ├── proposals.py           # Proposal lifecycle & management
│   ├── voting.py              # Vote casting, tally, quorum, veto
│   ├── session.py             # Council session orchestrator
│   ├── discussion.py          # Multi-agent proposal discussions
│   ├── agent_chat.py          # Agent-to-agent conversations
│   ├── human_chat.py          # Human-to-agent conversations
│   ├── characters.py          # Character template CRUD
│   ├── character_design.py    # Collaborative multi-phase design
│   ├── character_evolution.py # Governance-backed modifications
│   ├── evolution_history.py   # Version chain & diff engine
│   ├── council_expansion.py   # Add new council members
│   ├── analytics.py           # Read-only aggregation engine
│   ├── reports.py             # Markdown report generator
│   ├── cli.py                 # Click CLI entry point
│   ├── dashboard.py           # Rich terminal renderer
│   ├── web_api.py             # FastAPI backend
│   ├── web_static/            # SPA frontend (HTML/CSS/JS)
│   └── utils.py               # Shared utilities (atomic writes)
│
├── council/
│   └── members/               # 9 YAML profiles (Sage, Spark, etc.)
│
├── data/                      # All persistent data (git-ignored)
│   ├── proposals/             # P-XXXX.json proposal files
│   ├── votes/                 # V-P-XXXX.json vote records
│   ├── characters/            # CH-XXXX.json character templates
│   ├── character_designs/     # CD-XXXX.json design workflows
│   ├── character_evolutions/  # EV-XXXX.json evolution records
│   ├── council_expansions/    # EX-XXXX.json expansion records
│   ├── discussions/           # D-XXXX.json discussion records
│   ├── conversations/         # C-XXXX.json chat logs
│   ├── memories/              # Per-agent & shared memory
│   ├── reports/               # Generated Markdown reports
│   └── prompts/               # Character & system prompts
│
├── tests/                     # 1,318 tests (pytest)
│   ├── conftest.py            # Shared fixtures
│   ├── test_integration.py    # Cross-module integration tests
│   └── test_*.py              # Per-module test suites
│
├── features.json              # Feature backlog tracker
├── progress_log.md            # Institutional memory (session history)
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

All 1,318 tests should pass in approximately 13 seconds.

---

## Configuration

All configuration is centralized in `config/settings.py`:

| Setting                    | Default        | Description                                    |
|----------------------------|----------------|------------------------------------------------|
| `APPROVAL_THRESHOLD`       | 0.60           | 60% of votes must be "for" to approve          |
| `QUORUM_MINIMUM`           | 5              | Minimum voters for a valid decision            |
| `MAX_COUNCIL_SIZE`         | 15             | Upper limit for council expansion              |
| `API_MAX_RETRIES`          | 3              | API call retry attempts                        |
| `API_TIMEOUT_SECONDS`      | 120            | API call timeout                               |
| `DEFAULT_DISCUSSION_ROUNDS`| 2              | Default rounds per discussion                  |
| `MAX_DISCUSSION_ROUNDS`    | 10             | Maximum discussion rounds                      |
| `WEB_PORT`                 | 8080           | Web dashboard port                             |

API keys are loaded from environment variables or `config/.env`:
- `JERICHO_OPENROUTER_API_KEY`
- `JERICHO_MANCER_API_KEY`

---

## Dependencies

| Package        | Purpose                              |
|----------------|--------------------------------------|
| `click`        | CLI framework                        |
| `rich`         | Terminal formatting (tables, panels) |
| `httpx`        | Async HTTP client for API calls      |
| `pyyaml`       | YAML parsing for council profiles    |
| `python-dotenv`| Environment variable loading         |
| `fastapi`      | Web dashboard backend                |
| `uvicorn`      | ASGI server for FastAPI              |

Dev dependencies: `pytest`, `pytest-asyncio`, `pytest-cov`

---

## License

MIT
