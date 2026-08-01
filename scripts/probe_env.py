import requests
import json

BASE = 'http://localhost:8000'
r = requests.post(f'{BASE}/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']
h = {'X-Auth-Token': token}
c = requests.get(f'{BASE}/candidates', headers=h, timeout=10).json()
first = None
if isinstance(c, dict) and c.get('candidates'):
    first = c['candidates'][0]
elif isinstance(c, list) and c:
    first = c[0]
print('First candidate:')
print(json.dumps(first, indent=2, ensure_ascii=False))
print()
# Find candidate without release_card_required
items = c.get('candidates', []) if isinstance(c, dict) else c
print('Candidates without release_card_required:')
for item in items[:10]:
    data = item.get('data', {})
    if not data.get('release_card_required'):
        print(json.dumps(item, indent=2, ensure_ascii=False))
        break
print()
e = requests.get(f'{BASE}/mdm/equipment-templates', headers=h, timeout=10).json()
print('Equipment templates:')
print(json.dumps(e, indent=2, ensure_ascii=False)[:800])
