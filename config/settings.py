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

# Environment variable names for API keys
OPENROUTER_API_KEY_ENV = "JERICHO_OPENROUTER_API_KEY"
MANCER_API_KEY_ENV = "JERICHO_MANCER_API_KEY"

# Environment variable names for model selection
OPENROUTER_MODEL_ENV = "JERICHO_OPENROUTER_MODEL"
MANCER_MODEL_ENV = "JERICHO_MANCER_MODEL"

# Default models (can be overridden per council member)
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_MANCER_MODEL = "nothingiisreal/MN-12B-Celeste-V1.9"

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

# User description (injected into AI chat context)
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

# ─── Proposal Settings ─────────────────────────────────────────
PROPOSAL_STATUSES = ("draft", "open", "under_review", "decided", "withdrawn")
PROPOSAL_CATEGORIES = ("character", "governance", "ethics", "expansion", "general", "evolution")
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
EVOLUTION_TYPES = ("trait_add", "trait_remove", "trait_modify", "field_update", "version_bump")
EVOLUTION_STATUSES = ("draft", "proposed", "voting", "decided", "applied", "rejected")
MAX_EVOLUTION_CHANGES = 10              # Max changes per evolution proposal

# ─── Location Settings ────────────────────────────────────────
LOCATIONS_DIR = DATA_DIR / "locations"
LOCATION_STATUSES = ("draft", "active", "archived")
LOCATION_FEATURE_TYPES = ("landmark", "district", "building", "natural", "infrastructure", "custom")

# ─── Council Expansion Settings ───────────────────────────────
EXPANSION_DIR = DATA_DIR / "council_expansions"
EXPANSION_STATUSES = ("draft", "proposed", "voting", "decided", "applied", "rejected")
EXPANSION_REQUIRED_FIELDS = ("name", "role", "description", "api_provider", "model", "system_prompt")

# ─── Web Dashboard Settings ──────────────────────────────────
WEB_HOST = "127.0.0.1"
WEB_PORT = 8080
WEB_STATIC_DIR = CORE_DIR / "web_static"

# ─── Report Generator Settings ───────────────────────────────
REPORTS_DIR = DATA_DIR / "reports"
REPORT_SECTIONS = ("council", "proposals", "votes", "characters", "analytics")
