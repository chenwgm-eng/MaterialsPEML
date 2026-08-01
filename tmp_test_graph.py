import json, urllib.request

# search
url = 'http://127.0.0.1:8000/knowledge/search'
q = 'solid electrolyte'
data = json.dumps({'query': q, 'limit': 5}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=120).read().decode()
obj = json.loads(resp)
papers = obj.get('papers', [])
print(f"papers: {len(papers)}")

# build graph
url2 = 'http://127.0.0.1:8000/knowledge/graph'
data2 = json.dumps({'papers': papers}).encode()
req2 = urllib.request.Request(url2, data=data2, headers={'Content-Type': 'application/json'}, method='POST')
resp2 = urllib.request.urlopen(req2, timeout=120).read().decode()
obj2 = json.loads(resp2)
print(f"nodes: {len(obj2.get('nodes', []))}, edges: {len(obj2.get('edges', []))}")
for n in obj2.get('nodes', [])[:3]:
    print(json.dumps({k: n.get(k) for k in ['id', 'label', 'type', 'properties']}, ensure_ascii=False))
