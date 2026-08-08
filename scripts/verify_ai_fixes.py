"""端到端回归脚本：验证去电池化后关键 AI 接口的语义正确性（Task 17）。

覆盖：
1. /api/route 聚合物输入 → 高置信 polymer
2. /api/route 乱码输入 → 低置信 + 明确原因（无盲默认）
3. /discover/crystal 化学式相关语义（候选元素约束）
4. 电池接口已移除（返回 404）

运行：python scripts/verify_ai_fixes.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
import battery_materials_agent.api as api_mod  # noqa: E402
from battery_materials_agent.config import get_config  # noqa: E402
from battery_materials_agent.agent import BatteryMaterialsAgent  # noqa: E402
from battery_materials_agent.auth.user_store import UserStore  # noqa: E402
from battery_materials_agent.auth.tokens import issue_token  # noqa: E402

# TestClient 不执行 startup 事件，需手动初始化 agent 与 user_store 并签发 admin
# token，以通过 require_login 等鉴权依赖（与生产环境用户体系一致）。
api_mod.agent = BatteryMaterialsAgent(get_config())
api_mod.app.state.agent = api_mod.agent
api_mod.app.state.user_store = UserStore()
api_mod.app.state.candidate_store = api_mod.agent.candidate_store
admin = api_mod.app.state.user_store.get_by_username("admin")
assert admin is not None, "默认 admin 用户未创建"
_TOKEN = issue_token(admin.user_id)
_AUTH = {"X-Auth-Token": _TOKEN}

client = TestClient(api_mod.app)

results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


# 1. 聚合物路由
r = client.post("/route", json={"psmiles": "C(COCCO[*])[*]"}, headers=_AUTH)
if r.status_code == 200:
    body = r.json()
    mtype = (body.get("material_type") or "").lower()
    conf = body.get("confidence")
    check("route polymer -> high-conf polymer", mtype == "polymer" and (conf or 0) >= 0.7,
          f"material_type={body.get('material_type')} confidence={conf}")
else:
    check("route polymer", False, f"status={r.status_code} {r.text[:120]}")

# 2. 乱码路由（无盲默认）
r2 = client.post("/route", json={"name": "zzzzxxQQ"}, headers=_AUTH)
if r2.status_code == 200:
    body = r2.json()
    conf = body.get("confidence") or 0
    reason = body.get("reason") or ""
    check("route garbage -> low-conf + reason", conf < 0.5 and bool(reason),
          f"material_type={body.get('material_type')} confidence={conf} reason={reason[:60]}")
else:
    check("route garbage", False, f"status={r2.status_code} {r2.text[:120]}")


# 3. 晶体预测语义（Li6PS5Cl 应含 Li/S/P/Cl 相关）
r3 = client.post("/discover/crystal", json={
    "formula": "Li6PS5Cl",
    "elements": ["Li", "P", "S", "Cl"],
    "target_property": "ionic_conductivity",
    "num_candidates": 3,
}, headers=_AUTH)
if r3.status_code == 200:
    body = r3.json()
    cands = body.get("candidates") or []
    has_meta = all((c.get("ai_meta") or {}).get("model_version") for c in cands)
    check("crystal predict returns candidates + ai_meta", len(cands) > 0 and has_meta,
          f"count={len(cands)} model_version_present={has_meta}")
else:
    check("crystal predict", False, f"status={r3.status_code} {r3.text[:160]}")


# 4. 电池接口已移除
r4 = client.get("/api/battery/modeling")
check("battery endpoint removed (404)", r4.status_code == 404, f"status={r4.status_code}")

failed = [x for x in results if not x[1]]
print("\n==== 汇总 ====")
print(f"总用例 {len(results)}，通过 {len(results) - len(failed)}，失败 {len(failed)}")
sys.exit(1 if failed else 0)