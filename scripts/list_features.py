import json

with open("features.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# data might be a list directly
features = data if isinstance(data, list) else data.get("features", [])

for feat in features:
    deps = ", ".join(feat.get("dependencies", [])) if feat.get("dependencies") else ""
    dep_str = f"  deps=[{deps}]" if deps else ""
    print(f"{feat['id']:8s} [{feat['status']:10s}] {feat['title']}{dep_str}")
