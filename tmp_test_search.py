import json, urllib.request

url = 'http://127.0.0.1:8000/knowledge/search'
for q in ['锂电池', 'solid electrolyte']:
    data = json.dumps({'query': q, 'limit': 5}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        resp = urllib.request.urlopen(req, timeout=120).read().decode()
        obj = json.loads(resp)
        print(f'--- {q} ---')
        print(f"count: {obj.get('count')}")
        for p in obj.get('papers', [])[:3]:
            title = p.get('title', '')[:60]
            print(f"  source={p.get('source')} year={p.get('year')} title={title}")
    except Exception as e:
        print(f'--- {q} --- error: {e}')
