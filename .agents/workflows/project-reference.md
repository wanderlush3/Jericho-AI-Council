---
description: Jericho project reference — architecture, gotchas, and patterns for efficient coding sessions
---

# Jericho Project Reference

Read this BEFORE doing any work. It prevents known token-wasting pitfalls.

## ⚠️ Critical Gotchas

### 1. grep_search DOES NOT WORK on frontend files
Frontend JS and CSS files have encoding that causes `grep_search` to return **zero results**. Do NOT waste calls retrying.
- **Instead**: Use `view_file` on the specific module file (see module maps below)
- Grep works fine on all `.py` files

### 2. pytest output is garbled on Windows terminal
The PowerShell terminal encoding corrupts pytest's ANSI output. Do NOT try to read it directly.
- **Instead**: Use this pattern:
```python
python -c "import subprocess; r = subprocess.run(['python', '-m', 'pytest', 'tests/YOUR_TEST.py', '-v', '--tb=short', '--no-header'], capture_output=True, text=True, encoding='utf-8'); open(r'C:\\\\tmp\\\\testout.txt', 'w', encoding='utf-8').write(r.stdout + '\\n---STDERR---\\n' + r.stderr); print('returncode:', r.returncode)"
```
Then `view_file` on `C:\tmp\testout.txt`.

### 3. Modular Architecture — read ONLY the file you need
The codebase is split into focused modules. **Never read the full codebase.** Jump to the specific module using the maps below.

### 4. Test patches target core.web_api
Test fixtures patch `core.web_api.COUNCIL_MEMBERS_DIR` etc. The `web_api.py` re-exports these constants from `config.settings`. If a route module needs a settings constant that tests patch, import it via `core.web_api` inside the function body.

## Architecture Overview

```
c:\ai_tools\jericho\
├── core/
│   ├── web_api.py              # Thin FastAPI compositor (~115 lines)
│   ├── routes/                 # Backend route modules (20 files)
│   │   ├── _helpers.py         # Shared cross-module helpers
│   │   ├── council.py          # /api/council endpoints
│   │   ├── proposals.py        # /api/proposals endpoints
│   │   ├── characters.py       # /api/characters endpoints
│   │   ├── generation.py       # /api/generate endpoints
│   │   ├── explore.py          # /api/explore endpoints
│   │   ├── stories.py          # /api/stories endpoints
│   │   ├── settings.py         # /api/settings endpoints
│   │   ├── chat.py             # /api/chat endpoints
│   │   ├── evolutions.py       # /api/evolutions endpoints
│   │   ├── sessions.py         # /api/sessions endpoints
│   │   ├── votes.py            # /api/votes endpoints
│   │   ├── locations.py        # /api/locations endpoints
│   │   ├── items.py            # /api/items endpoints
│   │   ├── stores.py           # /api/stores endpoints
│   │   ├── treasury.py         # /api/treasury endpoints
│   │   ├── memories.py         # /api/memories endpoints
│   │   ├── laws.py             # /api/laws endpoints
│   │   ├── images.py           # /api/images endpoints
│   │   ├── tasks.py            # /api/tasks endpoints
│   │   └── status.py           # /api/status endpoint
│   ├── web_static/
│   │   ├── index.html          # Shell HTML (loads 26 JS modules)
│   │   ├── style.css           # Root CSS (@import aggregator)
│   │   ├── css/                # CSS modules (33 files)
│   │   └── js/                 # JS modules (26 files)
│   ├── characters.py           # CharacterManager
│   ├── locations.py            # LocationManager
│   ├── proposals.py            # ProposalManager
│   ├── voting.py               # VotingEngine
│   ├── registry.py             # Council member registry
│   ├── memory.py               # Council memory system
│   ├── human_chat.py           # Chat conversation manager
│   ├── agent_chat.py           # AI chat logic
│   ├── api_client.py           # LLM API client (OpenRouter/Mancer)
│   ├── api_keys.py             # Encrypted API key management
│   ├── generation_pipeline.py  # ComfyUI generation pipeline
│   ├── comfyui_client.py       # ComfyUI client + template manager
│   ├── image_manager.py        # Image storage manager
│   └── cli.py                  # Click CLI
├── config/settings.py          # Path constants
├── council/                    # Council member YAML profiles
├── tests/                      # pytest tests
└── progress_log.md             # Institutional memory
```

## Backend Route Module Map

Each module contains an `APIRouter` registered in `web_api.py`. To find an endpoint, read just the relevant module:

| Module | File | Key Endpoints |
|--------|------|---------------|
| Status | `core/routes/status.py` | `GET /api/status` |
| Council | `core/routes/council.py` | `/api/council`, `/api/council/{name}`, promote, avatars |
| Proposals | `core/routes/proposals.py` | `/api/proposals`, detail, handoffs, discussion |
| Votes | `core/routes/votes.py` | `/api/votes`, veto, lift-veto |
| Characters | `core/routes/characters.py` | `/api/characters`, CRUD, traits, avatars |
| Locations | `core/routes/locations.py` | `/api/locations`, CRUD, features |
| Items | `core/routes/items.py` | `/api/items`, CRUD, properties |
| Stores | `core/routes/stores.py` | `/api/stores`, inventory, purchasing |
| Chat | `core/routes/chat.py` | `/api/chat`, send, close, members |
| Sessions | `core/routes/sessions.py` | `/api/sessions`, rounds, handoff |
| Memories | `core/routes/memories.py` | `/api/memories`, beliefs, shared |
| Laws | `core/routes/laws.py` | `/api/laws`, CRUD, status |
| Treasury | `core/routes/treasury.py` | `/api/treasury`, credit/debit, taxation |
| Settings | `core/routes/settings.py` | `/api/settings`, API keys, models, ComfyUI |
| Images | `core/routes/images.py` | `/api/images`, upload, set-primary |
| Generation | `core/routes/generation.py` | `/api/generate/start`, SSE stream, queue |
| Explore | `core/routes/explore.py` | `/api/explore`, look-around, scenes |
| Stories | `core/routes/stories.py` | `/api/stories`, chapters, scenes, narrate, illustrate |
| Evolutions | `core/routes/evolutions.py` | `/api/evolutions`, create, rollback |
| Tasks | `core/routes/tasks.py` | `/api/tasks`, CRUD |
| Helpers | `core/routes/_helpers.py` | Shared: `_get_pipeline()`, `_build_participant_context()`, etc. |

## Frontend JS Module Map

All functions are global (no ES modules). `core.js` must load first:

| Module | File | Functions |
|--------|------|-----------|
| **Core** | `js/core.js` | `api()`, `navigateTo()`, `renderView()`, `applySkin()`, `showToast()` |
| Dashboard | `js/dashboard.js` | `renderDashboard()`, narrative banner |
| Council | `js/council.js` | `renderCouncil()`, `renderCouncilDetail()`, promote, avatar |
| Proposals | `js/proposals.js` | `renderProposals()`, `renderProposalDetail()`, discussion, handoffs |
| Votes | `js/votes.js` | `renderVotes()`, `renderVoteDetail()` |
| Gallery | `js/gallery.js` | `renderImageGallery()`, lightbox, upload |
| Generation | `js/generation.js` | `openGenerateModal()`, SSE progress, council vote |
| Explore | `js/explore.js` | `renderExplore()`, `renderExploreLocation()`, participants |
| Characters | `js/characters.js` | `renderCharacters()`, `renderCharacterDetail()`, traits, avatar |
| Locations | `js/locations.js` | `renderLocations()`, `renderLocationDetail()` |
| Items | `js/items.js` | `renderItems()`, `renderItemDetail()` |
| Stores | `js/stores.js` | `renderStores()`, `renderStoreDetail()` |
| Analytics | `js/analytics.js` | `renderAnalytics()` |
| Chat | `js/chat.js` | `renderChat()`, `renderChatDetail()`, messages |
| Settings | `js/settings.js` | `renderSettings()` (basic), model options |
| Memories | `js/memories.js` | `renderMemories()`, `renderMemoryDetail()` |
| Treasury | `js/treasury.js` | `renderTreasury()`, taxation, transfers |
| Evolutions | `js/evolutions.js` | `renderEvolution()`, `renderEvolutionDetail()`, timelines |
| Sessions | `js/sessions.js` | `renderCouncilSessions()`, rounds |
| Laws | `js/laws.js` | `renderLaws()`, `renderLawDetail()` |
| ComfyUI | `js/settings_comfyui.js` | Extended settings, templates, connection test |
| Tasks | `js/tasks.js` | `renderTasks()`, `renderTaskDetail()` |
| Queue | `js/gen_queue.js` | `renderGenerationQueue()`, polling |
| Presets | `js/presets.js` | `renderPresetEditor()`, create/edit/export |
| Batch | `js/batch_gen.js` | `openBatchGenerateModal()`, batch submit |
| Stories | `js/stories.js` | `renderStories()`, `renderStoryDetail()`, reader |

## Frontend CSS Module Map

Root `style.css` uses `@import url("css/...")`. Key modules:

| Module | Purpose |
|--------|---------|
| `css/tokens.css` | Design tokens (`:root` variables) |
| `css/base.css` | Reset & base styles |
| `css/layout.css` | Layout + sidebar |
| `css/skins.css` | Theme skins (Frutiger Aero, Y2K, Vaporwave) |
| `css/[feature].css` | Feature-specific styles (council, chat, explore, etc.) |

## Common Patterns

### Adding a new feature:
1. **Backend**: Add route to the relevant `core/routes/xxx.py` module
2. **Frontend JS**: Edit the relevant `js/xxx.js` module
3. **Frontend CSS**: Edit the relevant `css/xxx.css` module
4. **Tests**: Add to `tests/test_web_api.py`

### Manager pattern (characters, locations, proposals):
- All use lifecycle: `draft → active → archived/superseded`
- `_VALID_TRANSITIONS` dict controls allowed state changes
- Each manager has: `create()`, `get()`, `list()`, `update()`, `update_status()`

### Frontend pattern:
- `renderXxx()` = list view, `renderXxxDetail(id)` = detail view
- Forms use `id` attributes, read with `document.getElementById()`
- Toast notifications: `showToast(message, isError)`

### Test pattern:
- Test classes named `TestApiXxx` in `test_web_api.py`
- Fixtures create temp directories and mock paths via `core.web_api.*`
- Use `client` fixture for standard endpoints, specialized fixtures for features needing extra dirs

## Running Tests
// turbo
```
python -c "import subprocess; r = subprocess.run(['python', '-m', 'pytest', 'tests/', '-v', '--tb=short', '--no-header'], capture_output=True, text=True, encoding='utf-8'); open(r'C:\\\\tmp\\\\testout.txt', 'w', encoding='utf-8').write(r.stdout + '\\n---STDERR---\\n' + r.stderr); print('returncode:', r.returncode)"
```
Then view `C:\tmp\testout.txt` for results.

## ComfyUI Integration Reference

### Architecture: Workflow Template System
Users export ComfyUI workflows as API-format JSON, upload to Jericho. Jericho fills `%placeholder%` tokens and POSTs to ComfyUI's API.

### Implemented Modules
- `core/comfyui_client.py` — ComfyUIClient, WorkflowTemplateManager
- `core/image_manager.py` — ImageManager, EntityImage
- `core/prompt_builder.py` — PromptBuilder (5 modes), StylePreset
- `core/generation_pipeline.py` — GenerationPipeline, GenerationRequest

### Key Details
- **Prompt modes**: council_vote, character, system, user_refined, raw_user
- **IDs**: TPL-XXXX (templates), IMG-XXXX (images), GEN-XXXX (jobs)
- **Queue limit**: 10 concurrent generation jobs
- **Connection**: Local only, default `127.0.0.1:8188`
