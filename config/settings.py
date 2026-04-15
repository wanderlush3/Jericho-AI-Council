"""
Jericho — Configuration & Settings

Centralized paths, API configuration, and governance thresholds.
"""

from pathlib import Path

from dotenv import load_dotenv

# ─── Project Root ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── Directory Paths ──────────────────────────────────────────
CONFIG_DIR = PROJECT_ROOT / "config"
CORE_DIR = PROJECT_ROOT / "core"
COUNCIL_DIR = PROJECT_ROOT / "council"
COUNCIL_MEMBERS_DIR = COUNCIL_DIR / "members"
COUNCIL_TEMPLATES_DIR = COUNCIL_DIR / "templates"
COUNCIL_AVATARS_DIR = COUNCIL_DIR / "avatars"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
PROPOSALS_DIR = DATA_DIR / "proposals"
VOTES_DIR = DATA_DIR / "votes"
CHARACTERS_DIR = DATA_DIR / "characters"
CHARACTER_AVATARS_DIR = CHARACTERS_DIR / "avatars"
MEMORIES_DIR = DATA_DIR / "memories"
SHARED_MEMORIES_DIR = MEMORIES_DIR / "shared"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
DISCUSSIONS_DIR = DATA_DIR / "discussions"
COUNCIL_SESSIONS_DIR = DATA_DIR / "council_sessions"
TESTS_DIR = PROJECT_ROOT / "tests"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LOGS_DIR = PROJECT_ROOT / "logs"

# ─── Key Files ─────────────────────────────────────────────────
FEATURES_FILE = PROJECT_ROOT / "features.json"
PROGRESS_LOG_FILE = PROJECT_ROOT / "progress_log.md"
ENV_FILE = CONFIG_DIR / ".env"
ENV_EXAMPLE_FILE = CONFIG_DIR / ".env.example"

# Load environment variables from .env (keys may still be encrypted;
# core.api_keys.APIKeyManager handles decryption at runtime)
load_dotenv(ENV_FILE, override=False)

# ─── API Configuration ────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MANCER_BASE_URL = "https://neuro.mancer.tech/oai/v1"
LMSTUDIO_DEFAULT_BASE_URL = "http://localhost:1234/v1"
LMSTUDIO_BASE_URL_ENV = "JERICHO_LMSTUDIO_BASE_URL"

# Environment variable names for API keys
OPENROUTER_API_KEY_ENV = "JERICHO_OPENROUTER_API_KEY"
MANCER_API_KEY_ENV = "JERICHO_MANCER_API_KEY"
LMSTUDIO_API_KEY_ENV = "JERICHO_LMSTUDIO_API_KEY"

# Environment variable names for model selection
OPENROUTER_MODEL_ENV = "JERICHO_OPENROUTER_MODEL"
MANCER_MODEL_ENV = "JERICHO_MANCER_MODEL"
LMSTUDIO_MODEL_ENV = "JERICHO_LMSTUDIO_MODEL"

# Default models (can be overridden per council member)
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_MANCER_MODEL = "nothingiisreal/MN-12B-Celeste-V1.9"
DEFAULT_LMSTUDIO_MODEL = "Default"

# Valid Mancer model options (shown in dropdown menus)
MANCER_MODEL_OPTIONS = (
    "Default",
    "dans-pe-1.3-12b",
    "dans-pe-1.3-24b",
    "glm-4.7",
    "goliath-120b",
    "magnum-72b-v4",
    "mytholite",
    "mythomax",
    "remm-slerp",
    "weaver-alpha",
)

# Valid OpenRouter model options (shown in dropdown menus)
OPENROUTER_MODEL_OPTIONS = (
    "Default",
    "mistralai/mistral-small-creative",
    "deepseek/deepseek-v3.2-exp",
    "arcee-ai/trinity-large-preview:free",
    "anthropic/claude-sonnet-4.6",
    "z-ai/glm-4.6",
    "openrouter/healer-alpha",
    "mistralai/mistral-small-2603",
    "moonshotai/kimi-k2.5",
)

# Valid LM Studio model options (shown in dropdown menus)
# These are labels — actual model is whatever the user has loaded in LM Studio.
LMSTUDIO_MODEL_OPTIONS = (
    "Default",
    "Loaded Model",
)

# User profile (injected into AI chat context)
USER_NAME_ENV = "JERICHO_USER_NAME"
USER_NAME_MAX_LENGTH = 100
USER_DESCRIPTION_ENV = "JERICHO_USER_DESCRIPTION"
USER_DESCRIPTION_MAX_LENGTH = 700

# API retry settings
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 2.0
API_TIMEOUT_SECONDS = 120

# Multi-AI chat pacing: delay (seconds) between each AI response
MULTI_AI_RESPONSE_DELAY = 2.0

# ─── Governance Thresholds ─────────────────────────────────────
APPROVAL_THRESHOLD = 0.60      # 60% of votes must be 'for'
QUORUM_MINIMUM = 5             # Minimum voters for a valid decision (out of 9)
VOTE_OPTIONS = ("for", "against", "abstain")

# ─── Council Settings ──────────────────────────────────────────
INITIAL_COUNCIL_SIZE = 9
MAX_COUNCIL_SIZE = 15          # Upper limit for expansion

# ─── Memory Settings ──────────────────────────────────────────
MAX_MEMORY_CONTEXT_TOKENS = 4000   # Max tokens of memory injected per agent
SESSION_LOG_FORMAT = "jsonl"        # Append-only session memories

# ─── Memory Influence Settings ────────────────────────────────
MEMORY_INFLUENCE_MAX_MEMORIES = 10     # Max session log entries to inject
MEMORY_INFLUENCE_MAX_BELIEFS = 5       # Max core beliefs to inject
MEMORY_INFLUENCE_MIN_RELEVANCE = 0.1   # Minimum relevance score threshold
MEMORY_INFLUENCE_BELIEF_BOOST = 1.5    # Multiplier for belief scores

# ─── Memory Cache Settings (F-059) ────────────────────────────
MEMORY_CACHE_TTL_SECONDS = 300             # Cache MemoryContext for 5 minutes before re-scoring
MEMORY_CACHE_ENABLED = True                # Global toggle for memory context caching

# ─── World Context Injection Limits ───────────────────────────
# Max entities injected into LLM prompts (caps unbounded world growth).
# Used by MemoryInfluence.build_context and _build_participant_context.
CONTEXT_MAX_WORLD_LOCATIONS = 5        # Top N locations injected per prompt
CONTEXT_MAX_WORLD_ITEMS = 5            # Top N items injected per prompt
CONTEXT_MAX_WORLD_STORES = 5           # Top N stores injected per prompt
CONTEXT_MAX_WORLD_LAWS = 5             # Top N laws injected per prompt

# ─── Embedding Settings ───────────────────────────────────────
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"          # Sentence-transformer model
EMBEDDING_SIMILARITY_WEIGHT = 0.7                   # Weight for embedding score in hybrid mode
EMBEDDING_JACCARD_WEIGHT = 0.3                      # Weight for Jaccard fallback in hybrid mode

# ─── Memory Decay Settings ───────────────────────────────────
MEMORY_DECAY_HALF_LIFE_DAYS = 30       # Days until memory freshness decays to 50%
MEMORY_DECAY_MIN_FACTOR = 0.1          # Floor — memories never decay below 10% weight
MEMORY_DECAY_ENABLED = True            # Global toggle for time decay

# ─── Memory Summarization Settings ────────────────────────────
MEMORY_SUMMARIZATION_SESSION_THRESHOLD = 6   # Summarize after this many unique sessions
MEMORY_SUMMARIZATION_KEEP_RECENT = 3         # Always keep this many recent sessions intact
MEMORY_SUMMARIZATION_ENABLED = True          # Global toggle

# Summarization LLM: provider & model (user picks in Settings UI)
# Environment variable names for summarization model selection
SUMMARIZATION_PROVIDER_ENV = "JERICHO_SUMMARIZATION_PROVIDER"
SUMMARIZATION_MODEL_ENV = "JERICHO_SUMMARIZATION_MODEL"
DEFAULT_SUMMARIZATION_PROVIDER = "openrouter"
DEFAULT_SUMMARIZATION_MODEL = "mistralai/mistral-small-2603"

# Model options for summarization (separate from chat models)
SUMMARIZATION_OPENROUTER_MODELS = (
    "mistralai/mistral-small-2603",
    "mistralai/mistral-small-creative",
    "deepseek/deepseek-v3.2-exp",
    "arcee-ai/trinity-large-preview:free",
    "anthropic/claude-sonnet-4.6",
)
SUMMARIZATION_MANCER_MODELS = (
    "dans-pe-1.3-12b",
    "dans-pe-1.3-24b",
    "mythomax",
    "magnum-72b-v4",
)
SUMMARIZATION_LMSTUDIO_MODELS = (
    "Loaded Model",
)

# ─── Contested Memory Settings ────────────────────────────────
CONTESTED_MEMORY_ENABLED = True        # Allow agents to record divergent recollections
CONTESTED_MEMORY_PROBABILITY = 0.05    # 5% chance — rare but possible

# ─── Proposal Settings ─────────────────────────────────────────
PROPOSAL_STATUSES = ("draft", "open", "open_to_review", "under_review", "decided", "withdrawn")
PROPOSAL_CATEGORIES = ("character", "governance", "ethics", "expansion", "general", "evolution", "location", "item", "law")
REVIEW_STANCES = ("support", "oppose", "neutral")

# ─── Discussion Settings ──────────────────────────────────────
DEFAULT_DISCUSSION_ROUNDS = 2      # Default rounds per discussion
MAX_DISCUSSION_ROUNDS = 10         # Upper limit to prevent runaway discussions

# ─── Character Template Settings ──────────────────────────────
CHARACTER_STATUSES = ("draft", "active", "archived", "superseded")
CHARACTER_REQUIRED_TRAIT_TYPES = ("personality", "values", "flaws")

# ─── Character Design Settings ────────────────────────────────
CHARACTER_DESIGNS_DIR = DATA_DIR / "character_designs"
DEFAULT_DESIGN_PHASES = ("concept", "traits", "backstory", "prompt", "review")
MAX_DESIGN_CONTRIBUTORS = 9            # Full council

# ─── Character Evolution Settings ─────────────────────────────
EVOLUTION_DIR = DATA_DIR / "character_evolutions"
EVOLUTION_TYPES = ("trait_add", "trait_remove", "trait_modify", "field_update", "version_bump",
                   "system_prompt_update", "personality_update", "rollback")
EVOLUTION_STATUSES = ("draft", "proposed", "voting", "decided", "applied", "rejected")
EVOLUTION_OVERLAY_STATUSES = ("draft", "active", "archived")
EVOLUTION_TARGETS = ("character", "council_member")
MAX_EVOLUTION_CHANGES = 10              # Max changes per evolution proposal
MAX_EVOLUTION_HISTORY = 50              # Max rollback chain depth per target

# ─── Task Settings ────────────────────────────────────────────
TASKS_DIR = DATA_DIR / "tasks"
TASK_STATUSES = ("draft", "active", "completed")
TASK_MAX_ROUNDS = 5                     # Max narration rounds per task execution

# ─── Location Settings ────────────────────────────────────────
LOCATIONS_DIR = DATA_DIR / "locations"
LOCATION_STATUSES = ("draft", "active", "archived")
LOCATION_FEATURE_TYPES = ("landmark", "district", "building", "natural", "infrastructure", "custom")

# ─── Law Settings ─────────────────────────────────────────────
LAWS_DIR = DATA_DIR / "laws"
LAW_STATUSES = ("draft", "active", "archived")
LAW_SHARED_MEMORIES_DIR = MEMORIES_DIR / "law_shared"

# ─── Conditional Law Injection Settings (F-060) ──────────────
LAW_RELEVANCE_ENABLED = True               # Filter laws by context relevance
LAW_RELEVANCE_MIN_SCORE = 0.05             # Minimum Jaccard score to inject a law

# ─── Item Settings ────────────────────────────────────────────
ITEMS_DIR = DATA_DIR / "items"
ITEM_STATUSES = ("draft", "active", "archived")
ITEM_PROPERTY_TYPES = ("magical", "physical", "consumable", "equipment", "material", "custom")
ITEM_TIERS = ("permanent", "consumable", "degradable")
ITEM_LEGALITY_STATUSES = ("contraband", "legal")
CONSUMABLE_INJECTION_TTL_HOURS = 24     # Consumable item LLM injections expire after this many hours
ITEM_INJECTION_MAX_LENGTH = 500         # Max characters for item llm_injection field
LOCATION_INJECTION_MAX_LENGTH = 800     # Max characters for location llm_injection field
STORE_INJECTION_MAX_LENGTH = 500        # Max characters for store llm_injection field

# ─── Store Settings ──────────────────────────────────────────
STORES_DIR = DATA_DIR / "stores"
STORE_STATUSES = ("draft", "active", "archived")
STORE_TYPES = ("general", "blacksmith", "alchemist", "enchanter", "tavern", "custom")

# ─── Council Expansion Settings ───────────────────────────────
EXPANSION_DIR = DATA_DIR / "council_expansions"
EXPANSION_STATUSES = ("draft", "proposed", "voting", "decided", "applied", "rejected")
EXPANSION_REQUIRED_FIELDS = ("name", "role", "description", "api_provider", "model", "system_prompt")

# ─── ComfyUI Integration Settings ────────────────────────────
COMFYUI_DEFAULT_HOST = "127.0.0.1"
COMFYUI_DEFAULT_PORT = 8007
COMFYUI_TEMPLATES_DIR = DATA_DIR / "comfyui" / "templates"
COMFYUI_IMAGES_DIR = DATA_DIR / "images"           # For F-037b
COMFYUI_PRESETS_DIR = DATA_DIR / "comfyui" / "presets"  # Custom style presets (F-037g)
COMFYUI_TEMPLATE_ASSIGNMENTS_FILE = DATA_DIR / "comfyui" / "template_assignments.json"  # F-039
COMFYUI_ASSIGNABLE_ENTITY_TYPES = ("character", "location", "item", "store")  # F-039
COMFYUI_MAX_QUEUE_SIZE = 10                         # Max concurrent generation jobs
COMFYUI_POLL_INTERVAL = 1.0                         # Seconds between status polls
COMFYUI_POLL_TIMEOUT = 300                          # Max seconds to wait for generation
COMFYUI_HOST_ENV = "JERICHO_COMFYUI_HOST"
COMFYUI_PORT_ENV = "JERICHO_COMFYUI_PORT"
COMFYUI_DEFAULT_STYLE_ENV = "JERICHO_COMFYUI_DEFAULT_STYLE"

# ─── Exploration Settings (F-040) ────────────────────────────
EXPLORATION_DIR = DATA_DIR / "exploration"
EXPLORATION_SCENES_FILE = EXPLORATION_DIR / "scenes.json"

# ─── Story Illustration Settings (F-041) ─────────────────────
STORIES_DIR = DATA_DIR / "stories"
STORY_STATUSES = ("draft", "active", "completed", "archived")
STORY_MAX_CHAPTERS = 50
STORY_MAX_SCENES_PER_CHAPTER = 20

# ─── Prompt Generation Settings (F-037c) ─────────────────────
PROMPT_GENERATION_PROVIDER_ENV = "JERICHO_PROMPT_GENERATION_PROVIDER"
PROMPT_GENERATION_MODEL_ENV = "JERICHO_PROMPT_GENERATION_MODEL"
DEFAULT_PROMPT_GENERATION_PROVIDER = "openrouter"
DEFAULT_PROMPT_GENERATION_MODEL = "mistralai/mistral-small-2603"
PROMPT_GENERATION_MAX_TOKENS = 512          # Prompts are short
PROMPT_GENERATION_TEMPERATURE = 0.8         # Creative but focused

# ─── Web Dashboard Settings ──────────────────────────────────
WEB_HOST = "127.0.0.1"
WEB_PORT = 8080
WEB_STATIC_DIR = CORE_DIR / "web_static"

# ─── Report Generator Settings ───────────────────────────────
REPORTS_DIR = DATA_DIR / "reports"
REPORT_SECTIONS = ("council", "proposals", "votes", "characters", "analytics")

# ─── Treasury / Obelisk Settings ─────────────────────────────
TREASURY_DIR = DATA_DIR / "treasury"
OBELISK_TIERS = ("bronze", "silver", "gold")
OBELISK_CONVERSION_RATE = 100              # 100 bronze = 1 silver, 100 silver = 1 gold
OBELISK_DEFAULT_BALANCE = {"gold": 200, "silver": 0, "bronze": 0}
OBELISK_GOVERNMENT_BALANCE = {"gold": 1000, "silver": 0, "bronze": 0}
OBELISK_ACCOUNT_TYPES = ("council_member", "character", "user", "government")

# ─── Taxation Settings ───────────────────────────────────────
TAX_POLICY_FILE = DATA_DIR / "treasury" / "tax_policy.json"
TAX_LEDGER_FILE = DATA_DIR / "treasury" / "tax_ledger.jsonl"
TAX_DEFAULT_RATE = 0.05                    # 5% tax on transfers
TAX_GOVERNMENT_ACCOUNT_ID = "ACCT-gov-jericho"

# ─── Salary / Payroll Settings ────────────────────────────────
SALARY_LEDGER_FILE = DATA_DIR / "salary_ledger.json"
SALARY_INTERVAL_DAYS = 7               # Days between payroll runs
SALARY_COUNCIL_USER_AMOUNT = 200       # Gold Obelisk per council member / user
SALARY_CHARACTER_AMOUNT = 100          # Gold Obelisk per character

# ─── Narrative Engine Settings ───────────────────────────────
NARRATIVE_MAX_BULLETINS = 10               # Max bulletins returned per request
NARRATIVE_MAX_AGE_DAYS = 30                # Only consider events within this window

# ─── Context Budget Settings (F-057) ─────────────────────────
DEFAULT_CONTEXT_BUDGET_TOKENS = 32768      # Default target context window (tokens)
CONTEXT_BUDGET_SYSTEM_PROMPT_PCT = 0.15    # 15% for system prompt
CONTEXT_BUDGET_HISTORY_PCT = 0.35          # 35% for conversation history
CONTEXT_BUDGET_MEMORIES_PCT = 0.20         # 20% for memories & beliefs
CONTEXT_BUDGET_WORLD_PCT = 0.20            # 20% for world context
CONTEXT_BUDGET_INJECTIONS_PCT = 0.10       # 10% for LLM injections

# ─── Participant Preview Settings (F-062) ────────────────────
# Preview length for "other participants" in _build_participant_context.
# These previews tell OTHER participants who is in the room — not the
# participant themselves (their full prompt is already in the system message).
COUNCIL_PERSONA_PREVIEW_LENGTH = 500      # Council member system_prompt preview
CHARACTER_BACKSTORY_PREVIEW_LENGTH = 200  # Character backstory preview (was 500)
CHARACTER_PERSONA_PREVIEW_LENGTH = 200    # Character system_prompt preview (was 500)

# ─── Rolling Conversation Summary Settings (F-058) ───────────
ROLLING_SUMMARY_THRESHOLD = 10             # Summarize when message count exceeds this
ROLLING_SUMMARY_RECENT_MESSAGES = 5        # Keep this many recent raw messages alongside summary
ROLLING_SUMMARY_MAX_TOKENS = 300           # Max tokens for the generated summary
ROLLING_SUMMARY_ENABLED = True             # Global toggle for rolling summaries
