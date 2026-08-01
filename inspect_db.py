import sqlite3
import json

DB = r'C:\Users\chenw\.local\share\mimocode\mimocode.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

# Get user messages from BatteryEMCL session
sid = 'ses_07bccd361ffelbALVyfwBEP9l0'
c.execute("""
    SELECT p.id, p.data
    FROM part p
    WHERE p.session_id = ?
    ORDER BY p.time_created
""", (sid,))

print("=== ALL PARTS FROM BATTERYEMCL SESSION ===")
for r in c.fetchall():
    data = json.loads(r[1])
    ptype = data.get('type', '?')
    tool = data.get('tool', None)
    synthetic = data.get('synthetic', False)
    text = data.get('text', '')
    inp = data.get('state', {}).get('input', {}) if 'state' in data else {}
    
    print(f"\n--- Part {r[0]} (type={ptype}, tool={tool}, synthetic={synthetic}) ---")
    if ptype == 'text' and not synthetic:
        print(f"  TEXT: {text[:1500]}")
    elif ptype == 'tool':
        inp_str = json.dumps(inp, ensure_ascii=False)[:500]
        print(f"  TOOL INPUT: {inp_str}")
    elif ptype == 'reasoning':
        print(f"  REASONING: {text[:500]}")

conn.close()
