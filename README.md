# Jericho — AI Council

> *An AI city where LLM agents collaboratively design and evolve AI characters through democratic governance.*

## Overview

Jericho is a **human-orchestrated AI council system** where 9 LLM agents (via OpenRouter and Mancer APIs) work together to design, debate, and refine AI character prompts. The council operates through proposals, discussions, and democratic voting — creating a living governance system that evolves over time.

## Architecture

The **orchestrator** (Python) handles all filesystem operations. Agents interact through structured natural language — they never need tool access or filesystem capabilities. This design sidesteps LLM tool-use reliability problems entirely.

```
Human triggers session → Orchestrator sends structured prompts → 
Agents respond with JSON → Orchestrator persists everything
```

## The Council

| Member | Role | Specialty |
|--------|------|-----------|
| **Sage** | Ethics Advisor | Safety, values, long-term consequences |
| **Spark** | Creative Director | Novel ideas, unconventional approaches |
| **Logic** | Systems Analyst | Consistency, structure, edge cases |
| **Echo** | Historian | Memory, precedent, institutional knowledge |
| **Forge** | Character Builder | Identity design, personality crafting |
| **Lens** | Quality Reviewer | Critique, refinement, standards |
| **Pulse** | Community Advocate | User impact, accessibility, empathy |
| **Drift** | Devil's Advocate | Contrarian perspectives, stress-testing |
| **Anchor** | Moderator | Consensus building, tiebreaking |

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Set up API keys
copy config\.env.example config\.env
# Edit config\.env with your OpenRouter and Mancer API keys

# 4. Verify setup
python -c "from config.settings import *; print('Jericho ready.')"
```

## Session Protocol

Each AI council session follows this loop:

1. **Context Load** — read memories, pending proposals, recent history
2. **Council Briefing** — each member receives context via API call
3. **Activity Phase** — propose, discuss, vote, or create
4. **Record** — orchestrator writes all outputs to filesystem
5. **Summary** — human receives a session report

## Governance

- **60% approval threshold** for proposals
- **Quorum: 5 of 9** members must vote
- **Human veto** power on all decisions
- Each member has **1 vote** with equal weight

## Project Structure

```
jericho/
├── config/         # Settings, API keys
├── core/           # Python modules (orchestrator, API client, governance)
├── council/
│   ├── members/    # YAML profiles for each council member
│   └── templates/  # Prompt templates for activities
├── data/
│   ├── prompts/    # Evolved character/system prompts
│   ├── proposals/  # Pending and archived proposals
│   ├── votes/      # Vote records
│   ├── characters/ # Created AI characters
│   ├── memories/   # Per-agent persistent memories
│   └── conversations/  # Chat logs
├── tests/
├── scripts/
└── features.json   # Feature backlog
```

## License

MIT
