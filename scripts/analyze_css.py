"""
split_css.py — Split monolithic style.css into focused modules under css/.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "core" / "web_static" / "style.css"
CSS_DIR = ROOT / "core" / "web_static" / "css"
BACKUP = ROOT / "core" / "web_static" / "style_original.css"

content = SRC.read_text(encoding="utf-8")
lines = content.splitlines(keepends=True)

# Backup
BACKUP.write_text(content, encoding="utf-8")

# Find section boundaries by scanning for comment markers
# The CSS uses patterns like:
# /* ─── Section Name ─── */
# or multi-line comment blocks
section_markers = []
for i, line in enumerate(lines):
    stripped = line.strip()
    # Detect section headers with Unicode box-drawing chars or repeated dashes
    if stripped.startswith("/*") and (
        "\u2500" in stripped or  # ─ (box-drawing)
        "---" in stripped or
        "===" in stripped or
        "Section" in stripped
    ):
        section_markers.append((i+1, stripped[:100]))

# Write analysis
out = ROOT / "scripts" / "css_analysis.txt"
with open(out, "w", encoding="utf-8") as f:
    f.write(f"Total lines: {len(lines)}\n")
    f.write(f"Section markers found: {len(section_markers)}\n\n")
    for ln, text in section_markers:
        f.write(f"  {ln:5d}: {text}\n")
    
    # Also find @import, :root, and major selectors
    f.write("\n\nKey structures:\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("@import"):
            f.write(f"  {i+1:5d}: {stripped[:100]}\n")
        elif ":root" in stripped and "{" in stripped:
            f.write(f"  {i+1:5d}: {stripped[:100]}\n")
        elif stripped.startswith("/*") and len(stripped) > 30:
            f.write(f"  {i+1:5d}: {stripped[:100]}\n")

print(f"Analysis written to {out}")
print(f"File has {len(lines)} lines")
