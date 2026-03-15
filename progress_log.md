# Jericho — Progress Log (Institutional Memory)

> This file is the central memory of the project. Each AI agent session appends
> a structured entry below. **Never delete entries** — they are the historical
> record that future agents rely on for context.

---

## Session: S-INIT-00000001
**Timestamp:** 2026-03-13 22:30:00
**Feature:** `F-001` — Project Scaffolding
**Status:** completed

### Summary
Performed full project initialization for Jericho — the AI Council system:

- **Audited existing jericho01 codebase** — found 12 files with structural issues (missing imports, class mismatches, hardcoded paths, stub implementations). Preserved content files, flagged all Python code for rewrite.
- **Designed architecture** — orchestrator-mediated system where LLMs interact via structured prompts (no tool-use required). The Python orchestrator handles all filesystem I/O.
- **Scaffolded project at `c:\ai_tools\jericho\`:**
  - `config/settings.py` — paths, API config (OpenRouter + Mancer), governance thresholds (60% approval, 5/9 quorum)
  - `config/.env.example` — API key template
  - `pyproject.toml` — dependencies: httpx, click, rich, pyyaml, python-dotenv
  - `features.json` — 20-feature backlog across 6 tiers
  - `README.md` — project overview with council roster and architecture
  - `.gitignore` — API key protection, standard Python ignores
- **Created 9 council member YAML profiles** in `council/members/`:
  - Sage (Ethics), Spark (Creative), Logic (Systems), Echo (Historian), Forge (Character Builder), Lens (Quality), Pulse (Community), Drift (Devil's Advocate), Anchor (Moderator)
  - 5 use OpenRouter (Claude 3.5 Sonnet), 4 use Mancer (Celeste V1.9)
- **Migrated content from jericho01** — character prompt, system prompt, version history, 2 proposals, vote database
- **Created data directories** — prompts, proposals, votes, characters, memories (shared + per-member stubs), conversations

### Technical Debt
- No `__init__.py` for council package (intentional — it's data, not code)
- Per-member memory directories have stubs only — will be populated when memory system (F-004) is built
- Vote database format from jericho01 may need schema migration when voting engine (F-006) is built
- API keys not yet configured — user needs to create `config/.env` from template

### Advice for Next Agent
1. **F-002 (API Client), F-003 (Council Registry), F-004 (Memory System), and F-011 (Character Templates) are all unblocked** — they only depend on F-001
2. Start with F-002 (API Client) or F-003 (Council Registry) — they're foundational for everything else
3. Run `pip install -e ".[dev]"` in a venv before coding
4. User has API keys for both OpenRouter and Mancer — configure `config/.env`
5. The council member YAML profiles are the source of truth for agent identity — all system prompts live there
6. The architecture rule is: **orchestrator writes files, agents respond with structured text** — never give agents filesystem access

---

## Session: S-FEAT-00000002
**Timestamp:** 2026-03-13 23:25:00
**Feature:** `F-003` — Council Member Registry
**Status:** completed

### Summary
Implemented the council member registry system:

- **Created `core/registry.py`** — Two main components:
  - `CouncilMember` frozen dataclass — immutable representation of a member with all YAML fields (name, role, description, personality, api_provider, model, vote_weight, specialties, system_prompt, source_file). Includes `is_openrouter`/`is_mancer` convenience properties.
  - `CouncilRegistry` class — loads all `.yaml` files from members directory, validates each against the schema, stores in a dict keyed by lowercase name. Supports `get()` (case-insensitive), `list_members()` (sorted), `list_names()`, `members_by_provider()`, `validate()` (static), plus `__len__`, `__contains__`, `__iter__`.
  - Custom exceptions: `MemberNotFoundError(KeyError)`, `RegistryValidationError(ValueError)`.
- **Created `tests/test_registry.py`** — 39 tests across 5 test classes:
  - `TestRegistryLoading` (8 tests): real members, empty dir, nonexistent dir, custom member, duplicates, empty YAML
  - `TestRegistryQueries` (11 tests): exact/case-insensitive lookup, whitespace stripping, sorted listing, provider filtering
  - `TestCouncilMember` (4 tests): field verification, provider properties, frozen immutability
  - `TestValidation` (11 tests): missing fields, invalid provider, bad vote_weight, type checks
  - `TestDunderMethods` (5 tests): len, contains, iter, repr
- **All 39 tests pass** in 0.19s with no regressions.

### Technical Debt
- The actual provider split is 6 openrouter / 3 mancer (not 5/4 as stated in the S-INIT progress log). The progress log entry from S-INIT is inaccurate — Anchor uses openrouter, not mancer.
- No `__init__.py` updates needed — `core/__init__.py` exists and pytest pythonpath is configured.
- `test_out.txt` and `test_results.txt` and `tmp_status.txt` are temp files left in project root — should be gitignored or cleaned up.

### Advice for Next Agent
1. **F-002 (API Client), F-004 (Memory System), and F-011 (Character Templates) are the next unblocked features** — they only depend on F-001.
2. F-005 (Proposal System) is now also unblocked since F-003 is complete.
3. **F-002 (API Client) is recommended next** — it's the other foundational piece needed by the orchestrator (F-007) and chat features (F-008, F-009).
4. The registry is importable as: `from core.registry import CouncilRegistry, CouncilMember`
5. Usage pattern: `registry = CouncilRegistry().load()` — `load()` returns self for chaining.
6. The `sw` CLI has Unicode/encoding issues when run on this Windows terminal — use `subprocess` with `PYTHONIOENCODING=utf-8` or read data files directly.
7. Clean up temp files (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) before committing.

---

## Session: S-FEAT-00000003
**Timestamp:** 2026-03-15 09:11:00
**Feature:** `F-002` — API Client
**Status:** completed

### Summary
Implemented the unified async API client for OpenRouter and Mancer:

- **Created `core/api_client.py`** (~290 lines) — Three main components:
  - **Exception hierarchy**: `APIError` (base), `APIConnectionError` (network/timeout), `APIRateLimitError` (429), `APIAuthenticationError` (401/403, never retried).
  - **Data classes**: `ChatMessage` (frozen, with `to_dict()`), `ChatResponse` (frozen — content, model, provider, usage, raw response).
  - **`APIClient` class** — async context manager wrapping `httpx.AsyncClient`:
    - `chat(member, messages, temperature, max_tokens)` → `ChatResponse` — sends OpenAI-compatible `/chat/completions` requests
    - Smart retry: exponential backoff with jitter on 429 and 5xx; fail-fast on 401/403; no retry on other 4xx
    - Per-provider rate limiting via configurable minimum gap between requests
    - Keys loaded from constructor args or env vars (`JERICHO_OPENROUTER_API_KEY`, `JERICHO_MANCER_API_KEY`)
    - OpenRouter requests include `HTTP-Referer` and `X-Title` headers per their API requirements
    - System prompt from council member YAML automatically prepended as first message
- **Created `tests/test_api_client.py`** (~400 lines) — 45 tests across 9 classes:
  - `TestChatMessage` (3): fields, to_dict, frozen
  - `TestChatResponse` (3): fields, defaults, frozen
  - `TestAPIClientInit` (5): explicit keys, env keys, custom settings, context manager, close idempotency
  - `TestEndpointResolution` (5): OpenRouter URL+headers, Mancer URL+headers, unknown provider, missing keys
  - `TestRequestBuilding` (4): body shape, system prompt prepended, multi-turn messages, empty messages
  - `TestResponseParsing` (7): valid response, empty choices, missing keys, usage present/absent, raw preserved
  - `TestRetryBehavior` (10): success, auth fail-fast (401/403), 429 retry+success, 500 retry+success, max retries exhausted, connection error retry, timeout retry, 4xx no retry
  - `TestRateLimiting` (3): gap enforced, providers independent, no delay on first request
  - `TestExceptions` (5): field access, defaults, inheritance hierarchy
- **All 84 tests pass** (39 registry + 45 API client) in 3.23s with zero regressions.
- Added `pytest-asyncio` as a runtime dev dependency (used by async tests).

### Technical Debt
- `pytest-asyncio` is installed but not yet listed in `pyproject.toml` `[project.optional-dependencies].dev` — should be added.
- The `rate_limit_gap` default (0.5s) is a rough estimate — may need tuning once real API usage begins.
- No streaming support yet — `chat()` waits for full response. Streaming can be added later if needed.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-004 (Memory System), F-005 (Proposal System), and F-011 (Character Templates) are all unblocked** — F-004 and F-011 depend only on F-001; F-005 depends on F-003.
2. **F-007 (Council Session Orchestrator) is now unblocked once F-004 is also done** — it depends on F-002 + F-003 + F-004.
3. **F-008 (Agent-to-Agent Chat) and F-009 (Human-to-Agent Chat) are now unblocked once F-004 is done** — they depend on F-002 + F-004.
4. **F-004 (Memory System) is recommended next** — it's the other foundational piece needed by the orchestrator, both chat features, and memory influence.
5. The API client is importable as: `from core.api_client import APIClient, ChatMessage, ChatResponse`
6. Usage pattern: `async with APIClient() as client: resp = await client.chat(member, messages)`
7. All tests are fully mocked — no real API calls. To test against real APIs, set env vars and write integration tests separately.
8. Add `pytest-asyncio` to `pyproject.toml` dev dependencies.

---

## Session: S-FEAT-00000004
**Timestamp:** 2026-03-15 09:20:00
**Feature:** `F-004` — Memory System
**Status:** completed

### Summary
Implemented the per-agent and shared memory system for the Jericho AI Council:

- **Created `core/memory.py`** (~310 lines) — Four main components:
  - **Exception hierarchy**: `MemoryError` (base), `MemoryCorruptionError` (invalid data in memory files).
  - **Data classes**: `MemoryEntry` (frozen — timestamp, session_id, event_type, content, source, metadata dict) and `CoreBelief` (frozen — topic, content, added_timestamp, source). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **`AgentMemory` class** — per-member memory store:
    - Resolves `data/memories/<name>/` directory, creates if missing
    - `read_core_beliefs()` / `write_core_belief()` / `remove_core_belief()` — JSON file-backed, topic-keyed (upsert semantics)
    - `read_session_log()` / `append_session_event()` — JSONL append-only log, optional session_id filter
    - `get_recent_memories(limit)` — last N entries in reverse chronological order
  - **`SharedMemory` class** — council-wide memory:
    - `read_decisions()` / `record_decision()` — JSONL, skips `#` comment lines (compatible with existing stub)
    - `read_history()` / `append_history()` — markdown narrative history
  - **Atomic write helper** (`_atomic_write`) — write-to-tmp-then-rename pattern for corruption safety
- **Created `tests/test_memory.py`** (~370 lines) — 48 tests across 10 classes:
  - `TestMemoryEntry` (7): fields, defaults, frozen, to_dict, from_dict roundtrip, missing optionals, create factory
  - `TestCoreBelief` (5): fields, defaults, frozen, to_dict/from_dict roundtrip, create factory
  - `TestAgentMemoryInit` (5): dir creation, case-insensitive name, whitespace stripping, existing dir, paths
  - `TestCoreBeliefs` (9): read empty, write one/multiple, upsert same topic, remove existing/nonexistent, persistence, corrupt JSON, wrong type
  - `TestSessionLog` (7): read empty, append one/multiple, filter by session_id, JSONL format, corrupt line, persistence
  - `TestRecentMemories` (4): empty, limit, newest-first ordering, across sessions
  - `TestSharedMemory` (10): dir creation, decisions empty/read/record/multiple/comments/corrupt/format, history read/append
  - `TestAtomicWrites` (4): create, overwrite, nested dirs, no leftover tmps
  - `TestEdgeCases` (6): unicode beliefs/logs, empty file, blank lines, member isolation, large entries
- **All 142 tests pass** (84 existing + 48 new) in 3.49s with zero regressions.

### Technical Debt
- Existing `core_beliefs.md` stub files in per-member directories are markdown, but the new system uses `core_beliefs.json`. The old `.md` stubs are ignored (not harmful) but could be cleaned up.
- `_atomic_append` uses plain file append (not temp-file-rename) — acceptable for JSONL line-adds, but a mid-write crash could leave a partial line. This is a known JSONL trade-off.
- No max-size enforcement on session logs — very long-running projects may accumulate large `.jsonl` files. Consider adding rotation or archival later.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-005 (Proposal System), F-007 (Council Session Orchestrator), F-008 (Agent-to-Agent Chat), F-009 (Human-to-Agent Chat), and F-011 (Character Templates) are all now unblocked.**
   - F-007 depends on F-002 + F-003 + F-004 (all completed)
   - F-008 depends on F-002 + F-004 (all completed)
   - F-009 depends on F-002 + F-004 (all completed)
2. **F-005 (Proposal System) is recommended next** — it unlocks F-006 (Voting), F-010 (Discussion Rounds), and is simpler than the orchestrator.
3. The memory system is importable as: `from core.memory import AgentMemory, SharedMemory, MemoryEntry, CoreBelief`
4. Usage patterns:
   - `mem = AgentMemory("sage")` — loads from default `data/memories/sage/`
   - `mem.write_core_belief(CoreBelief.create("topic", "content", source="session"))` — auto-timestamps
   - `mem.append_session_event(MemoryEntry.create("S-001", "chat", "message"))` — auto-timestamps
   - `shared = SharedMemory()` — loads from default `data/memories/shared/`
5. All writes are synchronous. No async needed.
6. The old `core_beliefs.md` stubs in per-member dirs can be removed in a cleanup pass — the system does not read them.

---
