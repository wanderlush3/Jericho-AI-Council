---
description: Jericho project reference — architecture, gotchas, and patterns for efficient coding sessions
---

# Jericho Project Reference

Read this BEFORE doing any work. It prevents known token-wasting pitfalls.

## ⚠️ Critical Gotchas

### 1. grep_search DOES NOT WORK on frontend files
`app.js` (~165KB) and `style.css` (~74KB) have encoding that causes `grep_search` to return **zero results** for any query. Do NOT waste calls retrying.
- **Instead**: Use `view_file` with line ranges from the section map below
- Grep works fine on all `.py` files

### 2. pytest output is garbled on Windows terminal
The PowerShell terminal encoding corrupts pytest's ANSI output. Do NOT try to read it directly.
- **Instead**: Use this pattern:
```python
python -c "import subprocess; r = subprocess.run(['python', '-m', 'pytest', 'tests/YOUR_TEST.py', '-v', '--tb=short', '--no-header'], capture_output=True, text=True, encoding='utf-8'); open(r'C:\\tmp\\testout.txt', 'w', encoding='utf-8').write(r.stdout + '\n---STDERR---\n' + r.stderr); print('returncode:', r.returncode)"
```
Then `view_file` on `C:\tmp\testout.txt`.

### 3. app.js is ~3500+ lines — use the section map
Don't view the whole file. Jump straight to the section you need.

## Architecture Overview

```
c:\ai_tools\jericho\
├── core/                    # All backend logic
│   ├── web_api.py          # FastAPI endpoints (~1900+ lines)
│   ├── web_static/         # Frontend (served by FastAPI)
│   │   ├── index.html      # Shell HTML with nav sidebar
│   │   ├── app.js          # ALL frontend JS (~3500+ lines, single file)
│   │   └── style.css       # ALL CSS (~3050+ lines, single file)
│   ├── characters.py       # CharacterManager, Trait, CharacterTemplate
│   ├── locations.py        # LocationManager (mirrors characters pattern)
│   ├── png_embed.py        # TavernCard v2 PNG embedding
│   ├── proposals.py        # ProposalManager
│   ├── voting.py           # VotingEngine
│   ├── registry.py         # Council member registry
│   ├── memory.py           # Council memory system
│   ├── human_chat.py       # Chat conversation manager
│   ├── agent_chat.py       # AI chat logic
│   ├── api_client.py       # LLM API client (OpenRouter/Mancer)
│   ├── api_keys.py         # Encrypted API key management
│   ├── analytics.py        # Session analytics
│   ├── dashboard.py        # Terminal dashboard
│   ├── cli.py              # Click CLI
│   └── session.py          # Council session orchestration
├── config/settings.py      # Path constants (CHARACTERS_DIR, etc.)
├── council/                # Council member YAML profiles
├── tests/                  # pytest tests (conftest.py has shared fixtures)
├── features.json           # Feature backlog
└── progress_log.md         # Institutional memory
```

## app.js Section Map (approximate line ranges)

Use these to jump directly to the code you need:

| Section | Lines | Key Functions |
|---------|-------|---------------|
| Globals & State | 1–30 | `state`, `$main()`, helper functions |
| Router | 140–170 | `renderView()`, `navigateTo()` |
| Utilities | 30–140 | `api()`, `showToast()`, `badge()`, `escapeHtml()`, `formatDate()` |
| Dashboard | 170–400 | `renderDashboard()` |
| Council | 400–700 | `renderCouncil()`, `renderCouncilDetail()`, avatar editor |
| Proposals | 700–1000 | `renderProposals()`, `renderProposalDetail()` |
| Votes | 1235–1350 | `renderVotes()`, `renderVoteDetail()` |
| **Characters** | **1350–1950** | `renderCharacters()`, `renderCharacterDetail()`, create/edit/export/avatar |
| Locations | 1950–2300 | `renderLocations()`, `renderLocationDetail()` |
| Chat | 2300–2900 | `renderChat()`, `renderChatDetail()`, message handling |
| Settings | 2900–3200 | `renderSettings()`, API key management |
| Memories | 3200–3500 | `renderMemories()`, `renderMemoryDetail()` |
| Image Gallery | 2848–3132 | `renderImageGallery()`, lightbox, upload |
| Generation Pipeline | 3133–3681 | `openGenerateModal()`, SSE progress, council vote preview |

## web_api.py Endpoint Map (approximate line ranges)

| Section | Lines | Endpoints |
|---------|-------|-----------|
| Status & Council | 1–400 | `/api/status`, `/api/council`, council update/avatar |
| Proposals & Votes | 400–700 | `/api/proposals`, `/api/votes`, veto |
| Chat | 700–890 | `/api/chat`, send/close/add-member |
| **Characters** | **890–1260** | CRUD, status, avatar, export-png, traits |
| Locations | 1260–1400 | CRUD, status, features |
| Analytics & Settings | 1400–1600 | `/api/analytics`, keys, models, user-description |
| Memories | 1600–1900 | `/api/memories`, beliefs, shared |
| Image Gallery | 5001–5162 | `/api/images/file`, list, upload, set-primary, delete |
| Generation Pipeline | 5163–5417 | `/api/generate/start`, `/stream`, `/cancel`, `/jobs`, `/prompts` |

## Common Patterns

### Adding a new feature to an existing view:
1. **Backend**: Add endpoint(s) to `web_api.py` (import managers inside the function)
2. **Frontend**: Edit the relevant render function in `app.js`
3. **CSS**: Append styles to end of `style.css`
4. **Tests**: Add to relevant test class in `tests/test_web_api.py`

### Manager pattern (characters, locations, proposals):
- All use the same lifecycle: `draft → active → archived/superseded`
- `_VALID_TRANSITIONS` dict controls allowed state changes
- Characters now have bidirectional: `active ↔ archived`, `active ↔ draft`, `archived → draft`
- Each manager has: `create()`, `get()`, `list()`, `update()`, `update_status()`

### Frontend pattern:
- `renderXxx()` = list view, `renderXxxDetail(id)` = detail view
- Forms use `id` attributes, read with `document.getElementById()`
- Status updates re-render the detail view: `await renderXxxDetail(id)`
- Toast notifications: `showToast(message, isError)`

### Test pattern:
- Test classes named `TestApiXxx` in `test_web_api.py`
- Fixtures create temp directories and mock `config.settings` paths
- Use `client` fixture for standard endpoints, specialized fixtures for features needing extra dirs

## Key Data Models

### Character lifecycle transitions:
```
draft → active → archived (bidirectional between active/archived/draft)
draft → active → superseded (terminal, versioning only)
```

### Trait (dataclass):
```python
{trait_type: str, name: str, description: str, intensity: float}
# trait_type: "personality" | "values" | "flaws" | "custom"
# intensity: 0.0–1.0
```

## Running Tests
// turbo
```
python -c "import subprocess; r = subprocess.run(['python', '-m', 'pytest', 'tests/', '-v', '--tb=short', '--no-header'], capture_output=True, text=True, encoding='utf-8'); open(r'C:\\tmp\\testout.txt', 'w', encoding='utf-8').write(r.stdout + '\n---STDERR---\n' + r.stderr); print('returncode:', r.returncode)"
```
Then view `C:\tmp\testout.txt` for results.

## ComfyUI Integration Reference (F-037a through F-037g)

### Architecture: Workflow Template System
Users export ComfyUI workflows as API-format JSON, upload to Jericho. Jericho fills `%placeholder%` tokens and POSTs to ComfyUI's API. Images downloaded via ComfyUI's `/view` endpoint, stored in `data/images/{entity_type}/{entity_id}/`.

### Feature Dependency Chain
```
F-037a (Client)  →  F-037b (Images)  →  F-037d (Settings UI)  →  F-037e (Galleries)
        ↓                                                                ↓
F-037c (Prompts) ──────────────────────────────────────────→  F-037f (Pipeline)  →  F-037g (Polish)
```

### Implemented Modules
- `core/comfyui_client.py` — ComfyUIClient, WorkflowTemplateManager, ComfyUIConfig, GenerationJob
- `core/image_manager.py` — ImageManager, EntityImage
- `core/prompt_builder.py` — PromptBuilder (5 modes), StylePreset, PromptRequest/Result
- `core/generation_pipeline.py` — GenerationPipeline, GenerationRequest, GenerationProgress

### Key Design Details
- **Image retrieval**: POST `/prompt` → poll `/history/{id}` → GET `/view?filename=X&type=output`
- **Prompt modes**: council_vote, character, system, user_refined, raw_user
- **IDs**: TPL-XXXX (templates), IMG-XXXX (images), GEN-XXXX (generation jobs)
- **Queue limit**: 10 concurrent generation jobs
- **Connection**: Local only, default `127.0.0.1:8188`
- **Dimensions**: User-configurable per entity type (stored in settings)

### Full specification
See `progress_log.md` session `S-PLANNING-COMFYUI-00000001` for complete details.
