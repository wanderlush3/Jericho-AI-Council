import json

data = json.load(open('features.json', 'r', encoding='utf-8'))
if isinstance(data, list):
    features = data
else:
    features = data.get('features', data)

pending = []
for f in features:
    status = f['status']
    fid = f['id']
    title = f['title']
    print(f"{fid:8} {status:12} {title}")
    if status == 'pending':
        pending.append(f)

print("\n--- PENDING FEATURES ---")
for f in pending:
    deps = f.get('dependencies', [])
    dep_str = ', '.join(deps) if deps else 'none'
    print(f"{f['id']:8} {f['title']}")
    print(f"         deps: {dep_str}")
