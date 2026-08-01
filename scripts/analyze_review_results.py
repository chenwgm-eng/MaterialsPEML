"""Analyze backend review API results."""
from __future__ import annotations

import json
from collections import Counter

path = r"d:\BattleFish\BatteryEMCL Lab\doc\review_backend_api_results.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

calls = data["calls"]
print(f"Total calls: {len(calls)}")
print(f"Generated at: {data['generated_at']}")
print(f"State keys: {list(data['state'].keys())}")
print()

# Status code distribution
codes = Counter(c["status_code"] for c in calls)
print("Status code distribution:")
for code, count in sorted(codes.items(), key=lambda x: (x[0] is None, x[0])):
    print(f"  {code}: {count}")
print()

# By module
modules = {}
for c in calls:
    modules.setdefault(c["module"], []).append(c)
print("By module:")
for mod, cs in sorted(modules.items()):
    mod_codes = Counter(x["status_code"] for x in cs)
    fails = [x for x in cs if x["status_code"] not in (200, 201, 204, 401, 409) and x["status_code"] is not None]
    print(f"  {mod}: {len(cs)} calls, codes={dict(mod_codes)}, failures={len(fails)}")
print()

# List all failures and timeouts
print("Failures/timeouts (status not 2xx and not expected 401/409):")
for c in calls:
    sc = c["status_code"]
    if sc is None or sc >= 400:
        if sc in (401, 409):
            continue
        print(f"  {c['id']} {c['module']} {c['method']} {c['path']} -> {sc} | {c['description']}")
        if c["error"]:
            print(f"      error: {c['error'][:200]}")
        print(f"      summary: {c['response_summary'][:220]}")
