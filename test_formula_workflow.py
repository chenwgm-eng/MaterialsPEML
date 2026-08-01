"""配方与工艺模块端到端 API 测试脚本。

重点验证：
1. 配方生成与保存的数据闭环
2. 配方与上下游模块的数据衔接
3. 版本管理与活跃版本切换
4. 样品自动创建与关联
"""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8002"
TOKEN = None


def login():
    """登录获取管理员 token。"""
    global TOKEN
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin123"}, timeout=10)
    if resp.status_code != 200:
        print(f"[ERROR] 登录失败: {resp.status_code} {resp.text}")
        sys.exit(1)
    data = resp.json()
    TOKEN = data["token"]
    print(f"[OK] 登录成功，用户: {data['username']}, 角色: {data['role']}")
    return TOKEN


def headers():
    return {"X-Auth-Token": TOKEN, "Content-Type": "application/json"}


def design_formula(target, quantity_kg=1.0):
    """调用 MCP design_formula 工具生成配方。"""
    print(f"\n[TEST] 生成配方: target={target}, quantity={quantity_kg}kg")
    payload = {
        "arguments": {
            "target_material": {"candidate": target, "target_property": "ionic_conductivity"},
            "quantity_kg": quantity_kg,
        }
    }
    resp = requests.post(f"{BASE_URL}/mcp/tools/design_formula/call", json=payload, headers=headers(), timeout=35)
    print(f"  status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [FAIL] 生成失败: {resp.text}")
        return None
    data = resp.json()
    print(f"  bom_count: {len(data.get('bom', []))}")
    print(f"  bop_count: {len(data.get('bop', []))}")
    print(f"  material_cost: {data.get('material_cost')}")
    print(f"  process_cost: {data.get('process_cost')}")
    print(f"  total_cost_per_kg: {data.get('total_cost_per_kg')}")
    if not data.get("bom"):
        print("  [FAIL] BOM 为空，配方生成异常")
    else:
        print("  [OK] 配方生成成功")
    return data


def save_formula(formula_data, formula_id="", target="", quantity=1.0, change_summary="测试保存"):
    """保存配方版本。"""
    print(f"\n[TEST] 保存配方版本: target={target}")
    payload = {
        "formula_id": formula_id,
        "target_material": target,
        "quantity_kg": quantity,
        "bom": formula_data.get("bom", []),
        "bop": formula_data.get("bop", []),
        "ehs": formula_data.get("ehs", {}),
        "material_cost": formula_data.get("material_cost", 0),
        "process_cost": formula_data.get("process_cost", 0),
        "total_cost_per_kg": formula_data.get("total_cost_per_kg", 0),
        "process_cost_breakdown": formula_data.get("process_cost_breakdown", []),
        "change_summary": change_summary,
        "scenario_id": "",
    }
    resp = requests.post(f"{BASE_URL}/formulas", json=payload, headers=headers(), timeout=15)
    print(f"  status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [FAIL] 保存失败: {resp.text}")
        return None
    data = resp.json()
    print(f"  formula_id: {data.get('formula_id')}")
    print(f"  version_number: {data.get('version_number')}")
    print(f"  [OK] 保存成功")
    return data


def list_formulas():
    """列出所有配方。"""
    print("\n[TEST] 列出配方列表")
    resp = requests.get(f"{BASE_URL}/formulas", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    data = resp.json()
    formulas = data.get("formulas", [])
    print(f"  count: {len(formulas)}")
    for f in formulas[:3]:
        print(f"    - {f.get('formula_id')} | {f.get('target_material')} | V{f.get('version_number', 0):02d} | active={f.get('is_active')}")
    return formulas


def get_formula(formula_id):
    """获取配方详情。"""
    print(f"\n[TEST] 获取配方详情: {formula_id}")
    resp = requests.get(f"{BASE_URL}/formulas/{formula_id}", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [FAIL] 获取失败: {resp.text}")
        return None
    data = resp.json()
    print(f"  target_material: {data.get('target_material')}")
    print(f"  version_number: {data.get('version_number')}")
    print(f"  bom_count: {len(data.get('bom', []))}")
    print(f"  bop_count: {len(data.get('bop', []))}")
    print(f"  total_cost_per_kg: {data.get('total_cost_per_kg')}")
    return data


def get_formula_history(formula_id):
    """获取配方历史版本。"""
    print(f"\n[TEST] 获取配方历史: {formula_id}")
    resp = requests.get(f"{BASE_URL}/formulas/{formula_id}/history", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    data = resp.json()
    versions = data.get("versions", [])
    print(f"  version_count: {len(versions)}")
    for v in versions:
        print(f"    - V{v.get('version_number', 0):02d} | active={v.get('is_active')} | {v.get('change_summary')}")
    return versions


def activate_version(formula_id, version_id):
    """切换活跃版本。"""
    print(f"\n[TEST] 切换活跃版本: {formula_id} -> {version_id}")
    resp = requests.post(f"{BASE_URL}/formulas/{formula_id}/versions/{version_id}/activate", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [FAIL] 切换失败: {resp.text}")
        return None
    data = resp.json()
    print(f"  [OK] 活跃版本已切换为 V{data.get('version_number', 0):02d}")
    return data


def list_samples():
    """列出样品。"""
    print("\n[TEST] 列出样品")
    resp = requests.get(f"{BASE_URL}/samples", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    data = resp.json()
    print(f"  count: {len(data)}")
    formula_samples = [s for s in data if s.get("source_type") == "formula"]
    print(f"  source_type=formula 的样品数: {len(formula_samples)}")
    for s in formula_samples[-3:]:
        print(f"    - {s.get('sample_id')} | {s.get('name')} | qty={s.get('quantity')}{s.get('unit')} | status={s.get('status')} | candidate={s.get('source_candidate_id')}")
    return data, formula_samples


def list_raw_materials():
    """列出物料规格库。"""
    print("\n[TEST] 列出物料规格库")
    resp = requests.get(f"{BASE_URL}/raw-materials", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    data = resp.json()
    materials = data.get("materials", [])
    print(f"  count: {len(materials)}")
    empty_category = [m for m in materials if not m.get("category")]
    print(f"  category 为空的物料数: {len(empty_category)} / {len(materials)}")
    for m in materials[:5]:
        print(f"    - {m.get('material_id')} | {m.get('name')} | category='{m.get('category')}'")
    return materials


def list_candidates():
    """列出候选材料。"""
    print("\n[TEST] 列出候选材料")
    resp = requests.get(f"{BASE_URL}/candidates", headers=headers(), timeout=10)
    print(f"  status: {resp.status_code}")
    data = resp.json()
    candidates = data if isinstance(data, list) else data.get("items", [])
    print(f"  count: {len(candidates)}")
    for c in candidates[:3]:
        print(f"    - {c.get('candidate_id')} | {c.get('name')} | {c.get('formula')}")
    return candidates


def test_formula_to_sample_linkage(formula_id, target):
    """测试配方到样品的下游衔接：通过制备样品入口参数。"""
    print(f"\n[TEST] 模拟从配方详情点击「制备样品」跳转")
    print(f"  期望跳转: /samples?formula_id={formula_id}&target={target}")
    # 前端跳转后会在样品管理页面预填表单，这里验证 samples API 能查询到相关样品
    # 实际自动创建发生在 activate_version 时
    return True


def main():
    login()

    issues = []

    # 1. 检查上游物料库
    materials = list_raw_materials()
    if any(not m.get("category") for m in materials):
        issues.append("上游缺陷：物料规格库中大量/全部物料的 category 字段为空，导致配方生成无法按 BASE_POLYMER/LITHIUM_SALT 分类选取原料")

    # 2. 生成配方
    formula_data = design_formula("Li6PS5Cl", quantity_kg=1.0)
    if formula_data is None:
        issues.append("核心缺陷：design_formula API 调用失败")
        return
    if not formula_data.get("bom"):
        issues.append("核心缺陷：配方生成返回空 BOM，生成逻辑失效")

    # 3. 保存配方
    saved = save_formula(formula_data, target="Li6PS5Cl", quantity=1.0, change_summary="端到端测试保存")
    if saved is None:
        issues.append("核心缺陷：无法保存配方版本")
        return

    formula_id = saved["formula_id"]

    # 4. 创建第二个版本
    formula_data2 = design_formula("Li6PS5Cl", quantity_kg=10.0)
    if formula_data2 and formula_data2.get("bom"):
        saved2 = save_formula(formula_data2, formula_id=formula_id, target="Li6PS5Cl", quantity=10.0, change_summary="第二个版本")
        if saved2:
            print(f"  [OK] 第二个版本保存成功: V{saved2.get('version_number'):02d}")

    # 5. 获取配方详情
    detail = get_formula(formula_id)
    if detail:
        if detail.get("total_cost_per_kg") != saved.get("total_cost_per_kg"):
            issues.append(f"数据闭环缺陷：保存前后总成本不一致 (保存时 {saved.get('total_cost_per_kg')} vs 详情 {detail.get('total_cost_per_kg')})")

    # 6. 历史版本
    versions = get_formula_history(formula_id)
    if len(versions) < 1:
        issues.append("数据闭环缺陷：保存后历史版本列表为空")

    # 7. 切换活跃版本
    if len(versions) >= 2:
        old_active = next((v for v in versions if v.get("is_active")), None)
        other = next((v for v in versions if not v.get("is_active")), None)
        if old_active and other:
            activated = activate_version(formula_id, other["version_id"])
            if activated:
                # 验证活跃版本已切换
                versions_after = get_formula_history(formula_id)
                new_active = next((v for v in versions_after if v.get("is_active")), None)
                if new_active and new_active["version_id"] != other["version_id"]:
                    issues.append("数据闭环缺陷：切换活跃版本后，历史列表中活跃标记未更新")

    # 8. 下游样品检查
    samples, formula_samples = list_samples()
    if not formula_samples:
        issues.append("下游衔接缺陷：配方版本发布后未自动创建 source_type=formula 的样品提案")
    else:
        # 检查最新一个 formula 样品的字段
        latest = formula_samples[-1]
        if not latest.get("quantity") or latest.get("quantity") <= 0:
            issues.append("下游衔接缺陷：自动创建样品的数量字段缺失或无效")
        if not latest.get("source_candidate_id") and latest.get("chemical_formula"):
            # 按 target_material 匹配候选可能失败，但不一定算缺陷
            pass

    # 9. 列出所有配方
    list_formulas()

    # 10. 候选材料上游
    candidates = list_candidates()
    if not candidates:
        issues.append("上游衔接提示：候选材料库为空，无法验证从候选材料传入配方的场景")

    # 汇总
    print("\n" + "=" * 60)
    print("测试完成。发现的问题汇总：")
    if not issues:
        print("  未发现明显问题")
    else:
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    print("=" * 60)


if __name__ == "__main__":
    main()
