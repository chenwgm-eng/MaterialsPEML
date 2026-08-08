"""领域包流水线与金发科技领域包落库。

背景：
1. 0045 迁移建立的 battery 领域包 data 中缺少 "pipeline" 段，导致从数据库
   读取领域包时无法驱动可插拔流水线（仅代码内置兜底有该段）。本迁移为库中
   battery 记录补上 pipeline 段（与代码内置 BUILTIN_PIPELINES 保持一致）。
2. 落库金发科技（kingfa）领域包作为跨材料领域的演示对象，演示新型材料企业
   （改性塑料/聚合物复合材料）无需改动代码即可通过领域包接入研发流水线。

Revision ID: 0046_domain_pack_pipeline_kingfa
Revises: 0045_domain_packs
Create Date: 2026-08-07
"""
from __future__ import annotations

import json

from alembic import op


revision = "0046_domain_pack_pipeline_kingfa"
down_revision = "0045_domain_packs"
branch_labels = None
depends_on = None


# —— 与代码内置 BUILTIN_PIPELINES 一致的三分支默认流水线 ——
_BUILTIN_PIPELINES = {
    "crystal": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_crystal_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "predict_crystal_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "verify_dft", "agent_role": "doer", "autonomy_level": "L1", "when": "requires_dft"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
    "polymer": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "predict_polymer_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
    "molecule": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "check_synthesis_feasibility", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "predict_crystal_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
}


# —— 金发科技（kingfa）领域包 ——
# 金发科技主营改性塑料/聚合物复合材料（聚丙烯、汽车材料、阻燃材料、生物降解
# 材料、高性能尼龙等）。其研发核心是"配方共混 + 性能预测 + 合规"，而非晶体
# 离子电导率优化。此领域包演示新增一家材料企业时，仅新增一条记录即可接入。
_KINGFA_DOMAIN = {
    "material_representation": "formula",
    "recipe_templates": [
        {
            "material_type": "BASE_POLYMER",
            "main_ratio": 0.85,
            "additives": [
                {"category": "FILLER", "ratio": 0.08},
                {"category": "FLAME_RETARDANT", "ratio": 0.05},
                {"category": "STABILIZER", "ratio": 0.02},
            ],
            "equipment": "双螺杆挤出机",
            "bop": [
                {"step": "预混", "temperature": 60, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
                {"step": "螺杆共混挤出", "temperature": 230, "duration_min": 15, "rpm": 400, "equipment": "双螺杆挤出机"},
                {"step": "水冷造粒", "temperature": 25, "duration_min": 10, "rpm": 0, "equipment": "水冷造粒机"},
                {"step": "干燥", "temperature": 90, "duration_min": 240, "rpm": 0, "equipment": "鼓风干燥箱"},
            ],
        },
        {
            "material_type": "*",
            "main_ratio": 0.85,
            "additives": [
                {"category": "FILLER", "ratio": 0.1},
                {"category": "STABILIZER", "ratio": 0.05},
            ],
            "equipment": "双螺杆挤出机",
            "bop": [
                {"step": "预混", "temperature": 60, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
                {"step": "螺杆共混挤出", "temperature": 230, "duration_min": 15, "rpm": 400, "equipment": "双螺杆挤出机"},
                {"step": "水冷造粒", "temperature": 25, "duration_min": 10, "rpm": 0, "equipment": "水冷造粒机"},
            ],
        },
    ],
    "fallback_recipe": {
        "bom": {"BASE_POLYMER": 0.85, "FILLER": 0.1, "STABILIZER": 0.05},
        "equipment": "双螺杆挤出机",
        "bop": [
            {"step": "预混", "temperature": 60, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
            {"step": "螺杆共混挤出", "temperature": 230, "duration_min": 15, "rpm": 400, "equipment": "双螺杆挤出机"},
            {"step": "水冷造粒", "temperature": 25, "duration_min": 10, "rpm": 0, "equipment": "水冷造粒机"},
        ],
    },
    "consistency": {
        "polymer_kw": ["peo", "polymer", "pvdf", "pp", "pa6", "pa66", "abs", "pc",
                       "pbt", "pet", "pla", "pbat", "pp", "psmiles", "[*]"],
        "crystal_kw": [],
    },
    "default_target_properties": ["tensile_strength", "flexural_modulus", "flame_retardancy", "thermal_stability"],
    "example_formulas": ["PP/GF30", "PA6/GF20", "PLA/PBAT", "PC/ABS"],
    # 体系模板：聚合物共混研发场景的推荐体系（含重心元素集合），供前端
    # 候选生成/性质预测页的体系下拉使用，使金发领域完全驱动体系模板。
    "material_systems": [
        {"name": "聚丙烯改性体系", "elements": ["C", "H"]},
        {"name": "尼龙增强体系", "elements": ["C", "H", "O", "N"]},
        {"name": "汽车用工程塑料", "elements": ["C", "H", "O", "N", "Cl"]},
        {"name": "阻燃聚合物体系", "elements": ["C", "H", "O", "N", "P", "Cl", "Br"]},
        {"name": "生物降解材料体系", "elements": ["C", "H", "O", "N"]},
    ],
    "industry": "改性塑料/聚合物复合材料",
    # 金发专属流水线：基于聚合物共混场景定制，route→候选→配方→预测→合规
    "pipeline": {
        "polymer": [
            {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
            {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
            {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
            {"action": "predict_polymer_properties", "agent_role": "doer", "autonomy_level": "L1"},
            {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
        ],
        "*": [
            {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
            {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
            {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
            {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
        ],
    },
}


def _js(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).replace("'", "''")


def upgrade() -> None:
    # 1. 为库中 battery 领域包补充 pipeline 段（仅当缺失时写入，避免覆盖用户定制）
    op.execute(
        f"""
        UPDATE industrialization.domain_packs
        SET data = data || '{{"pipeline": {_js(_BUILTIN_PIPELINES)}}}'::jsonb,
            updated_at = NOW()
        WHERE domain_key = 'battery'
          AND NOT (data ? 'pipeline')
        """
    )
    # 2. 落库金发科技领域包
    op.execute(
        """
        INSERT INTO industrialization.domain_packs
        (domain_key, name, description, material_representation, data, is_active)
        VALUES
        ('kingfa', '金发科技（改性塑料）',
         '金发科技改性塑料/聚合物复合材料领域包：配方共混研发流水线',
         'formula',
        """ + f"'{_js(_KINGFA_DOMAIN)}'::jsonb, TRUE)"
        + """
        ON CONFLICT (domain_key) DO UPDATE SET
            name=EXCLUDED.name,
            description=EXCLUDED.description,
            material_representation=EXCLUDED.material_representation,
            data=EXCLUDED.data,
            is_active=EXCLUDED.is_active,
            updated_at=NOW()
        """
    )


def downgrade() -> None:
    # 移除金发科技领域包；battery 的 pipeline 段保留（不破坏 0045 落下数据）
    op.execute("DELETE FROM industrialization.domain_packs WHERE domain_key = 'kingfa'")