import os

dirs = ["core", "config", "tests", "scripts"]
py_total = 0
for d in dirs:
    count = 0
    for r, _, fs in os.walk(d):
        if "__pycache__" in r:
            continue
        for f in fs:
            if f.endswith(".py"):
                try:
                    count += sum(1 for _ in open(os.path.join(r, f), encoding="utf-8", errors="ignore"))
                except Exception:
                    pass
    print(f"{d}: {count} lines Python")
    py_total += count

js_total = 0
css_total = 0
for r, _, fs in os.walk("core/web_static"):
    for f in fs:
        try:
            lines = sum(1 for _ in open(os.path.join(r, f), encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if f.endswith(".js"):
            js_total += lines
        elif f.endswith(".css"):
            css_total += lines

print(f"\nPython: {py_total}")
print(f"JavaScript: {js_total}")
print(f"CSS: {css_total}")
print(f"Grand Total: {py_total + js_total + css_total}")
