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

## Session: S-FEAT-00000005
**Timestamp:** 2026-03-15 09:29:00
**Feature:** `F-005` — Proposal System
**Status:** completed

### Summary
Implemented the proposal system for the Jericho AI Council:

- **Created `core/proposals.py`** (~350 lines) — Four main components:
  - **Exception hierarchy**: `ProposalError` (base), `ProposalNotFoundError`, `ProposalValidationError`, `ProposalLifecycleError`.
  - **Data classes**: `Review` (frozen — reviewer, stance, comment, timestamp) and `Proposal` (frozen — id, title, description, author, category, status, created_at, updated_at, body, reviews list, metadata dict). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Lifecycle state machine**: `draft → open → under_review → decided`, with `withdrawn` reachable from any non-terminal state. Transitions validated via `_VALID_TRANSITIONS` dict.
  - **`ProposalManager` class** — filesystem-backed, one JSON file per proposal (`P-XXXX.json`):
    - `create()` — auto-generates sequential `P-XXXX` IDs, validates required fields, saves as JSON
    - `get()` / `list_proposals()` — load by ID or list with optional filters (status, category, author)
    - `update_status()` — validates lifecycle transitions
    - `add_review()` — appends review, validates reviewer uniqueness (case-insensitive) and proposal status
    - `update()` — updates mutable fields only (title, description, body, category, metadata), rejects immutables
    - `withdraw()` — author-only withdrawal with identity verification
  - **Atomic writes** via temp-file + rename pattern (same as memory system)
- **Updated `config/settings.py`** — added `PROPOSAL_STATUSES`, `PROPOSAL_CATEGORIES`, `REVIEW_STANCES` tuples.
- **Created `tests/test_proposals.py`** (~400 lines) — 71 tests across 11 classes:
  - `TestReview` (5): fields, frozen, roundtrip, create factory, invalid stance
  - `TestProposal` (6): fields, frozen, roundtrip, create factory, invalid category, defaults
  - `TestProposalManagerInit` (3): directory creation, existing dir, repr
  - `TestProposalCreation` (8): basic, sequential IDs, persistence, body+metadata, invalid category, empty title/author, whitespace stripping
  - `TestProposalRetrieval` (7): get by ID, not found, list all, filter by status/category/author, empty list, combined filters
  - `TestStatusLifecycle` (12): valid transitions (draft→open→under_review→decided), invalid skip, terminal states, withdraw from draft/open/under_review, cannot withdraw from decided, cannot unwithdraw, unknown status
  - `TestReviews` (8): add review, multiple reviewers, duplicate rejected (case-insensitive), draft/decided rejected, under_review allowed, persistence
  - `TestProposalUpdate` (8): update title/body/category, invalid category, immutable fields rejected (id/author), not found, multiple fields
  - `TestWithdraw` (4): author can withdraw, case-insensitive, non-author rejected, cannot withdraw decided
  - `TestEdgeCases` (5): unicode, long body, corrupt JSON skipped, legacy .md ignored, ID sequencing with gaps
  - `TestExceptions` (4): hierarchy, not-found fields, validation fields, lifecycle fields
- **All 213 tests pass** (142 existing + 71 new) in 3.75s with zero regressions.

### Technical Debt
- Legacy markdown proposals (`2023-10-15_ethical_constraints.md`, `2023-10-16_curiosity_framework.md`) remain in `data/proposals/`. They are harmlessly ignored by `ProposalManager` (which only reads `P-*.json`), but could be cleaned up or migrated into JSON format.
- The `_atomic_write` helper in `proposals.py` is duplicated from `memory.py`. A shared utility module (`core/utils.py`) could be created to DRY this up.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-006 (Voting Engine) is now unblocked** — it depends only on F-005 (now completed). This is the natural next step, as it builds directly on the proposal system.
2. **F-011 (Character Templates) is also unblocked** — depends only on F-001. It's independent of the governance chain.
3. **F-006 is recommended next** — it unlocks F-013 (Character Evolution), F-016 (Session Analytics), and F-019 (Council Expansion).
4. The proposal system is importable as: `from core.proposals import ProposalManager, Proposal, Review`
5. Usage pattern: `mgr = ProposalManager(); p = mgr.create("Title", "Desc", author="Sage", category="ethics")`
6. The `ProposalManager` reads/writes `P-XXXX.json` files — integrate with the voting engine by reading `proposal.reviews` and `proposal.status`.
7. Lifecycle enforcement: reviews can only be added to `open` or `under_review` proposals. The voting engine should transition proposals to `decided` after tallying votes.
8. Consider DRYing up `_atomic_write` into `core/utils.py` when working on the next feature.

---

## Session: S-FEAT-00000006
**Timestamp:** 2026-03-15 09:42:00
**Feature:** `F-006` — Voting Engine
**Status:** completed

### Summary
Implemented the voting engine for the Jericho AI Council:

- **Created `core/voting.py`** (~370 lines) — Four main components:
  - **Exception hierarchy**: `VotingError` (base), `VoteNotFoundError` (no record for proposal), `VotingValidationError` (invalid vote data), `VotingStateError` (operation conflicts with current state).
  - **Data classes**: `Vote` (frozen — voter, choice, reason, timestamp, weight), `VoteTally` (frozen — computed tally with counts, weighted values, approval rate, quorum/threshold/approved/vetoed booleans), `VoteRecord` (frozen — per-proposal record with votes list, status, veto fields, timestamps, metadata). All have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Tally logic**: Approval rate = `weighted_for / (weighted_for + weighted_against)` — abstains do not count toward the ratio. Quorum checks total voter count (not weighted). Threshold defaults to 60% from `settings.py`. Approved requires: quorum met AND threshold met AND not vetoed.
  - **`VotingEngine` class** — filesystem-backed, one JSON file per proposal (`V-P-XXXX.json`):
    - `open_voting(proposal_id)` — creates vote record, prevents duplicates
    - `cast_vote(proposal_id, vote)` — validates voter uniqueness (case-insensitive), requires open status
    - `tally(proposal_id)` → `VoteTally` — computes approval rate, quorum, threshold, veto status
    - `close_voting(proposal_id)` — sets status to closed, records timestamp
    - `veto(proposal_id, reason)` / `lift_veto(proposal_id)` — human veto override power
    - `get()` / `list_records()` / `has_record()` — query methods
    - Configurable `quorum` and `threshold` via constructor args (defaults from `settings.py`)
  - **Atomic writes** via temp-file + rename pattern (same as memory and proposal systems)
- **Created `tests/test_voting.py`** (~380 lines) — 70 tests across 12 classes:
  - `TestVote` (9): fields, defaults, frozen, roundtrip, create factory, invalid choice, custom/invalid weight
  - `TestVoteRecord` (5): fields, frozen, roundtrip, create factory, defaults
  - `TestVoteTally` (2): to_dict, frozen
  - `TestVotingEngineInit` (4): directory creation, existing dir, custom quorum/threshold, repr
  - `TestOpenVoting` (6): basic, creates file, with metadata, duplicate raises, empty/whitespace ID raises
  - `TestCastVote` (7): basic, multiple, persistence, duplicate voter (case-insensitive), closed raises, nonexistent raises
  - `TestTally` (10): empty, quorum met/not met, threshold met/not met, abstains excluded from ratio, all abstain, weighted votes, exact boundary, nonexistent raises
  - `TestCloseVoting` (4): basic, preserves votes, already closed raises, nonexistent raises
  - `TestHumanVeto` (9): basic, overrides approval, already vetoed raises, nonexistent, without reason, on closed voting, lift veto, not vetoed raises, lift restores approval
  - `TestListRecords` (5): empty, all, filter by status, has_record, corrupt file skipped
  - `TestEdgeCases` (6): unicode, exact threshold, just below threshold, large voter count, persistence after reopen, vote after veto-then-lift
  - `TestExceptions` (4): hierarchy, field access for each exception type
- **All 283 tests pass** (213 existing + 70 new) in 4.48s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in three modules (`memory.py`, `proposals.py`, `voting.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- Vote weight comes from the `Vote.create()` caller — there is no automatic integration with council member `vote_weight` from YAML profiles yet. The orchestrator (F-007) should pass `member.vote_weight` when casting votes on behalf of agents.
- No integration with `ProposalManager` lifecycle yet — the voting engine does not automatically transition proposals to `decided` when voting is closed. This should be done by the orchestrator or a higher-level workflow.
- The existing `data/votes/` directory contains a legacy `votes.db` file from the jericho01 migration. It is harmlessly ignored (VotingEngine only reads `V-*.json`), but could be cleaned up.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-007 (Council Session Orchestrator) is the natural next step** — it depends on F-002 + F-003 + F-004 (all completed). It ties together API calls, registry, memory, and can wire in proposals + voting.
2. **F-008 (Agent-to-Agent Chat) and F-009 (Human-to-Agent Chat) are also unblocked** — both depend on F-002 + F-004.
3. **F-011 (Character Templates) is independently unblocked** — depends only on F-001.
4. **F-013 (Character Evolution) and F-019 (Council Expansion) are now partially unblocked** — F-013 needs F-012+F-006; F-019 needs F-006+F-003.
5. The voting engine is importable as: `from core.voting import VotingEngine, Vote, VoteRecord, VoteTally`
6. Usage pattern:
   - `engine = VotingEngine()` — uses defaults from `settings.py`
   - `engine.open_voting("P-0001")` → `engine.cast_vote("P-0001", Vote.create("Sage", "for", weight=member.vote_weight))` → `tally = engine.tally("P-0001")` → `engine.close_voting("P-0001")`
7. When integrating with proposals, the orchestrator should: (a) transition proposal to `under_review` or `open`, (b) open voting, (c) collect votes, (d) close voting, (e) transition proposal to `decided` based on tally.
8. **DRY up `_atomic_write`** into `core/utils.py` — it is now in three separate files.

---

## Session: S-FEAT-00000007
**Timestamp:** 2026-03-15 09:50:00
**Feature:** `F-007` — Council Session Orchestrator
**Status:** completed

### Summary
Implemented the council session orchestrator — the central module that ties together the API client, registry, and memory system into a complete session lifecycle:

- **Created `core/session.py`** (~580 lines) — Five main components:
  - **Exception hierarchy**: `SessionError` (base), `SessionNotFoundError`, `SessionStateError`, `SessionValidationError`.
  - **Data classes**: `SessionMessage` (frozen — speaker, content, timestamp, phase, activity_type, metadata) and `SessionRecord` (frozen — session_id, title, phase, activity_type, agenda, participants, messages, summary, timestamps, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Phase state machine**: `created → briefing → active → summary → closed`, with transitions validated via `_VALID_TRANSITIONS` dict. No skipping phases, no backward transitions.
  - **Prompt builders**: `_build_briefing_prompt()` (context + memories + agenda), `_build_discussion_prompt()` (topic + prior contributions), `_build_summary_prompt()` (session recap request). All produce structured markdown for LLM consumption.
  - **`SessionOrchestrator` class** — filesystem-backed, one JSON file per session (`S-<id>.json`):
    - `create_session()` — validates participants against registry, creates record file
    - `start_session()` — transitions to briefing, sets started_at timestamp
    - `brief_member()` — loads recent memories, sends briefing prompt via API client, records exchange + memory event
    - `activate_session()` — transitions to active phase
    - `discuss()` — structured multi-member discussion with sequential prompting (each member sees prior contributions)
    - `send_to_member()` — freeform single-member interaction, returns both record and raw ChatResponse
    - `add_human_message()` — inject human messages during briefing or active phases
    - `begin_summary()` — transitions to summary phase
    - `collect_summary()` — asks each member for their session takeaways
    - `close_session()` — transitions to closed, persists summary to shared memory (decisions JSONL + narrative history)
    - `get()` / `list_sessions()` / `has_session()` / `get_transcript()` — query methods with filtering
- **Created `tests/test_session.py`** (~550 lines) — 76 tests across 14 classes:
  - `TestSessionMessage` (5): fields, frozen, roundtrip, create factory, metadata
  - `TestSessionRecord` (8): fields, frozen, roundtrip, create factory, empty ID, empty title, invalid activity, whitespace stripping
  - `TestConstants` (3): phases, activity types, valid transitions
  - `TestOrchestratorInit` (3): dir creation, properties, repr
  - `TestCreateSession` (6): basic, with options, persistence, duplicate, unknown participant, sequential IDs
  - `TestPhaseTransitions` (8): all valid transitions, skip phase, closed, not found, backward
  - `TestBriefMember` (4): messages recorded, API called, wrong phase, memory recorded
  - `TestDiscussion` (4): messages recorded, API per member, wrong phase, multiple rounds
  - `TestSendToMember` (2): exchange recorded, wrong phase
  - `TestHumanMessage` (3): briefing, active, wrong phase
  - `TestSummaryAndClose` (6): collect summary, wrong phase, close with summary, auto summary, shared memory, history
  - `TestQueryMethods` (8): get, not found, list, filter by phase, filter by activity, has_session, transcript, transcript filter, corrupt skip
  - `TestPromptBuilders` (6): briefing title/agenda/memories, discussion topic/prior, summary
  - `TestExceptions` (4): hierarchy, not found, state error, validation error
  - `TestEdgeCases` (5): unicode, long agenda, empty participants, full lifecycle, persistence roundtrip
- **All 359 tests pass** (283 existing + 76 new) in 5.17s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **four** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- No integration with `ProposalManager` or `VotingEngine` yet in the orchestrator. The `discuss()` method handles free-form discussion, but structured proposal review + voting rounds should be added when F-010 (Discussion Rounds) is implemented.
- The orchestrator does not yet inject core beliefs into briefing context — only recent session memories are loaded. F-018 (Memory Influence) should add relevance-scored belief injection.
- Session file naming uses `S-<session_id>.json`, meaning the session ID appears twice (e.g., `S-S-001.json`). This is functional but slightly redundant. Consider whether session IDs should include the `S-` prefix or not.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-008 (Agent-to-Agent Chat) and F-009 (Human-to-Agent Chat) are the natural next steps** — both depend on F-002 + F-004 (completed). They can build on the orchestrator's `send_to_member()` and `add_human_message()` methods.
2. **F-010 (Discussion Rounds) is now unblocked** — depends on F-008 + F-005. Could be implemented as a higher-level workflow on top of `SessionOrchestrator.discuss()`.
3. **F-011 (Character Templates) is independently unblocked** — depends only on F-001.
4. **F-012 (Collaborative Character Design) is now unblocked** — depends on F-007 + F-011.
5. **F-014 (CLI Interface) is now unblocked** — depends on F-007.
6. **F-016 (Session Analytics) is now partially unblocked** — depends on F-006 + F-007 (both completed).
7. The session orchestrator is importable as: `from core.session import SessionOrchestrator, SessionRecord, SessionMessage`
8. Usage pattern:
   ```python
   registry = CouncilRegistry().load()
   async with APIClient() as client:
       orch = SessionOrchestrator(registry=registry, api_client=client)
       rec = orch.create_session("S-001", "Ethics Review", activity_type="discussion", participants=["Sage", "Logic"])
       rec = await orch.start_session("S-001")
       rec = await orch.brief_member("S-001", "Sage")
       rec = await orch.activate_session("S-001")
       rec = await orch.discuss("S-001", "AI Ethics", ["Sage", "Logic"])
       rec = await orch.begin_summary("S-001")
       rec = await orch.close_session("S-001", summary="Ethics discussed.")
   ```
9. **DRY up `_atomic_write`** into `core/utils.py` — it is now in four separate files.

---

## Session: S-FEAT-00000008
**Timestamp:** 2026-03-15 09:58:00
**Feature:** `F-008` — Agent-to-Agent Chat
**Status:** completed

### Summary
Implemented orchestrator-mediated agent-to-agent conversations with automatic memory recording:

- **Created `core/agent_chat.py`** (~430 lines) — Five main components:
  - **Exception hierarchy**: `ChatError` (base), `ChatNotFoundError` (no conversation record), `ChatValidationError` (invalid data).
  - **Data classes**: `ChatExchange` (frozen — speaker, content, timestamp, metadata) and `ConversationRecord` (frozen — conversation_id, title, participants, topic, exchanges list, summary, created_at, closed_at, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Prompt builders**: `_build_opening_prompt()` (initiates conversation with partner context) and `_build_chat_prompt()` (continuation with full history, limited to last 10 exchanges for context window management).
  - **`AgentChat` class** — filesystem-backed, one JSON file per conversation (`C-<id>.json`):
    - `create_conversation()` — validates 2+ participants against registry, creates record file
    - `exchange()` — core method: speaker sees full history, API sends multi-turn messages (own messages as "assistant", others as "user"), records exchange + memory event. Returns updated record and raw ChatResponse
    - `converse()` — orchestrated multi-turn: each member takes a turn per round, configurable number of rounds
    - `close_conversation()` — sets closed_at, persists summary to shared memory (decisions JSONL + narrative history)
    - `get()` / `list_conversations()` / `has_conversation()` / `get_exchanges()` — query methods with filtering (participant, closed/open, speaker)
  - **API message building**: `_build_api_messages()` converts conversation history into alternating user/assistant messages from the speaker's perspective for natural multi-turn LLM interaction
- **Created `tests/test_agent_chat.py`** (~530 lines) — 65 tests across 12 classes:
  - `TestChatExchange` (5): fields, frozen, roundtrip, create factory, metadata
  - `TestConversationRecord` (6): fields, frozen, roundtrip, create factory, empty ID, whitespace strip
  - `TestAgentChatInit` (3): dir creation, properties, repr
  - `TestCreateConversation` (7): basic, with options, persistence, duplicate, unknown participant, single participant rejected, sequential IDs
  - `TestExchange` (7): basic, records messages, API called, memory recorded, wrong participant, closed conversation, not found
  - `TestConverse` (7): two members one round, multiple rounds, records all, API calls match, memory per member, closed raises, empty members
  - `TestCloseConversation` (5): basic, with summary, auto summary, shared memory, already closed
  - `TestQueryMethods` (8): get, not found, list all, filter participant, filter closed, has_conversation, get_exchanges with filter, corrupt skip
  - `TestPromptBuilders` (5): opening content, without topic, history, topic, context limit
  - `TestExceptions` (4): hierarchy, not found, validation, base
  - `TestEdgeCases` (5): unicode, long content, three-way, persistence roundtrip, full lifecycle
  - `TestMemoryIntegration` (5): each speaker recorded, both sides recorded, memory content, session ID, source
- **All 426 tests pass** (359 existing + 65 new + 2 from prior adjustments) in 5.62s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **five** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- No streaming / real-time callback support — the `exchange()` method waits for full API response. Could add an `on_message` callback for interactive UIs later.
- Conversation IDs are user-supplied, not auto-generated like proposals (`P-XXXX`). Consider adding auto-sequencing if needed.
- File naming `C-<id>.json` could collide with session files `S-<id>.json` in the same `conversations/` directory, but the prefixes keep them distinct.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-009 (Human-to-Agent Chat) is the natural next step** — depends on F-002 + F-004 (completed). Can reuse the same `AgentChat` patterns with a "human" participant or build as a simpler variant.
2. **F-010 (Discussion Rounds) is now unblocked** — depends on F-008 + F-005. Should build on `AgentChat.converse()` as a higher-level workflow with proposal integration.
3. **F-011 (Character Templates) is independently unblocked** — depends only on F-001.
4. **F-014 (CLI Interface) is unblocked** — depends on F-007.
5. The agent chat module is importable as: `from core.agent_chat import AgentChat, ConversationRecord, ChatExchange`
6. Usage pattern:
   ```python
   registry = CouncilRegistry().load()
   async with APIClient() as client:
       chat = AgentChat(registry=registry, api_client=client)
       chat.create_conversation("C-001", "Ethics Debate", participants=["Sage", "Logic"], topic="AI autonomy")
       rec = await chat.converse("C-001", ["Sage", "Logic"], "AI autonomy", rounds=3)
       rec = chat.close_conversation("C-001", summary="Agreed on guidelines.")
   ```
7. Key design difference from `SessionOrchestrator`: no phase machine, no briefing/summary phases. Agent chat is lightweight and immediate. Use sessions for formal council proceedings, chat for informal discussions.
8. The `_build_api_messages()` method converts history into multi-turn format (own messages = "assistant", others = "user") for natural LLM conversation flow.
9. **DRY up `_atomic_write`** into `core/utils.py` — it is now in five separate files.

---

## Session: S-FEAT-00000009
**Timestamp:** 2026-03-15 10:12:00
**Feature:** `F-009` — Human-to-Agent Chat
**Status:** completed

### Summary
Implemented direct human-to-agent conversations with automatic memory recording:

- **Created `core/human_chat.py`** (~380 lines) — Five main components:
  - **Exception hierarchy**: `HumanChatError` (base), `HumanChatNotFoundError` (no chat record), `HumanChatValidationError` (invalid data).
  - **Data classes**: `HumanChatMessage` (frozen — role [human/agent], speaker, content, timestamp, metadata) and `HumanChatRecord` (frozen — chat_id, title, member_name, topic, messages list, summary, created_at, closed_at, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Prompt builder**: `_build_human_chat_prompt()` — presents conversation history to the council member with human messages as context, limited to last 10 messages for context window management.
  - **`HumanChat` class** — filesystem-backed, one JSON file per chat (`H-<id>.json`):
    - `create_chat()` — validates member against registry, creates record file
    - `send_human_message()` — records human message (no API call)
    - `get_agent_response()` — sends history to API, records agent response + memory event
    - `close_chat()` — sets closed_at, persists summary to shared memory (decisions JSONL + narrative history)
    - `get()` / `list_chats()` / `has_chat()` / `get_messages()` — query methods with filtering (member, closed/open, role)
  - **API message building**: `_build_api_messages()` converts history into standard user/assistant roles (human = user, agent = assistant)
- **Created `tests/test_human_chat.py`** (~530 lines) — 65 tests across 12 classes:
  - `TestHumanChatMessage` (6): fields, frozen, roundtrip, create factory, metadata, invalid role
  - `TestHumanChatRecord` (7): fields, frozen, roundtrip, create factory, empty ID, empty title, whitespace strip
  - `TestHumanChatInit` (3): dir creation, properties, repr
  - `TestCreateChat` (6): basic, with options, persistence, duplicate, unknown member, sequential IDs
  - `TestSendHumanMessage` (6): basic, multiple, persistence, closed raises, not found, metadata
  - `TestGetAgentResponse` (8): basic, API called, memory recorded, closed raises, not found, history built, multi-turn
  - `TestCloseChat` (5): basic, with summary, auto summary, shared memory, already closed
  - `TestQueryMethods` (8): get, not found, list all, filter member, filter closed, has_chat, get_messages, corrupt skip
  - `TestPromptBuilder` (4): with history, without topic, human messages labeled, context limit
  - `TestExceptions` (4): hierarchy, not found, validation, base
  - `TestEdgeCases` (5): unicode, long content, persistence roundtrip, full lifecycle, multiple chats same member
  - `TestMemoryIntegration` (4): agent response recorded, memory content, session ID, source
- **All 491 tests pass** (426 existing + 65 new) in 5.89s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **six** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`, `human_chat.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- No streaming / real-time callback support — `get_agent_response()` waits for full API response. Could add an `on_message` callback for interactive CLIs later.
- The human's speaker name is hardcoded to `"Human"` — could be made configurable if multiple human operators need distinct identities.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-010 (Discussion Rounds) is now unblocked** — depends on F-008 + F-005 (both completed). It should build on `AgentChat.converse()` as a higher-level workflow with proposal integration.
2. **F-011 (Character Templates) is independently unblocked** — depends only on F-001.
3. **F-014 (CLI Interface) is unblocked** — depends on F-007. Could integrate both `AgentChat` and `HumanChat` as subcommands.
4. **F-016 (Session Analytics) is unblocked** — depends on F-006 + F-007 (both completed).
5. The human chat module is importable as: `from core.human_chat import HumanChat, HumanChatRecord, HumanChatMessage`
6. Usage pattern:
   ```python
   registry = CouncilRegistry().load()
   async with APIClient() as client:
       chat = HumanChat(registry=registry, api_client=client)
       rec = chat.create_chat("H-001", "Ethics Q&A", member_name="Sage")
       rec = chat.send_human_message("H-001", "What are your core beliefs?")
       rec, resp = await chat.get_agent_response("H-001")
       rec = chat.close_chat("H-001", summary="Discussed ethics.")
   ```
7. Key design difference from `AgentChat`: human messages are recorded synchronously (no API call), only agent responses hit the API. The `send_human_message()` + `get_agent_response()` pattern gives the human operator explicit control over turn-taking.
8. **DRY up `_atomic_write`** into `core/utils.py` — it is now in six separate files.

---

## Session: S-FEAT-00000010
**Timestamp:** 2026-03-15 10:55:00
**Feature:** `F-010` — Discussion Rounds
**Status:** completed

### Summary
Implemented structured multi-agent discussion rounds on proposals:

- **Created `core/discussion.py`** (~480 lines) — Five main components:
  - **Exception hierarchy**: `DiscussionError` (base), `DiscussionNotFoundError`, `DiscussionValidationError`, `DiscussionStateError`.
  - **Data classes**: `DiscussionContribution` (frozen — speaker, content, round_number, timestamp, metadata) and `DiscussionRecord` (frozen — discussion_id, proposal_id, title, participants, contributions list, round_count, current_round, status, summary, created_at, closed_at, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Prompt builder**: `_build_discussion_prompt()` — includes full proposal details (title, description, body, category, author) plus prior contributions (last 10 for context window), asks member to respond in character about the proposal.
  - **`DiscussionManager` class** — filesystem-backed, one JSON file per discussion (`D-<id>.json`):
    - `create_discussion()` — validates proposal exists (via ProposalManager), validates participants against registry, validates round count against MAX_DISCUSSION_ROUNDS, creates record file
    - `run_round()` — runs one round where each participant speaks in order with proposal context + all prior contributions, records each contribution + memory event, increments `current_round`
    - `run_all_rounds()` — convenience to run remaining rounds (or custom count), respects remaining round count
    - `close_discussion()` — sets status to closed, persists summary + metadata to shared memory (decisions JSONL + narrative history)
    - `get()` / `list_discussions()` / `has_discussion()` / `get_contributions()` — query methods with filtering (proposal_id, status, participant, speaker, round_number)
  - **Atomic writes** via temp-file + rename pattern (same as other modules)
- **Updated `config/settings.py`** — added `DISCUSSIONS_DIR`, `DEFAULT_DISCUSSION_ROUNDS` (2), `MAX_DISCUSSION_ROUNDS` (10).
- **Created `tests/test_discussion.py`** (~540 lines) — 68 tests across 12 classes:
  - `TestDiscussionContribution` (5): fields, frozen, roundtrip, create factory, metadata
  - `TestDiscussionRecord` (7): fields, frozen, roundtrip, create factory, empty ID, empty title, whitespace strip
  - `TestDiscussionManagerInit` (3): dir creation, properties, repr
  - `TestCreateDiscussion` (8): basic, with options, persistence, duplicate, unknown participant, missing proposal, single participant, exceeds max rounds
  - `TestRunRound` (8): basic, records contributions, API called, memory recorded, round tracking, closed raises, not found, all rounds complete
  - `TestRunAllRounds` (5): default rounds, custom rounds, records all, closed raises, respects remaining
  - `TestCloseDiscussion` (5): basic, with summary, auto summary, shared memory, already closed
  - `TestQueryMethods` (9): get, not found, list all, filter proposal, filter status, has_discussion, get_contributions (speaker + round), corrupt skip, filter participant
  - `TestPromptBuilder` (5): proposal title, body, prior contributions, context limit, member identity
  - `TestExceptions` (4): hierarchy, not found, validation, state error
  - `TestEdgeCases` (5): unicode, long content, many participants, persistence roundtrip, full lifecycle
  - `TestMemoryIntegration` (4): each speaker recorded, memory content, session ID, source type
- **All 559 tests pass** (491 existing + 68 new) in 6.38s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **seven** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`, `human_chat.py`, `discussion.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- No integration with `VotingEngine` yet — the discussion manager creates and runs discussions, but does not automatically transition proposals or open voting upon discussion close. This should be done by a higher-level workflow or the CLI.
- The discussion prompt does not inject agent core beliefs or recent memories — F-018 (Memory Influence) should add relevance-scored belief injection to discussion prompts as well.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-011 (Character Templates) is independently unblocked** — depends only on F-001. It's the simplest remaining feature.
2. **F-012 (Collaborative Character Design) is now partially unblocked** — depends on F-007 + F-011.
3. **F-014 (CLI Interface) is unblocked** — depends on F-007. Could integrate discussions as a subcommand.
4. **F-016 (Session Analytics) is unblocked** — depends on F-006 + F-007.
5. **F-017 (Test Suite) is unblocked** — depends on F-002–F-006 (all completed). Note: each feature already has its own test suite, so F-017 may be about integration/E2E testing or can be considered implicitly addressed.
6. **F-018 (Memory Influence) is unblocked** — depends on F-004 + F-007.
7. **F-019 (Council Expansion) is unblocked** — depends on F-006 + F-003.
8. The discussion module is importable as: `from core.discussion import DiscussionManager, DiscussionRecord, DiscussionContribution`
9. Usage pattern:
   ```python
   registry = CouncilRegistry().load()
   proposals = ProposalManager()
   async with APIClient() as client:
       mgr = DiscussionManager(registry=registry, api_client=client, proposal_manager=proposals)
       rec = mgr.create_discussion("D-001", "P-0001", "Ethics Review", participants=["Sage", "Logic", "Drift"])
       rec = await mgr.run_all_rounds("D-001")
       rec = mgr.close_discussion("D-001", summary="Council discussed ethics proposal.")
   ```
10. Key design difference from `AgentChat`: discussions are proposal-aware (prompt includes full proposal context), have explicit round tracking, and prevent discussion beyond configured round count. Use `AgentChat` for freeform conversations, `DiscussionManager` for structured proposal deliberation.
11. **DRY up `_atomic_write`** into `core/utils.py` — it is now in seven separate files.

---

## Session: S-FEAT-00000011
**Timestamp:** 2026-03-15 11:04:00
**Feature:** `F-011` — Character Template System
**Status:** completed

### Summary
Implemented the character template system for AI characters designed by the council:

- **Created `core/characters.py`** (~480 lines) — Five main components:
  - **Exception hierarchy**: `CharacterError` (base), `CharacterNotFoundError` (with `character_id`), `CharacterValidationError` (with `errors` list), `CharacterLifecycleError` (with `character_id`, `current_status`, `requested_status`).
  - **Data classes**: `Trait` (frozen — trait_type, name, description, intensity 0.0–1.0) and `CharacterTemplate` (frozen — id, name, description, author, status, backstory, traits list, system_prompt, greeting, example_messages, tags, version, created_at, updated_at, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Lifecycle state machine**: `draft → active → archived` and `draft → active → superseded`. Both `archived` and `superseded` are terminal states. Transitions validated via `_VALID_TRANSITIONS` dict.
  - **YAML export**: `export_yaml()` produces a clean YAML representation of a character, omitting empty optional fields. Optionally writes to a file path.
  - **`CharacterManager` class** — filesystem-backed, one JSON file per character (`CH-XXXX.json`):
    - `create()` — auto-sequential IDs, validates required fields (name, description, author, at least one trait), saves as JSON
    - `get()` / `list_characters()` — load by ID, list with optional filters (status, author, tag — all case-insensitive)
    - `update_status()` — lifecycle validation
    - `update()` — update mutable fields (name, description, backstory, system_prompt, greeting, example_messages, tags, metadata), bumps `updated_at`
    - `add_trait()` / `remove_trait()` — modify trait list with validation (no duplicate names, cannot remove last trait)
    - `export_yaml()` — clean YAML export with optional file output
    - `create_version()` — creates a new template as a copy with version+1, supersedes the original, links via `metadata["previous_version"]`
  - **Atomic writes** via temp-file + rename pattern (same as other modules)
- **Updated `config/settings.py`** — added `CHARACTER_STATUSES` (`draft`, `active`, `archived`, `superseded`) and `CHARACTER_REQUIRED_TRAIT_TYPES` (`personality`, `values`, `flaws`).
- **Created `tests/test_characters.py`** (~530 lines) — 68 tests across 12 classes:
  - `TestTrait` (7): fields, frozen, roundtrip, create factory, invalid intensity (too high, negative), default intensity
  - `TestCharacterTemplate` (7): fields, frozen, roundtrip, create factory, defaults, from_dict missing optionals, create with metadata
  - `TestCharacterManagerInit` (3): dir creation, existing dir, repr
  - `TestCharacterCreation` (8): basic, sequential IDs, persistence, with all fields, empty name/author, no traits, whitespace stripping
  - `TestCharacterRetrieval` (8): get by ID, not found, list all, filter by status/author/tag, combined filters, empty list
  - `TestStatusLifecycle` (8): draft→active, active→archived, active→superseded, skip phase, archived terminal, superseded terminal, unknown status, not found
  - `TestTraitManagement` (7): add trait, duplicate name rejected, remove trait, remove nonexistent, remove last trait, add persists, remove case-insensitive
  - `TestCharacterUpdate` (8): update name/description/backstory, immutable field rejected, author immutable, not found, multiple fields, bumps updated_at
  - `TestExportYaml` (6): basic export, roundtrip, includes traits, to custom path, not found, omits empty optionals
  - `TestVersioning` (6): create version, supersedes original, links via metadata, copies all fields, not active raises, not found
  - `TestEdgeCases` (5): unicode, long backstory, many traits, corrupt JSON skipped, persistence roundtrip
  - `TestExceptions` (4): hierarchy, not-found fields, validation fields, lifecycle fields
- **All 636 tests pass** (559 existing + 68 new + 9 from prior adjustments) in 6.85s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **eight** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`, `human_chat.py`, `discussion.py`, `characters.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- `CHARACTER_REQUIRED_TRAIT_TYPES` is defined in settings but not yet enforced in `CharacterManager.create()` — this allows any string as `trait_type`. Enforcement can be added when collaborative design (F-012) needs it.
- The `pyyaml` dependency is listed in `pyproject.toml` but the YAML export uses `yaml.dump()` with `sort_keys=False` — this works in PyYAML 6.x but verify if an older version is pinned.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-012 (Collaborative Character Design) is now unblocked** — depends on F-007 + F-011 (both completed). This is the natural next step, integrating the session orchestrator with the character template system.
2. **F-014 (CLI Interface) is unblocked** — depends on F-007. Could integrate character management as subcommands.
3. **F-016 (Session Analytics) is unblocked** — depends on F-006 + F-007.
4. **F-017 (Test Suite) is unblocked** — depends on F-002–F-006. Note: each feature already has comprehensive tests, so F-017 may focus on integration/E2E testing.
5. **F-018 (Memory Influence) is unblocked** — depends on F-004 + F-007.
6. **F-019 (Council Expansion) is unblocked** — depends on F-006 + F-003.
7. The character module is importable as: `from core.characters import CharacterManager, CharacterTemplate, Trait`
8. Usage pattern:
   ```python
   mgr = CharacterManager()
   trait = Trait.create("personality", "Curious", "Always asking questions", intensity=0.7)
   char = mgr.create("Atlas", "An explorer AI", author="Forge", traits=[trait])
   mgr.update_status(char.id, "active")
   yaml_str = mgr.export_yaml(char.id)
   new_ver = mgr.create_version(char.id)  # supersedes original, creates v2
   ```
9. Key design note: Characters are the **output** of the council's work — distinct from council member profiles (`council/members/*.yaml`). Council members are fixed LLM personas; characters are the AI personalities they collaboratively design.
10. **DRY up `_atomic_write`** into `core/utils.py` — it is now in eight separate files.

---

## Session: S-FEAT-00000012
**Timestamp:** 2026-03-15 11:13:00
**Feature:** `F-012` — Collaborative Character Design
**Status:** completed

### Summary
Implemented collaborative character design — council members contribute to character creation via structured prompts in a multi-phase workflow:

- **Created `core/character_design.py`** (~600 lines) — Five main components:
  - **Exception hierarchy**: `DesignError` (base), `DesignNotFoundError` (with `design_id`), `DesignValidationError` (with `errors` list), `DesignStateError` (with `design_id`, `message`).
  - **Data classes**: `DesignContribution` (frozen — speaker, content, phase, parsed_data, timestamp, metadata) and `DesignRecord` (frozen — design_id, title, contributors, contributions, current_phase, phases_completed, target_character_id, status, summary, timestamps, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Prompt builders**: Five phase-specific builders (`_build_concept_prompt`, `_build_traits_prompt`, `_build_backstory_prompt`, `_build_prompt_prompt`, `_build_review_prompt`) — each produces structured markdown for the LLM, with prior contributions included for context (limited to last 10).
  - **`CharacterDesigner` class** — filesystem-backed, one JSON file per design (`CD-<id>.json`):
    - `create_design()` — validates contributors against registry, enforces MAX_DESIGN_CONTRIBUTORS
    - `run_phase()` — runs one design phase (concept/traits/backstory/prompt/review) with all contributors, records contributions + memory events, tracks phases_completed
    - `run_all_phases()` — convenience to run all remaining DEFAULT_DESIGN_PHASES, skips already-completed phases
    - `assemble_character()` — parses contributions and creates a `CharacterTemplate` via `CharacterManager`: extracts name from concept, traits from traits phase, backstory, system prompt. Links template to design via metadata
    - `close_design()` — marks closed, persists summary to shared memory (decisions JSONL + narrative history)
    - `get()` / `list_designs()` / `has_design()` / `get_contributions()` — query methods with filtering (status, contributor, speaker, phase)
  - **Atomic writes** via temp-file + rename pattern (same as other modules)
- **Updated `config/settings.py`** — added `CHARACTER_DESIGNS_DIR`, `DEFAULT_DESIGN_PHASES` tuple (concept, traits, backstory, prompt, review), `MAX_DESIGN_CONTRIBUTORS` (9).
- **Created `tests/test_character_design.py`** (~550 lines) — 69 tests across 12 classes:
  - `TestDesignContribution` (5): fields, frozen, roundtrip, create factory, metadata
  - `TestDesignRecord` (7): fields, frozen, roundtrip, create factory, empty ID, empty title, whitespace strip
  - `TestCharacterDesignerInit` (3): dir creation, properties, repr
  - `TestCreateDesign` (7): basic, with options, persistence, duplicate, unknown contributor, no contributors, sequential IDs
  - `TestRunPhase` (8): basic, records contributions, API called, memory recorded, phase tracking, closed raises, not found, invalid phase
  - `TestRunAllPhases` (5): default phases, records all, closed raises, sequential phases, respects completed
  - `TestAssembleCharacter` (7): creates template, uses concept name, includes traits, includes backstory, includes prompt, links design_id, not found
  - `TestCloseDesign` (5): basic, with summary, auto summary, shared memory, already closed
  - `TestQueryMethods` (8): get, not found, list all, filter status, filter contributor, has_design, get_contributions (phase + speaker), corrupt skip
  - `TestPromptBuilders` (5): concept content, traits with prior, backstory, prompt/greeting, review
  - `TestExceptions` (4): hierarchy, not found, validation, state error
  - `TestEdgeCases` (5): unicode, long content, many contributors, persistence roundtrip, full lifecycle
- **All 705 tests pass** (636 existing + 69 new) in 7.39s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **nine** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`, `human_chat.py`, `discussion.py`, `characters.py`, `character_design.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- Trait extraction from LLM-generated text (`_extract_traits`) uses simple heuristic parsing (looks for "- **Name**: Description" patterns). More robust parsing could use structured output from the LLM (e.g., JSON mode) when available.
- The `_extract_name` helper is similarly heuristic — looks for "Name: something" lines. Could be improved with more robust parsing.
- Character assembly always sets author to "Council" by default — could be made configurable or derived from the design contributors.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up.

### Advice for Next Agent
1. **F-013 (Character Evolution) is now unblocked** — depends on F-012 + F-006 (both completed). This is the natural next step, adding governance-based modifications to existing characters.
2. **F-014 (CLI Interface) is unblocked** — depends on F-007. Could integrate character design as a subcommand.
3. **F-016 (Session Analytics) is unblocked** — depends on F-006 + F-007.
4. **F-017 (Test Suite) is unblocked** — depends on F-002–F-006. Each feature already has comprehensive tests, so F-017 may focus on integration/E2E testing.
5. **F-018 (Memory Influence) is unblocked** — depends on F-004 + F-007.
6. **F-019 (Council Expansion) is unblocked** — depends on F-006 + F-003.
7. The character design module is importable as: `from core.character_design import CharacterDesigner, DesignRecord, DesignContribution`
8. Usage pattern:
   ```python
   registry = CouncilRegistry().load()
   chars = CharacterManager()
   async with APIClient() as client:
       designer = CharacterDesigner(
           registry=registry,
           api_client=client,
           character_manager=chars,
       )
       rec = designer.create_design("CD-001", "A Curious Explorer", contributors=["Forge", "Spark", "Sage"])
       rec = await designer.run_all_phases("CD-001")
       template = designer.assemble_character("CD-001")
       rec = designer.close_design("CD-001", summary="Character designed collaboratively.")
   ```
9. Key design note: The design workflow is separate from but integrates with `CharacterManager`. After `assemble_character()`, the template exists in both the design record (via `target_character_id`) and the character store (as `CH-XXXX.json`). The design record preserves all contributions as the creative provenance.
10. **DRY up `_atomic_write`** into `core/utils.py` — it is now in nine separate files.

---

## Session: S-FEAT-00000013
**Timestamp:** 2026-03-15 11:23:00
**Feature:** `F-013` — Character Evolution
**Status:** completed

### Summary
Implemented governance-backed character modification via proposals and voting:

- **Created `core/character_evolution.py`** (~530 lines) — Five main components:
  - **Exception hierarchy**: `EvolutionError` (base), `EvolutionNotFoundError` (with `evolution_id`), `EvolutionValidationError` (with `errors` list), `EvolutionStateError` (with `evolution_id`, `message`).
  - **Data classes**: `CharacterChange` (frozen — change_type, field_name, old_value, new_value, rationale) and `EvolutionRecord` (frozen — evolution_id, character_id, author, changes list, proposal_id, vote_record_id, status, applied_character_id, summary, timestamps, metadata). Both have `to_dict()`, `from_dict()`, and `create()` factory methods.
  - **Lifecycle state machine**: `draft → proposed → voting → decided → applied`, with `rejected` reachable from `voting`. Transitions validated via `_VALID_TRANSITIONS` dict.
  - **Change types**: `trait_add`, `trait_remove`, `trait_modify`, `field_update`, `version_bump` — each applied atomically to a new character version.
  - **`CharacterEvolution` class** — filesystem-backed, one JSON file per evolution (`EV-XXXX.json`):
    - `create_evolution()` — validates character exists and is `active`, validates changes count and types, auto-sequential ID
    - `submit_for_review()` — creates a `Proposal` (category=`"character"`) via `ProposalManager`, transitions to `proposed`
    - `open_voting()` — opens voting via `VotingEngine`, transitions proposal to `under_review`, transitions to `voting`
    - `resolve()` — closes voting, tallies results, transitions to `decided` (approved) or `rejected` based on quorum/threshold/veto
    - `apply_evolution()` — creates new character version via `CharacterManager.create_version()`, applies each change, activates new version, links `applied_character_id`
    - `get()` / `list_evolutions()` / `has_evolution()` — query methods with filtering (character_id, status, author)
  - **Atomic writes** via temp-file + rename pattern (same as other modules)
- **Updated `config/settings.py`** — added `EVOLUTION_DIR`, `EVOLUTION_TYPES`, `EVOLUTION_STATUSES`, `MAX_EVOLUTION_CHANGES`.
- **Created `tests/test_character_evolution.py`** (~550 lines) — 71 tests across 12 classes:
  - `TestCharacterChange` (6): fields, frozen, roundtrip, create factory, invalid change_type, empty field_name
  - `TestEvolutionRecord` (7): fields, frozen, roundtrip, create factory, empty ID, empty character_id, empty author
  - `TestCharacterEvolutionInit` (3): dir creation, properties, repr
  - `TestCreateEvolution` (8): basic, sequential IDs, persistence, multiple changes, no changes, character not found, character not active, exceeds max changes
  - `TestSubmitForReview` (6): basic, creates proposal, links proposal_id, already submitted, not found, wrong status
  - `TestOpenVoting` (5): basic, links vote record, not proposed, already voting, not found
  - `TestResolve` (7): approved, rejected below threshold, rejected no quorum, already resolved, not in voting, handles veto, not found
  - `TestApplyEvolution` (8): creates new version, applies trait_add, applies trait_remove, applies field_update, links applied_character_id, not decided, already applied, not found
  - `TestQueryMethods` (8): get, not found, list all, filter by character_id, filter by status, filter by author, has_evolution, corrupt skip
  - `TestLifecycleIntegration` (4): full happy path, rejected path, cannot skip states, persistence roundtrip
  - `TestEdgeCases` (5): unicode, multiple changes, large rationale, trait_modify, version_bump
  - `TestExceptions` (4): hierarchy, not found fields, validation fields, state error fields
- **All 776 tests pass** (705 existing + 71 new) in 8.99s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is now duplicated in **ten** modules (`memory.py`, `proposals.py`, `voting.py`, `session.py`, `agent_chat.py`, `human_chat.py`, `discussion.py`, `characters.py`, `character_design.py`, `character_evolution.py`). A shared `core/utils.py` should be created to DRY this up — noted since S-FEAT-00000005.
- The `_apply_change` method for `trait_modify` does a remove-then-add, which silently succeeds even if the original trait doesn't exist. Could be made stricter.
- No automatic notification to council members when their characters are evolved — could be added as a memory event in the future.
- Temp files from S-FEAT-00000002 (`test_out.txt`, `test_results.txt`, `tmp_status.txt`) still not cleaned up. `test_evo_output.txt` was also added during this session and should be cleaned up.

### Advice for Next Agent
1. **F-014 (CLI Interface) is unblocked** — depends on F-007 (completed). This is a good next step to provide a user interface for all the features built so far.
2. **F-016 (Session Analytics) is unblocked** — depends on F-006 + F-007 (both completed).
3. **F-017 (Test Suite) is unblocked** — depends on F-002–F-006 (all completed). Each feature already has comprehensive tests, so F-017 may focus on cross-module integration or E2E testing.
4. **F-018 (Memory Influence) is unblocked** — depends on F-004 + F-007 (both completed).
5. **F-019 (Council Expansion) is unblocked** — depends on F-006 + F-003 (both completed).
6. **F-020 (Prompt Evolution History) is NOT yet unblocked** — depends on F-013 (now completed) + F-015 (pending, depends on F-014).
7. The character evolution module is importable as: `from core.character_evolution import CharacterEvolution, EvolutionRecord, CharacterChange`
8. Usage pattern:
   ```python
   chars = CharacterManager()
   proposals = ProposalManager()
   engine = VotingEngine()
   evo = CharacterEvolution(
       character_manager=chars,
       proposal_manager=proposals,
       voting_engine=engine,
   )
   change = CharacterChange.create("trait_add", "courage",
                                    new_value={"trait_type": "personality",
                                               "name": "courage",
                                               "description": "Brave",
                                               "intensity": 0.7},
                                    rationale="Needs more bravery")
   rec = evo.create_evolution("CH-0001", author="Sage", changes=[change])
   rec = evo.submit_for_review(rec.evolution_id)
   rec = evo.open_voting(rec.evolution_id)
   # ... cast votes ...
   rec = evo.resolve(rec.evolution_id)
   if rec.status == "decided":
       template = evo.apply_evolution(rec.evolution_id)
   ```
9. Key design note: Each evolution creates a **new version** of the character — the original is superseded, changes are applied to the copy. This preserves full history and is non-destructive.
10. **DRY up `_atomic_write`** into `core/utils.py` — it is now in ten separate files.

---

### Session — Implementing F-014 (CLI Interface)

**Date**: 2026-03-15
**Feature**: F-014 — CLI Interface
**Status**: ✅ Completed

#### What was done
1. Created `core/cli.py` — Click-based CLI with 5 subcommand groups:
   - `council list|show` — council member management
   - `proposals list|show|create` — governance proposals with filtering
   - `vote list|show|cast|veto` — voting engine interaction
   - `characters list|show|export` — character template management
   - `status` — project overview (member/proposal/vote/character counts)
2. Created `tests/test_cli.py` — 61 tests across 16 classes using `click.testing.CliRunner`:
   - All subcommands tested with positive and negative cases
   - Filter options verified (status, category, author, tag, provider)
   - Error handling: missing args, nonexistent records, invalid choices
   - Help output and version verified for all groups
3. Entry point already wired in `pyproject.toml`: `jericho = "core.cli:cli"`

#### Test results
- CLI tests: 61 passed
- Full suite: 837 passed, 0 failed (including all prior tests)

#### Files changed
- `core/cli.py` (new — 340 lines)
- `tests/test_cli.py` (new — 715 lines)
- `features.json` — F-014 status → `completed`

#### Advice for next session
1. F-015 (Rich Terminal Dashboard) is now unblocked — depends only on F-014.
2. The CLI outputs plain text via `click.echo()` — F-015 should layer Rich formatting on top.
3. Consider adding `session` subcommands when F-007 session orchestrator gets CLI exposure.
4. The `_atomic_write` duplication across 10+ modules should be refactored to `core/utils.py`.

---

## Session: S-FEAT-00000015
**Timestamp:** 2026-03-15 11:45:00
**Feature:** `F-015` — Rich Terminal Dashboard
**Status:** completed

### Summary
Implemented the Rich terminal dashboard — Rich-formatted output for all CLI commands:

- **Created `core/dashboard.py`** (~300 lines) — Three main components:
  - **Status colour mapping**: `STATUS_COLOURS` dict maps statuses to Rich colours (draft→dim, open→green, under_review→yellow, decided→blue, withdrawn→red, active→green, archived→dim, superseded→yellow, rejected→red). `_style_status()` returns styled `rich.text.Text`.
  - **`_truncate()` helper**: moved from `core/cli.py` — display-layer concern.
  - **`DashboardRenderer` class** — wraps `rich.console.Console` (injectable for testing):
    - `render_member_list/detail()` — Table/Panel with coloured providers, personality dict, specialties
    - `render_proposal_list/detail()` — Table/Panel with status-coloured badges, reviews by stance
    - `render_vote_list/detail()` — Table/Panel with approval bar (█░), quorum/threshold indicators, choice colours
    - `render_character_list/detail()` — Table/Panel with trait intensity dots (●○), cyan hash-tags
    - `render_status_dashboard()` — Nested panels for Council, Proposals, Vote Records, Characters
    - `render_success()` / `render_error()` — styled ✓/Error feedback
- **Updated `core/cli.py`** (~280 lines, was 470) — replaced all `click.echo()` with `DashboardRenderer`:
  - Module-level `_renderer = DashboardRenderer()` shared by all commands
  - YAML export still uses `click.echo()` for raw text output
- **Created `tests/test_dashboard.py`** (~360 lines) — 51 tests across 10 classes covering all render methods
- **Updated `tests/test_cli.py`** — adapted 9 assertions for Rich output format
- **All 888 tests pass** (837 existing + 51 new) in ~9s with zero regressions.

### Technical Debt
- The `_atomic_write` helper is still duplicated in **ten** modules — noted since S-FEAT-00000005.
- Module-level `_renderer` creates `Console()` at import time. Fine for CLI, but consider lazy init if import time matters.
- Temp files need cleanup: `test_out.txt`, `test_results.txt`, `tmp_status.txt`, `test_failures.json`, `cli_fails.json`.
- Minor: `render_status_dashboard()` has a slightly redundant proposals rendering path.

### Advice for Next Agent
1. **F-016 (Session Analytics), F-017 (Test Suite), F-018 (Memory Influence), F-019 (Council Expansion) are all unblocked.**
2. **F-020 (Prompt Evolution History) is now unblocked** — depends on F-013 + F-015 (both completed).
3. The dashboard module: `from core.dashboard import DashboardRenderer, STATUS_COLOURS, _truncate`
4. Testing pattern: `DashboardRenderer(console=Console(file=StringIO(), force_terminal=True, width=120))` captures output.
5. For new CLI subcommands, add render methods on `DashboardRenderer` — don't use `click.echo()` directly.
6. **DRY up `_atomic_write`** into `core/utils.py` — it is now in ten separate files.
7. Clean up temp files before committing.

---

## Session: S-FEAT-00000016
**Timestamp:** 2026-03-15 15:40:00
**Feature:** `F-016` — Session Analytics
**Status:** completed

### Summary
Implemented read-only analytics engine for the Jericho AI Council. The module aggregates data from existing managers (proposals, voting, sessions, discussions) — no filesystem writes.

### Files Created
- **`core/analytics.py`** (~380 lines) — `SessionAnalytics` engine class + frozen data classes:
  - `MemberStats` — per-member: sessions, votes (with for/against/abstain breakdown), proposals authored, discussions
  - `ProposalStats` — total, by_status, by_category, approval_rate
  - `VotingStats` — total_records, total_votes, avg_votes_per_record, quorum_achievement_rate, approval_rate, veto_count
  - `SessionStats` — total_sessions, by_phase, by_activity, avg_messages, avg_participants
  - `AnalyticsReport` — bundles everything + generated_at timestamp
  - Engine methods: `member_stats()`, `all_member_stats()`, `proposal_stats()`, `voting_stats()`, `session_stats()`, `top_participants()`, `full_report()`
  - Graceful degradation: any manager can be None
- **`tests/test_analytics.py`** (~600 lines) — 65 tests in 15 classes covering all data classes, computation, edge cases

### Files Modified
- **`core/dashboard.py`** — Added `render_analytics_overview(report)` and `render_member_stats(name, stats)` methods
- **`core/cli.py`** — Added `analytics` subcommand group with `overview` and `member <name>` commands
- **`features.json`** — F-016 status → `completed`

### Test Results
- **961 tests pass** (888 existing + 65 new analytics + 8 from dashboard/CLI) in ~10s with zero regressions.

### Design Decisions
- **No filesystem writes** — analytics is pure computation. No `ANALYTICS_DIR` needed.
- **Constructor injection** — `SessionAnalytics` takes manager instances, making it fully testable with mocks.
- **Case-insensitive matching** — member name lookups use `.lower()` for consistent results.
- **Auto-discovery** — `all_member_stats()` discovers member names from data sources if no explicit list is given.
- **Lazy import in CLI** — `from core.analytics import SessionAnalytics` inside command functions to keep CLI startup fast.

### Technical Debt
- The `_atomic_write` helper is still duplicated across **ten** modules.
- Analytics currently accesses `VotingEngine._compute_tally()` (private method) for quorum stats. Consider adding a public accessor.
- Temp files still need cleanup.

### Advice for Next Agent
1. **F-017 (Test Suite), F-018 (Memory Influence), F-019 (Council Expansion), F-020 (Prompt Evolution History) are all unblocked.**
2. To add new analytics dimensions, extend the data classes and add computation methods on `SessionAnalytics`.
3. Dashboard testing pattern: `DashboardRenderer(console=Console(file=StringIO(), force_terminal=True, width=120))` captures output.
4. Analytics uses `_FakeSessionOrchestrator` and `_FakeDiscussionManager` mocks for testing — no real LLM calls needed.
5. **DRY up `_atomic_write`** into `core/utils.py` — it is now in ten separate files.

---

## Session: S-FTEST-00000017
**Timestamp:** 2026-03-15 15:50:00
**Feature:** `F-017` — Test Suite (Cross-Module Integration Tests)
**Status:** completed

### Summary
Implemented F-017 by adding shared test fixtures and cross-module integration tests that exercise real workflows spanning multiple managers.

### Files Created
- **`tests/conftest.py`** (~120 lines) — Shared pytest fixtures:
  - `tmp_dirs` — creates all standard project subdirectories
  - `make_member()`, `mock_registry()`, `mock_api_client()` — reusable helpers
  - `proposal_mgr`, `voting_engine`, `character_mgr`, `shared_memory` — manager factory fixtures
- **`tests/test_integration.py`** (~500 lines) — 43 integration tests across 5 suites:
  - `TestGovernanceWorkflow` (9 tests) — proposal → discussion → vote → decide
  - `TestCharacterLifecycle` (9 tests) — create → activate → evolve → apply → version
  - `TestSessionLifecycle` (9 tests) — create → brief → discuss → close → shared memory
  - `TestMemoryIntegration` (8 tests) — agent memory, shared memory, core beliefs, cross-agent isolation
  - `TestAnalyticsIntegration` (8 tests) — stats from real managers, full analytics report

### Files Modified
- **`features.json`** — F-017 status → `completed`

### Test Results
- **1004 tests pass** (961 existing + 43 new integration tests) with zero regressions.

### Design Decisions
- **Real managers, mock API** — integration tests use real filesystem-backed managers via `tmp_path`; only API calls are mocked at the transport layer.
- **Shared fixtures** — `conftest.py` contains reusable factories that any test file can import. Eliminates the `_make_member()` / `_mock_registry()` duplication across test files.
- **No test-order dependencies** — each test class creates its own environment via fixtures; tests are fully isolated.

### Technical Debt
- The `_atomic_write` helper is still duplicated across ten modules.
- Existing test files still define their own `_make_member()` / `_mock_registry()` locally — they could be refactored to use `conftest.py` helpers.
- Temp files from previous sessions still need cleanup.

### Advice for Next Agent
1. **F-018 (Memory Influence), F-019 (Council Expansion), F-020 (Prompt Evolution History) are all unblocked.**
2. New integration tests can be added to `tests/test_integration.py` or to new files — `conftest.py` fixtures are available project-wide.
3. Existing test files can be gradually migrated to use `conftest.py` helpers instead of local duplicates.
4. **DRY up `_atomic_write`** into `core/utils.py` — it is now in ten separate files.

---

## F-018: Memory Influence ✓

**Date:** 2026-03-15

### Summary
Memories now affect agent responses via context injection with relevance scoring. A new `MemoryInfluence` engine scores and selects the most relevant core beliefs and session memories for a given conversational context, formats them as markdown, and injects them into prompt builders across all four chat/session modules, making agents contextually aware and consistent based on their past experience.

### Files Created
- **`core/memory_influence.py`** — Main module (~300 lines). Contains:
  - `ScoredMemory`, `ScoredBelief`, `MemoryContext` frozen data classes
  - `MemoryInfluence` engine with keyword-based Jaccard similarity scoring
  - Configurable thresholds: memory/belief limits, min relevance, belief boost multiplier
  - `format_for_prompt()` — renders scored context as injectable markdown
  - `extract_keywords()` — convenience helper for deriving keywords from titles/topics
  - `_tokenise()`, `_jaccard()` — internal scoring primitives with stop-word filtering

- **`tests/test_memory_influence.py`** — Comprehensive test suite (~450 lines, 71 tests):
  - `TestTokenise` (6 tests) — tokenisation, stop word removal, unicode, edge cases
  - `TestJaccard` (6 tests) — similarity metric, degenerate cases
  - `TestScoredMemory` (5 tests) — data class fields, frozen, roundtrip
  - `TestScoredBelief` (5 tests) — data class fields, frozen, roundtrip
  - `TestMemoryContext` (4 tests) — has_content property, roundtrip
  - `TestMemoryInfluenceInit` (3 tests) — defaults, custom values, repr
  - `TestScoreMemories` (8 tests) — scoring, thresholds, limits, sort order
  - `TestScoreBeliefs` (7 tests) — scoring, boost multiplier, capping at 1.0
  - `TestBuildContext` (4 tests) — end-to-end from filesystem, limits, case insensitivity
  - `TestFormatForPrompt` (6 tests) — empty input, beliefs-only, memories-only, both
  - `TestExtractKeywords` (4 tests) — extraction, stop words, sorting
  - `TestEdgeCases` (7 tests) — unicode, long content, all-below-threshold, special chars
  - `TestSessionIntegration`, `TestDiscussionIntegration`, `TestAgentChatIntegration`, `TestHumanChatIntegration` (4 tests) — integration verification

### Files Modified
- **`config/settings.py`** — Added 4 memory influence settings: `MEMORY_INFLUENCE_MAX_MEMORIES`, `MEMORY_INFLUENCE_MAX_BELIEFS`, `MEMORY_INFLUENCE_MIN_RELEVANCE`, `MEMORY_INFLUENCE_BELIEF_BOOST`
- **`core/session.py`** — `_build_briefing_prompt()` and `_build_discussion_prompt()` accept `memory_context_text`. `SessionOrchestrator.__init__` gains optional `memory_influence` parameter. `brief_member()` and `discuss()` inject memory context when engine is configured.
- **`core/discussion.py`** — `_build_discussion_prompt()` accepts `memory_context_text`. `DiscussionManager.__init__` gains optional `memory_influence` parameter. `run_round()` injects memory context.
- **`core/agent_chat.py`** — `_build_opening_prompt()` and `_build_chat_prompt()` accept `memory_context_text`. `AgentChat.__init__` gains optional `memory_influence` parameter. `exchange()` injects memory context.
- **`core/human_chat.py`** — `_build_human_chat_prompt()` accepts `memory_context_text`. `HumanChat.__init__` gains optional `memory_influence` parameter. `get_agent_response()` injects memory context.
- **`core/cli.py`** — Added `memory` subcommand group with `beliefs <member>` and `recent <member>` commands.
- **`core/dashboard.py`** — Added `render_member_beliefs()` and `render_recent_memories()` methods.
- **`features.json`** — F-018 status → `done`

### Test Results
- **1075 tests pass** (1004 existing + 71 new) with zero regressions.

### Design Decisions
- **Jaccard similarity scoring** — Simple, deterministic, zero external dependencies. Tokenises content into lowercase word sets, filters stop words, computes `|intersection| / |union|`. Good enough for keyword-level relevance without heavyweight NLP.
- **Belief boost multiplier** (default 1.5×) — Core beliefs represent persistent stance and should score higher than ephemeral session memories. Capped at 1.0 after boosting.
- **Additive integration** — Every prompt builder gains an optional `memory_context_text` parameter. When the `MemoryInfluence` engine is not configured (i.e., passed as `None`), existing behavior is preserved with zero overhead — the feature is opt-in per manager instance.
- **Fallback in briefing** — `_build_briefing_prompt()` uses scored context when available but falls back to the original bare memory list when `memory_context_text` is empty, maintaining backward compatibility.

### Technical Debt
- The `_atomic_write` helper is still duplicated across eleven modules (now including `memory_influence.py` is clean — it doesn't need it).
- Stop-word list is hardcoded in English; a future i18n pass could make it configurable.
- The scoring algorithm is keyword-level; a future enhancement could add embedding-based similarity.

### Advice for Next Agent
1. **F-019 (Council Expansion) and F-020 (Prompt Evolution History) are unblocked.**
2. To enable memory influence for a session, pass `memory_influence=MemoryInfluence()` when constructing `SessionOrchestrator`, `DiscussionManager`, `AgentChat`, or `HumanChat`. Without it, behavior is unchanged.
3. The `MemoryInfluence` class is fully configurable via constructor kwargs or `config/settings.py` constants.
4. **DRY up `_atomic_write`** into `core/utils.py` — it is now in ten/eleven separate files.

---

## Session 19 — F-019: Council Expansion

**Feature:** F-019 — Council Expansion
**Status:** ✅ Completed
**Tests before:** 1075 | **Tests after:** 1145 (+70)

### Summary

Agents can now propose adding new council members via the governance system. The module follows the same governance-backed lifecycle as F-013 (Character Evolution):

```
draft → proposed → voting → decided → applied
                                     ↘ rejected
```

### Files Changed

| File | Action | Description |
|------|--------|-------------|
| `config/settings.py` | Modified | Added `EXPANSION_DIR`, `EXPANSION_STATUSES`, `EXPANSION_REQUIRED_FIELDS` |
| `core/council_expansion.py` | **New** | ~530 lines — `MemberSpec`, `ExpansionRecord`, `CouncilExpansion` classes |
| `tests/test_council_expansion.py` | **New** | ~570 lines, 70 tests across 12 classes |
| `core/cli.py` | Modified | Added `expansion list` and `expansion show` subcommands |
| `core/dashboard.py` | Modified | Added `render_expansion_list` and `render_expansion_detail` methods |
| `features.json` | Modified | F-018 status typo fix (`done` → `completed`), F-019 → `completed` |

### Key Design Decisions

1. **MemberSpec.to_yaml()** generates YAML matching the existing `council/members/*.yaml` format (with comment header).
2. **MAX_COUNCIL_SIZE** check prevents unbounded council growth — validated at creation time.
3. **Case-insensitive duplicate name** check against existing registry members.
4. **Atomic writes** for both JSON records and YAML member files.
5. **Shared memory recording** — both `resolve()` and `apply_expansion()` record decisions and history.

### Test Coverage

12 test classes: MemberSpec, ExpansionRecord, Init, Create, SubmitForReview, OpenVoting, Resolve, ApplyExpansion, QueryMethods, LifecycleIntegration, EdgeCases, Exceptions.

### Technical Debt (Carried Forward)

- `_atomic_write` is now duplicated in twelve files. The DRY refactoring into `core/utils.py` remains a priority.

### Advice for Next Agent

1. **F-020 (Prompt Evolution History) is the last unblocked feature.**
2. The expansion module's `apply_expansion()` writes YAML but does not auto-reload the registry — callers should reload if needed.
3. The `MemberSpec.to_yaml()` output includes a `# Council Member: {name} — {role}` header comment.
4. **DRY up `_atomic_write`** into `core/utils.py` — it is now in twelve separate files.

---

## Session 20 — F-020: Prompt Evolution History

**Feature:** F-020 — Prompt Evolution History
**Status:** ✅ Completed
**Tests before:** 1145 | **Tests after:** 1221 (+76)

### Summary

Visual timeline of how characters changed over council decisions. A new read-only engine traces version chains through `metadata["previous_version"]` links and evolution records, producing ordered timelines with Rich-formatted CLI output.

### Files Created

| File | Description |
|------|-------------|
| `core/evolution_history.py` | ~360 lines — `VersionSnapshot`, `EvolutionEvent`, `CharacterTimeline` data classes + `EvolutionHistory` engine |
| `tests/test_evolution_history.py` | ~560 lines, 76 tests across 12 classes |

### Files Modified

| File | Description |
|------|-------------|
| `core/dashboard.py` | Added `render_evolution_timeline()`, `render_version_diff()`, `render_timeline_list()` methods |
| `core/cli.py` | Added `history` subcommand group with `timeline`, `diff`, `list` commands |
| `features.json` | F-020 → `completed` — **all 20 features now complete** |

### Key Design Decisions

1. **Read-only engine** — `EvolutionHistory` reads from `CharacterManager` and `CharacterEvolution` but writes nothing. Pure computation.
2. **Version chain walking** — follows `metadata["previous_version"]` backwards from any character to the original, with circular-link guard and graceful handling of missing intermediates.
3. **Timeline aggregation** — snapshots (compact character summaries) and events (evolution records with vote results) are collected per lineage and sorted chronologically.
4. **Diff engine** — compares two character versions field-by-field with `+/-/~` notation for traits added/removed/modified, field changes, tag changes, and version bumps.
5. **Evolution manager optional** — if not provided, timelines are built without evolution events (useful for simpler queries).
6. **Constructor injection** — fully testable with mocks, no filesystem writes.

### Test Coverage

12 test classes: VersionSnapshot, EvolutionEvent, CharacterTimeline, Helpers, EvolutionHistoryInit, GetVersionChain, GetSnapshot, BuildTimeline, ListTimelines, DiffVersions, EdgeCases, DashboardRendering, CLICommands.

### Technical Debt (Carried Forward)

- `_atomic_write` is still duplicated in twelve modules. The DRY refactoring into `core/utils.py` remains the primary tech debt item.
- Temp files from earlier sessions (`test_out.txt`, `test_results.txt`, `tmp_status.txt`, `test_failures.json`, `cli_fails.json`, `test_cli_output.txt`, `test_dash_out.txt`, `test_evo_output.txt`) still live in the project root and should be cleaned up or gitignored.

### Advice for Next Agent

1. **All 20 features are now complete.** The project has a full 1221-test suite with zero failures.
2. The main remaining work is **tech debt reduction** (DRY up `_atomic_write`, clean up temp files, add `pytest-asyncio` to `pyproject.toml`).
3. If extending the project further, consider: async CLI commands, embedding-based memory influence, streaming API support, web dashboard.
4. The evolution history module is importable as: `from core.evolution_history import EvolutionHistory, CharacterTimeline, VersionSnapshot, EvolutionEvent`
5. Usage pattern:
   ```python
   chars = CharacterManager()
   evo = CharacterEvolution(...)
   history = EvolutionHistory(character_manager=chars, evolution_manager=evo)
   timeline = history.build_timeline("CH-0003")
   diffs = history.diff_versions("CH-0001", "CH-0002")
   ```
6. Clean up temp files before committing.

---

## Session: S-TECHDEBT-001
**Timestamp:** 2026-03-15 21:00:00
**Feature:** Tech Debt Reduction — DRY `_atomic_write`
**Status:** completed

### Summary
Addressed the primary tech debt item: the `_atomic_write` function duplicated identically across 11 core modules.

### Changes Made

1. **Created `core/utils.py`** — new shared utility module containing `atomic_write()` and `atomic_append()` functions.
2. **Refactored 11 core modules** — removed local `_atomic_write` definitions, added `from core.utils import atomic_write`, updated all call sites:
   - `core/memory.py` (also had `_atomic_append`)
   - `core/proposals.py`
   - `core/voting.py`
   - `core/session.py`
   - `core/agent_chat.py`
   - `core/human_chat.py`
   - `core/discussion.py`
   - `core/characters.py`
   - `core/character_design.py`
   - `core/character_evolution.py`
   - `core/council_expansion.py`
3. **Updated `tests/test_memory.py`** — import `atomic_write` from `core.utils` instead of `core.memory`.
4. **Deleted 5 temp files** from project root: `test_cli_output.txt`, `test_dash_out.txt`, `test_evo_output.txt`, `cli_fails.json`, `test_failures.json`.
5. **Updated `.gitignore`** — added patterns for broader temp file exclusion.

### Tests
- Full suite: **1221 passed**, 0 failures, 1 warning (12.4s)
- No regressions from refactoring

### Net Impact
- **~200 lines of duplicated code removed** (18 lines × 11 modules)
- Unused `import os` and `import tempfile` removed from 11 modules
- Single source of truth for atomic file operations

### Advice for Next Agent
1. All 20 features remain complete with 1221 passing tests.
2. The primary tech debt item (`_atomic_write` duplication) is now resolved.
3. `pytest-asyncio` was already in `pyproject.toml` — no action needed.
4. The shared utility is importable as: `from core.utils import atomic_write, atomic_append`

---

## Session: S-FEAT-00000021
**Timestamp:** 2026-03-15 17:00:00
**Feature:** `F-021` — Web Dashboard
**Status:** completed

### Summary
Implemented a browser-based dashboard with FastAPI backend and single-page HTML/JS/CSS frontend:

- **Created `core/web_api.py`** (~280 lines) — FastAPI application with REST endpoints:
  - `GET /api/status` — project overview (member/proposal/vote/character counts)
  - `GET /api/council` / `GET /api/council/{name}` — council member list/detail
  - `GET /api/proposals` / `GET /api/proposals/{id}` — proposals with filtering (status, category, author)
  - `GET /api/votes` / `GET /api/votes/{proposal_id}` — vote records with tallies
  - `GET /api/characters` / `GET /api/characters/{id}` — characters with filtering (status, author, tag)
  - `GET /api/analytics` — full analytics report
  - Static file serving for the SPA frontend
  - App factory pattern (`create_app()`) for testability
- **Created `core/web_static/`** — Single-page application:
  - `index.html` — semantic HTML shell with sidebar navigation
  - `styles.css` — premium dark-mode CSS with glassmorphism, gradients, micro-animations
  - `app.js` (~740 lines) — hash-based routing SPA with views for Dashboard, Council, Proposals, Votes, Characters, Analytics
- **Updated `config/settings.py`** — added `WEB_HOST`, `WEB_PORT`, `WEB_STATIC_DIR`
- **Updated `core/cli.py`** — added `jericho web` subcommand to launch dashboard via uvicorn
- **Updated `pyproject.toml`** — added `fastapi` and `uvicorn` dependencies
- **Created `tests/test_web_api.py`** — 27 tests covering all API endpoints via `TestClient`
- **All 1248 tests pass** (1221 existing + 27 new) with zero regressions.

### Technical Debt
- No WebSocket support for real-time updates — dashboard polls on navigation
- API endpoints re-instantiate managers on each request (stateless) — fine for low traffic but could be optimized with dependency injection
- No authentication on API endpoints — suitable for local use only

### Advice for Next Agent
1. All 21 features are now complete with 1248 passing tests.
2. The web API is importable as: `from core.web_api import create_app, app`
3. Launch via `jericho web` or `uvicorn core.web_api:app --port 8080`
4. To add new API endpoints, add routes inside `create_app()` and corresponding tests in `test_web_api.py`
5. The SPA uses hash-based routing (`/#council`, `/#proposals/P-0001`, etc.) — add new views by extending `renderView()` in `app.js`

---

## Session: S-FEAT-00000022
**Timestamp:** 2026-03-15 17:15:00
**Feature:** `F-022` — Governance Report Generator
**Status:** completed

### Summary
Implemented a read-only report engine that exports governance activity as structured Markdown documents:

- **Created `core/reports.py`** (~430 lines) — Report generator module:
  - `ReportSection` (frozen data class) — title, content, section_type
  - `GovernanceReport` (frozen data class) — report_id, title, sections, `to_markdown()` method
  - `ReportGenerator` class with constructor injection for all managers:
    - `council_roster_section()` — member table with roles, providers, specialties
    - `proposals_section(status=)` — proposals table + per-proposal detail with reviews
    - `voting_section()` — vote records with for/against/abstain tallies and approval rates
    - `characters_section(status=)` — character templates with traits and tags
    - `analytics_section()` — aggregate stats from SessionAnalytics
    - `full_report(title=, sections=)` — assembles all available sections
    - `save_report()` / `list_reports()` / `get_report()` — file persistence via atomic_write
  - Graceful degradation — any manager can be None, that section is silently skipped
- **Updated `config/settings.py`** — added `REPORTS_DIR`, `REPORT_SECTIONS`
- **Updated `core/cli.py`** — added `jericho report generate` and `jericho report list` subcommands
- **Created `tests/test_reports.py`** — 70 tests covering data classes, section builders, full report assembly, persistence, edge cases, and exceptions
- **All 1318 tests pass** (1248 existing + 70 new) with zero regressions.

### Technical Debt
- No PDF/HTML export — Markdown only for now
- No templating engine — sections are hard-coded in Python

### Advice for Next Agent
1. All 22 features are now complete with 1318 passing tests.
2. The report generator is importable as: `from core.reports import ReportGenerator`
3. Generate via CLI: `jericho report generate` (stdout) or `jericho report generate --save`
4. To add new report sections, add a builder method to `ReportGenerator` and register it in `full_report()`
5. Reports are saved as Markdown to `data/reports/` — could be extended to support HTML/PDF

---

## Session: S-FEAT-00000023
**Timestamp:** 2026-03-15 21:53:00
**Feature:** `F-023` — Secure API Key Management
**Status:** completed

### Summary
Implemented web-based API key configuration with encryption at rest:

- **Created `core/api_keys.py`** — `APIKeyManager` class:
  - Fernet (AES-128-CBC) encryption for API keys stored in `.env` file
  - Auto-generates encryption key on first use, stores in `config/.fernet_key`
  - `save(provider, api_key)` — encrypts and persists to `.env`
  - `load_all()` — decrypts all keys at startup so `APIClient` reads real keys from `os.environ`
  - `load_model(provider)` — loads model overrides from `.env`
  - `get_obfuscated(provider)` — returns `sk-...xxxx` format for safe display
  - Supports OpenRouter and Mancer providers
- **Added API endpoints in `core/web_api.py`**:
  - `GET /api/settings/keys` — returns obfuscated key status for all providers
  - `POST /api/settings/keys` — saves encrypted API keys
  - `GET /api/settings/models` — returns current model configuration
  - `POST /api/settings/models` — saves model overrides
- **Added Settings page to frontend** (`app.js`) — API key input fields with obfuscated display, model selection, save/clear buttons
- **Created `tests/test_api_keys.py`** — tests for encryption, decryption, persistence, obfuscation
- **Startup decryption** — `create_app()` in `web_api.py` calls `mgr.load_all()` and `mgr.load_model()` at startup so keys are available to `APIClient`

### Technical Debt
- `.fernet_key` is stored as plaintext — acceptable for local use but not production-grade
- No key rotation mechanism

### Advice for Next Agent
1. API keys are managed via: `from core.api_keys import APIKeyManager`
2. Keys are auto-decrypted at web server startup — no manual step needed
3. The Settings page in the web UI allows key entry without touching `.env` directly
4. Model overrides (e.g., `JERICHO_MANCER_MODEL`) are stored in `.env` alongside keys

---

## Session: S-FEAT-00000024
**Timestamp:** 2026-03-16 01:32:00
**Feature:** `F-024` — Web Chat Interface
**Status:** completed

### Summary
Implemented browser-based chat interface with multiple enhancement sessions:

**Session 1 — Basic Chat (ba674e8b):**
- Added chat view to `app.js` with council member selection and message input
- SSE streaming endpoint `POST /api/chat/stream` in `web_api.py` for real-time AI responses
- Chat history display with styled message bubbles

**Session 2 — Enhanced Chat (f3e2922e):**
- Added ability to include additional council members in a chat session
- Implemented pause feature for AI-to-AI conversations when multiple members active
- `POST /api/chat/pause` endpoint to stop ongoing multi-AI conversations

**Session 3 — Multi-Party AI Chat (7dd8ae07):**
- Enabled multiple AI council members to converse with each other autonomously
- Message forwarding so each AI sees the full conversation context
- Clear turn order for sequential AI speaking
- User interjection capability mid-conversation

**Session 4 — Streaming Fixes (9588b16b):**
- Fixed `TypeError: 'NoneType' object is not subscriptable` in multi-AI chat responses
- Added delays between AI responses for better UX
- Implemented immediate response posting (display each AI output as it arrives via SSE)

**Session 5 — Council UI Debugging (7d188fff):**
- Fixed council member detail/editing panel visibility issues
- Verified rendering of council detail view with editable fields

### Files Modified
- `core/web_api.py` — Added chat streaming endpoint, pause endpoint, multi-member chat orchestration
- `core/web_static/app.js` — Chat view with SSE streaming, member selection, pause controls, multi-party support
- `core/web_static/style.css` — Chat message styling, input areas, streaming indicators

### Technical Debt
- Chat history is session-only (not persisted between page reloads)
- No integration with the backend `HumanChat` / `AgentChat` persistence layer — chats use direct API calls

### Advice for Next Agent
1. The chat system uses SSE (Server-Sent Events) via `POST /api/chat/stream` for real-time streaming
2. Multi-party AI chat uses sequential turn-taking with message forwarding for context
3. The pause mechanism sets a server-side flag that the streaming generator checks between turns
4. Chat is stateless on the backend (no persistence) — consider integrating with `HumanChat`/`AgentChat` modules for persistence if needed

---

## Session: S-FEAT-00000025
**Timestamp:** 2026-03-16 20:30:00
**Feature:** `F-025` — Proposal System Web UI
**Status:** completed

### Summary
Implemented the full interactive proposal lifecycle in the web dashboard, allowing users to create proposals, have AI council members discuss them in real-time, and trigger voting:

### Backend — `core/web_api.py`

6 new API endpoints added:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/proposals` | POST | Create proposal, auto-open, create discussion with all council members |
| `/api/proposals/{id}/discuss-stream` | POST | Run one discussion round via SSE (streams each contribution live) |
| `/api/proposals/{id}/discuss-pause` | POST | Close discussion, transition to under_review |
| `/api/proposals/{id}/vote` | POST | AI-driven voting — each council member votes based on discussion context, tally computed |
| `/api/proposals/{id}/withdraw` | POST | Withdraw a proposal by its author |
| `/api/proposals/{id}/discussion` | GET | Retrieve the discussion record for a proposal |

### Frontend — `core/web_static/app.js`

- **Proposal Creation Form**: Council member author selector, category dropdown, title, description textarea
- **Lifecycle Progress Bar**: `Draft → Open → Review → Decided` with animated pulsing active dot and withdrawn state
- **Discussion Feed**: Scrollable panel showing all AI council contributions with avatars, speaker name, round number
- **SSE Streaming**: Real-time discussion round — each member's response appears as it arrives with slide-in animation
- **Action Buttons**: "Continue Discussion", "⏸ Pause Discussion", "🗳️ Call Vote", "↩️ Withdraw" — context-aware based on proposal status
- **Vote Results Panel**: For/Against/Abstain counters, approval bar, quorum/threshold status, individual vote breakdown
- **Helper Functions**: Added `escapeHtml()` and `escapeAttr()` for XSS safety

### Styling — `core/web_static/style.css`

~340 lines of new CSS for proposal form, lifecycle progress bar with connector lines, discussion message bubbles, vote summary cards, and action button variants.

### Files Modified

| File | Lines Added | Description |
|------|-------------|-------------|
| `core/web_api.py` | ~400 | 6 new proposal API endpoints inside `create_app()` |
| `core/web_static/app.js` | ~350 | Proposal views rewritten + helper functions |
| `core/web_static/style.css` | ~340 | Full proposal component styling |
| `features.json` | +13 | F-024 → completed, F-025 added as completed |

### Tests
- `python -m pytest tests/test_proposals.py` — all existing proposal tests pass
- `py_compile.compile('core/web_api.py')` — no syntax errors
- All referenced methods verified: `list_members()`, `list_names()`, `vote_weight`, `StreamingResponse`, `json_module`

### Design Decisions
1. **Proposal IDs as Discussion IDs** — for simplicity, the proposal ID is reused as the discussion ID
2. **AI-driven voting** — each council member receives a structured prompt with proposal + discussion summary and casts a vote autonomously
3. **SSE for discussions** — same streaming pattern as the chat system, but for structured discussion rounds
4. **Lifecycle enforcement** — action buttons are shown/hidden based on proposal status and discussion state

### Technical Debt
- No web API tests for the new proposal endpoints yet — should be added to `tests/test_web_api.py`
- Discussion streaming does not handle partial failures gracefully (if one member's API call fails mid-round)
- Vote results are not persisted to a separate vote record view — they're embedded in the proposal detail

### Advice for Next Agent
1. All 25 features are now complete.
2. The proposal web UI uses the same SSE pattern as the chat system — see `POST /api/chat/stream` for reference
3. To add new proposal actions, add endpoints in `web_api.py` inside `create_app()` and corresponding UI in `app.js` `renderProposalDetail()`
4. The `/api/proposals/{id}/vote` endpoint orchestrates the full vote: opens voting, casts all AI votes, closes voting, returns tally
5. Consider adding tests for the new proposal endpoints in `test_web_api.py`
6. The lifecycle progress bar CSS uses `:has()` selector — modern browsers only (Chrome 105+, Firefox 121+, Safari 15.4+)

---

## Session: S-FEAT-00000026
**Timestamp:** 2026-03-16 23:40:00
**Feature:** `F-026` — Council Member Editing & Avatar Upload
**Status:** completed

### Summary
Implemented editable council member profiles and avatar upload/framing functionality directly in the web dashboard:

### Backend — `core/registry.py`

- Added field classification constants:
  - `EDITABLE_FIELDS` — `name`, `api_provider`, `model`, `vote_weight`, `system_prompt`
  - `EDITABLE_PERSONALITY_FIELDS` — `traits`, `communication_style`, `decision_approach`
  - `READONLY_FIELDS` — `role`, `description`, `specialties`
- Added `update_member()` method to `CouncilRegistry`:
  - Reads YAML file, merges editable field updates, validates via existing `validate()`, writes back, reloads member in registry
  - Rejects any read-only field modifications with descriptive error messages
  - Returns the updated `CouncilMember` instance

### Backend — `core/web_api.py`

4 new API endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/council/{name}` | PUT | Update editable fields (enforces read-only boundary) |
| `/api/council/{name}/avatar-upload` | POST | Upload base64-encoded avatar PNG + zoom/offset metadata |
| `/api/council/{name}/avatar` | GET | Serve avatar PNG from filesystem |
| `/api/council/{name}/avatar-meta` | GET | Retrieve avatar zoom/offset metadata JSON |

- Updated `GET /api/council` and `GET /api/council/{name}` to include `avatar_url` when an avatar exists
- Added `COUNCIL_AVATARS_DIR = COUNCIL_DIR / "avatars"` to `config/settings.py`

### Frontend — `core/web_static/app.js`

- **`renderCouncil()`** — updated to display uploaded avatars on member cards (falls back to colored initials)
- **`renderCouncilDetail()`** — completely rewritten with:
  - Editable form inputs: name, API provider (dropdown), model, vote weight, traits (comma-separated), communication style, decision approach, system prompt (textarea)
  - Read-only displays: role, description, specialties (as tags)
  - Clickable avatar area with hover overlay → opens edit modal
- **`saveCouncilMember()`** — reads form values, PUTs to API, shows toast feedback
- **Avatar Editor Modal**: `openAvatarEditor()`, `loadAvatarImage()`, `updateAvatarPreview()`, `saveAvatar()`
  - Canvas-based circular preview with zoom slider (0.5x–3x) and drag-to-pan
  - Drag-and-drop file upload support
  - Saves cropped image as base64 + metadata to backend
- **Utility functions**: `escapeAttr()`, `escapeHtml()`

### Styling — `core/web_static/style.css`

~290 lines of new CSS for:
- Council edit form layout (`.council-edit-form`, `.council-fields-grid`, `.council-field-group`)
- Read-only field displays (`.council-field-readonly`, `.council-readonly-value`)
- Save bar with gradient primary button + status text
- Avatar upload area with hover overlay
- Full-screen avatar editor modal with glassmorphism backdrop
- Drag-and-drop zone, circular canvas preview, custom zoom slider thumb
- `.btn-secondary` and `.btn:disabled` states

### Files Modified

| File | Lines Added | Description |
|------|-------------|-------------|
| `config/settings.py` | 2 | `COUNCIL_AVATARS_DIR` constant |
| `core/registry.py` | ~60 | Field constants + `update_member()` method |
| `core/web_api.py` | ~110 | 4 new council editing/avatar endpoints |
| `core/web_static/app.js` | ~300 | Council detail rewrite + avatar modal |
| `core/web_static/style.css` | ~290 | Council edit form + avatar modal CSS |
| `tests/test_web_api.py` | ~110 | 14 new test cases |

### Tests

Added `TestApiCouncilUpdate` class with 14 test cases:
- `test_update_member_success` — PUT editable fields verifies YAML updated
- `test_update_member_readonly_fields_rejected` — role/description/specialties → 400
- `test_update_member_invalid_provider` — invalid provider → 400
- `test_update_member_invalid_weight` — negative weight → 400
- `test_update_member_not_found` — nonexistent member → 404
- `test_update_system_prompt` — system prompt editable
- `test_update_api_provider` — provider switch works
- `test_upload_avatar` — base64 PNG upload saves file
- `test_get_avatar_not_found` / `test_get_avatar_member_not_found` — 404 cases
- `test_upload_avatar_missing_data` — missing image_data → 400
- `test_council_list_no_avatar_url_by_default` — no avatar_url when none uploaded

**All 14 new tests pass. Full test suite passes with zero regressions (exit code 0).**

### Design Decisions
1. **Editable/readonly boundary** — enforced on both backend (`update_member()` rejects readonly fields) and frontend (readonly fields rendered as plain text, not inputs)
2. **Avatar storage** — avatars stored as `{name.lower()}.png` in `council/avatars/`, zoom metadata in `{name.lower()}.json` alongside them, separate from YAML config
3. **Client-side image manipulation** — zoom/pan done on canvas element, cropped image sent as base64 to avoid multipart form complexity
4. **Avatar framing** — user uploads a PNG, adjusts zoom (0.5x–3x) and pan position, then saves — stored as static PNG with metadata for re-editing

### Technical Debt
- No image size/format validation on the backend (accepts any base64 data)
- Avatar modal does not load existin avatar image for re-editing (always starts fresh)
- No confirmation dialog before overwriting existing avatar
- The `escapeHtml` and `escapeAttr` utility functions are defined at module scope — could be consolidated

### Advice for Next Agent
1. Council editing is live — click any member card to edit, scroll down for Save Changes button
2. Avatar upload: click the avatar area → modal with upload/zoom/pan → Save Avatar
3. The editable field boundary is enforced in `core/registry.py` constants — to make a new field editable, add it to `EDITABLE_FIELDS` or `EDITABLE_PERSONALITY_FIELDS`
4. Avatar files are stored in `council/avatars/` — the directory is auto-created on first upload
5. Browser caching can prevent users from seeing updates — **Ctrl+Shift+R** to force reload
6. If adding new council member fields to the edit form in `app.js`, also update the `saveCouncilMember()` function to include the new fields in the PUT body

---

## Session: S-FEAT-00000027
**Timestamp:** 2026-03-17 08:06:00
**Feature:** `F-027` — Avatar Images in Chat & Proposal Discussions
**Status:** completed

### Summary
Linked council member custom avatar images (from F-026) to the chat section and proposal discussion views:

### Frontend — `core/web_static/app.js`

- **`renderChat()`** — builds `avatarMap` lookup from already-fetched `/api/council` data; uses `memberAvatarWithImage()` for chat list card avatars (was `memberAvatar()`)
- **`renderChatDetail()`** — builds `avatarMap` + stores on `state.chatAvatarMap` for SSE handlers; uses `memberAvatarWithImage()` for:
  - Chat message bubbles (agent responses)
  - Member chips in the topbar
- **`appendAgentBubble()`** — now accepts `avatarUrl` parameter; uses `memberAvatarWithImage()` instead of `memberAvatar()`
- **`sendChatMessage()`** — SSE handler passes avatar URL from `state.chatAvatarMap` to `appendAgentBubble()`
- **`continueChat()`** — same pattern as `sendChatMessage()`
- **`renderProposalDetail()`** — fetches council data, builds `proposalAvatarMap` on `state.proposalAvatarMap`; uses `memberAvatarWithImage()` for discussion contribution messages
- **`runDiscussionRound()`** — SSE handler uses `state.proposalAvatarMap` for streamed discussion messages

### Call Sites Updated

| Location | Before | After |
|----------|--------|-------|
| Chat list card avatars | `memberAvatar(m, idx + i)` | `memberAvatarWithImage(m, idx + i, null, avatarMap[...])` |
| Chat message bubbles | `memberAvatar(speakerName, idx)` | `memberAvatarWithImage(speakerName, idx, null, avatarMap[...])` |
| Chat member chips | `memberAvatar(m, i)` | `memberAvatarWithImage(m, i, null, avatarMap[...])` |
| `appendAgentBubble()` x2 | `memberAvatar(speaker, 0)` | `memberAvatarWithImage(speaker, 0, null, avatarUrl)` |
| Proposal discussion feed | `memberAvatar(c.speaker, idx)` | `memberAvatarWithImage(c.speaker, idx, null, avatarMap[...])` |
| Proposal discussion SSE | `memberAvatar(data.speaker, 0)` | `memberAvatarWithImage(data.speaker, 0, null, avatarMap[...])` |

### Tests
- **All 1394 tests pass** with 4 pre-existing failures (unrelated API key/registry tests).
- No new test failures introduced — this is a frontend-only change.

### Technical Debt
- The `/api/council` endpoint is now called an additional time in `renderProposalDetail()` to get avatar URLs. If performance becomes a concern, this data could be cached on `state` or fetched once at app init.
- The 4 pre-existing test failures should be investigated and fixed separately.

### Advice for Next Agent
1. Avatar images now appear everywhere council member faces/initials are shown: council page, chat messages, chat list, member chips, and proposal discussions.
2. The avatar lookup pattern is: build a `{ name.toLowerCase(): avatar_url }` map from `/api/council` data, pass to `memberAvatarWithImage()`.
3. If adding new views that show member avatars, use `memberAvatarWithImage(name, idx, size, avatarUrl)` — it falls back to colored initials automatically when `avatarUrl` is falsy.
4. `state.chatAvatarMap` and `state.proposalAvatarMap` are set during render and available to SSE handlers.

---

## Session — F-026: World Locations

**Feature**: F-026 — World Locations
**Status**: ✅ Completed

#### What was done
1. **Configuration** (`config/settings.py`):
   - Added `LOCATIONS_DIR`, `LOCATION_STATUSES` (draft, active, archived), and `LOCATION_FEATURE_TYPES` (landmark, district, building, natural, infrastructure, custom).

2. **Core Backend** (`core/locations.py`):
   - Exception hierarchy: `LocationError`, `LocationNotFoundError`, `LocationValidationError`, `LocationLifecycleError`.
   - Data models: `LocationFeature` (frozen dataclass with type validation) and `Location` (frozen dataclass with full lifecycle support).
   - `LocationManager`: filesystem-backed JSON store using `LOC-XXXX` sequential IDs, CRUD operations, status transitions (draft→active→archived), feature management, hierarchical parent/child relationships, and multi-field filtering.

3. **Memory Integration** (`core/memory_influence.py`):
   - Extended `build_context()` with `locations_dir` parameter.
   - Extended `format_for_prompt()` with a "World Locations (Your Known World)" section.
   - Active locations (with features and lore) are now injected into every council member's prompt context.

4. **Web API** (`core/web_api.py`):
   - `GET /api/locations` — list with optional status/author/tag/parent_location_id filters.
   - `GET /api/locations/{id}` — detail view.
   - `POST /api/locations` — create with features, tags, coordinates.
   - `PUT /api/locations/{id}` — update mutable fields.
   - `PUT /api/locations/{id}/status` — lifecycle transitions.
   - `GET /api/status` — now includes `locations` count and status breakdown.

5. **Web Frontend** (`index.html`, `app.js`, `style.css`):
   - New "World" nav section with 🗺️ Locations link and live count badge.
   - Dashboard: rose-colored stat card for locations with status breakdown.
   - Locations list view with inline creation form and clickable cards showing features and tags.
   - Location detail view with lore, coordinates, features, sub-locations, status actions (Activate/Archive), and inline edit form.
   - Feature type dots with color-coded indicators per type.

6. **Testing** (`tests/conftest.py`, `tests/test_locations.py`):
   - Added `location_mgr` fixture to conftest.py.
   - 70 tests across 10 test classes covering: LocationFeature, Location, LocationManager init, creation, retrieval, lifecycle, feature management, updates, children, edge cases, and exceptions.

#### Test results
- Location tests: 70 passed

---

### Session — Implementing F-027 (User Description)

**Date**: 2026-03-17
**Feature**: F-027 — User Description
**Status**: ✅ Completed

#### What was done
1. **Configuration** (`config/settings.py`):
   - Added `USER_DESCRIPTION_ENV` and `USER_DESCRIPTION_MAX_LENGTH` (700) constants.

2. **Storage** (`core/api_keys.py`):
   - Added `get_user_description()` and `save_user_description()` methods to `APIKeyManager`.
   - Description stored as plain text in `.env` file with 700-character max enforcement.

3. **API Endpoints** (`core/web_api.py`):
   - `GET /api/settings/user-description` — retrieve current user description.
   - `POST /api/settings/user-description` — save user description with length validation.

4. **Chat Context Injection** (`core/human_chat.py`):
   - Modified `_build_human_chat_prompt()` to accept and inject user description.
   - Updated all 4 call sites: `get_agent_response`, `get_agent_response_streaming`, `continue_conversation`, `continue_conversation_streaming`.

5. **Web Frontend** (`app.js`, `style.css`):
   - User Profile card at top of Settings page with 👤 icon and "About You" label.
   - Textarea with 700-char `maxlength`, live character counter with color feedback (amber at 600+, rose at 700).
   - Save button with loading state, success/error toast notifications.
   - Added `escapeHtml()`, `updateCharCount()`, and `saveUserDescription()` functions.
   - CSS: `.user-profile-card`, `.user-desc-textarea`, `.user-desc-counter` with `.near-limit`/`.at-limit` states.

6. **Testing** (`test_web_api.py`, `test_human_chat.py`):
   - 5 API tests: empty GET, save+get roundtrip, too-long rejection, exactly 700 acceptance, empty save.
   - 2 prompt builder tests: description injected when provided, omitted when empty.

---

## S-FEAT-028 — Memory Explorer Web UI
**Timestamp:** 2026-03-18T20:25:00-04:00
**Feature:** F-028 — Memory Explorer Web UI
**Status:** ✅ COMPLETED

### Summary
Added a dedicated "Memories" section to the web dashboard for browsing council member memories (core beliefs, session events) and shared council memory (decisions, narrative history). Includes belief deletion support.

### Changes Made

1. **Backend API** (`web_api.py`):
   - `GET /api/memories` — list members with belief/event counts and avatar URLs.
   - `GET /api/memories/shared` — shared council decisions (JSONL) + narrative history (markdown).
   - `GET /api/memories/{member}?limit=N` — member's core beliefs + recent session events.
   - `DELETE /api/memories/{member}/beliefs?topic=X` — remove a core belief by topic.
   - Updated `GET /api/status` to include memory statistics (total beliefs, events, decisions).

2. **Frontend Navigation** (`index.html`):
   - Added 🧠 Memories nav item in a new "Memory" section with count badge.

3. **Frontend Views** (`app.js`):
   - `renderMemories()` — grid of member cards (avatar, name, role, belief/event counts) plus shared memory card.
   - `renderMemoryDetail(member)` — two-panel view: core beliefs (with delete buttons) and recent events.
   - `renderSharedMemory()` — two-panel view: council decisions list and narrative history.
   - `deleteCoreBelief()` — confirmation dialog + DELETE API call + view refresh.
   - Updated `updateNavCounts()` to display memory count badge.

4. **CSS Styles** (`style.css`):
   - Memory card styles (`.memory-card`, `.memory-avatar`, `.memory-stats`).
   - Two-column detail layout (`.memory-detail-grid`, `.memory-panel`).
   - Belief items (`.belief-item`, `.belief-topic`, `.btn-icon`, `.belief-delete`).
   - Event items (`.event-item`, `.event-header`, `.event-content`).
   - Shared history content styling (`.shared-history-content`).

5. **Testing** (`test_web_api.py`):
   - 13 new tests in `TestApiMemories` class: list with stats, detail with beliefs/events, limit param, case-insensitive lookup, not-found, belief deletion (success/missing topic/unknown topic), shared memory (empty/with data), status includes memories.
   - Fixed pre-existing test `test_council_list_no_avatar_url_by_default` by patching `COUNCIL_AVATARS_DIR` to temp dir in `client` fixture.
   - All 115 web_api tests pass (0 failures).

### Advice for Future Agents
- Memory tests require patching **both** `config.settings.MEMORIES_DIR` and `core.memory.MEMORIES_DIR` because the memory module imports the constant at the module level.
- The `COUNCIL_AVATARS_DIR` must also be patched in test fixtures to avoid reading real avatar files.
- 16 pre-existing failures exist in `test_registry.py`, `test_api_client.py`, and `test_memory_influence.py` — these are due to council member YAML changes and are unrelated to F-028.

---

## S-TECHDEBT-002 — Fix 16 Pre-existing Test Failures
**Timestamp:** 2026-03-19T01:00:00-04:00
**Status:** ✅ COMPLETED

### Summary
Resolved all 16 pre-existing test failures caused by user-customized council member YAML profiles. Tests had hardcoded old member names (Sage, Drift, etc.) and provider counts (6 OpenRouter / 3 Mancer) that no longer matched after the user renamed all 9 members and changed the provider split to 8/1.

### Root Causes
1. **`test_registry.py` (13 failures):** Tests loaded real YAML files and asserted hardcoded names (`Sage`, `Drift`), old provider counts (`openrouter=6`, `mancer=3`), specific personality traits (`thoughtful`), and specific models (`anthropic/claude-3.5-sonnet`).
2. **`test_api_client.py` (2 failures):** Tests for missing API keys created clients with empty strings, but the `APIClient.__init__` uses `or` which falls through to real env vars when real keys are set.
3. **`test_memory_influence.py` (1 failure):** `test_empty_member_memories` didn't pass `locations_dir`, so `build_context()` loaded real locations from disk, making `formatted_text` non-empty.

### Changes Made

1. **`tests/test_registry.py`** — Made 8 assertion blocks dynamic:
   - `test_all_expected_names_present`: Verifies 9 unique members instead of hardcoded name set.
   - `test_get_by_exact_name`, `test_get_case_insensitive_*`, `test_get_with_whitespace_stripped`: Use `registry.list_names()[0]` instead of `"Sage"`.
   - `test_contains_case_insensitive`: Uses dynamic first member name.
   - `test_members_by_provider_openrouter`: Asserts `> 0` instead of `== 6`.
   - `test_members_by_provider_mancer` → `test_members_by_provider_counts_consistent`: Asserts provider counts sum to total.
   - `test_sage_fields` → `test_member_fields_complete`: Validates all required fields are populated on first member.
   - `test_drift_uses_mancer` → `test_mancer_member_properties`: Tests first mancer member if any exist.
   - `test_sage_uses_openrouter` → `test_openrouter_member_properties`: Tests first openrouter member.
   - `test_frozen_dataclass`: Uses `registry.list_members()[0]` instead of `registry.get("Sage")`.

2. **`tests/test_api_client.py`** — Added `monkeypatch` to 2 tests:
   - `test_missing_openrouter_key_raises`: Clears `JERICHO_OPENROUTER_API_KEY` env var.
   - `test_missing_mancer_key_raises`: Clears `JERICHO_MANCER_API_KEY` env var.

3. **`tests/test_memory_influence.py`** — Fixed 1 test:
   - `test_empty_member_memories`: Passes `locations_dir` pointing to empty temp dir.

### Test Results
- **Before:** 1509 passed, 16 failed
- **After:** 1525 passed, 0 failed, 1 warning

### Advice for Future Agents
- Tests that load real council member data should **never hardcode member names** — the user actively customizes their YAML profiles. Use `registry.list_names()[0]` or similar dynamic lookups.
- Tests for "empty" or "missing" API keys must **clear the env vars** with `monkeypatch.delenv()` because the user has real keys set.
- Tests calling `build_context()` should pass **both** `memories_dir` and `locations_dir` temp dirs to avoid picking up real data.

---

## S-TECHDEBT-003: Consolidate Duplicated Test Helpers

### Summary
Removed ~300 lines of duplicated helper functions and fixture definitions across 5 test files. Each file had identical copies of `_make_member()`, `_mock_registry()`, and `_mock_api_client()` plus local fixture overrides (`tmp_dirs`, `members`, `registry`, `api_client`) that were already centralized in `conftest.py`.

### Files Changed

1. **`tests/test_agent_chat.py`** — Removed 67 lines, imported `make_member` from `tests.conftest`
2. **`tests/test_session.py`** — Removed 67 lines, imported `make_member` from `tests.conftest`
3. **`tests/test_human_chat.py`** — Removed 67 lines, imported `make_member` from `tests.conftest`
4. **`tests/test_discussion.py`** — Removed 39 lines (3 helper functions), imported `make_member`, `mock_registry`, `mock_api_client` from `tests.conftest`. Kept custom `tmp_dirs`, `members`, `_mock_proposal`, `_mock_proposal_manager` fixtures (legitimately different).
5. **`tests/test_character_design.py`** — Removed 39 lines (3 helper functions), imported `make_member`, `mock_registry`, `mock_api_client` from `tests.conftest`. Kept custom `tmp_dirs`, `members` fixtures (different directory structure and member names).

### Files Analyzed — No Change Needed
- **`tests/test_api_client.py`** — Uses `**overrides` dict pattern with different defaults; not a duplicate.
- **`tests/test_dashboard.py`** — Uses `SimpleNamespace` (not `CouncilMember`); completely different helper.

### Cleanup
- Deleted `test_output.txt` and `test_output_full.txt` from project root.
- `.gitignore` already contained `test_output*.txt`.

### Test Results
- **Before:** 1525 passed, 0 failed
- **After:** 1525 passed, 0 failed, 1 warning ✅

### Advice for Future Agents
- Use `from tests.conftest import make_member` (not `from conftest import`) because `tests/` has `__init__.py`.
- The conftest `mock_api_client` returns `"Acknowledged."` by default — update assertions accordingly when switching from local helpers.
- Files with legitimately different fixture structures (custom `tmp_dirs` keys, different member names) should keep their local fixtures even when helper functions are consolidated.

---

## F-029 — Evolution Web UI (2026-03-20)

### Summary
Integrated Character Evolution (F-013) and Evolution History (F-020) backends into the web dashboard (F-021).

### Backend — `core/web_api.py`
- **10 REST endpoints** added under `/api/evolutions`:
  - `GET /api/evolutions` — list with optional `character_id`, `status`, `author` filters
  - `GET /api/evolutions/{id}` — evolution detail
  - `POST /api/evolutions` — create evolution in draft status
  - `POST /api/evolutions/{id}/submit` — submit for governance review
  - `POST /api/evolutions/{id}/open-voting` — open voting
  - `POST /api/evolutions/{id}/resolve` — resolve voting
  - `POST /api/evolutions/{id}/apply` — apply approved evolution
  - `GET /api/evolutions/timelines` — list character timelines
  - `GET /api/evolutions/timelines/{id}` — timeline for specific character
  - `GET /api/evolutions/diff?old=...&new=...` — diff two character versions
- `GET /api/status` updated with `evolutions.count` and `evolutions.by_status`

### Frontend
- **`index.html`**: Added 🧬 Evolution nav item under Characters section
- **`app.js`**: Added `evolution` route case, 4 view functions (`renderEvolution`, `renderEvolutionDetail`, `renderEvolutionTimelines`, `renderEvolutionTimelineDetail`), dashboard stat card, nav count updater
- **`style.css`**: Added `.stat-card.cyan` and ~340 lines of evolution-specific styles (lifecycle stepper, change cards, timeline cards, version chain chips, snapshot cards, event items)

### Tests — `tests/test_web_api.py`
- 16 new tests in `TestApiEvolutions`:
  - List (empty, with records, filter by status, filter by character)
  - Detail (found, not found)
  - Create (success, missing fields, char not found, char not active)
  - Status includes evolutions
  - Timelines (list, detail, not found)
  - Diff (same version, not found)

### Test Results
- **Baseline:** 1533 passed, 2 pre-existing failures
- **After:** 1549 passed, 2 pre-existing failures (same), 0 regressions ✅

---

## Session: S-FEAT-00000030
**Timestamp:** 2026-03-20 18:55:00
**Feature:** `F-030` — Presence Wrapper System (SilentPassa)
**Status:** completed

### Summary
Implemented the `[PRESENT]/[SILENCE]` wrapper system for agent chat messages — a frontend-only display feature inspired by Ankha's decree:

- **Modified `core/web_static/app.js`** — Five changes:
  - Added `silentpassaEnabled` flag to `state` object, initialized from `localStorage` (defaults to ON)
  - Created `wrapPresenceContent(renderedHtml, speakerName)` — wraps agent HTML in `[PRESENT]` tags; empty content becomes `[SILENCE]` with speaker name
  - Created `toggleSilentPassa(chatId)` — toggles state, persists to `localStorage`, re-renders chat
  - Applied wrappers to agent messages in `renderChatDetail()` (historical messages) and `appendAgentBubble()` (streaming messages)
  - Added "SilentPassa" pill toggle button in chat topbar `.chat-topbar-actions`, showing 🔔/🔕 with styled ON/OFF states

- **Modified `core/web_static/style.css`** — ~80 lines:
  - `.silentpassa-toggle` / `.silentpassa-on` / `.silentpassa-off` — styled toggle button (pill-shaped, cyan glow when active)
  - `.presence-wrapper` / `.presence-tag` — cyan left-border, monospace `[PRESENT]` tags
  - `.silence-wrapper` / `.silence-tag` / `.silence-speaker` — muted left-border, dim italic style

- **Updated `features.json`** — added F-030 entry

### Technical Debt
- None — this is a pure frontend display feature with no backend changes.

### Test Results
- **1550 passed**, 1 pre-existing failure (`test_archived_terminal` in `test_characters.py` — unrelated), 0 regressions ✅

### Advice for Next Agent
1. The wrapper system is controlled by `state.silentpassaEnabled` — toggled via `toggleSilentPassa()` in the chat topbar
2. `localStorage` key is `silentpassa` — values `'on'`/`'off'` (defaults ON when not set)
3. Wrappers are applied at render time only — stored messages are unmodified
4. To add new citizens' soul-text expressions, modify `wrapPresenceContent()` to check speaker names and output character-specific wrapper content

---

## Session: S-FEAT-00000031
**Timestamp:** 2026-03-20 19:21:00
**Feature:** Evolution Proposal Category
**Status:** completed

### Summary
Added `"evolution"` as a new proposal category with navigational handoff to the Evolution section:

- **Modified `config/settings.py`** — added `"evolution"` to `PROPOSAL_CATEGORIES` tuple
- **Modified `core/web_api.py`** — added `evolution_handoff` field to the vote response when an evolution-category proposal passes (category == "evolution" && tally.approved)
- **Modified `core/web_static/app.js`** — two changes:
  - Added `'evolution'` to the hardcoded category dropdown in `renderProposals()`
  - Added an evolution handoff banner in `renderProposalDetail()` — shows a "🧬 Go to Evolution Section" button when an evolution proposal is approved
- **Modified `core/web_static/style.css`** — added `badge-evolution` (purple) and `evolution-handoff-banner` styles
- **Added 2 tests to `tests/test_web_api.py`**:
  - `test_create_proposal_evolution_category` — verifies evolution-category proposals can be listed/filtered
  - `test_evolution_category_in_settings` — verifies "evolution" is in PROPOSAL_CATEGORIES

### Test Results
- **1552 passed**, 1 pre-existing failure (`test_archived_terminal` in `test_characters.py` — unrelated), 0 regressions ✅

### Advice for Next Agent
1. The handoff is **navigational only** — clicking the button navigates to the Evolution view. No auto-creation of EV-XXXX records from proposals.
2. The Evolution section already has its own creation flow (`POST /api/evolutions`).
3. `character_evolution.submit_for_review()` still creates proposals with category `"character"`, not `"evolution"`. The new `"evolution"` category is for user-created proposals that suggest evolutions.

---

## Session: S-FEAT-00000032
**Timestamp:** 2026-03-21 23:25:00
**Feature:** Frutiger Aero Skin
**Status:** completed

### Summary
Added a "Frutiger Aero" skin option to the Settings page's Appearance section:

- **Modified `core/web_static/app.js`** — added `frutiger_aero` entry to the `SKINS` object with:
  - Label, icon (🫧), description ("Glossy Y2K optimism"), and 5 representative swatches
  - CSS variable overrides for all design tokens: light backgrounds, dark-on-light text, sky-blue accents, glossy borders, and soft shadows
- **Modified `core/web_static/style.css`** — appended ~210 lines of `[data-skin="frutiger_aero"]` CSS rules covering:
  - Sky/nature gradient `body::before` background
  - Frosted-glass sidebar and cards (glassmorphism with `backdrop-filter`)
  - Glossy aqua gradient buttons with inner highlights
  - Light-mode scrollbars, toasts, tables, chat bubbles, inputs
  - Smooth skin transition animation via `[data-skin-transitioning]`

No changes to settings HTML structure — the existing `renderSettings()` skin card loop automatically picks up new SKINS entries.

### Test Results
- **1588 passed**, 1 pre-existing failure (`test_archived_terminal` in `test_characters.py` — unrelated), 0 regressions ✅

### Advice for Next Agent
1. To add more skins, add entries to the `SKINS` object in `app.js` (top of file) with `vars` mapping CSS custom properties, then add corresponding `[data-skin="your_skin"]` CSS rules
2. The `applySkin()` function applies overrides via `root.style.setProperty()` and sets `data-skin` attribute on `<html>` — CSS selectors use `[data-skin="..."]` for non-variable overrides
3. Skin choice persists in `localStorage` key `jericho-skin` and is applied on `DOMContentLoaded`
4. The `[data-skin-transitioning]` attribute enables smooth cross-skin transitions for 0.5s after switching

---

## Session: S-FEAT-00000033
**Timestamp:** 2026-03-22 09:59:00
**Feature:** `F-032` — Obelisk Monetary System — Backend
**Status:** completed

### Summary
Implemented the Obelisk monetary system backend — a three-tier currency (Bronze, Silver, Gold) for the Jericho world with 100:1 conversion between tiers.

### Changes Made
- **Created `config/settings.py`** additions — `TREASURY_DIR`, `OBELISK_TIERS`, `OBELISK_CONVERSION_RATE` (100), `OBELISK_DEFAULT_BALANCE` (200 Gold), `OBELISK_GOVERNMENT_BALANCE` (1000 Gold), `OBELISK_ACCOUNT_TYPES`
- **Created `core/treasury.py`** (~370 lines) — full filesystem-backed treasury module:
  - `ObeliskBalance` frozen dataclass with `total_in_bronze()`, `total_in_gold_display()`, `create()` factory
  - `TreasuryAccount` frozen dataclass with `to_dict()`/`from_dict()` roundtrip
  - `TreasuryManager` — `get_or_create()`, `credit()`, `debit()`, `transfer()`, `normalize()`, `initialize_defaults()`
  - `make_account_id()` helper — canonical account IDs like `ACCT-cm-sage`, `ACCT-gov-jericho`
  - Exception hierarchy: `TreasuryError`, `AccountNotFoundError`, `InsufficientFundsError`, `TreasuryValidationError`
- **Modified `core/web_api.py`** — added 7 treasury API endpoints:
  - `GET /api/treasury` (list, optional `?type=` filter)
  - `GET /api/treasury/{account_id}` (detail)
  - `POST /api/treasury/initialize` (create defaults for all entities)
  - `POST /api/treasury/{account_id}/credit` and `/debit`
  - `POST /api/treasury/transfer`
  - `GET /api/status` now includes `treasury.total_accounts` and `treasury.government_balance`
- **Created `tests/test_treasury.py`** (~500 lines, 82 tests) — comprehensive core module tests
- **Modified `tests/test_web_api.py`** — added `TestApiTreasury` class (11 API endpoint tests)
- **Updated `features.json`** — added F-032 (completed), F-033 (pending: Frontend UI), F-034 (pending: Taxation)

### Test Results
- **1681 passed**, 1 pre-existing failure (`test_archived_terminal`), 0 regressions ✅
- 93 new treasury tests (82 core + 11 API) — all passing

### Advice for Next Agent
1. **F-033 (Frontend)** is the next task: add Treasury nav/view, Obelisk balance on character/council/user profiles
2. Account IDs follow the pattern `ACCT-{prefix}-{slug}` — prefixes: `cm` (council), `ch` (character), `user`, `gov` (government)
3. Use `POST /api/treasury/initialize` to bootstrap accounts for all existing entities before displaying balances
4. The `normalize()` method auto-converts excess coins upward (e.g. 150 bronze → 1 silver + 50 bronze)
5. **F-034 (Taxation)** is in the backlog — add tax on transactions collected into government treasury
6. The pre-existing `test_archived_terminal` failure is still present — `archived` status allows transitions to `active`/`draft` but the test expects it to be terminal

---

## Session — F-033: Obelisk Monetary System — Frontend Web UI

**Date**: 2026-03-22
**Feature**: F-033

### Summary
Implemented the Treasury frontend web UI for the Obelisk monetary system. This is a frontend-only feature — all 7 backend API endpoints already existed from F-032.

### Changes Made
- **`core/web_static/index.html`** — Added `🪙 Treasury` nav item under **World** section with count badge
- **`core/web_static/app.js`** — ~370 lines added:
  - Router case for `treasury` view (list + detail)
  - `renderTreasury()` — list view with type filter, Initialize button, 4-column card grid
  - `renderTreasuryDetail()` — detail view with Gold/Silver/Bronze tier display, credit/debit forms
  - `openTransferModal()` / `executeTransfer()` — modal for account-to-account transfers
  - `initializeTreasury()` / `treasuryCredit()` / `treasuryDebit()` — action handlers
  - Dashboard stat card showing total accounts + government balance
  - Nav count updater for treasury account count
- **`core/web_static/style.css`** — ~240 lines added:
  - `.treasury-grid`, `.treasury-card`, `.obelisk-balance`, `.obelisk-coin` — card layout
  - `.treasury-tier-gold/silver/bronze` — tier display with gradient backgrounds
  - `.treasury-balance-panel`, `.treasury-input-row` — detail view forms
  - `.badge-council_member/character/user/government` — account type badges
- **`features.json`** — F-033 status set to `completed`

### Test Results
- **190 passed** in `test_web_api.py`, 0 regressions ✅
- No new backend tests needed (frontend-only feature)

### Advice for Next Agent
1. **F-034 (Obelisk Taxation System)** is the next eligible feature
2. Treasury nav count now shows in sidebar, updates via `/api/status → treasury.total_accounts`
3. The transfer modal reuses `.promote-modal` CSS classes for consistency
4. `obeliskTotal()` in app.js converts balances to gold equivalent using rate=100
5. The `badge()` function's second parameter controls CSS class — account type badges use e.g. `badge-government`

---

## Session: S-INIT-00000035
**Timestamp:** 2026-03-22 11:00:00
**Feature:** `F-035` — World Items System
**Status:** completed

### Summary
Implemented a complete World Items system mirroring the Locations pattern across all layers.

### Changes Made
- **`config/settings.py`** — Added `ITEMS_DIR`, `ITEM_STATUSES`, `ITEM_PROPERTY_TYPES`, `"item"` to `PROPOSAL_CATEGORIES`
- **`core/items.py`** — **[NEW]** ~420 lines: `ItemProperty`, `Item` frozen dataclasses, `ItemManager` with CRUD, lifecycle (draft→active→archived), property management, atomic writes
- **`core/web_api.py`** — 6 item REST endpoints (`GET/POST /api/items`, `GET/PUT /api/items/{id}`, `PUT .../status`), item proposal handoff endpoint, items count in `/api/status`
- **`core/memory_influence.py`** — Added `_load_active_items()`, wired into `build_context()` and `format_for_prompt()` for LLM injection
- **`core/web_static/index.html`** — Added 📦 Items nav entry under World section
- **`core/web_static/app.js`** — ~380 lines: `renderItems()`, `renderItemDetail()`, `createItem()`, `saveItemEdit()`, `updateItemStatus()`, `addItemProperty()`, `removeItemProperty()`, `handoffItemProposal()`, dashboard items card, nav count
- **`tests/test_items.py`** — **[NEW]** 65 unit tests across 12 classes
- **`tests/test_web_api.py`** — Added `TestApiItemProposalHandoff` (5 tests)
- **`features.json`** — F-035 added and marked completed

### Test Results
- **65 passed** in `test_items.py` ✅
- **1751 passed, 1 pre-existing failure** in full suite (unrelated characters test)

### Advice for Next Agent
1. Items follow the same pattern as Locations — look at `core/locations.py` as the canonical reference
2. The frontend property add/remove works by fetching current item, modifying the properties array, and sending via PUT update
3. `"item"` is now a valid proposal category — council can propose items just like locations
4. Active items get injected into LLM context in the "World Items (Known Artifacts & Objects)" section
5. The 1 pre-existing test failure is `test_characters.py::TestStatusLifecycle::test_archived_terminal` — unrelated to items

---

## Session: Dashboard Layout — Move Analytics to Overview
**Timestamp:** 2026-03-22 19:14:00
**Feature:** Dashboard sidebar reorganization (not a features.json feature)
**Status:** completed

### Summary
Reorganized the sidebar navigation in `index.html` to free up space:

- **Moved Analytics nav item** from the standalone "Insights" section into the "Overview" section, directly below Dashboard
- **Removed the "Insights" section** entirely — it only contained the single Analytics link
- No changes to `app.js`, `style.css`, or any backend files — routing and rendering remained unchanged

### Technical Debt
- None introduced.

### Test Results
- **1754 passed**, 1 pre-existing failure (`test_archived_terminal` — unrelated characters test)

### Advice for Next Agent
1. The sidebar sections are now: Overview (Dashboard, Analytics), Governance, Characters, World, Communication, Memory, Configuration
2. If more space is needed in the future, consider collapsing the Memory section into Configuration, or making the sidebar scrollable/collapsible
3. The 1 pre-existing test failure is `test_characters.py::TestStatusLifecycle::test_archived_terminal` — caused by bidirectional character transitions added earlier, not by this change

---

## Session: S-NARRATIVE-00000001
**Timestamp:** 2026-03-23 02:30:00
**Feature:** Emergent Narrative Engine
**Status:** completed

### Summary
Implemented a template-driven narrative engine that generates "news bulletins" from recent in-world events and displays them on the Dashboard homepage.

### Changes
- **New:** `core/narrative_engine.py` — `NarrativeBulletin` dataclass + `NarrativeEngine` class with template banks for 6 event types (proposals, votes, characters, items, locations, treasury)
- **New:** `tests/test_narrative_engine.py` — 30 tests covering bulletins, sorting, time window filtering, template variety, and API endpoint
- **Modified:** `config/settings.py` — Added `NARRATIVE_MAX_BULLETINS=10`, `NARRATIVE_MAX_AGE_DAYS=30`
- **Modified:** `core/web_api.py` — Added `GET /api/narrative-bulletins` endpoint
- **Modified:** `core/web_static/app.js` — Added Jericho Times banner to `renderDashboard()` with auto-cycling, prev/next controls, fade animation, click-to-navigate
- **Modified:** `core/web_static/style.css` — ~220 lines of banner CSS with skin support (default, frutiger_aero, vaporwave)

### Test Results
- **226 passed** (30 narrative engine + 196 web_api)

### Advice for Next Agent
1. The narrative engine uses pure templates — no LLM calls. If richer narratives are wanted, consider an LLM-based generation path
2. Bulletin count and age window are controlled via `NARRATIVE_MAX_BULLETINS` and `NARRATIVE_MAX_AGE_DAYS` in `config/settings.py`
3. To add new event types, add a template bank and a `_<type>_bulletins()` method to `NarrativeEngine`, then call it from `generate_bulletins()`
4. The banner auto-cycles every 8 seconds and supports click-to-navigate to the source section

---

## Session: S-STORES-00000001
**Timestamp:** 2026-03-26 00:00:00
**Feature:** F-036 World Stores System
**Status:** completed

### Summary
Implemented a full commerce system enabling world stores with inventory management, pricing, and treasury-integrated purchasing.

### Changes
- **New:** `core/stores.py` — `StoreItem` + `Store` frozen dataclasses, `StoreManager` with CRUD, inventory management, lifecycle (draft→active→archived), and purchase flow with `TreasuryManager` integration
- **New:** `tests/test_stores.py` — 88 comprehensive unit tests covering dataclasses, manager ops, lifecycle, inventory, purchases, edge cases
- **Modified:** `config/settings.py` — Added `STORES_DIR`, `STORE_STATUSES`, `STORE_TYPES`
- **Modified:** `core/web_api.py` — Replaced old location-based store stub with 8 StoreManager-backed endpoints (list, detail, create, update, status, inventory add/remove/update, purchase)
- **Modified:** `core/web_api.py` — Added stores count to `/api/status` endpoint
- **Modified:** `core/web_static/app.js` — Rewrote `renderStores()` (list with filters + create form) and `renderStoreDetail()` (inventory table, add/remove, status transitions, edit form, purchase form)
- **Modified:** `core/web_static/style.css` — Added inventory table styles + store type badge variants
- **Modified:** `core/web_static/index.html` — Nav item already existed (pre-scaffolded)
- **Modified:** `features.json` — Added F-036 entry

### Architecture
- StoreManager follows established pattern: atomic filesystem writes, frozen dataclasses, sequential IDs (STORE-0001)
- Store inventory is a list of `StoreItem` entries (item_id, price in gold/silver/bronze, quantity)
- Purchase flow: validates stock → resolves seller account → `TreasuryManager.transfer()` → decrements quantity
- Store types: general, blacksmith, alchemist, enchanter, tavern, custom

### Test Results
- **2117 passed**, 12 skipped, 0 failures (up from 2029 → +88 new store tests)

### Advice for Next Agent
1. Store inventory references item IDs but does not validate they exist in the Items system — a future cross-manager validation could be added
2. The purchase endpoint uses `TreasuryManager.transfer()` which requires both buyer and seller accounts to exist
3. Store types are defined in `config/settings.py` as `STORE_TYPES` — add new types there if needed
4. The frontend purchase form uses raw Account IDs — a future enhancement could add a buyer account picker dropdown

---

## Session: S-BUGFIX-STORE-MODAL-00000001
**Timestamp:** 2026-04-05 00:07:00
**Focus:** Fix "Add Location as Store" button not progressing to modal (F-036 Store System)

### Problem
The "Add Location as Store" button in the Stores section appeared non-functional — clicking it produced no visible result.

### Root Cause (Two-Part CSS Bug)
1. **Missing `.promote-modal-overlay` CSS class** — The `openLocationStoreModal()` function creates an overlay div with `className = 'promote-modal-overlay'`, but this CSS class was never defined in `style.css`. Without CSS, the overlay used default browser styles (position static, zero height), rendering it invisible.
2. **Conflicting `.promote-modal` class on inner content** — The inner modal content div used `class="promote-modal store-form-card"`. The `.promote-modal` CSS rule includes `display: none` by default, hiding the form content.

### Fix Applied
- **`core/web_static/style.css`** — Added `.promote-modal-overlay` CSS class with `display: flex; position: fixed; inset: 0; z-index: 2000;` and backdrop styling.
- **`core/web_static/app.js`** — Changed inner div class from `"promote-modal store-form-card"` to just `"store-form-card"` with inline width constraints.

### Files Modified
- **Modified:** `core/web_static/style.css` — Added `.promote-modal-overlay` CSS rule
- **Modified:** `core/web_static/app.js` — Removed conflicting `promote-modal` class from inner modal div

### Test Results
- **2118 passed**, 12 skipped, 0 failures (no regressions)

### Advice for Next Agent
1. The `.promote-modal-overlay` class differs from `.promote-modal` in that it uses `display: flex` by default (no JS toggle needed) — use it for dynamically created modals appended to `document.body`
2. The `openTransferModal()` in Treasury uses `className = 'promote-modal'` with `style.display = 'flex'` — both patterns work, just be consistent

---

## Session: S-UX-STORE-DROPDOWN-00000001
**Timestamp:** 2026-04-05 14:55:00
**Focus:** Replace manual Item ID text inputs with dropdown selects in Store detail view

### Summary
Enhanced the Stores tab UX by replacing free-text Item ID inputs with dropdown menus populated from active items.

### Changes Made
- **Modified:** `core/web_static/app.js` — `renderStoreDetail()` function:
  1. **Fetches active items** from `/api/items?status=active` on detail load
  2. **"Add Inventory Item" form**: Replaced `<input type="text">` with `<select>` dropdown showing all active items as `"ITEM-XXXX — Item Name"`. Items already in the store's inventory are excluded from the dropdown
  3. **"Purchase an Item" form**: Replaced `<input type="text">` with `<select>` dropdown showing only items currently in the store's inventory, with price and quantity info: `"ITEM-XXXX — Item Name · 10G · Qty: 5"`
  4. **Inventory table**: Item ID column now also shows the item name alongside the ID for readability

### Test Results
- **2117 passed**, 12 skipped, 1 pre-existing failure (`test_memory_influence` — unrelated) — 0 regressions ✅

### Advice for Next Agent
1. The active items fetch uses `try/catch` with empty fallback — if the items API isn't available, the dropdown will show "No active items available" gracefully
2. The add-inventory dropdown filters out items already in inventory (`existingItemIds` Set) to prevent duplicate adds
3. The purchase dropdown includes price and quantity in each option label for quick reference
4. The `addStoreInventory()` and `purchaseFromStore()` functions use `.value` on the select element — no handler changes were needed since `.value` works identically for `<select>` and `<input>`

---

## Session: S-DOCS-README-00000001
**Timestamp:** 2026-04-05 19:14:00
**Focus:** Complete README.md rewrite
**Status:** completed

### Summary
Rewrote the entire `README.md` to accurately reflect the current state of the Jericho project after 36 feature implementations.

### Changes Made
- **Modified:** `README.md` — Full rewrite (~420 lines) covering:
  - Updated project description from "AI Council" to "AI city" simulation
  - Council member table with all 9 current members
  - Comprehensive features list organized into 7 domains: Core Infrastructure, Governance, Character System, World Building, Economy, Intelligence, Communication, plus User Interfaces
  - Quick Start guide with installation, one-click Windows launcher, and web dashboard launch
  - Web Dashboard section with navigation overview and key capabilities
  - Full CLI reference with all available commands
  - Governance Model section with lifecycle diagrams for proposals, character evolutions, and laws
  - Economy section covering the Obelisk currency system, account types, taxation, and stores
  - Updated Project Structure tree showing all ~35 core modules, data directories, and 2,117+ tests
  - Configuration reference tables (governance, economy, API, memory settings)
  - Dependencies table
  - Architecture Principles section documenting the 7 core design patterns

### Test Results
- **2117 passed**, 1 pre-existing failure (`test_archived_terminal`), 0 regressions ✅

### Advice for Next Agent
1. The README is now comprehensive — if a new feature is added, update the relevant section (features list, project structure, configuration tables)
2. The council member table may need updating if the user customizes their YAML profiles
3. Test count should be updated as new tests are added — currently 2,117+
4. The pyproject.toml description still says the old "AI characters through democratic governance" — consider updating it to match the broader scope

---

## Session: S-BUGFIX-MEMINFLUENCE-00000001
**Timestamp:** 2026-04-05 19:21:00
**Focus:** Fix pre-existing `test_memory_influence::TestBuildContext::test_empty_member_memories` failure
**Status:** completed

### Problem
`test_empty_member_memories` asserted that `ctx.formatted_text == ""` for a member with no memories/beliefs. The assertion failed because the formatted text contained active items from the production `data/items/` directory.

### Root Cause
The test passed `memories_dir` and `locations_dir` overrides to isolate from production data, but did **not** pass `items_dir`. When `items_dir=None`, `_load_active_items()` falls back to the real `ITEMS_DIR` from `config.settings`, which contained active items (e.g., "Liquid Luck" potion). These items were included in the formatted output, breaking the empty-text assertion.

### Fix
Added an empty `items_dir` override to the test, matching the existing pattern for `memories_dir` and `locations_dir`:
- **Modified:** `tests/test_memory_influence.py` — `test_empty_member_memories` now creates and passes `items_dir = tmp_path / "items"` to fully isolate from production data.

### Test Results
- **2118 passed**, 12 skipped, 0 failures — the previously-failing test now passes ✅

### Advice for Next Agent
1. When testing `build_context()`, always pass **all three** directory overrides (`memories_dir`, `locations_dir`, `items_dir`) to isolate from production data
2. If a new world-data source is added to `build_context()` (e.g., stores, NPCs), ensure existing tests are updated with the new directory override to prevent similar regressions
3. Test count is now 2,118 (up from 2,117)

---

## Session: S-F038-00000001
**Timestamp:** 2026-04-05 19:58:00
**Feature:** `F-038` — Sidebar Accordion Navigation
**Status:** completed

### Summary
Redesigned the sidebar navigation from a flat always-visible list to a collapsible accordion, solving the UI overflow problem caused by 18 nav items exceeding the viewport height.

### Problem
The sidebar had 18 navigation items across 5 sections (Overview, Governance, Characters, World, Configuration). The bottom items (Stores, Treasury, Taxation, Settings) were cut off below the viewport, with no way to access them without scrolling the entire page. The upcoming ComfyUI integration feature would make this worse.

### Solution — Collapsible Accordion (Option A)
Three design options were proposed (Accordion, Icon Rail, Scrollable); the user approved Option A for its minimal disruption and scalability.

### Changes Made
- **Modified:** `core/web_static/index.html` — Section headers now have `onclick="toggleNavSection()"` handlers and chevron indicators (▸/▾). Nav items are wrapped in `.nav-section-items` containers. Settings is pinned to sidebar bottom with `nav-section-pinned`. Cache-busted CSS/JS to `?v=4`.
- **Modified:** `core/web_static/style.css` — Added `.nav-sections-scroll` (scrollable nav area), `.nav-section-items` (collapsible via `max-height` transition), `.nav-chevron` (rotates 90° on expand), `.nav-section-pinned` (flex `margin-top: auto`). Reduced logo margin. Thin scrollbar for edge cases.
- **Modified:** `core/web_static/app.js` — Added `VIEW_TO_SECTION` mapping, `toggleNavSection()`, `_expandSectionForView()` (auto-opens on navigation), `_saveAccordionState()` / `_restoreAccordionState()` (localStorage persistence). Section state survives page reloads.
- **Modified:** `features.json` — Added F-037 (ComfyUI Integration, planned) and F-038 (Sidebar Accordion, completed).

### Skin Compatibility
Verified across all 3 UI skins:
- **Default** (dark glassmorphism) — chevrons and transitions integrate seamlessly
- **Frutiger Aero** (glossy Y2K) — section headers readable on light background
- **Vaporwave** (neon retro) — neon styling properly applied to accordion elements

### Behavior
- Default state: Overview + section containing active page are expanded; others collapsed
- Click section header → toggle open/closed with smooth CSS transition
- Navigate to any page → its parent section auto-expands
- Settings always visible (pinned to bottom with border separator)
- Accordion state persisted in `localStorage('jericho-nav-accordion')`

### Test Results
- **2118 passed**, 12 skipped, 0 failures — no backend regressions ✅
- Browser-tested: navigation, toggle, persistence, all 3 skins ✅

### Advice for Next Agent
1. When adding new nav items, just add them inside the appropriate `.nav-section-items` div and update `VIEW_TO_SECTION` in app.js
2. `F-037` (ComfyUI Integration) is now in the backlog as `planned` — it depends on F-031 (Task System)
3. The accordion CSS uses `max-height: 500px` for expanded sections — this will comfortably fit 10+ items per section before needing adjustment
4. Test count remains at 2,118 (pure frontend change, no new backend tests needed)

---

## Session: S-PLANNING-COMFYUI-00000001
**Timestamp:** 2026-04-05 20:30:00
**Feature:** ComfyUI Integration — Architecture & Planning
**Status:** planning complete — ready for implementation

### Summary
Researched ComfyUI's API surface, analyzed three integration architectures, and produced a detailed 7-feature implementation plan for integrating image generation into Jericho. All architecture decisions were approved by the user.

### Architecture Decision: Workflow Template System (Option B)

**Chosen approach:** Users design workflows in ComfyUI's visual editor, export as API-format JSON, upload to Jericho. Jericho fills placeholder tokens (`%prompt%`, `%negative%`, `%seed%`, `%width%`, `%height%`, `%entity_name%`, `%entity_type%`) and POSTs the filled JSON to ComfyUI's `POST /prompt` endpoint. Same pattern SillyTavern uses.

**Rejected approaches:**
- Option A (hardcoded workflow) — too inflexible, locks users into one model/sampler
- Option C (custom ComfyUI node) — too complex, tight coupling, requires custom node installation

### Key Decisions (User-Approved)

| Decision | Resolution |
|----------|-----------|
| Architecture | Workflow Template System (Option B) |
| ComfyUI Connection | Local only — `127.0.0.1:8188` default, configurable host:port |
| Prompt Generation | 5 modes: council vote, character/member, standalone system, user+character refinement, raw user input |
| Per-Entity Templates | Yes but deferred (start with single default template, F-039 later) |
| Image Storage | `data/images/{entity_type}/{entity_id}/` with `images.json` metadata, multiple images per entity, primary flag |
| Image Retrieval | Download via ComfyUI's `GET /view` API — don't touch ComfyUI's filesystem |
| Style Presets | Yes — ship with defaults (Fantasy Art, Anime, Realistic, etc.) |
| Image Dimensions | User-configurable per entity type in Settings (not hardcoded — different models need different resolutions) |
| Generation Queue | Yes, capped at 10 jobs |

### Feature Breakdown (7 features from original F-037)

```
F-037a → ComfyUI Client & Connection Manager     (backend core — HTTP client, templates)
F-037b → Image Manager & Storage System           (backend core — image files, metadata)
F-037c → Prompt Generation Engine                 (backend — 5-mode prompt builder, style presets)
F-037d → ComfyUI Settings & Templates Web UI      (frontend — settings page)
F-037e → Entity Image Galleries                   (frontend — galleries on detail pages)
F-037f → Generation Pipeline & Progress UI        (frontend — generate button, SSE progress, queue)
F-037g → Prompt Style Presets & Queue Polish       (polish — batch gen, queue dashboard, preset editor)
```

Future features (separate conversations):
```
F-039 → Per-Entity-Type Workflow Templates
F-040 → Exploration Image Galleries
F-041 → Story Illustration System
```

### Image Retrieval Flow (Critical Design Detail)

ComfyUI saves images to its own output folder. Jericho retrieves them via API:
1. `POST /prompt` → get `prompt_id`
2. Poll `GET /history/{prompt_id}` → get output filename from `outputs.{node_id}.images[0].filename`
3. `GET /view?filename=X&subfolder=&type=output` → download image bytes
4. Save to `data/images/{entity_type}/{entity_id}/img_XXX.png`
5. Update `images.json` metadata

### ComfyUI API Reference (for implementing agents)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/system_stats` | GET | Connection test — returns system info |
| `/prompt` | POST | Queue workflow for execution, returns `{"prompt_id": "..."}` |
| `/history/{prompt_id}` | GET | Execution status/results — includes output filenames |
| `/view?filename=X&subfolder=Y&type=output` | GET | Download generated image bytes |
| `/upload/image` | POST | Upload input image (for img2img workflows) |

### Prompt Generation Modes (for F-037c)

1. **Council Vote** — Multiple members each generate a prompt, user picks or votes on the best
2. **Character/Member** — A specific character generates the prompt in their style
3. **System (Standalone)** — Generic "image prompt expert" system prompt, no personality
4. **User + Refinement** — User writes base prompt, character enhances it
5. **Raw User** — User provides exact prompt, no LLM involvement

### Files Changed in This Planning Session

- **Modified:** `features.json` — replaced monolithic F-037 with F-037a through F-037g, added F-039/F-040/F-041
- **Created:** Implementation plan artifact with full specifications

### Technical Debt
- None introduced (planning session only)

### Advice for Next Agent

1. **Start with F-037a** (ComfyUI Client) — it's pure backend with no frontend or prompt logic. Clean, focused scope.
2. **Follow Jericho patterns exactly:** frozen dataclasses, `to_dict()`/`from_dict()`/`create()` factories, `atomic_write()` from `core.utils`, sequential IDs (TPL-XXXX, IMG-XXXX, GEN-XXXX)
3. **ComfyUI's API is sync HTTP** — use `httpx` (already a project dependency) for the client. No WebSocket needed; polling `/history/{id}` is sufficient given the 10-job queue cap
4. **The implementation plan artifact** has detailed pseudocode for all classes and methods — use it as the specification
5. **Each feature is scoped for a single session** — don't scope-creep into the next feature
6. **Test everything with mocks** — the ComfyUI server won't be running during tests. Mock all HTTP calls via `httpx` mocking or `unittest.mock.patch`
7. **app.js is 3500+ lines** — use the section map in `project-reference.md` to navigate. grep_search does NOT work on it
8. **pytest is garbled on Windows** — use the subprocess→file→view_file pattern from `project-reference.md`
9. **Per-entity-type resolutions are user-configured** — store defaults in `.env` via the existing `APIKeyManager` pattern or a new config module
10. **The user explicitly requested diligence and accuracy** — take time to design properly, prioritize correctness over speed

---

## Session: S-F037A-00000001
**Timestamp:** 2026-04-05 20:50:00
**Feature:** `F-037a` — ComfyUI Client & Connection Manager
**Status:** completed

### Summary
Implemented the backend HTTP client for ComfyUI and the workflow template storage system — the foundation of Jericho's image generation pipeline.

### Changes Made
- **New:** `core/comfyui_client.py` (~580 lines) — Three major components:
  1. **Exception hierarchy**: `ComfyUIError` (base), `ComfyUIConnectionError` (with host/port), `ComfyUIWorkflowError` (with prompt_id), `TemplateError` (base), `TemplateNotFoundError` (with template_id), `TemplateValidationError` (with errors list)
  2. **Data classes**:
     - `ComfyUIConfig` (frozen) — host, port, base_url property, create() with validation
     - `WorkflowTemplate` (frozen) — id, name, description, workflow_json, auto-detected placeholders, entity_type, author, timestamps, metadata
     - `GenerationJob` (frozen) — job_id, prompt_id, template_id, entity linkage, status tracking
  3. **Placeholder system**: `detect_placeholders()` recursively scans JSON for `%token%` patterns, `fill_placeholders()` deep-copies and replaces tokens. 12 known placeholder types (prompt, negative, seed, width, height, entity_name, entity_type, steps, cfg, sampler, scheduler, batch_size)
  4. **ComfyUIClient class** — async HTTP client wrapping `httpx.AsyncClient`:
     - `test_connection()` → `GET /system_stats`
     - `queue_workflow()` → `POST /prompt`, returns prompt_id
     - `get_history()` → `GET /history/{prompt_id}`
     - `poll_until_complete()` — polls with configurable interval and max attempts
     - `extract_output_images()` — parses history for output filenames
     - `download_image()` → `GET /view?filename=X&type=output`
     - `upload_image()` → `POST /upload/image`
  5. **WorkflowTemplateManager class** — filesystem-backed CRUD for `TPL-XXXX.json`:
     - `create()` — validates name/workflow, auto-detects placeholders, sequential IDs
     - `get()` / `list_templates()` / `has_template()` — with entity_type and author filters
     - `update()` — mutable fields only, re-detects placeholders on workflow change
     - `delete()` — removes template file
     - `fill_template()` — loads template, fills placeholders, returns ready-to-submit JSON
     - `get_unfilled_placeholders()` — reports which placeholders still need values

- **Modified:** `config/settings.py` — Added ComfyUI settings section:
  - `COMFYUI_DEFAULT_HOST` ("127.0.0.1"), `COMFYUI_DEFAULT_PORT` (8188)
  - `COMFYUI_TEMPLATES_DIR` (data/comfyui/templates/)
  - `COMFYUI_IMAGES_DIR` (data/images/) — placeholder for F-037b
  - `COMFYUI_MAX_QUEUE_SIZE` (10), `COMFYUI_POLL_INTERVAL` (1.0s), `COMFYUI_POLL_TIMEOUT` (300s)

- **New:** `tests/test_comfyui_client.py` (~930 lines) — 118 tests across 22 classes:
  - `TestComfyUIConfig` (10): fields, defaults, base_url, frozen, roundtrip, create factory, validation
  - `TestWorkflowTemplate` (7): fields, frozen, roundtrip, create factory, auto-detect, defaults
  - `TestGenerationJob` (5): fields, frozen, roundtrip, create factory, defaults
  - `TestDetectPlaceholders` (7): basic, no placeholders, dedup, sorted, nested, empty, non-string
  - `TestFillPlaceholders` (8): basic, multiple, unfilled, immutable original, non-string, nested, empty, numeric
  - `TestPlaceholderPattern` (4): matches, no-match, uppercase, frozenset
  - `TestTemplateManagerInit` (3): dir creation, properties, repr
  - `TestTemplateCreate` (8): basic, sequential IDs, persistence, all fields, empty name, empty workflow, whitespace, auto-detect
  - `TestTemplateRead` (8): get, not found, list all, filter entity_type, filter author, has_template, empty, corrupt skip
  - `TestTemplateUpdate` (8): name, description, workflow redetect, immutable raises, unknown raises, not found, bumps updated_at, multiple
  - `TestTemplateDelete` (3): delete, not found, preserves others
  - `TestFillTemplate` (4): fill, not found, unfilled, all satisfied
  - `TestComfyUIClientInit` (4): defaults, custom config, repr, not-entered raises
  - `TestComfyUIClientContextManager` (2): enter/exit, close idempotent
  - `TestComfyUIClientTestConnection` (2): success, connection refused
  - `TestComfyUIClientQueueWorkflow` (5): success, client_id, reject, missing prompt_id, connection error
  - `TestComfyUIClientGetHistory` (3): completed, not found, connection error
  - `TestComfyUIClientPollUntilComplete` (4): immediate, delayed, workflow error, timeout
  - `TestExtractOutputImages` (5): single, multiple, multiple nodes, no outputs, no images key
  - `TestComfyUIClientDownloadImage` (3): success, subfolder, error
  - `TestComfyUIClientUploadImage` (2): success, error
  - `TestExceptions` (6): hierarchy, connection fields, workflow fields, not found, validation list, validation string
  - `TestEdgeCases` (7): unicode, large workflow, persistence roundtrip, deeply nested fill, ID gap sequencing, config equality, job roundtrip

### Test Results
- **2,241 passed**, 12 skipped, 0 failures — zero regressions ✅
- New tests: 118 (up from 2,123)

### Technical Debt
- `ComfyUIClient` uses `import httpx` inside `__aenter__` to defer the dependency — this works but is unconventional. Could be moved to module-level if httpx is guaranteed present.
- `GenerationJob` is defined as a data class but no manager persists it yet — F-037f (Generation Pipeline) will need a `GenerationJobManager` or queue system.
- The `COMFYUI_IMAGES_DIR` setting is a placeholder for F-037b (Image Manager) — not used in this feature.
- No API endpoints yet — F-037d (Settings UI) will add the REST API for template management and connection testing.

### Advice for Next Agent
1. **F-037b (Image Manager & Storage System) is the natural next step** — it depends only on F-037a (now completed). It provides filesystem-backed image storage with metadata tracking.
2. **F-037c (Prompt Generation Engine) is also unblocked** — it depends only on F-037a. It's independent of F-037b so could be done in parallel.
3. The module is importable as:
   ```python
   from core.comfyui_client import (
       ComfyUIClient, ComfyUIConfig,
       WorkflowTemplateManager, WorkflowTemplate,
       GenerationJob,
       detect_placeholders, fill_placeholders,
   )
   ```
4. Usage pattern for the client:
   ```python
   config = ComfyUIConfig.create(host="127.0.0.1", port=8188)
   async with ComfyUIClient(config) as client:
       stats = await client.test_connection()
       prompt_id = await client.queue_workflow(filled_json)
       history = await client.poll_until_complete(prompt_id)
       images = ComfyUIClient.extract_output_images(history)
       img_bytes = await client.download_image(images[0]["filename"])
   ```
5. Usage pattern for template management:
   ```python
   mgr = WorkflowTemplateManager()
   tpl = mgr.create("My Workflow", workflow_json=exported_json)
   print(tpl.placeholders)  # ['height', 'negative', 'prompt', 'seed', 'width']
   filled = mgr.fill_template(tpl.id, {"prompt": "a cat", "seed": "42", ...})
   ```
6. **Placeholder tokens** use the `%token_name%` format (lowercase only). The 12 known tokens are in `KNOWN_PLACEHOLDERS`. Custom tokens are also detected — only the `%lowercase_with_underscores%` pattern is matched.
7. **Template IDs** are sequential: `TPL-0001`, `TPL-0002`, etc. Generation job IDs follow `GEN-XXXX`.
8. The `poll_until_complete()` method defaults to 1-second intervals with 300 attempts (5 minutes). These can be overridden via constructor params.
9. **All HTTP calls in tests are fully mocked** — no real ComfyUI server needed. Tests use `unittest.mock.MagicMock` and `AsyncMock`.
10. When adding API endpoints (F-037d), import the managers inside the endpoint function (Jericho pattern to avoid circular imports).

---

## Session: S-F037B-00000001
**Timestamp:** 2026-04-06 18:59:00
**Feature:** `F-037b` — Image Manager & Storage System
**Status:** completed

### Summary
Implemented the filesystem-backed image storage system — the second layer of Jericho's image generation pipeline. Provides structured storage organized by entity type and entity ID, with metadata tracking, primary image management, and sequential global IDs.

### Changes Made
- **New:** `core/image_manager.py` (~430 lines) — Three major components:
  1. **Exception hierarchy**: `ImageError` (base), `ImageNotFoundError` (with `image_id`), `ImageValidationError` (with `errors` list)
  2. **Data class**: `EntityImage` (frozen) — id, entity_type, entity_id, filename, original_filename, prompt, negative_prompt, is_primary, file_size, width, height, template_id, generation_job_id, created_at, metadata. Full `to_dict()`/`from_dict()`/`create()` factory with validation and auto-timestamp.
  3. **ImageManager class** — filesystem-backed CRUD organized as `{images_dir}/{entity_type}/{entity_id}/`:
     - `save_image()` — writes bytes to disk, generates sequential `img_XXXX.ext` filename, detects extension from filename or magic bytes (PNG/JPEG/WebP), creates metadata entry in `images.json`, auto-sets first image as primary
     - `get()` — global scan to find image by `IMG-XXXX` ID across all entities
     - `list_images()` — list images for a specific entity with `primary_only` filter
     - `get_primary_image()` — convenience method returning the primary image or None
     - `set_primary()` — designate one image as primary, clear flag from all others
     - `delete()` — removes file and metadata, auto-promotes next image if deleted was primary
     - `get_image_path()` — resolve filesystem path for serving
     - `count_images()` — count images for an entity
     - `delete_entity_images()` — bulk delete all images for an entity
     - Sequential `IMG-XXXX` global IDs via counter file (`.next_id`) with fallback to metadata scan

- **New:** `tests/test_image_manager.py` (~680 lines) — 82 tests across 15 classes:
  - `TestEntityImage` (12): fields, defaults, frozen, roundtrip, create factory, validation errors for empty id/entity_type/entity_id/filename, whitespace stripping, missing optionals, metadata
  - `TestImageManagerInit` (3): dir creation, existing dir, repr
  - `TestSaveImage` (13): basic, auto-primary, second not primary, explicit primary, sequential IDs, sequential filenames, persistence, file written on disk, all fields, empty entity_type/entity_id/data validation, whitespace entity_type validation
  - `TestGetImage` (3): get existing, not found, across entities
  - `TestListImages` (4): empty, all, primary_only, entity isolation
  - `TestGetPrimaryImage` (3): no images returns None, returns primary, after set_primary
  - `TestSetPrimary` (4): basic, clears others, not found, idempotent
  - `TestDeleteImage` (6): removes file, removes metadata, not found, primary promotes next, non-primary no promotion, preserves others
  - `TestGetImagePath` (2): correct path, not found
  - `TestCountImages` (2): empty, multiple
  - `TestDeleteEntityImages` (3): delete all, delete empty, preserves other entities
  - `TestExtensionDetection` (9): from filename (png/jpg/jpeg/webp), from magic bytes (png/jpeg/webp), unknown defaults to png, unsupported falls back to magic
  - `TestConstants` (4): valid entity types, supported extensions, both are frozenset
  - `TestExceptions` (4): hierarchy, not found fields, validation single/list
  - `TestEdgeCases` (10): unicode, large data, many images per entity, persistence roundtrip, corrupt metadata, multiple entity types, ID continuity after reload, full lifecycle, explicit non-primary first, delete with missing file

### Test Results
- **2,323 passed**, 12 skipped, 0 failures — zero regressions ✅
- New tests: 82 (up from 2,241)

### Technical Debt
- The `get()` method does a full scan of all entity directories to find an image by global ID. This is O(entities × images) and could be slow for large collections. A global index file (or in-memory cache) could be added if performance becomes an issue.
- No API endpoints yet — F-037d (Settings UI) and F-037e (Entity Image Galleries) will add the REST API for image upload/serve/delete.
- `VALID_ENTITY_TYPES` is defined as documentation/reference in the module but not currently enforced in `save_image()`. This allows arbitrary entity types, which adds flexibility but could lead to typos. Consider enforcing in a future pass.
- The `.next_id` counter file is a simple text file. If multiple processes write images simultaneously, there could be a race condition. Acceptable for single-user local usage.

### Advice for Next Agent
1. **F-037c (Prompt Generation Engine) is the natural next step** — it depends only on F-037a (completed). It's independent of F-037b.
2. **F-037d (ComfyUI Settings & Templates Web UI) is now unblocked** — depends on F-037a + F-037b (both completed). It will add the REST API endpoints for template and image management.
3. The module is importable as:
   ```python
   from core.image_manager import (
       ImageManager, EntityImage,
       ImageError, ImageNotFoundError, ImageValidationError,
       VALID_ENTITY_TYPES, SUPPORTED_EXTENSIONS,
   )
   ```
4. Usage pattern for saving images:
   ```python
   mgr = ImageManager()
   img = mgr.save_image(
       image_data=raw_bytes,
       entity_type="character",
       entity_id="CH-0001",
       original_filename="portrait.png",
       prompt="a noble knight",
       negative_prompt="blurry",
       width=512,
       height=768,
       template_id="TPL-0001",
   )
   print(img.id)             # "IMG-0001"
   print(img.is_primary)     # True (first image auto-primary)
   path = mgr.get_image_path(img.id)
   ```
5. **Extension detection** works in priority order: original filename → magic bytes → default PNG. Supports `.png`, `.jpg`, `.jpeg`, `.webp`.
6. **Primary image management**: first image is auto-primary unless `is_primary=False` is explicitly passed. Setting a new primary automatically clears all others. Deleting the primary auto-promotes the next image.
7. **Image IDs are global** (`IMG-XXXX`) and sequential across all entities. The counter is stored in `{images_dir}/.next_id` and survives restarts.
8. **File naming** within an entity directory is also sequential: `img_0001.png`, `img_0002.png`, etc. This is per-entity (not global).
9. When adding API endpoints, use `mgr.get_image_path(image_id)` to resolve the file for serving via FastAPI's `FileResponse`.
10. The `delete_entity_images()` method uses `shutil.rmtree()` — it's a destructive bulk operation that removes the entire entity image directory.

---

## Session — F-037c: Prompt Generation Engine

**Date:** 2026-04-07
**Feature:** F-037c — Prompt Generation Engine
**Status:** ✅ Complete
**Agent:** Antigravity (Gemini)
**Baseline Tests:** 2,323 passed, 12 skipped
**Final Tests:** 2,415 passed, 12 skipped (+92 new)

### What Was Built

The Prompt Generation Engine — a multi-mode LLM-driven prompt construction system for AI image generation. This is the core intelligence layer that translates entity data into high-quality image prompts via 5 distinct generation modes.

### Files Changed

- **Created:** `core/prompt_builder.py` — Main module (~650 lines)
- **Created:** `tests/test_prompt_builder.py` — Comprehensive test suite (92 tests)
- **Modified:** `config/settings.py` — Added prompt generation settings (provider, model, tokens, temperature)
- **Modified:** `features.json` — Marked F-037c as `done`

### Architecture & Key Decisions

1. **Five Generation Modes:**
   - `raw_user` — User provides exact prompt text, no LLM. Works without API client.
   - `system` — Generic "image prompt expert" system prompt, no personality injection. Uses a temporary CouncilMember with the expert prompt.
   - `character` — Uses a specific council member's personality and system prompt to generate the prompt.
   - `user_refined` — User writes a base prompt; a member enhances/refines it.
   - `council_vote` — Multiple members each generate a prompt; returns a list for operator to choose from.

2. **Data Classes (frozen dataclasses, Jericho pattern):**
   - `StylePreset` — Named style with positive_suffix/negative_prefix fragments
   - `PromptRequest` — Input with mode, entity context, member name, user prompt, style
   - `PromptResult` — Output with positive/negative prompts, metadata, raw LLM response

3. **Built-in Style Presets (8):** fantasy_art, anime, realistic, oil_painting, watercolor, pixel_art, concept_art, dark_fantasy. Each has positive_suffix and negative_prefix fragments.

4. **Entity Context Building:** `build_entity_context()` reads character, location, item, store, or council_member data from their respective managers and formats it as structured text for LLM injection.

5. **Response Parsing:** `parse_prompt_response()` extracts `POSITIVE:` / `NEGATIVE:` lines from LLM output. Falls back to using full text as positive prompt if format isn't followed.

6. **Style Application:** `apply_style_preset()` appends positive_suffix and prepends negative_prefix from the selected style preset.

7. **LLM Integration:** Uses the existing `APIClient.chat()` method with `ChatMessage` objects. For `system` mode, creates a temporary `CouncilMember` with the image-expert system prompt. For `character`/`user_refined`/`council_vote`, uses the real member from the registry.

### Settings Added (config/settings.py)

```python
PROMPT_GENERATION_PROVIDER_ENV = "JERICHO_PROMPT_GENERATION_PROVIDER"
PROMPT_GENERATION_MODEL_ENV = "JERICHO_PROMPT_GENERATION_MODEL"
DEFAULT_PROMPT_GENERATION_PROVIDER = "openrouter"
DEFAULT_PROMPT_GENERATION_MODEL = "mistralai/mistral-small-2603"
PROMPT_GENERATION_MAX_TOKENS = 512
PROMPT_GENERATION_TEMPERATURE = 0.8
```

### Usage Examples

```python
from core.prompt_builder import PromptBuilder, PromptRequest, StylePreset, get_style_preset

# Raw user mode (no API needed)
builder = PromptBuilder()
req = PromptRequest.create("raw_user", user_prompt="a majestic castle")
result = await builder.generate(req)

# Character mode with style preset
builder = PromptBuilder(api_client=client, registry=registry)
preset = get_style_preset("fantasy_art")
req = PromptRequest.create(
    "character",
    member_name="Spark",
    entity_type="character",
    entity_id="CH-0001",
    style_preset=preset,
)
result = await builder.generate(req)

# Council vote mode (returns list)
req = PromptRequest.create(
    "council_vote",
    participants=["Spark", "Sage", "Forge"],
    entity_type="location",
    entity_id="LOC-0001",
)
results = await builder.generate(req)  # list[PromptResult]
```

### Technical Debt

- None introduced. Clean implementation following all existing patterns.
- The `build_entity_context()` function uses `hasattr()` checks for location/item/store fields because those managers have slightly varying attribute names. This is intentional defensive coding.

### Advice for Next Agent

1. **F-037d (Settings & Templates Web UI) is next** — it needs REST API endpoints for ComfyUI settings and template management. The prompt builder will be exposed via the generation pipeline (F-037f), not directly via web API yet.
2. **The PromptBuilder accepts managers via constructor injection** — the web_api.py layer should instantiate it with all relevant managers.
3. **All LLM calls in prompt_builder are mocked in tests** — no real API calls. The mock pattern uses `AsyncMock` for `client.chat()`.
4. **Style presets are hardcoded** — a future enhancement could support user-defined presets stored on disk (like workflow templates), but the current built-in set covers the most common use cases.
5. **The `parse_prompt_response()` function is lenient** — it handles various casing and whitespace. If the LLM doesn't follow the `POSITIVE:` / `NEGATIVE:` format, the entire response becomes the positive prompt.
6. **Council vote mode is sequential** (not concurrent) — each participant's LLM call awaits before the next. This respects API rate limits. Could be parallelized later if needed.

---

## Session: F-037e — Entity Image Galleries (2026-04-07)

### What Was Done

Implemented the Entity Image Gallery feature (F-037e), adding visual image management to all four entity detail pages (character, location, item, store). The feature provides:

1. **Backend API** — 6 REST endpoints in `web_api.py` wrapping the existing `ImageManager` from F-037b:
   - `GET /api/images/file/{image_id}` — serve raw bytes for `<img>` src
   - `GET /api/images/info/{image_id}` — full metadata + prompt info
   - `POST /api/images/set-primary/{image_id}` — set primary flag
   - `DELETE /api/images/delete/{image_id}` — delete image + file
   - `GET /api/images/{entity_type}/{entity_id}` — list gallery
   - `POST /api/images/{entity_type}/{entity_id}` — upload (base64 JSON)

2. **Frontend Gallery Module** (~280 lines in `app.js`):
   - `renderImageGallery(entityType, entityId)` — reusable async function returning HTML
   - Thumbnail grid with primary badges (⭐), prompt info tooltips
   - Lightbox viewer with prev/next navigation + keyboard support (←/→/Esc)
   - Upload modal with drag-and-drop + file picker
   - Action handlers: set primary, delete, download
   - In-place `refreshGallery()` without full page reload

3. **Gallery CSS** (~435 lines in `style.css`):
   - Responsive grid, hover lifts, primary badges, action overlays
   - Lightbox with blur backdrop + image entrance animation
   - Upload modal with drag-over states
   - Responsive breakpoint at 768px

4. **Gallery injected into 4 detail pages**:
   - `renderCharacterDetail` — after Example Messages
   - `renderLocationDetail` — after Children
   - `renderItemDetail` — after page header
   - `renderStoreDetail` — after Purchase section

### Test Results

- **39 new tests** in `test_web_api_gallery.py` (7 test classes)
- **Full suite: 2,476 passed, 12 skipped, 0 failures** (63.8s)

### Key Technical Decision

**Route ordering matters in FastAPI.** Specific routes (`/api/images/file/{id}`, `/api/images/info/{id}`, etc.) must be registered BEFORE the parameterized catch-all route (`/api/images/{entity_type}/{entity_id}`). Without this, paths like `file` or `info` would be matched as entity types, returning 400 errors. This was the main bug during initial implementation and required restructuring the routes with disambiguated prefixes (`/api/images/set-primary/{id}` instead of `/api/images/{id}/set-primary`).

### Files Changed

| File | Change |
|------|--------|
| `core/web_api.py` | +165 lines — 6 image gallery API endpoints |
| `core/web_static/app.js` | +290 lines — gallery module + 4 detail page injections |
| `core/web_static/style.css` | +435 lines — gallery CSS |
| `tests/test_web_api_gallery.py` | NEW — 39 tests |
| `features.json` | F-037e status → `done` |

### Technical Debt

- None introduced. All endpoints follow established patterns.
- Upload uses base64 JSON (matching existing avatar upload pattern), not multipart form.

### Advice for Next Agent

1. **F-037f (Generation Pipeline) is next** — it connects the PromptBuilder (F-037c) to ComfyUI (F-037a) and saves results via ImageManager (F-037b). The gallery (this feature) will display those generated images.
2. **Route ordering in web_api.py is critical** — always register specific image routes BEFORE the `{entity_type}/{entity_id}` catch-all. New single-image routes should use the `/api/images/<action>/{image_id}` pattern.
3. **The gallery module uses module-level state** (`_galleryImages`, `_galleryEntityType`, `_galleryEntityId`) — this works because only one gallery is visible at a time. If multiple galleries are needed simultaneously, refactor to pass state through function parameters.
4. **The `refreshGallery()` function re-renders in-place** by replacing the `#entity-gallery` element's `outerHTML`. This avoids full page navigation.
5. **Test fixture pattern**: `test_web_api_gallery.py` monkeypatches both `config.settings.COMFYUI_IMAGES_DIR` and `core.image_manager.COMFYUI_IMAGES_DIR` — both are needed because the module-level import caches the value.

---

## Session: S-037f-00000001
**Timestamp:** 2026-04-08 03:11:00
**Feature:** `F-037f` — Generation Pipeline & Progress UI
**Status:** completed

### Summary
Verified and finalized the F-037f Generation Pipeline & Progress UI feature. All components were fully implemented across two prior sessions and this session confirmed everything is working correctly:

- **Backend — `core/generation_pipeline.py`** (792 lines):
  - `GenerationRequest` frozen dataclass with factory validation for all 5 prompt modes
  - `GenerationProgress` frozen dataclass for SSE-compatible progress updates
  - `GenerationPipeline` orchestrator with in-memory job queue (configurable max, default 10)
  - 7-stage async pipeline: `prompt_generating → template_filling → queued → running → downloading → saving → completed`
  - Exception hierarchy: `GenerationError`, `GenerationNotFoundError`, `GenerationValidationError`, `GenerationQueueFullError`
  - Council vote mode with multi-prompt selection
  - Completed job pruning (max 100 retained)
  - Cancel support with inter-stage checking

- **Web API — `core/web_api.py`** (endpoints at lines 5163–5417):
  - `POST /api/generate/{entity_type}/{entity_id}` — start a generation job
  - `GET /api/generate/stream/{job_id}` — SSE stream (events: progress/done/error)
  - `POST /api/generate/cancel/{job_id}` — cancel a running job
  - `GET /api/generate/jobs` — list all jobs (with `?active_only` filter)
  - `GET /api/generate/jobs/{job_id}` — job detail
  - `POST /api/generate/prompts` — preview prompts without queuing
  - Lazy singleton pipeline initialization with `_get_pipeline()`

- **Frontend — `core/web_static/app.js`** (lines 3133–3681):
  - `openGenerateModal()` — full form with template/style/mode selectors
  - 5 prompt mode fields: system (no extra), character (member select), raw_user (textarea), user_refined (member + textarea), council_vote (participant checkboxes + preview)
  - `previewCouncilPrompts()` — fetches prompt previews from `/api/generate/prompts`
  - `submitGeneration()` — POSTs to start endpoint, connects SSE
  - `connectGenerateSSE()` — EventSource with progress/done/error handlers
  - `updateGenerateProgress()` — live progress bar + stage labels + prompt display
  - `cancelGeneration()` / `retryGeneration()` — cancel and retry flows
  - `onGenerationComplete()` — auto-refreshes gallery, shows success toast
  - "🎨 Generate Image" button integrated into gallery header

- **Frontend — `core/web_static/style.css`** (lines 6394–6714):
  - Full modal styling with glassmorphism and gradient header
  - Animated progress bar with shimmer effect
  - Participant checkbox pills with `:has(input:checked)` styling
  - Council vote prompt selection cards
  - Responsive breakpoints for mobile

- **Tests** — 91 tests across 2 files:
  - `tests/test_generation_pipeline.py` — 70 tests covering all data classes, stages, modes, edge cases
  - `tests/test_web_api_generation.py` — 21 tests covering endpoint validation and error handling

### Baseline
- **Before:** 2,567 passed, 12 skipped
- **After:** 2,567 passed, 12 skipped (no regressions; generation tests already counted in baseline)

### Files Changed

| File | Change |
|------|--------|
| `core/generation_pipeline.py` | 792 lines — full pipeline module (prior session) |
| `core/web_api.py` | +255 lines — 7 generation API endpoints + singleton (prior session) |
| `core/web_static/app.js` | +550 lines — generation modal, SSE progress, all modes (prior session) |
| `core/web_static/style.css` | +320 lines — generation modal & progress CSS (prior session) |
| `tests/test_generation_pipeline.py` | NEW — 70 tests (prior session) |
| `tests/test_web_api_generation.py` | NEW — 21 tests (prior session) |
| `features.json` | F-037f status → `done` |

### Technical Debt

- None introduced. All endpoints follow established route patterns.
- The pipeline singleton (`_generation_pipeline`) is module-level within the `create_app()` closure — safe for single-process uvicorn but would need refactoring for multi-process deployment.

### Advice for Next Agent

1. **F-037g (Prompt Style Presets & Generation Queue Polish) is next** — batch generation for entity lists, queue dashboard with status cards, preset editor with preview.
2. **The SSE stream is a single-consumer design** — if the user opens multiple tabs, each tab gets its own EventSource. The pipeline stage transitions are not broadcast via WebSocket; each SSE stream runs its own `pipeline.run_job()`, so only one tab should trigger generation for a given job.
3. **Route ordering matters** — the catch-all `POST /api/generate/{entity_type}/{entity_id}` MUST remain after all specific `/api/generate/...` routes (cancel, stream, jobs, prompts) to avoid matching "cancel" as an entity_type.
4. **Gallery auto-refresh** — `onGenerationComplete()` calls `refreshGallery()` which re-renders the `#entity-gallery` element in-place. This works because the gallery module-level state (`_galleryEntityType`, `_galleryEntityId`) is still set from the page load.
5. **Pipeline is in-memory** — job state is not persisted to disk. If the server restarts, all job state is lost. This is acceptable for the current single-user deployment model.

---

## Session: S-037G-00000001
**Timestamp:** 2026-04-08 22:00:00
**Feature:** `F-037g` — Prompt Style Presets & Generation Queue Polish
**Status:** completed

### Summary
Finalized the ComfyUI image generation pipeline polish features — custom style preset management, batch generation, queue dashboard, and global toast notifications.

#### Component 1: Custom Style Preset Manager (Backend)
- `CustomStylePresetManager` class in `core/prompt_builder.py` — filesystem-backed CRUD for user-defined style presets stored as JSON in `data/comfyui/presets/`
- Sequential IDs (`PST-XXXX`), key normalization, duplicate detection
- Import/export support for preset sharing
- `get_style_preset()` and `list_style_presets()` updated to check custom presets first (allowing override of builtins)
- **Critical bug fix**: Added missing `from pathlib import Path` import that was blocking all 28 preset tests

#### Component 2: Batch Generation (Backend)
- `start_batch_generation()` method on `GenerationPipeline` — all-or-nothing queue validation for up to 10 requests
- `POST /api/generate/batch` endpoint in `web_api.py`
- Full custom presets CRUD API: GET/POST/PUT/DELETE `/api/settings/comfyui/presets/{id}`
- Import/export endpoints: GET `/api/settings/comfyui/presets/export`, POST `/api/settings/comfyui/presets/import`

#### Component 3: Frontend
- **Queue Dashboard** (`renderGenerationQueue()`) — sortable status cards with progress bars, cancel/retry actions, entity navigation, auto-polling (3s) for active jobs
- **Custom Preset Editor** — rendered inside Settings/ComfyUI tab via `renderPresetEditor()`. Create/edit/delete modals, live prompt preview, JSON import/export
- **Batch Generation Modal** (`openBatchGenerateModal()`) — entity checkbox selection (max 10), template/style/size config. Accessible via "🎨 Batch Generate" buttons on Characters, Locations, Items, and Stores list pages
- **Completion Toast Poller** (`startGenToastPoller()`) — global 5s interval polling that shows toast notifications when generation jobs complete or fail, regardless of which view the user is on
- **Sidebar nav item** for Generation Queue
- **CSS** for queue cards, preset cards, preview boxes (~200 lines)

#### Component 4: Tests
- `tests/test_style_preset_manager.py` — 28 tests covering CRUD, import/export, roundtrip, builtin merge, validation
- Batch generation and preset API tests in existing test suites

### Baseline
- **Before:** 2,595 passed, 12 skipped
- **After:** 2,595 passed, 12 skipped (no regressions)

### Files Changed

| File | Change |
|------|--------|
| `core/prompt_builder.py` | +1 line import fix (`from pathlib import Path`); `CustomStylePresetManager` class (prior session) |
| `core/generation_pipeline.py` | `start_batch_generation()` method (prior session) |
| `core/web_api.py` | +180 lines — 8 preset CRUD/import/export endpoints + batch endpoint (prior session) |
| `core/web_static/app.js` | +600 lines — queue dashboard, preset editor, batch modal, toast poller; +4 batch buttons on entity list pages |
| `core/web_static/style.css` | +200 lines — queue cards, preset cards, preview CSS (prior session) |
| `core/web_static/index.html` | +1 nav item for Generation Queue |
| `config/settings.py` | `COMFYUI_PRESETS_DIR` constant (prior session) |
| `tests/test_style_preset_manager.py` | NEW — 28 tests (prior session) |
| `features.json` | F-037g status → `completed` |

### Technical Debt

- `_atomic_write` is duplicated across ~10 modules. A shared `core/utils.py` should consolidate this.
- Temp test files (`test_out.txt`, `test_results.txt`) accumulate in the project root — should be gitignored.

### Advice for Next Agent

1. **F-039 (Per-Entity-Type Workflow Templates) is next** — advanced template management assigning different ComfyUI workflows per entity type.
2. **Preset override semantics** — custom presets with the same key as builtins take precedence. This is by design so users can customize built-in styles.
3. **Toast poller is global** — `startGenToastPoller()` runs on `DOMContentLoaded` and polls every 5s forever. This is lightweight (single GET) but should be gated behind a "has ComfyUI configured" check if the user doesn't use image generation.
4. **Queue polling stops automatically** — `startQueuePolling()` (3s interval) auto-stops when there are no active jobs or when navigating away from the queue view.
5. **Batch generation route ordering** — `POST /api/generate/batch` is registered BEFORE the catch-all `POST /api/generate/{entity_type}/{entity_id}` to prevent "batch" from being matched as an entity_type.

---

## Session — F-039: Per-Entity-Type Workflow Templates (2026-04-08)

### What Was Done

Implemented **F-039: Per-Entity-Type Workflow Templates** — a system for assigning default ComfyUI workflow templates to each entity type (character, location, item, store).

### Files Created

- `core/template_assignments.py` — TemplateAssignmentManager with JSON-backed storage, CRUD operations, smart fallback chain, and template validation
- `tests/test_template_assignments.py` — 50 unit tests for the manager
- `tests/test_web_api_template_assignments.py` — 16 API integration tests

### Files Modified

- `config/settings.py` — Added `COMFYUI_TEMPLATE_ASSIGNMENTS_FILE` and `COMFYUI_ASSIGNABLE_ENTITY_TYPES` constants
- `core/web_api.py` — 5 new endpoints: GET/POST/DELETE template-assignments, GET recommended-template, POST template test
- `core/web_static/app.js` — Template assignment panel in Settings → ComfyUI, smart template pre-selection in Generate modal with 📌 Default badge, assignment save function
- `core/web_static/style.css` — Template assignment card styles (grid, cards, status badges, active states)
- `features.json` — F-039 marked completed
- `progress_log.md` — Session entry added

### Architecture

```
TemplateAssignmentManager
├── Storage: data/comfyui/template_assignments.json
├── CRUD: get/set/clear/set_all assignments
├── Fallback chain: explicit assignment → entity_type match → first template
└── Validation: entity type checking, template existence verification

API Endpoints:
├── GET  /api/settings/comfyui/template-assignments
├── POST /api/settings/comfyui/template-assignments
├── DELETE /api/settings/comfyui/template-assignments/{entity_type}
├── GET  /api/settings/comfyui/recommended-template/{entity_type}
└── POST /api/settings/comfyui/template-assignments/test/{template_id}
```

### Design Decisions

1. **Any template can be assigned to any entity type** — no enforcement that the template's `entity_type` field must match. Users may want a general-purpose template for specific entities.
2. **Smart fallback chain** — three levels: explicit assignment → matching entity_type field → first available template. This ensures the Generate modal always pre-selects something useful.
3. **Stale assignment detection** — if an assigned template is deleted, the fallback chain gracefully skips it and moves to the next level.

### Test Results

- **66 new tests** (50 unit + 16 API integration)
- **Full suite: 2661 passed, 12 skipped, 0 failed** (up from 2595 baseline)

### Technical Debt

- The `monkeypatch` for API tests needs to patch both `config.settings` AND the already-imported module-level constants (`core.comfyui_client.COMFYUI_TEMPLATES_DIR`, `core.template_assignments.COMFYUI_TEMPLATE_ASSIGNMENTS_FILE`) due to Python's import-time binding. This is a common pattern but creates test fragility.

### Advice for Next Agent

1. **F-041 (Story Illustration System) is next** — LLM-narrated story segments with inline illustrations.
2. **Template assignments are independent per entity type** — clearing one does not affect others. The JSON file stores only 4 keys.
3. **Recommended template endpoint returns source** — `"assignment"`, `"entity_type_match"`, or `"fallback"`. The frontend uses this for display purposes only.

---

## Session: S-F040-20260409
**Timestamp:** 2026-04-09 00:57:00
**Feature:** `F-040` — Exploration Image Galleries
**Status:** completed

### Summary
Implemented a visual location exploration system with generated scene images, "Look Around" generation, and illustrated location navigation.

### Changes Made

**Backend:**
- **`config/settings.py`** — Added `EXPLORATION_DIR` and `EXPLORATION_SCENES_FILE` constants
- **`core/exploration.py`** [NEW] — Complete ExplorationManager with:
  - `ExplorationScene` frozen dataclass (scene_id, location_id, image_id, scene_type, description, metadata)
  - Scene types: `overview`, `feature`, `transition`
  - CRUD operations: `add_scene()`, `get_scene()`, `list_scenes()`, `delete_scene()`, `delete_scenes_for_location()`
- `get_navigation_targets()` static method — resolves parent, children, siblings via LocationManager
  - `build_look_around_description()` — builds contextual prompts from location data
  - JSON file persistence via `atomic_write`
- **`core/web_api.py`** — 7 new `/api/explore` endpoints:
  - `GET /api/explore` — List all active locations with scene counts and primary images
  - `GET /api/explore/{id}` — Full exploration data (location, scenes, nav targets, features)
  - `POST /api/explore/{id}/look-around` — Trigger scene generation via existing pipeline
  - `GET /api/explore/{id}/scenes` — List scenes for location
  - `POST /api/explore/{id}/scenes` — Add scene manually
  - `DELETE /api/explore/{id}/scenes/{scene_id}` — Delete scene
  - Helper: `_explore_primary_image()` for nav card thumbnails

**Frontend:**
- **`index.html`** — Added 🧭 Explore nav item in World section
- **`app.js`** — ~380 lines of new code:
  - `renderExplore()` — Location grid with primary images and scene count badges
  - `renderExploreLocation(id)` — Immersive detail view with hero image, gradient overlay, location info
  - "Look Around" button with generation progress polling and auto-scene-add on completion
  - Scene gallery strip with horizontal scroll, lightbox viewer, delete buttons
  - Navigation panel showing parent/children/siblings with thumbnail cards
  - Full keyboard support in lightbox (Escape, arrows)
- **`style.css`** — 470+ lines of exploration CSS:
  - Hero image with gradient overlay, scene strip, nav cards, progress bar
  - Responsive breakpoints, hover micro-animations, scroll snapping

### Design Decisions

1. **Scenes reference existing images** — Scenes are metadata linking to ImageManager images via `image_id`. No storage duplication.
2. **Navigation uses parent/child relationships** — The existing `parent_location_id` field defines the world graph. Siblings = locations sharing the same parent.
3. **Dedicated Explore view** — Separate from Location detail to provide an immersive, visual-first experience.
4. **"Look Around" uses system prompt mode** — Auto-builds context from location description, lore, features, and tags.

### Test Results

- **66 new tests** (56 unit + 10 API integration)
- **Full suite: 2727 passed, 12 skipped, 0 failed** (up from 2661 baseline)

### Advice for Next Agent

1. **F-041 (Story Illustration System) is next** — unblocked by F-037f and F-039.
2. **`grep_search` does not work on `app.js`** — use `view_file` with specific line ranges. The Explore view is ~lines 3694–4074.
3. **ExplorationManager is stateless** — scenes persist to `data/exploration/scenes.json`. Safe to instantiate in each endpoint.
4. **Look Around currently stores all scenes as "overview"** — future work could auto-classify based on features.

---

## Session: S-F041-20260409
**Timestamp:** 2026-04-09 10:25:00
**Feature:** `F-041` — Story Illustration System
**Status:** completed

### Summary
Implemented the complete Story Illustration System: LLM-narrated story segments with inline generated illustrations, hierarchical Story -> Chapter -> Scene management, and an immersive reader UI. Built across multiple sessions with backend, API, frontend, and CSS all verified working.

### Changes Made

**Backend:**
- **`config/settings.py`** — Added `STORIES_DIR`, `STORY_STATUSES`, `STORY_MAX_CHAPTERS` (50), `STORY_MAX_SCENES_PER_CHAPTER` (20)
- **`core/story.py`** [NEW] — 1000 lines. Complete `StoryManager` with:
  - `StoryScene`, `StoryChapter`, `StoryRecord` frozen dataclasses
  - Full CRUD: `create()`, `get()`, `list_stories()`, `update()`, `update_status()`, `delete()`
  - Chapter management: `add_chapter()`, `update_chapter()`, `delete_chapter()`
  - Scene management: `add_scene()`, `update_scene()`, `attach_illustration()`, `delete_scene()`
  - `build_scene_narration_prompt()` — rich context builder with preceding scenes, character/location data, mood directives
  - Status lifecycle: draft -> active -> completed -> archived with validated transitions
  - JSON file persistence via `atomic_write`
  - 5 custom exceptions: StoryNotFoundError, ChapterNotFoundError, SceneNotFoundError, StoryValidationError, StoryLifecycleError
- **`core/web_api.py`** — ~680 lines of 14 new `/api/stories` endpoints:
  - Full story CRUD (list, create, get, update, status, delete)
  - Chapter CRUD (add, update, delete)
  - Scene CRUD (add, update, delete)
  - `POST .../scenes/{sc_id}/narrate` — LLM narration generation
  - `POST .../scenes/{sc_id}/illustrate` — ComfyUI illustration generation via pipeline

**Frontend:**
- **`index.html`** — Added Stories nav item in World section
- **`app.js`** — ~530 lines of new code (lines 11024-11550):
  - `renderStories()` — Story list with status filter tabs, card grid with metadata chips
  - `renderStoryDetail(id)` — Editor view with chapter blocks, scene management, Narrate/Illustrate buttons
  - `renderStoryReader(id)` — Immersive book-like reader with inline illustrations
  - Create Story modal, Edit Story modal, Add Scene modal with mood picker
  - Chapter/Scene CRUD, narration/illustration triggers, lightbox viewer
- **`style.css`** — Story-specific CSS:
  - Story grid, chapter blocks, scene items, reader typography
  - Mood badges, entity chips, metadata chips, lightbox overlay

### Design Decisions

1. **Story -> Chapter -> Scene hierarchy** — Mirrors traditional book structure. Scenes are the atomic unit for narration and illustration.
2. **Per-scene LLM narration** — Each scene generates prose using rich context from story synopsis, chapter context, preceding scenes, character/location data, and mood directives.
3. **Per-scene illustration** — Uses the existing GenerationPipeline (F-037f) with auto-determined template from TemplateAssignments (F-039).
4. **Dual-mode UI** — Editor mode for content management; Reader mode for immersive book-like consumption.
5. **Entity reference tracking** — `entity_refs` on StoryRecord tracks all characters and locations referenced across scenes.

### Test Results

- **86 tests** (53 unit in test_story.py + 33 API in test_web_api_stories.py)
- **Full suite: 2813 passed, 12 skipped, 0 failed** — zero regressions

### Advice for Next Agent

1. **Story narration requires an LLM provider** — The `/narrate` endpoint calls an LLM via APIClient.
2. **Story illustration requires ComfyUI** — The `/illustrate` endpoint uses the GenerationPipeline.
3. **`grep_search` does not work on `app.js` or `style.css`** — use `view_file` with specific line ranges. Story code is at lines 11024-11550 in app.js.
4. **The story file format is one JSON file per story** — `data/stories/ST-XXXX.json` containing the full chapter/scene hierarchy.
5. **All entity IDs are auto-sequential** — ST-XXXX for stories, CHP-XXXX for chapters, SCE-XXXX for scenes.

---

## Session — F-042: Explore Participant System

**Date**: 2026-04-10
**Status**: ✅ Complete
**Feature ID**: F-042

### Summary

Added council member and character participant support to the Explore section. Users can select up to 10 participants (any combination of council members and characters) whose full identity context — persona, beliefs, memories, traits, laws, locations, items — is injected into the "Look Around" scene generation prompt.

### Changes

- **core/web_api.py** — Backend additions: GET /api/participants/available, _build_participant_context() helper, enhanced look-around endpoint with participants
- **core/web_static/app.js** — Collapsible participant selector panel with avatars, type badges, search, counter (N/10)
- **core/web_static/style.css** — Participant selector styling
- **tests/test_participants.py** — 18 new tests

### Test Results

- **18 new tests** in test_participants.py
- **Full suite: 2831 passed, 12 skipped, 0 failed**

### Advice for Next Agent

1. Story section participants (next task) — Apply the same _build_participant_context() helper to the Story narration flow.
2. Participant selector UI code in app.js at renderExploreLocation — look for F-042 markers.
3. _build_participant_context() is defined inside create_app() in web_api.py as a closure-scoped helper.
4. Council member IDs are lowercase names; character IDs use CH-XXXX format.
5. Participant context truncates system prompts to 500 chars to manage prompt size.

---

## Session: S-DEBT-20260410
**Timestamp:** 2026-04-10 11:55:00
**Feature:** Technical Debt Cleanup
**Status:** completed

### Summary
Performed project-wide technical debt cleanup and metadata hygiene pass. All 43 features are complete; the project is entering bug-fix/optimization phase ahead of beta release.

### Changes Made

1. **Committed pending F-042/F-043 work** — Story & Explore participant system changes were uncommitted. Staged and committed as `feat(participants): Story & Explore participant system [F-042, F-043]`.

2. **Normalized `features.json` statuses** — Three features (F-037c, F-037e, F-037f) used `"done"` instead of `"completed"`. All 43 features now consistently use `"completed"`.

3. **Added missing `title` fields** — Features F-001 through F-020 lacked a `title` field (unlike F-021+ which all had one). Added human-readable titles to all 20 early features. Key ordering also standardized to `id → title → description → status → dependencies`.

4. **Updated `.gitignore`** — Added `*.egg-info/`, `dist/`, `build/` patterns for Python build artifacts. The `jericho.egg-info/` directory was present in the repo root.

5. **Bumped version to 0.9.0** — `pyproject.toml` version updated from `0.1.0` to `0.9.0` to reflect project maturity (43 features, 2841 tests, full web dashboard).

### Technical Debt — Resolved Items
- ✅ `_atomic_write` duplication (noted since S-FEAT-00000005) — was already consolidated into `core/utils.py` in a prior session
- ✅ Inconsistent feature statuses (`done` vs `completed`) — normalized
- ✅ Missing `title` fields on early features — added
- ✅ Build artifact gitignore gaps — fixed
- ✅ Stale temp files (`test_out.txt`, etc.) — already cleaned up and gitignored

### Technical Debt — Remaining
- `web_api.py` is 274KB (~7000+ lines) and growing. Consider splitting into route modules (e.g., `routes/council.py`, `routes/stories.py`) for maintainability.
- `app.js` is ~165KB (~3500+ lines). Consider splitting into ES modules or a lightweight bundler setup.
- `style.css` is ~74KB (~3050+ lines). Could benefit from CSS custom property consolidation or splitting by section.
- The `data/` directory contains runtime user content that isn't gitignored. Consider whether seed data should be separated from user-generated content.

### Test Results
- **2841 passed, 12 skipped, 0 failed** — zero regressions (no functional changes)

### Advice for Next Agent
1. **All 43 features are complete.** The backlog is empty. Next work should be bug fixing, optimization, or new feature planning for beta.
2. **Version is now 0.9.0** — the user plans bug fixing and optimization before a 1.0 beta release.
3. **`features.json` is now fully consistent** — every entry has `id`, `title`, `description`, `status`, `dependencies` in that order. All statuses are `"completed"`.
4. **The biggest remaining debt is file size** — `web_api.py` (274KB), `app.js` (165KB), and `style.css` (74KB) are all single monolithic files. Splitting these would improve maintainability but is a significant refactoring effort.
5. **`grep_search` still does not work on `app.js` or `style.css`** — use `view_file` with the section map from `.agents/workflows/project-reference.md`.

---

## Session: S-BUGFIX-00000006
**Timestamp:** 2026-04-10 19:50:00
**Feature:** `BUGFIX` — ComfyUI Integration Fixes
**Status:** completed

### Summary
Fixed two bugs in the ComfyUI generation pipeline:

1. **"No template specified" error** — `TemplateAssignmentManager()` was instantiated without a `template_manager` parameter in both the explore "Look Around" handler and the story scene illustration handler. Without it, the fallback chain (find template by entity_type match → first template overall) was broken because `self._template_manager is None`. Only explicit user assignments (step 1) could work, but if no assignment was configured, the manager returned an empty string, triggering the error.

2. **Port 8188 test failures** — The default ComfyUI port was changed from 8188 to 8007 in a previous session (S-BUGFIX-00000004), but multiple test files still asserted the old default. Updated all default-port assertions across `test_comfyui_client.py` and `test_web_api_comfyui_settings.py`.

3. **Frontend fallback port** — The ComfyUI settings page had a hardcoded fallback of `port: 8188` in its error handler, which would show the wrong default if the API endpoint failed. Updated to `8007`.

### Files Changed
- `core/web_api.py` — Added `template_manager=WorkflowTemplateManager()` to both `TemplateAssignmentManager()` instantiations (lines ~6314 and ~7088)
- `core/web_static/app.js` — Updated frontend catch fallback port from 8188 to 8007
- `tests/test_comfyui_client.py` — Updated 5 default-port assertions from 8188 to 8007
- `tests/test_web_api_comfyui_settings.py` — Updated 1 default-port assertion from 8188 to 8007

### Root Cause Analysis
The `TemplateAssignmentManager` class has an optional `template_manager` parameter that enables its smart fallback chain. The settings API endpoints (GET/POST/DELETE assignments) correctly passed `WorkflowTemplateManager()`, but the generation endpoints that actually *use* the recommendation did not. This is a classic "works in settings, fails in production" integration gap.

### Test Results
- **2849 passed, 12 skipped, 0 failed** — all tests pass including the previously-failing default port assertions

### Advice for Next Agent
1. The ComfyUI server connection persistence was investigated — the `.env` file correctly stores `JERICHO_COMFYUI_HOST=127.0.0.1` and `JERICHO_COMFYUI_PORT=8007`. The `save_env_value` method writes to `.env` and `load_dotenv` reads at startup. If the user reports the issue again, check whether `load_dotenv(override=False)` is being preempted by system-level env vars.
2. When adding new generation endpoints that need template recommendations, always pass `template_manager=WorkflowTemplateManager()` to `TemplateAssignmentManager()`.

---

## Session: S-EVO-FRONTEND-00000001
**Timestamp:** 2026-04-10 21:56:00
**Feature:** Evolution System Expansion — Frontend UI (Conv 2)
**Status:** completed

### Summary
Implemented the full frontend UI for the Evolution expansion system (backend completed in Conv 1). Six sub-features delivered:

1. **Create Evolution Form (J)** — Modal with target type toggle (Character / Council Member), entity dropdown populated from `/api/characters` and `/api/council`, evolution name input, author field, and a dynamic change builder supporting add/remove change rows with change_type dropdown, field_name, old/new value textareas, and rationale input. Submits via `POST /api/evolutions`.

2. **Rollback UI (K)** — Rollback button on evolution detail view (for applied/decided/active overlay evolutions) with confirmation modal. Also added "↩ Rollback to Version…" button in timeline detail view with version picker dropdown. Both create new rollback evolutions via their respective API endpoints.

3. **Status Management UI (L)** — Overlay status filter tabs (All / Draft / Active / Archived) in the evolution list view, filtering via `overlay_status` query parameter. Overlay status transition buttons in detail view (Draft → Activate/Archive, Active → Archive, Archived → Draft/Re-activate) with warning confirmation when activating.

4. **Active Evolution Icon (M)** — ✨ LIVE badge on evolution list rows with `overlay_status === 'active'`. Evolution name display with sequence number badge and target type badge in detail view.

5. **Evolution Detail Enhancements (N)** — New fields displayed: name, sequence_number, target_type, target_id, overlay_status, rollback_of. Overlay lifecycle visualization (draft → active → archived with active step highlighted). Rollback indicator link when `rollback_of` is set. Active overlay banner at top of detail view.

6. **Auto-fill Integration (O)** — Updated the evolution handoff banner in proposal detail view to add "🧬 Auto-Create Evolution" button alongside the existing navigation button. Calls `createEvolutionFromProposal(proposalId)` which hits `POST /api/evolutions/from-proposal/{proposal_id}`.

### Files Changed
- `core/web_static/app.js` — Rewrote Evolution section (~800 lines): `renderEvolution()` with overlay tabs, `renderEvolutionDetail()` with full expansion, `updateEvoOverlayStatus()`, `confirmRollbackEvolution()`, `executeRollbackEvolution()`, `openRollbackToVersionModal()`, `executeRollbackToVersion()`, `openCreateEvolutionModal()`, `switchEvoTargetType()`, `addEvoChangeRow()`, `removeEvoChangeRow()`, `submitCreateEvolution()`, `createEvolutionFromProposal()`. Updated proposal handoff banner.
- `core/web_static/style.css` — Added ~490 lines: `.evo-overlay-tabs`, `.evo-overlay-badge`, `.evo-active-banner`, `.evo-name-display`, `.evo-seq-badge`, `.evo-target-badge`, `.evo-rollback-indicator`, `.evo-overlay-lifecycle`, `.evo-create-modal`, `.evo-target-toggle`, `.evo-change-builder`, `.evo-status-actions`, `.evo-confirm-modal`, `.evo-form-label`

### Gotchas
- **PowerShell encoding corruption** — Using `[System.IO.File]::WriteAllLines()` from PowerShell to remove lines corrupted emoji bytes (double-encoding: UTF-8 bytes treated as Latin-1, then re-encoded as UTF-8). Fixed with a Python script that detected and repaired 36 double-encoded emoji sequences. **Never use PowerShell `WriteAllLines` on files containing non-ASCII characters**.
- **Mixed line endings** — Parts of `app.js` use `\r\n` (from the replace_file_content tool) and parts use `\n` (from PowerShell). For byte-level operations, always read with `newline=''` and match the actual line endings.

### Test Results
- **2864 passed, 12 skipped, 0 failed** — identical to pre-change baseline

### Advice for Next Agent
1. The Evolution frontend is complete. All backend APIs (Conv 1) and frontend UI (Conv 2) are implemented for: create, rollback, overlay status management, timelines, and auto-fill from proposals.
2. The file `app.js` is now ~12,370 lines and `style.css` is ~9,010 lines. Both are monolithic and represent significant technical debt.
3. Browser verification was not possible (server not running). The UI should be manually tested before considering this feature shipped.
4. The `createEvolutionFromProposal()` function in the proposal handoff banner constructs the URL using `${data.id}` which requires the proposal to have the expected `id` field — this is standard for all proposal objects.

---

## Session: Chat Response Timer Feature
**Timestamp:** 2026-04-11
**Feature:** Ad-hoc — Chat Response Timer for World Chat
**Status:** completed

### Summary
Added per-participant response timing to the World Chat section, allowing human operators to gauge LLM response times across different models and providers.

**Backend changes** (`core/routes/chat.py`):
- Added `import time` for monotonic timing
- Both `/api/chat/{chat_id}/send-stream` and `/api/chat/{chat_id}/continue-stream` SSE endpoints now include `response_time_ms` in each `message` event
- Timer uses `time.monotonic()` for accurate, monotonically-increasing measurement
- Timer resets between participants so each agent/character gets their own individual timing
- Timing measures from when the request is dispatched to when the response is received (includes network + LLM inference time)

**Frontend changes** (`js/chat.js`):
- `appendAgentBubble()` now accepts optional `responseTimeMs` parameter
- When present, a styled badge (e.g. "3.2s") is displayed next to the message timestamp
- `formatResponseTime(ms)` utility: shows milliseconds for <1s, seconds with 1 decimal otherwise
- `startResponseTimer()` utility: creates a live counting timer element (updates at 100ms intervals) with a pulsing animation
- Both `sendChatMessage()` and `continueChat()` now show a live ⏱ timer while waiting for each participant's response, which is replaced by the agent's message bubble (with final time badge) when the response arrives

**CSS changes** (`css/chat.css`):
- `.chat-response-time` — inline badge with blue accent, monospace font, pill shape
- `.chat-response-timer` — live timer with dashed border, pulsing opacity animation
- Timer value in accent blue for visibility

### Technical Debt
- None introduced. Feature is purely additive.

### Test Results
- **2859 passed, 6 failed (pre-existing), 12 skipped** — zero regressions

### Advice for Next Agent
1. The response timer is only in the World Chat section as requested — not in proposals, sessions, or other discussion views.
2. The `response_time_ms` is server-side measured using `time.monotonic()` — it includes async I/O wait time for the LLM API call. The frontend live timer is client-side via `performance.now()` and will differ slightly due to network latency.
3. The timer resets between participants in multi-member chats, so each agent's time is individually measured.
4. If you need to add response time tracking to the non-streaming endpoints (`/api/chat/{chat_id}/send` and `/api/chat/{chat_id}/continue`), the same pattern can be applied there.

---

## Session: S-EVO-SYSPROMPT-00000001
**Timestamp:** 2026-04-12 00:00:00
**Agent ID:** Antigravity
**Feature:** Evolution System Prompt Auto-Fill (F-013 Enhancement)
**Status:** ✅ Complete

### What Was Done
Enhanced the evolution creation modal to support a streamlined workflow for updating the **system_prompt** of a character or council member. When the user selects `system_prompt_update` from the change type dropdown, the system now:

1. **Auto-fills the field name** to `system_prompt`
2. **Automatically loads the current system prompt** of the selected target (character or council member) into the "Old Value" textarea
3. **Expands the textareas** to 8+ rows for comfortable prompt editing
4. **Shows a "📋 Load Current System Prompt" button** for manual re-loading (e.g., after switching targets)

### Files Modified

#### `core/web_static/js/evolutions.js`
- Added `_evoCharactersCache` and `_evoCouncilCache` module-level variables to store fetched entity data for auto-fill access
- Added `onchange="onEvoChangeTypeSelect(this)"` to all change-type `<select>` elements (both initial row and dynamically added rows)
- Added `evo-change-row-autofill` div with load button to each change row (hidden by default)
- New function `onEvoChangeTypeSelect(selectEl)` — handles change type selection, auto-fills field name, toggles autofill UI, auto-loads prompt
- New function `loadCurrentSystemPrompt(btn)` — reads the current target's system prompt from the cached data and populates the Old Value textarea

#### `core/web_static/css/evolutions.css`
- Added `.evo-change-row-autofill` styles — gradient background, flex layout, smooth animation
- Added `.evo-load-prompt-btn` styles — pill-shaped button with cyan gradient accent

### Design Decisions
- **Cached data approach**: Entity data is fetched once when the modal opens and stored in module-level variables. This avoids redundant API calls when switching change types or clicking the load button.
- **Auto-load on select**: When `system_prompt_update` is selected, the prompt loads immediately without requiring a button click, reducing friction. The button remains available for manual re-loading if the user switches targets.
- **Textarea expansion**: Rows expand from 2 to 8+ rows when dealing with system prompts, which are typically multi-paragraph.

### Test Results
- **2859 passed, 6 failed (pre-existing), 12 skipped** — zero regressions

### Advice for Next Agent
1. The `_evoCharactersCache` and `_evoCouncilCache` are populated when `openCreateEvolutionModal` is called. If the user creates a new character while the modal is open, they would need to reopen the modal to see it.
2. The `personality_update` change type also auto-fills the field name but does NOT show the load button — personality data is structured differently.
3. The backend `_apply_change` method in `character_evolution.py` already handles `field_update` with `field_name="system_prompt"`, so no backend changes were needed.
4. For council member evolutions, the system prompt update creates an evolution record but does not directly modify the YAML file — it creates an overlay. Direct YAML modification would require the `apply_evolution` flow for council members, which is not yet implemented.

---

## Session: S-UI-COUNCIL-EVO-BADGE
**Timestamp:** 2026-04-12
**Feature:** Council Page — Evolution Badge & LM Studio Provider Bubble
**Status:** completed

### Summary
Enhanced the Council page UI with two improvements:
1. **Evolution trait badge**: Council members with an active evolution overlay now display a distinctive purple "✦ {name} Evolution" bubble on both the card grid and detail views.
2. **LM Studio provider badge**: Added `badge-lmstudio` CSS styling (amber color) so LM Studio members get a provider bubble matching the treatment that Mancer (cyan) and OpenRouter (indigo) already receive.

### Files Modified

#### `core/routes/council.py`
- **List endpoint** (`/api/council`): Queries active evolution overlays for `council_member` target types and attaches `active_evolution: {evolution_id, name}` to each council member's response data.
- **Detail endpoint** (`/api/council/{name}`): Same lookup for individual member detail views.
- Both use try/except fallback so the feature degrades gracefully if the evolution system is unavailable.

#### `core/web_static/css/badges.css`
- Added `.badge-lmstudio` — amber background/text matching the existing provider badge pattern.
- Added `.badge-evolution-trait` — distinctive purple gradient with border, glow, `✦` prefix character, and a subtle `evoTraitShimmer` animation for a premium feel.

#### `core/web_static/js/council.js`
- **Card grid** (`renderCouncil`): Renders the evolution trait badge below the member description if `active_evolution` is present.
- **Detail view** (`renderCouncilDetail`): Shows the evolution trait badge under the description field.

### Design Decisions
- **Backend enrichment over frontend fetch**: Rather than making a separate API call from the frontend, we enriched the existing council endpoints with evolution data. This avoids an extra network roundtrip and keeps the frontend simple.
- **Evolution badge uses a standalone class**: Instead of reusing the generic `badge()` helper, the evolution trait uses a dedicated `badge-evolution-trait` class with a gradient, border, and shimmer animation to make it visually distinct from status/provider badges.
- **Graceful degradation**: If the evolution system fails (missing data dir, etc.), the council endpoints still return all member data — just without the `active_evolution` field.

### Test Results
- **2859 passed, 6 failed (pre-existing), 12 skipped** — zero regressions

### Advice for Next Agent
1. The council member evolution target_id convention is `CM-{MemberName}` (e.g., `CM-Araushnee`). This is set in `create_council_evolution()` in `character_evolution.py`.
2. If no evolution overlay is active for a council member, the `active_evolution` field is simply absent from the API response — the frontend checks for its presence.
3. The evolution badge text is `"{name} Evolution"` where `name` comes from the evolution record (e.g., "Brave" → "Brave Evolution"). It does NOT include the word "Evolution" in the data; the frontend appends it.

---

## Session: S-STORY-CHAT-00000001
**Timestamp:** 2026-04-12 16:00:00
**Feature:** `F-044` — Story Chat (Interactive Discussion within Scenes)
**Status:** completed

### Summary
Added interactive conversational chat to the story system, mirroring the explore chat pattern. Council members and characters can discuss story scenes with a 5-round conversation limit.

### Changes

**Backend** (`core/routes/stories.py`):
- Added 6 new endpoints: `GET .../chat/active`, `POST .../chat`, `POST .../inject-narration`, `POST .../send-stream`, `POST .../continue-stream`, `POST .../narrate-round`
- Added 5 helper functions for chat instantiation, ID generation, and round tracking
- Chat metadata stores `story_chat: true`, `story_id`, `chapter_id`, `scene_id`, and `story_round`
- `narrate-round` generates LLM narration incorporating recent chat context, saves to scene, and injects into chat log
- All SSE streams emit `message`, `done`, `error` events with round tracking and auto-close at limit

**Frontend** (`core/web_static/js/stories.js`):
- Added ~490 lines: chat state management, SSE streaming, bubble rendering, narration injection
- 💬 Chat button in each scene's action bar
- Chat section renders inline below scenes with message container, input bar, and controls
- Controls: Send message, Continue Discussion, Narrate Next Round, End Chat
- Round badge with amber/rose styling and auto-close behavior
- Auto-creates chat and injects narration when Narrate is clicked with participants selected

**CSS** (`core/web_static/css/stories.css`):
- Added ~200 lines of chat styling: section card, round badge, system/narration bubbles, input bar, controls, responsive overrides

### Test Results
- **2826 passed, 12 skipped** — 1 pre-existing failure in test_registry.py (member count mismatch)
- Zero regressions from story chat changes

### Advice for Next Agent
1. Story chat IDs use the prefix `STC-XXXX` and files are stored as `H-STC-XXXX.json` in `CONVERSATIONS_DIR`.
2. Round tracking is in `chat.metadata.story_round`. The limit is `_STORY_CHAT_MAX_ROUNDS = 5` in `stories.py`.
3. The `narrate-round` endpoint reuses `StoryManager.build_scene_narration_prompt` and appends recent chat messages as context for the LLM.
4. Chat uses the existing `HumanChat` infrastructure from `human_chat.py` — no new data models were needed.
5. The frontend state uses `window._storyChatId` and `window._storyChatSceneId` to track the active chat.

---

## Session: S-COUNCIL-SESSION-TESTS-001
**Timestamp:** 2026-04-12
**Feature:** `F-045` — Council Session Unit Tests
**Status:** completed

### Summary
Added comprehensive unit tests for `core/council_session.py`, which previously had zero test coverage. The test file covers the `CouncilSessionRecord` dataclass and `CouncilSessionManager` across 61 tests in 10 test classes.

### Files Added

#### `tests/test_council_session.py` (NEW)
- **TestCouncilSessionRecord** (11 tests): fields, frozen, to_dict/from_dict roundtrip, create factory, validation errors (empty session_id/title/topic), whitespace stripping, defaults
- **TestCouncilSessionManagerInit** (3 tests): directory creation, existing dir, repr
- **TestCreateSession** (8 tests): basic creation, options, persistence, sequential IDs, validation errors, ID gap sequencing
- **TestGetSession** (3 tests): get existing, not found, contribution preservation through save/load
- **TestListSessions** (5 tests): list all, empty, filter by status, sorted order, corrupt file skipping
- **TestCloseSession** (6 tests): close with summary, auto-summary, already-closed error, not-found error, field preservation, persistence
- **TestSavePublic** (1 test): public save method for SSE handler callers
- **TestBuildProposalData** (7 tests): basic handoff, custom overrides, not-closed error, not-found error, summary/contributions/agenda inclusion
- **TestAutoSummary** (5 tests): auto-generated summary content (title, topic, participants, contributions, no-participants edge case)
- **TestExceptions** (4 tests): hierarchy, not-found fields, validation fields, state error fields
- **TestEdgeCases** (8 tests): Unicode, long agenda, many participants, persistence roundtrip, full lifecycle, repr counts, nested metadata, contribution limit in handoff

### Test Results
- **2963 passed, 12 skipped** — zero regressions (+61 new tests)

### Advice for Next Agent
1. `core/council_session.py` is the **manager** for open-ended council deliberation sessions (`CS-XXXX`). It is distinct from `core/session.py` which is the **orchestrator** for structured sessions with phase transitions (briefing → active → summary → closed).
2. The `test_session.py` file tests the orchestrator; `test_council_session.py` tests the manager. Do not confuse them.
3. The auto-generated summary is produced by `CouncilSessionManager._generate_summary()` and has a predictable format: title, topic, contribution count, rounds, participants, active speakers.
4. `build_proposal_data()` limits contribution inclusion to the **last 20** and truncates each to **300 characters** — the `test_contribution_limit_in_handoff` test verifies this boundary.
5. The `sw` CLI tool is NOT available on this system's PATH. Use direct Python commands and file reads instead.

---

## Session — F-046: Explore & Story Route Test Coverage (2026-04-12)

### Objective
Increase endpoint test coverage for the two largest route files with the thinnest test coverage:
- `core/routes/explore.py` (912 lines, was 10 tests → now 43 tests)
- `core/routes/stories.py` (1420 lines, was 29 tests → now 73 tests)

### Changes

#### tests/test_web_api_exploration.py — Expanded from 10 → 43 tests

| Test Class | Tests | Coverage |
|---|---|---|
| TestExploreListEndpoint | 4 | List endpoint fields, detail keys, scene count |
| TestExploreDetailEndpoint | 6 | Detail data, navigation, coordinates, lore, not-found |
| TestSceneEndpoints | 11 | Add/list/delete scenes, wrong-location guard, filter by type, image_url enrichment, empty image_id, metadata |
| TestLookAroundValidation | 4 | Participant count limits, not-list validation, location not found |
| TestExploreChatEndpoints | 7 | Active chat null, create validation, location not found, inject-scene/send-stream content validation |
| TestParticipantContextBuilder | 6 | Empty input, council/character sections, world context, unknown member, character not found |
| TestExploreChatIdGeneration | 2 | First ID, sequential ID |

#### tests/test_web_api_stories.py — Expanded from 29 → 73 tests

| Test Class | Tests | Coverage |
|---|---|---|
| TestStoryCRUD | 18 | Create/list/get/update/delete, status transitions, not-found errors, empty list, optional fields |
| TestChapterCRUD | 8 | Add/update/delete, not-found (chapter, story), multiple chapters |
| TestSceneCRUD | 15 | Add/update/delete, image_url enrichment, not-found for story/chapter/scene, multiple scenes |
| TestStoryParticipants | 16 | Narrate with/without participants, count limits, type validation, saves to scene, model info |
| TestStoryChatHelpers | 8 | Round tracking, limit detection (below/equal/above/default/null metadata) |
| TestStoryChatEndpoints | 6 | Active chat null, create validation, inject-narration/send-stream content validation |
| TestNarrateRoundEndpoint | 2 | Chat not found, wrong story |

### Test Results
- **3040 passed, 12 skipped** — zero regressions (+77 new tests)

### Advice for Next Agent
1. Explore/stories test fixtures use `patch("core.story.StoryManager", ...)` at the constructor level. This works because `conftest.py` `invalidate_all()` clears singletons between tests.
2. `CONVERSATIONS_DIR` is imported lazily from `config.settings`. To mock it, patch `config.settings.CONVERSATIONS_DIR` — NOT the route module attribute.
3. Valid scene types for ExplorationManager are `overview`, `feature`, `transition` — NOT `detail`.
4. The `sw` CLI tool is NOT available. Use direct Python commands instead.

---

## Session — F-047: Utils Edge-Case Tests (2026-04-12)

### Objective
Add dedicated unit tests for `core/utils.py` — cover `atomic_write` and `atomic_append` edge cases including concurrent writes, permission errors, empty content, and Unicode handling.

### Changes

#### tests/test_utils.py (NEW) — 32 tests across 11 test classes

| Test Class | Tests | Coverage |
|---|---|---|
| TestAtomicWriteBasic | 6 | Creates file, overwrite, nested dirs, no temp leftovers, empty content, multiline |
| TestAtomicWriteUnicode | 4 | CJK/Arabic, emoji, mixed scripts, null/control chars |
| TestAtomicWriteLargeContent | 2 | 1 MiB single file, 10K lines |
| TestAtomicWriteErrors | 3 | Cleanup on write failure, cleanup on replace failure, preserves original on failure |
| TestAtomicWriteConcurrent | 2 | 20-thread concurrent writes (no corruption), no temp file leftovers |
| TestAtomicAppendBasic | 4 | Creates file, appends to existing, nested dirs, multiple appends |
| TestAtomicAppendNewlines | 3 | Auto-adds newline, preserves existing newline, empty string append |
| TestAtomicAppendUnicode | 2 | Unicode lines, emoji |
| TestAtomicAppendConcurrent | 1 | 50-thread serialized appends (no data loss) |
| TestAtomicAppendLarge | 2 | 512 KiB single line, 1000 small appends |
| TestWriteAppendInteraction | 3 | Write-then-append, append-then-write replaces, empty-write-then-append |

### Windows-Specific Notes
- `\r` is excluded from control character tests — Python text-mode on Windows translates `\r` → `\n`
- Concurrent `os.replace` tests tolerate `PermissionError` (Windows file-locking under contention)
- Concurrent append test uses a threading lock to test logic without OS-level interleaving noise

### Test Results
- **3072 passed, 12 skipped** — zero regressions (+32 new tests)

### Advice for Next Agent
1. `core/utils.py` is only 39 lines — `atomic_write` and `atomic_append`. All other modules import from here (DRY refactor completed earlier).
2. The concurrent write tests deliberately tolerate `PermissionError` on Windows — this is a known `os.replace` limitation, not a utils bug. On Linux, those errors will not occur.
3. The `test_cleanup_on_write_failure` test uses a custom `exploding_fdopen` wrapper because `os.fdopen` can't be simply side-effected — `mkstemp` creates the fd before fdopen wraps it.
4. The `sw` CLI tool is NOT available. Use direct Python commands instead.
5. **All features F-001 through F-047 are now completed.** The backlog has no remaining `pending` features — new features need to be added to `features.json` before the next session.

---

## Session — F-048: README Documentation Update (2026-04-12)

### Summary
Comprehensive README update to reflect the current state of the project after 47 features of development. The README was significantly out of date, still referencing the monolithic `web_api.py` (7,000+ lines) architecture and monolithic `app.js`/`style.css` frontend files.

### Changes

#### README.md — Major Rewrite

| Section | Update |
|---|---|
| Overview | Added LM Studio as third supported provider alongside OpenRouter and Mancer |
| Features | Changed from 8 to 9 domains; added Manager Cache, Chat Response Timers, Explore Participants, Explore Chat, Story Participants, Story Chat, Evolution Traits Display, LM Studio Provider Badge |
| Web Dashboard | Updated capabilities list with participant selection, interactive scene chat, response time tracking |
| Project Structure | Completely rewritten: `web_api.py` now shown as thin compositor (~145 lines), added `routes/` directory with 20 route modules, added `manager_cache.py`, replaced monolithic `app.js`.`style.css` with modular `js/` (26 modules, ~13,500 lines) and `css/` (33 modules, ~9,400 lines) |
| Tests | Updated from 2,813+ to 3,072 tests, 47 to 52 test suites, ~70s to ~90s runtime |
| Appearance | Updated Frutiger Aero description to include Y2K |

#### features.json — Added F-048

### Advice for Next Agent
1. The `features.json` backlog now has no remaining `pending` features again — F-048 was added and immediately completed.
2. The README `Features` count still says 47 — this is correct because F-048 is a documentation task, not a system feature. Update the count if you add actual system features.
3. The `sw` CLI tool is NOT available. Use direct Python commands instead.
4. All test counts and line counts in the README are accurate as of this session.


---

## Session — F-049: Item Image Prompt Context Refinement (2026-04-12)

### Objective
Refine how item entity context is built for LLM-driven image generation prompts. Prioritize item features in the order: Tags -> Name -> Description -> Lore. Include rich detail (rarity, tier, individual property descriptions) for ComfyUI generation.

### Changes

#### core/prompt_builder.py — uild_entity_context() item block rewritten
- **Before**: Minimal context — just name + description, dead item_type reference (items never had this attribute), properties shown as count only
- **After**: Full priority-ordered context:
  1. **Tags** (first line — strongest visual/categorical signal)
  2. **Entity name**
  3. **Description**
  4. **Lore** (if present)
  5. **Rarity** (if present)
  6. **Tier** (if present)
  7. **Properties** (each with name, type, and description)
- Removed dead item_type check that would never match actual Item objects

#### core/routes/generation.py — _get_pipeline() fixed
- **Bug fix**: Added item_manager=get_item_manager() and store_manager=get_store_manager() to the PromptBuilder initialization inside the pipeline singleton
- Previously, item and store entity context was silently returning empty strings when generating through the pipeline route (only the /api/generate/prompts preview endpoint had them wired)

#### tests/test_prompt_builder.py — 	est_item_context overhauled
- Replaced MagicMock item with real Item and ItemProperty dataclass instances
- Now validates: tag priority ordering (first line), name, description, lore, rarity, tier, and individual property detail strings
- Fixed item ID format from ITM-0001 to ITEM-0001 (matches actual ID scheme)

### Test Results
- **3072 passed, 12 skipped** — zero regressions

### Advice for Next Agent
1. The item context block now outputs tags as the **first line** — this is intentional for prompt priority. If you need to change the order, update both uild_entity_context() and 	est_item_context.
2. The _get_pipeline() singleton now wires all 4 entity managers (character, location, item, store). If a new entity type is added, remember to wire its manager here too.
3. The sw CLI tool is NOT available. Use direct Python commands instead.
4. Store context still uses the old minimal format (name + description + type). If store image generation needs similar enrichment, follow the same pattern used here for items.


---

## Session — F-050: Analytics Expansion — 20 New Metrics (2026-04-12)

### Summary
Expanded the Analytics dashboard from 4 governance-only cards to 9 cards covering all major Jericho subsystems. Added 20 new metrics plus 1 enhancement (unanimous votes) to the existing voting card.

### Changes

#### core/analytics.py — 5 new dataclasses + computation methods

| Dataclass | Fields |
|---|---|
| WorldBuildingStats | total_characters, characters_by_status, total_locations, locations_by_status, total_items, items_by_status, total_stores, active_stores, total_inventory_slots |
| EconomyStats | total_accounts, total_circulation_gold, government_balance, total_tax_events |
| ContentStats | total_stories, stories_by_status, total_chapters, total_scenes, illustrated_scenes |
| ImageStats | total_images, images_by_entity_type, total_storage_bytes, total_templates |
| MemoryKnowledgeStats | total_beliefs, total_session_events, total_shared_decisions, total_laws, laws_by_status |

- VotingStats extended with unanimous_count field
- AnalyticsReport extended with 5 new optional fields
- SessionAnalytics.__init__ now accepts 11 additional keyword-only manager arguments
- 5 new computation methods: world_building_stats(), economy_stats(), content_stats(), image_stats(), memory_knowledge_stats()
- All new methods follow the existing pattern: return defaults if manager is None, silently handle exceptions

#### core/routes/settings.py — /api/analytics endpoint expanded
- Replaced direct ProposalManager/VotingEngine instantiation with manager_cache accessors
- Added optional imports for ImageManager, WorkflowTemplateManager, TaxationManager with graceful fallback
- Passes all 13 managers to SessionAnalytics

#### core/web_static/js/analytics.js — 9-card rendering
- Page now organized into two labeled sections: Governance (4 cards) and System (5 cards)
- Added formatBytes() helper for human-readable storage display
- Added statusChips() helper for rendering status breakdowns

#### core/web_static/css/analytics.css — Layout expansion
- Grid minimum column width: 300px to 340px
- Added .analytics-section-label styling

#### tests/test_analytics.py — 25 new tests

### Test Results
- **3097 passed, 12 skipped** — zero regressions (+25 new tests)

### Advice for Next Agent
1. The SessionAnalytics.__init__ now accepts 15 keyword-only arguments (4 original + 11 new). All are optional and default to None.
2. The economy stats use OBELISK_CONVERSION_RATE from config.settings to convert total bronze to gold display.
3. The image stats method walks the ImageManager.directory structure. If the directory structure changes, update image_stats().
4. The memory/knowledge stats method scans all members from registry.list_names(). If the project has many members with large memory files, this could be slow.
5. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session: S-FEAT-00000051
**Timestamp:** 2026-04-12 16:55:00
**Feature:** `F-051` — Location Image Prompt Context Refinement
**Status:** completed

### Summary
Refined the location entity context in `build_entity_context()` to produce richer, place-focused prompts for image generation — mirroring the approach already established for items in F-049.

**Before:** Location context only included name, description, location_type, and feature names (no descriptions).

**After:** Location context now uses a clear priority hierarchy:
1. **Name** — the primary identifier
2. **Description** — visual and atmospheric details
3. **Lore** — historical/narrative atmosphere *(new)*
4. **Tags** — categorical visual signals *(new)*
5. **Type** — location classification
6. **Coordinates** — spatial context *(new)*
7. **Features** — now includes full descriptions and feature types *(enhanced)*

#### core/prompt_builder.py — `build_entity_context()` location branch
- Reordered fields: name → description → lore → tags → type → coordinates → features
- Added lore, tags, and coordinates extraction with `hasattr`/truthy guards
- Features now render with full descriptions and type annotations (e.g., `Crystal Lake (landmark): A shimmering lake`)
- Handles both dict-based features and LocationFeature dataclass instances

#### tests/test_prompt_builder.py — TestBuildEntityContext
- Replaced `test_location_context` with comprehensive test verifying priority order and all fields
- Added `test_location_context_minimal` — validates graceful handling when optional fields are empty

### Test Results
- **3098 passed, 12 skipped** — zero regressions (+2 net new tests, 1 replaced)

### Technical Debt
- None introduced. This is a pure refinement of the existing entity context builder.

### Advice for Next Agent
1. The location context now mirrors the item context pattern (F-049). If store context needs similar refinement, follow the same approach.
2. Features handle both `dict` and dataclass forms because the test mock uses dicts while the actual LocationManager produces LocationFeature dataclasses.
3. All entity context builders (character, location, item, store, council_member) are in `build_entity_context()` in `core/prompt_builder.py` lines 648–753.
4. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session: S-F052-ABSENT-001
**Timestamp:** 2026-04-12 21:45:00
**Feature:** `F-052` — Chat Absent Response Handling
**Status:** completed

### Summary
Implemented graceful error handling for individual participant API failures in the chat system. When a council member or character's LLM API call fails (timeout, network error, provider issue, etc.), the system now injects an `[absent]` message and continues to the next participant instead of crashing the entire SSE stream.

### Files Modified

#### core/human_chat.py — All 4 response methods
- `get_agent_response()` (non-streaming, lines ~538–585): Wrapped API call in try/except, records `[absent]` message on failure
- `get_agent_response_streaming()` (streaming, lines ~975–1020): Same pattern, plus builds a stub `ChatResponse` for SSE yield
- `continue_conversation()` (non-streaming, lines ~860–910): Same try/except pattern for AI-to-AI rounds
- `continue_conversation_streaming()` (streaming, lines ~1090–1140): Same pattern with stub `ChatResponse`
- On error, the absent message is: `[absent] Was unavailable to respond at this time. [/absent]`
- Absent messages get `metadata={"absent": True}` for downstream identification
- Memory recording is skipped for absent responses (nothing meaningful to record)

#### core/web_static/js/chat.js — renderMarkdown()
- Added regex to convert `[absent]...[/absent]` tags into styled HTML: `.absent-wrapper` with `.absent-tag` and `.absent-text` spans
- Runs before bold/italic parsing to ensure tag brackets aren't mangled

#### core/web_static/css/chat.css — Absent styling
- `.absent-wrapper`: dashed amber border, subtle warm background, italic text
- `.absent-tag`: JetBrains Mono monospace, amber color, small caps feel
- `.absent-text`: muted color, standard message size

### Design Decisions
1. **Per-participant resilience**: Each participant's API call is independently wrapped, so one failure doesn't affect others in the same round.
2. **Stub ChatResponse**: Streaming methods need to yield a `ChatResponse` object even on error, so we construct a minimal stub with empty model/provider strings.
3. **No memory recording on absence**: When a participant is absent, we don't create a memory entry since there's no meaningful content to record.
4. **Frontend rendering**: The `[absent]` tag is parsed in `renderMarkdown()` and rendered as a visually distinct amber-themed block, consistent with the paused/warning visual language used elsewhere.

### Test Results
- **3098 passed, 12 skipped** — zero regressions

### Advice for Next Agent
1. The `[absent]` tag is rendered by `renderMarkdown()` which is shared across all chat views (world chat, explore chat, story chat). All views automatically get absent styling.
2. The explore.py and stories.py route files use the same `hc.get_agent_response_streaming()` and `hc.continue_conversation_streaming()` methods, so they automatically benefit from this error handling without any route-level changes.
3. If you need to distinguish absent messages from real ones in business logic, check `msg.metadata.get("absent")`.
4. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session: S-F053-INJECT-001
**Timestamp:** 2026-04-14 23:19:00
**Feature:** `F-053` — LLM Injection System
**Status:** completed

### Summary
Added user-authored `llm_injection` text fields to **Items**, **Locations**, and **Stores**. These fields inject custom text into the LLM context alongside existing layers (laws, memories, character/council prompts). Non-consumable items have static (always-on) injections, while consumable items have 24-hour TTL injections that expire based on `updated_at`.

### Files Modified

#### config/settings.py
- Added `CONSUMABLE_INJECTION_TTL_HOURS = 24` constant

#### core/items.py — Item dataclass + ItemManager
- Added `llm_injection: str = ""` to `Item` frozen dataclass
- Wired through `to_dict()`, `from_dict()`, `Item.create()`, and `ItemManager.create()`
- Added to mutable fields in `ItemManager.update()` (explicit comment)
- Added `is_injection_active(item: Item) -> bool` helper function:
  - Empty injection → `False`
  - Non-consumable tier → always `True` (static)
  - Consumable tier → checks `updated_at` against 24h TTL window

#### core/locations.py — Location dataclass + LocationManager
- Added `llm_injection: str = ""` to `Location` frozen dataclass
- Wired through `to_dict()` (via asdict), `from_dict()`, `Location.create()`, `LocationManager.create()`
- Added to `_MUTABLE_FIELDS` set
- **Carefully** updated all 4 manual Location reconstruction sites:
  - `update_status()` — preserves llm_injection
  - `add_feature()` — preserves llm_injection
  - `remove_feature()` — preserves llm_injection
  - `update()` — supports llm_injection edits via fields.get()

#### core/stores.py — Store dataclass + StoreManager
- Added `llm_injection: str = ""` to `Store` frozen dataclass
- Wired through `to_dict()` (via asdict), `from_dict()`, `Store.create()`, `StoreManager.create()`
- Added to `_MUTABLE_FIELDS` set
- Store uses `Store.from_dict({**store.to_dict(), ...})` pattern so mutations auto-carry the field

#### core/routes/explore.py — `_build_participant_context()`
- Location entries now append `💉 *{loc.llm_injection}*` when non-empty
- Item entries now check `is_injection_active(item)` before appending injection text
- **New** `### Known Stores` section added with store descriptions + injection text
- Imported `get_store_manager` from manager_cache

#### core/routes/items.py — API endpoints
- `POST /api/items` — accepts `llm_injection` in body
- `GET /api/items` — adds `injection_active` boolean to response
- `GET /api/items/{id}` — adds `injection_active` boolean to response
- `PUT /api/items/{id}` — already works via `**body` passthrough

#### core/routes/locations.py — API endpoints
- `POST /api/locations` — accepts `llm_injection` in body
- `PUT /api/locations/{id}` — already works via `**body` passthrough

#### core/routes/stores.py — API endpoints
- `POST /api/stores` — accepts `llm_injection` in body
- `PUT /api/stores/{id}` — already works via `**body` passthrough

#### core/web_static/js/items.js — Frontend
- Create form: added LLM Injection textarea with consumable TTL hint
- List cards: 💉 Active/Expired badge when injection present
- Detail/edit: injection textarea with active/expired indicator
- Create and save functions pass `llm_injection` to API

#### core/web_static/js/locations.js — Frontend
- Create form: added LLM Injection textarea
- List cards: 💉 badge when injection present
- Detail/edit: injection textarea with active indicator
- Create and save functions pass `llm_injection` to API

#### core/web_static/js/stores.js — Frontend
- Create form: added LLM Injection textarea
- List cards: 💉 badge when injection present
- Detail/edit: injection textarea with active indicator
- Create and submit functions pass `llm_injection` to API

#### tests/test_llm_injection.py — 27 new tests
- `TestItemInjection` (5 tests): create, update, roundtrip, backward compat
- `TestIsInjectionActive` (8 tests): permanent/degradable always active, consumable within/past 24h, boundary, empty, no updated_at, default tier
- `TestLocationInjection` (7 tests): create, update, roundtrip, backward compat, status/add/remove feature preservation
- `TestStoreInjection` (5 tests): create, update, roundtrip, backward compat, status preservation

### Context Stacking Order
```
1. Council member persona + beliefs + memories
2. Character description + traits + backstory
3. Active Laws
4. Known Locations + location LLM injections (NEW)
5. Known Items + item LLM injections with TTL (NEW)
6. Known Stores + store LLM injections (NEW)
```

### Test Results
- **3125 passed, 12 skipped** — +27 new tests, zero regressions

### Backlog Items
- **F-054**: Injection text length limits — deferred to next session for deep dive discussion

### Advice for Next Agent
1. The `is_injection_active()` function is in `core/items.py`. Import it anywhere you need to check injection status: `from core.items import is_injection_active`.
2. Locations and stores have **static** injections (always active while entity is active). Only items have the consumable TTL logic.
3. The `_build_participant_context()` function in `core/routes/explore.py` is the central injection point used by Explore, Stories, and Chat views. All three automatically get the new injection text.
4. Characters and council members do NOT have `llm_injection` fields — they use evolution system `system_prompt` instead.
5. F-054 (injection text length limits) is in features.json as "planned" — the user wants a deep-dive discussion before deciding on approach.
6. All injection text is truncated to 300 chars in the context builder as a safety measure, but this is NOT a formal limit — F-054 will address that properly.
7. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session — 2026-04-14 — F-054: Injection Text Length Limits

**Feature**: F-054 — Injection Text Length Limits
**Status**: ✅ Completed
**Tests**: 3151 passed (+26 new), 12 skipped, 0 failures

### What was built
Configurable per-entity character limits for `llm_injection` fields to prevent context window domination while keeping the system practical.

### Implementation details
- **Config**: Added `ITEM_INJECTION_MAX_LENGTH=500`, `LOCATION_INJECTION_MAX_LENGTH=800`, `STORE_INJECTION_MAX_LENGTH=500` to `config/settings.py`
- **Backend validation**: `ItemManager`, `LocationManager`, `StoreManager` all validate injection length on `create()` and `update()`, raising clear validation errors with the actual vs. max length
- **Context builder**: Replaced hardcoded `[:300]` truncation in `explore.py` with the per-entity configurable limits — single source of truth
- **API metadata**: All list/detail routes for items, locations, and stores now include `injection_max_length` in responses
- **Frontend**: All injection textareas have `maxlength` attribute + live character counters (`X / 500`) with color feedback (amber at 90%, red at limit)
- **Utility**: Added `updateInjectionCounter()` function to `core.js` for reuse across entity types

### Files modified
- `config/settings.py` — 3 new constants
- `core/items.py` — import + validation in create/update
- `core/locations.py` — import + validation in create/update
- `core/stores.py` — import + validation in create/update
- `core/routes/explore.py` — replaced [:300] with configurable limits
- `core/routes/items.py` — injection_max_length in responses
- `core/routes/locations.py` — injection_max_length in responses
- `core/routes/stores.py` — injection_max_length in responses
- `core/web_static/js/core.js` — updateInjectionCounter utility
- `core/web_static/js/items.js` — maxlength + char counter on create/edit
- `core/web_static/js/locations.js` — maxlength + char counter on create/edit
- `core/web_static/js/stores.js` — maxlength + char counter on create/edit
- `tests/test_injection_limits.py` — 26 new tests (NEW)

### Advice for next session
- F-054 is now done. Check features.json for the next `planned` feature.
- The injection limit constants in `config/settings.py` are the single source of truth — changing them will automatically propagate through validation, truncation, and API metadata.
- Consider whether the frontend should fetch limits dynamically from a settings endpoint rather than using hardcoded fallback values (currently `|| 500` / `|| 800`).

---

## Session — 2026-04-14 (F-055 + Backlog Population)

### Features Implemented

#### F-055: Eliminate Explore/Story Chat Context Duplication
**Problem:** When explore or story chats trigger agent responses, `MemoryInfluence.build_context()` injects world locations and items into the prompt. But `_build_participant_context()` had ALREADY injected the same world entities into the chat message history (via scene injection or look-around prompt text). This caused the LLM to see the same world data twice — wasting ~500–1,500 tokens per chat turn.

**Solution — Two-layer deduplication:**

1. **`_build_participant_context()`** — Added `skip_world_context` keyword parameter (default `False`). When `True`, the entire "World Context" section (laws, locations, items, stores) is omitted. Non-chat callers (look-around image gen, story narration, story illustration) continue to use the default `False` since they don't use MemoryInfluence.

2. **`MemoryInfluence.build_context()`** — Added `skip_world_entities` keyword parameter (default `False`). When `True`, the active locations and items are not loaded or formatted. This is the primary dedup mechanism.

3. **`HumanChat._should_skip_world_entities()`** — New static method that inspects chat metadata for `explore_location_id` (explore chats) or `story_chat: True` (story chats). Returns `True` for chats where participant context with world data is already in the chat history.

4. **All 4 `build_context()` call sites** in `HumanChat` (`get_agent_response`, `continue_conversation`, `get_agent_response_streaming`, `continue_conversation_streaming`) now pass `skip_world_entities=self._should_skip_world_entities(record)`.

5. **`_helpers.py` re-export** updated to forward `skip_world_context` parameter.

**Token savings:** ~500–1,500 tokens per explore/story chat turn, scaling with the number of active world entities.

### Backlog Population
Added 8 new features to `features.json` (F-056 through F-062) from the LLM Injection Optimization task list:
- **F-056**: Skip Self-Persona Preview (S-03)
- **F-057**: Global Token Budget Manager (S-04)
- **F-058**: Rolling Conversation Summary (S-06)
- **F-059**: Lazy/Cached Memory Scoring (S-07)
- **F-060**: Conditional Law Injection (S-09)
- **F-061**: Tiered Injection Profiles (S-10)
- **F-062**: Aggressive Character Preview Truncation (S-11)

### Test Results
- 14 new tests in `tests/test_context_dedup.py`
- Full suite: **3,165 passed**, 12 skipped, 0 failures (89s)

### Files Modified
- `core/routes/explore.py` — `skip_world_context` param on `_build_participant_context`
- `core/routes/_helpers.py` — Re-export forwards new parameter
- `core/memory_influence.py` — `skip_world_entities` param on `build_context`
- `core/human_chat.py` — `_should_skip_world_entities` helper + 4 call site updates
- `features.json` — F-055 completed, F-056–F-062 added to backlog
- `tests/test_context_dedup.py` — 14 new tests (NEW)

### Advice for next session
- F-055 is done. Next P1 optimization is **F-056** (skip self-persona preview), also small effort.
- The `_should_skip_world_entities` method is extensible — if new chat types are added where world context enters the history, just add their metadata key there.
- The `skip_world_entities` param on `MemoryInfluence.build_context()` could also be used by other callers (sessions, discussions) if they embed world context elsewhere.


---

## Session — 2026-04-14 — F-056: Skip Self-Persona Preview in Participant Context

**Feature**: F-056 — Skip Self-Persona Preview in Participant Context
**Status**: Completed
**Tests**: 3180 passed (+15 new), 12 skipped, 0 failures

### What was built
Added a current_speaker parameter to _build_participant_context() that skips the redundant persona preview when the participant IS the current speaker. The speaker already has their full system_prompt injected as the LLM system message, so repeating a 500-char preview is wasteful.

### Implementation details

#### core/routes/explore.py
- Added current_speaker: str | None = None keyword parameter
- Council members: When member.name matches current_speaker (case-insensitive), the **Persona:** {system_prompt[:500]} line is omitted
- Characters: When char.name matches current_speaker (case-insensitive), both **Backstory:** and **Persona:** lines are omitted
- Preserved for self: Name, role/description, specialties, and traits are always included
- No changes to existing call sites: All 4 current callers pass current_speaker=None by default

#### core/routes/_helpers.py
- Updated re-export wrapper to accept and forward current_speaker parameter

#### tests/test_self_persona_skip.py — 15 new tests
- TestCouncilMemberSelfPersonaSkip (6 tests)
- TestCharacterSelfPersonaSkip (5 tests)
- TestMixedParticipantsSelfSkip (2 tests)
- TestHelpersForwardsCurrentSpeaker (2 tests)

### Token savings
- ~500 chars of system_prompt preview = ~125 tokens saved per participant turn
- Compound savings with multiple participants: 3 members = ~375 tokens saved per round

### Advice for Next Agent
1. The current_speaker parameter is opt-in. No existing call site passes it yet. To realize savings, callers that know the speaker should pass current_speaker=member.name.
2. The most impactful integration would be modifying HumanChat.get_agent_response() to use _build_participant_context(participants, current_speaker=member.name) per-turn. However, those methods use _build_human_chat_prompt() instead. A future feature could unify these.
3. Next eligible features: F-057 (Token Budget Manager), F-058 (Rolling Conversation Summary), F-059 (Lazy/Cached Memory Scoring), F-060 (Conditional Law Injection), F-062 (Aggressive Character Preview Truncation). F-061 depends on F-057.
4. The sw CLI tool is NOT available. Use direct Python commands instead.


---

## Session — F-057: Global Token Budget / Context Window Manager
**Date:** 2026-04-14
**Status:** Completed

### What was done
Implemented F-057 — a ContextBudget class that manages a global token budget across priority-ordered context layers. This ensures total context stays within a target window regardless of world size.

### Files created
- core/context_budget.py — New module with estimate_tokens, truncate_to_tokens, ContextLayer enum, LayerAllocation dataclass, ContextBudget class
- tests/test_context_budget.py — 55 unit tests across 10 test classes

### Files modified
- config/settings.py — Added 6 new constants for context budget allocation
- features.json — F-057 status set to completed

### Test results
- F-057 tests: 55 passed in 0.07s
- Full regression: 3235 passed, 12 skipped, 0 failures (+55 new tests)

### Advice for Next Agent
1. F-057 is opt-in. No existing callers modified.
2. Next eligible: F-058, F-059, F-060, F-061 (now unblocked), F-062.
3. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session — F-058: Rolling Conversation Summary
**Date:** 2026-04-14
**Status:** Completed

### What was done
Implemented F-058 — rolling LLM-based summaries for long conversations. When a conversation exceeds 10 messages, older messages are compressed into a cached summary and injected alongside the 5 most recent raw messages, replacing the old 'raw last 10' window. This preserves context continuity while reducing token usage in long conversations.

### Files created
- core/conversation_summary.py — New module with ConversationSummarizer, RollingSummaryResult, and CachedSummary classes. Content-hash caching avoids re-summarizing unchanged conversation prefixes. Graceful fallback on LLM failure.
- 	ests/test_rolling_summary.py — 37 unit tests across 9 test classes

### Files modified
- config/settings.py — Added 4 new constants: ROLLING_SUMMARY_THRESHOLD, ROLLING_SUMMARY_RECENT_MESSAGES, ROLLING_SUMMARY_MAX_TOKENS, ROLLING_SUMMARY_ENABLED
- core/human_chat.py — Import, __init__ summarizer param, _build_human_chat_prompt summary_result, _build_api_messages summary_result, all 4 response methods wired with graceful fallback
- eatures.json — F-058 status set to completed

### Design decisions
- **Content-hash caching**: Only re-summarizes when the older-message prefix actually changes
- **Opt-in**: Existing callers without a summarizer get identical behavior
- **Graceful fallback**: LLM failure silently falls back to raw last-10 behavior
- **Reuses existing infrastructure**: Same SUMMARIZATION_PROVIDER/MODEL config as memory summarization

### Test results
- F-058 tests: 37 passed in 0.32s
- Full regression: 3,272 passed, 12 skipped, 0 failures (+37 new tests)

### Advice for Next Agent
1. F-058 is opt-in. Pass summarizer=ConversationSummarizer(api_client=client) to HumanChat.__init__ to activate.
2. Next eligible features: F-059, F-060, F-061 (depends on F-057 done), F-062.
3. The sw CLI tool is NOT available. Use direct Python commands instead.

---

## Session — 2026-04-14 — F-062: Aggressive Character Preview Truncation

**Feature**: F-062 — Aggressive Character Preview Truncation
**Status**: Completed
**Tests**: 3288 passed (+16 new), 12 skipped, 0 failures

### What was built
Reduced character backstory and persona (system_prompt) preview length from 500 to 200 characters in `_build_participant_context()`. These previews tell OTHER participants who is in the room — the character themselves already has their full backstory and system_prompt in their LLM system message. Council member persona previews remain at 500 chars since their system_prompt IS their primary identity.

### Token savings
- **Per character**: ~300 chars backstory + ~300 chars persona = ~150 tokens saved
- **3 characters**: ~450 tokens saved per prompt
- **Compound with F-056**: Characters who are the current speaker already skip previews entirely, so savings stack for non-speaker characters

### Implementation details

#### config/settings.py — 3 new constants
- `COUNCIL_PERSONA_PREVIEW_LENGTH = 500` — Council member preview (unchanged behavior)
- `CHARACTER_BACKSTORY_PREVIEW_LENGTH = 200` — Character backstory preview (was 500)
- `CHARACTER_PERSONA_PREVIEW_LENGTH = 200` — Character persona preview (was 500)

#### core/routes/explore.py — `_build_participant_context()`
- Imported all 3 new constants
- Council member persona preview now uses `COUNCIL_PERSONA_PREVIEW_LENGTH` (still 500)
- Character backstory preview now uses `CHARACTER_BACKSTORY_PREVIEW_LENGTH` (200)
- Character persona preview now uses `CHARACTER_PERSONA_PREVIEW_LENGTH` (200)
- All ellipsis logic updated to use the same constants for consistency

#### tests/test_character_preview_truncation.py — 16 new tests
- `TestCharacterBackstoryTruncation` (4 tests): short/long/exact-200/201-char backstory
- `TestCharacterPersonaTruncation` (3 tests): short/long/exact-200-char persona
- `TestCouncilMemberPreserved` (2 tests): council stays at 500, 300-char no ellipsis
- `TestSettingsConstants` (3 tests): verify constant values
- `TestConfigurablePreviewLength` (2 tests): monkey-patch constants to verify configurability
- `TestMultiCharacterSavings` (2 tests): multi-character preview size verification

### Advice for Next Agent
1. The preview length constants in `config/settings.py` are the single source of truth. Changing them will automatically propagate through `_build_participant_context()`.
2. Next eligible features: F-059 (Lazy/Cached Memory Scoring), F-060 (Conditional Law Injection), F-061 (Tiered Injection Profiles).
3. The sw CLI tool is NOT available. Use direct Python commands instead.

