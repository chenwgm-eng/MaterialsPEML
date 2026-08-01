import json, urllib.request

url = 'http://127.0.0.1:8000/knowledge/search'
q = '锂电池'
data = json.dumps({'query': q, 'limit': 3}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=120).read().decode()
obj = json.loads(resp)
print(f"query: {obj.get('query')}, count: {obj.get('count')}")
for p in obj.get('papers', [])[:3]:
    print(json.dumps({k: p.get(k) for k in ['title', 'year', 'source', 'score']}, ensure_ascii=False))
