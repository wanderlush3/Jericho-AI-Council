"""
split_css.py — Split monolithic style.css into focused module files under css/.

Sections are grouped into logical modules by feature area.
The original style.css is replaced with @import directives.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "core" / "web_static" / "style.css"
CSS_DIR = ROOT / "core" / "web_static" / "css"
BACKUP = ROOT / "core" / "web_static" / "style_original.css"

content = SRC.read_text(encoding="utf-8")
lines = content.splitlines(keepends=True)
total = len(lines)

# Backup
BACKUP.write_text(content, encoding="utf-8")
print(f"Backed up {total} lines to {BACKUP.name}")

# ── Define extraction groups ──────────────────────────────
# Each tuple: (filename, start_comment_substring, end_before_comment_substring)
# We'll use the section marker text found in the analysis

# Instead of brittle substring matching, define by line ranges.
# Based on css_analysis.txt section markers:
MODULES = [
    # (output_filename, start_line_inclusive, end_line_inclusive)
    ("tokens.css",      1,    77),    # @import + design tokens (:root) + font import
    ("base.css",       78,   112),    # Reset & base
    ("layout.css",    113,   296),    # Layout + sidebar + sidebar accordion
    ("content.css",   297,   346),    # Main content area
    ("cards.css",     322,   419),    # Cards + stat cards  (overlaps with content, adjust)
    ("badges.css",    420,   573),    # Status badges
    ("council.css",   574,   758),    # Member grid + member detail
    ("tables.css",    759,   839),    # Data table + approval bar
    ("characters.css", 840, 1003),    # Character cards + creation form
    ("locations.css", 1004, 1132),    # Location cards
    ("filters.css",   1133, 1178),    # Filters bar
    ("analytics.css", 1179, 1303),    # Analytics
    ("votes.css",     1264, 1320),    # Vote detail (overlaps; adjust)  
    ("utilities.css", 1304, 1401),    # Empty state, loading, back button, table wrapper, responsive
    ("animations.css",1392, 1401),    # Animations (small)
    ("settings.css",  1402, 1680),    # Settings page
    ("toast.css",     1638, 1748),    # Toast notifications + utility states (overlap; adjust)
    ("chat.css",      1749, 2330),    # Chat view + chat detail + multi-member
    ("forms.css",     2331, 2623),    # Editable form layout + read-only fields + save bar + avatar
    ("proposals.css", 2624, 3001),    # Proposal form/lifecycle/actions/discussion/votes
    ("memories.css",  3002, 3686),    # Memory explorer
    ("promote.css",   3687, 3847),    # Promote to council modal
    ("skins.css",     3848, 4768),    # Settings skins + Frutiger Aero + Vaporwave + skin overrides
    ("treasury.css",  4529, 5022),    # Treasury (obelisk) + store section (overlap; adjust)
    ("store.css",     5023, 5332),    # Store form components
    ("themes.css",    5333, 5514),    # Skin: Frutiger Aero + Vaporwave (theme-specific)
    ("comfyui.css",   5515, 6260),    # ComfyUI templates, generation settings
    ("images.css",    6261, 6679),    # Lightbox, upload modal, responsive, gallery
    ("generation.css",6680, 7119),    # Progress bar, responsive, generation UI, presets
    ("explore.css",   7120, 7795),    # Explore grid/hero/scenes/navigation/participants
    ("stories.css",   7796, 8524),    # Stories UI: list/detail/chapters/scenes/reader
    ("evolutions.css",8525, 9013),    # Evolutions overlay/badges/lifecycle/modals
]

# Clean up overlaps — use non-overlapping ranges
# Re-define with exact non-overlapping ranges

MODULES_CLEAN = [
    ("tokens.css",      1,    77),
    ("base.css",       78,   112),
    ("layout.css",    113,   296),
    ("content.css",   297,   321),
    ("cards.css",     322,   419),
    ("badges.css",    420,   573),
    ("council.css",   574,   758),
    ("tables.css",    759,   839),
    ("characters.css", 840, 1003),
    ("locations.css", 1004, 1132),
    ("filters.css",   1133, 1178),
    ("analytics.css", 1179, 1263),
    ("votes.css",     1264, 1303),
    ("utilities.css", 1304, 1391),
    ("animations.css",1392, 1401),
    ("settings.css",  1402, 1637),
    ("toast.css",     1638, 1680),
    ("states.css",    1681, 1748),
    ("chat.css",      1749, 2330),
    ("forms.css",     2331, 2623),
    ("proposals.css", 2624, 3001),
    ("memories.css",  3002, 3686),
    ("promote.css",   3687, 3847),
    ("skins.css",     3848, 4528),
    ("treasury.css",  4529, 5022),
    ("store.css",     5023, 5332),
    ("themes.css",    5333, 5514),
    ("comfyui.css",   5515, 6260),
    ("images.css",    6261, 6679),
    ("generation.css",6680, 7119),
    ("explore.css",   7120, 7795),
    ("stories.css",   7796, 8524),
    ("evolutions.css",8525, 9013),
]

# Verify coverage
covered = set()
for name, start, end in MODULES_CLEAN:
    for i in range(start, end + 1):
        if i in covered:
            print(f"WARNING: Line {i} covered by multiple modules (second: {name})")
        covered.add(i)

missing = set(range(1, total + 1)) - covered  
if missing:
    print(f"WARNING: {len(missing)} lines not covered: {sorted(missing)[:20]}...")
else:
    print(f"All {total} lines covered by {len(MODULES_CLEAN)} modules")

# Create output directory
CSS_DIR.mkdir(parents=True, exist_ok=True)

# Extract each module
for filename, start, end in MODULES_CLEAN:
    chunk = lines[start - 1 : end]  # Convert from 1-indexed
    out_path = CSS_DIR / filename
    out_path.write_text("".join(chunk), encoding="utf-8")
    print(f"  {filename:20s} -> {len(chunk):5d} lines (L{start}-L{end})")

# Build the new root style.css with @import directives
header = """\
/* ═══════════════════════════════════════════════════════════════
   Jericho Dashboard — Root Stylesheet
   
   All styles are modularised into css/*.css files.
   Edit individual modules rather than this aggregator.
   ═══════════════════════════════════════════════════════════════ */

"""
imports = "\n".join(
    f'@import url("css/{fname}");'
    for fname, _, _ in MODULES_CLEAN
)

SRC.write_text(header + imports + "\n", encoding="utf-8")
print(f"\nNew style.css written with {len(MODULES_CLEAN)} @import directives")
print("Done!")
