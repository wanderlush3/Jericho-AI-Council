"""
Jericho — Configuration & Settings

Centralized paths, API configuration, and governance thresholds.
"""

from pathlib import Path

# ─── Project Root ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── Directory Paths ──────────────────────────────────────────
CONFIG_DIR = PROJECT_ROOT / "config"
CORE_DIR = PROJECT_ROOT / "core"
COUNCIL_DIR = PROJECT_ROOT / "council"
COUNCIL_MEMBERS_DIR = COUNCIL_DIR / "members"
COUNCIL_TEMPLATES_DIR = COUNCIL_DIR / "templates"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
PROPOSALS_DIR = DATA_DIR / "proposals"
VOTES_DIR = DATA_DIR / "votes"
CHARACTERS_DIR = DATA_DIR / "characters"
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

# ─── API Configuration ────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MANCER_BASE_URL = "https://neuro.mancer.tech/oai/v1"

# Environment variable names for API keys
OPENROUTER_API_KEY_ENV = "JERICHO_OPENROUTER_API_KEY"
MANCER_API_KEY_ENV = "JERICHO_MANCER_API_KEY"

# Default models (can be overridden per council member)
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_MANCER_MODEL = "nothingiisreal/MN-12B-Celeste-V1.9"

# API retry settings
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 2.0
API_TIMEOUT_SECONDS = 120

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

# ─── Proposal Settings ─────────────────────────────────────────
PROPOSAL_STATUSES = ("draft", "open", "under_review", "decided", "withdrawn")
PROPOSAL_CATEGORIES = ("character", "governance", "ethics", "expansion", "general")
REVIEW_STANCES = ("support", "oppose", "neutral")

# ─── Discussion Settings ──────────────────────────────────────
DEFAULT_DISCUSSION_ROUNDS = 2      # Default rounds per discussion
MAX_DISCUSSION_ROUNDS = 10         # Upper limit to prevent runaway discussions

# ─── Character Template Settings ──────────────────────────────
CHARACTER_STATUSES = ("draft", "active", "archived", "superseded")
CHARACTER_REQUIRED_TRAIT_TYPES = ("personality", "values", "flaws")
