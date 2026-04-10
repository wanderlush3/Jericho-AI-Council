"""
split_js.py - Split monolithic app.js into focused module files under js/.

All functions remain global (no ES module import/export).
index.html will load them via <script> tags in dependency order.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "core" / "web_static" / "app.js"
JS_DIR = ROOT / "core" / "web_static" / "js"
BACKUP = ROOT / "core" / "web_static" / "app_original.js"

content = SRC.read_text(encoding="utf-8")
lines = content.splitlines(keepends=True)
total = len(lines)

# Backup
BACKUP.write_text(content, encoding="utf-8")
print(f"Backed up {total} lines to {BACKUP.name}")

# Define extraction groups (filename, start_line, end_line) - 1-indexed, inclusive
MODULES = [
    # Core utilities - must load first (skinning, API, navigation, helpers)
    ("core.js",            1,   354),
    # Dashboard
    ("dashboard.js",     355,   629),
    # Council (members grid, detail, promote, avatar editor)
    ("council.js",       630,  1162),
    # Proposals (list, detail, discussion, category fields, handoffs)
    ("proposals.js",    1163,  2735),
    # Votes
    ("votes.js",        2736,  2866),
    # Image Gallery (gallery, lightbox, upload)
    ("gallery.js",      2867,  3153),
    # Generation (generate modal, SSE progress, poll)
    ("generation.js",   3154,  3704),
    # Explore (explore grid, location detail, look-around, scenes, participants)
    ("explore.js",      3705,  4202),
    # Characters (list, detail, CRUD, traits, avatar)
    ("characters.js",   4203,  5012),
    # Locations
    ("locations.js",    5013,  5342),
    # Items
    ("items.js",        5343,  5777),
    # Stores
    ("stores.js",       5778,  6387),
    # Analytics
    ("analytics.js",    6388,  6461),
    # Chat
    ("chat.js",         6462,  7169),
    # Settings (model options + basic settings)
    ("settings.js",     7170,  7553),
    # Memories
    ("memories.js",     7554,  7866),
    # Treasury (nav counts + obelisk + treasury + taxation + transfers)
    ("treasury.js",     7867,  8396),
    # Evolutions (overlays, rollback, create, timelines)
    ("evolutions.js",   8397,  9190),
    # Sessions
    ("sessions.js",     9191,  9708),
    # Laws
    ("laws.js",         9709,  9947),
    # Settings Extended (ComfyUI config, templates, presets, skin selection)
    ("settings_comfyui.js", 9948, 10772),
    # Tasks
    ("tasks.js",       10773, 11101),
    # Generation Queue
    ("gen_queue.js",   11102, 11227),
    # Preset Editor
    ("presets.js",     11228, 11498),
    # Batch Generation
    ("batch_gen.js",   11499, 11679),
    # Stories
    ("stories.js",     11680, 12370),
]

# Verify coverage
covered = set()
for name, start, end in MODULES:
    for i in range(start, end + 1):
        if i in covered:
            print(f"WARNING: Line {i} covered by multiple modules (second: {name})")
        covered.add(i)

missing = set(range(1, total + 1)) - covered
if missing:
    print(f"WARNING: {len(missing)} lines not covered: {sorted(missing)[:20]}...")
else:
    print(f"All {total} lines covered by {len(MODULES)} modules")

# Create output directory
JS_DIR.mkdir(parents=True, exist_ok=True)

# Extract each module
for filename, start, end in MODULES:
    chunk = lines[start - 1 : end]
    out_path = JS_DIR / filename
    out_path.write_text("".join(chunk), encoding="utf-8")
    print(f"  {filename:25s} -> {len(chunk):5d} lines (L{start}-L{end})")

print(f"\nExtracted {len(MODULES)} JS modules to {JS_DIR}")
print("Done! Now update index.html to load these scripts.")
