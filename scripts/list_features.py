import json

with open("features.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Handle both list and dict formats
features = data if isinstance(data, list) else data.get("features", [])

for feat in features:
    fid = feat["id"]
    status = feat["status"]
    title = feat.get("title", "")
    deps = feat.get("dependencies", [])
    dep_str = ", ".join(deps) if deps else ""
    print(f"{fid:8s} {status:12s} {title:60s} deps=[{dep_str}]")
