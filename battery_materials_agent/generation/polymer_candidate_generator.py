"""Polymer candidate generation using LLM APIs and rule-based molecular design."""

from __future__ import annotations
from pydantic import BaseModel, Field
import asyncio
import json
import hashlib
import re
import uuid
import logging

import httpx

from ..config import AgentConfig, EngineMode, LLMConfig, InternLMConfig
from ..llm.schemas import ChatMessage, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

# 聚合物 LLM 生成调用整体超时（秒），需小于前端 axios 默认 15s
POLYMER_LLM_TIMEOUT = 10.0


class PolymerCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: f"CAND-{uuid.uuid4().hex[:8].upper()}")
    name: str
    psmiles: str = ""
    smiles: str = ""
    monomer_smiles: list[str] = Field(default_factory=list)
    source: str = ""
    description: str = ""
    predicted_ionic_conductivity: float = 0.0
    molecular_weight: float = 0.0
    multi_objective_score: float = 0.0  # 多目标加权综合评分（0-1）
    provenance: list[dict] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)  # 扩展领域数据（工程塑料配方/增强方案等）


# 聚合物属性提取器与方向（与晶体保持一致语义，仅支持可计算字段）
# v4.1 改性塑料：工程塑料候选属性存于 data（字段名与全链路 tensile_strength 等一致）
_POLY_PROPERTY_GETTERS = {
    "ionic_conductivity": lambda c: c.predicted_ionic_conductivity,
    "molecular_weight": lambda c: c.molecular_weight,
    "tensile_strength": lambda c: float((c.data or {}).get("tensile_strength") or 0.0),
    "flexural_modulus": lambda c: float((c.data or {}).get("flexural_modulus") or 0.0),
    "impact_strength": lambda c: float((c.data or {}).get("impact_strength") or 0.0),
    "heat_deflection_temp": lambda c: float((c.data or {}).get("heat_deflection_temp") or 0.0),
    "melt_flow_index": lambda c: float((c.data or {}).get("melt_flow_index") or 0.0),
    "elongation_at_break": lambda c: float((c.data or {}).get("elongation_at_break") or 0.0),
    "thermal_stability": lambda c: float((c.data or {}).get("thermal_stability") or 0.0),
    "glass_transition_temp": lambda c: float((c.data or {}).get("glass_transition_temp") or 0.0),
}
_POLY_PROPERTY_DIRECTION = {
    "ionic_conductivity": "maximize",
    "molecular_weight": "minimize",  # 通常希望分子量适中偏小以利加工
    "tensile_strength": "maximize",
    "flexural_modulus": "maximize",
    "impact_strength": "maximize",
    "heat_deflection_temp": "maximize",
    "melt_flow_index": "maximize",
    "elongation_at_break": "maximize",
    "thermal_stability": "maximize",
    "glass_transition_temp": "maximize",
}

# 电池时代属性集（走电解质 KNOWN_POLYMERS 通道），其余高分子目标走工程塑料模式
_BATTERY_POLYMER_PROPS = {"ionic_conductivity", "molecular_weight"}


def _is_engineering_target(dict_props: dict | None) -> bool:
    """判断目标是否属于高分子工程性能（非电池电解质属性）。"""
    if not dict_props:
        return True
    t = dict_props.get("target_property") or ""
    if t and t not in _BATTERY_POLYMER_PROPS:
        return True
    props = dict_props.get("properties") or []
    if isinstance(props, list):
        for p in props:
            key = (p or {}).get("property") or (p or {}).get("target_property") or ""
            if key and key not in _BATTERY_POLYMER_PROPS:
                return True
    return False


def _apply_polymer_multi_objective(
    candidates: list[PolymerCandidate],
    target_properties: list[dict],
) -> list[PolymerCandidate]:
    """聚合物多目标加权评分（与晶体 _apply_multi_objective 同算法）。

    v4.1（ADR-0003）：归一化采用**绝对规格基准**（material_properties.REFERENCE_RANGES），
    与后端补算 `_backfill_multi_objective_scores` 同源，分数跨列表/轮次可比。
    """
    from ..material_properties import REFERENCE_RANGES

    if not candidates:
        return candidates

    configs = []
    for tp in target_properties:
        prop = tp.get("property") or tp.get("target_property") or ""
        if not prop or prop not in _POLY_PROPERTY_GETTERS:
            continue
        weight = float(tp.get("weight", 1.0))
        direction = tp.get("direction") or _POLY_PROPERTY_DIRECTION.get(prop, "maximize")
        min_val = tp.get("min")
        max_val = tp.get("max")
        configs.append({
            "property": prop,
            "weight": max(weight, 0.0),
            "direction": direction,
            "min": float(min_val) if min_val is not None else None,
            "max": float(max_val) if max_val is not None else None,
        })

    if not configs:
        return candidates

    # 1. 约束过滤
    filtered = []
    for c in candidates:
        passed = True
        for cfg in configs:
            val = _POLY_PROPERTY_GETTERS[cfg["property"]](c)
            if cfg["min"] is not None and val < cfg["min"]:
                passed = False
                break
            if cfg["max"] is not None and val > cfg["max"]:
                passed = False
                break
        if passed:
            filtered.append(c)

    if not filtered:
        return filtered

    # 2. 绝对规格基准归一化 + 加权求和（ADR-0003）
    total_weight = sum(cfg["weight"] for cfg in configs) or 1.0
    for cfg in configs:
        ref = REFERENCE_RANGES.get(cfg["property"])
        for c in filtered:
            v = _POLY_PROPERTY_GETTERS[cfg["property"]](c)
            if ref is not None:
                lo, hi, _unit, _src = ref
                rng = (hi - lo) if hi > lo else 1.0
                normalized = max(0.0, min(1.0, (v - lo) / rng))
            else:
                # 无参考范围的属性回退池内相对
                vals = [_POLY_PROPERTY_GETTERS[cfg["property"]](x) for x in filtered]
                v_min, v_max = min(vals), max(vals)
                rng = (v_max - v_min) if v_max > v_min else 1.0
                normalized = (v - v_min) / rng
            if cfg["direction"] == "minimize":
                normalized = 1.0 - normalized
            c.multi_objective_score += (cfg["weight"] / total_weight) * normalized

    filtered.sort(key=lambda c: c.multi_objective_score, reverse=True)
    return filtered


class PolymerDesignRules:
    """Rule-based polymer electrolyte design knowledge base."""

    BACKBONE_MOTIFS = [
        ("Poly(ethylene oxide)", "[*]CCO[*]", "CCO", "PEO", "High Li+ solvation via ether oxygen"),
        ("Poly(propylene oxide)", "[*]CC(C)O[*]", "CC(C)O", "PPO", "Methyl side chain reduces crystallinity"),
        ("Poly(vinyl alcohol)", "[*]CC(O)[*]", "CC(O)", "PVA", "Hydroxyl groups for H-bonding"),
        ("Poly(acrylonitrile)", "[*]CCC#N[*]", "C=CC#N", "PAN", "Nitrile group for high dielectric constant"),
        ("Poly(methyl methacrylate)", "[*]CC(C)(C(=O)OC)[*]", "CC(C)(C(=O)OC)", "PMMA", "Good mechanical stability"),
        ("Poly(vinylidene fluoride)", "[*]CC(F)(F)[*]", "C=C(F)F", "PVDF", "High dielectric constant, piezoelectric"),
        ("Poly(vinyl fluoride)", "[*]CCF[*]", "C=CF", "PVF", "Fluorinated backbone"),
        ("Poly(ethylene carbonate)", "[*]CCOC(=O)O[*]", "CCOC(=O)O", "PEC", "Cyclic carbonate for high conductivity"),
        ("Poly(propylene carbonate)", "[*]CC(C)OC(=O)O[*]", "CC(C)OC(=O)O", "PPC", "Biodegradable, good ion transport"),
        ("Poly(trimethylene carbonate)", "[*]CCCOC(=O)O[*]", "CCCOC(=O)O", "PTMC", "Flexible carbonate backbone"),
    ]

    SALT_ADDITIVES = [
        ("LiTFSI", "LiN(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F", "Lithium bis(trifluoromethanesulfonyl)imide"),
        ("LiFSI", "LiN(S(=O)(=O)C(F)F)S(=O)(=O)C(F)F", "Lithium bis(fluorosulfonyl)imide"),
        ("LiClO4", "[Li+].[O-]Cl(=O)(=O)=O", "Lithium perchlorate"),
        ("LiBF4", "[Li+].[F-]B(F)(F)F", "Lithium tetrafluoroborate"),
        ("LiPF6", "[Li+].[F-]P(F)(F)(F)(F)F", "Lithium hexafluorophosphate"),
        ("LiBOB", "[Li+].[O-]C(=O)C1([O-])CCC1", "Lithium bis(oxalate)borate"),
    ]

    FILLER_MOTIFS = [
        ("LLZO", "Li7La3Zr2O12", "Garnet-type ceramic filler"),
        ("LATP", "Li1.3Al0.3Ti1.7(PO4)3", "NASICON-type filler"),
        ("LLTO", "La0.5Li0.5TiO3", "Perovskite-type filler"),
        ("SiO2", "O=[Si]=O", "Silica nanoparticle"),
        ("Al2O3", "O=[Al]O[Al]=O", "Alumina nanoparticle"),
    ]

    # ── 工程塑料骨架库（kingfa 领域：改性塑料/工程塑料/生物降解塑料） ──
    ENGINEERING_PLASTICS = [
        ("Polypropylene", "PP", "[*]CC(C)[*]", "C=CC", "通用热塑性树脂，可增强/阻燃/耐候改性，典型拉伸强度 25-40 MPa"),
        ("Polyamide 6", "PA6", "[*]CCCCC(=O)N[*]", "C1CCCCC(=O)N1", "尼龙 6，玻纤增强后拉伸强度 120-180 MPa，耐磨耐油"),
        ("Polyamide 66", "PA66", "[*]CCCCC(=O)NCCCCCCN[*]", "NCCCCCCN.C(=O)CCCCC", "尼龙 66，尺寸稳定、耐热，HDT 180°C（GF 增强）"),
        ("Polycarbonate", "PC", "[*]OC(=O)OC1=CC=C(C(C)(C)C2=CC=C(OC(=O)O[*])C=C2)C=C1[*]", "O=C(OC1=CC=C(C(C)(C)C2=CC=C(O)C=C2)C=C1)O", "聚碳酸酯，透明高冲击，HDT 130°C"),
        ("Acrylonitrile-Butadiene-Styrene", "ABS", "[*]CC(C#N)[*]", "C=CC#N", "ABS 树脂，韧性好，PC/ABS 合金用于汽车内饰"),
        ("Polybutylene terephthalate", "PBT", "[*]O=C(OCCO)C1=CC=C(C(=O)O[*])C=C1[*]", "O=C(OCCO)C1=CC=C(C(=O)O)C=C1", "PBT 工程塑料，耐化学、尺寸稳定，GF 增强用于连接器"),
        ("Polyethylene terephthalate", "PET", "[*]O=C(OCC)C1=CC=C(C(=O)O[*])C=C1[*]", "O=C(OCCO)C1=CC=C(C(=O)O)C=C1", "PET 树脂，瓶级/膜级/纤维级"),
        ("Polylactic acid", "PLA", "[*]OC(=O)C(C)[*]", "CC(=O)O", "生物降解塑料，脆性高，常与 PBAT 共混增韧"),
        ("Poly(butylene adipate-co-terephthalate)", "PBAT", "[*]O=C(OCCO)C1=CC=C(C(=O)O[*])C=C1[*]", "O=C(OCCO)C1=CC=C(C(=O)O)C=C1", "生物降解共聚酯，柔韧性好，与 PLA 共混"),
        ("Liquid Crystal Polymer", "LCP", "[*]OC(=O)C1=CC=C(OC(=O)C2=CC=C(C(=O)O[*])C=C2)C=C1[*]", "O=C(OC1=CC=C(C(=O)O)C=C1)C1=CC=C(C(=O)O)C=C1", "液晶聚合物，耐高温高流动，用于 AI 服务器/高频连接器"),
        ("Polyphenylene sulfide", "PPS", "[*]C1=CC=C(S[*])C=C1[*]", "C1=CC=C(S)C=C1", "聚苯硫醚，耐高温耐化学，HDT >260°C"),
        ("Polyphenylsulfone", "PPSU", "[*]OC1=CC=C(S(=O)(=O)C2=CC=C(OC3=CC=C(S(=O)(=O)C4=CC=C(O[*])C=C4)C=C3)C=C2)C=C1[*]", "OC1=CC=C(S(=O)(=O)C2=CC=C(OC3=CC=C(S(=O)(=O)C4=CC=C(O)C=C4)C=C3)C=C2)C=C1", "聚苯砜，耐高温透明，医疗级"),
        ("Polyoxymethylene", "POM", "[*]CO[*]", "C=O", "聚甲醛，高刚性耐磨，齿轮/精密件"),
        ("High-density polyethylene", "HDPE", "[*]CCCC[*]", "C=C", "高密度聚乙烯，耐化学品"),
        ("Polystyrene", "PS", "[*]CC(C1=CC=CC=C1)[*]", "C=CC1=CC=CC=C1", "通用聚苯乙烯，透明脆性，HIPS 增韧改性"),
        ("High-impact polystyrene", "HIPS", "[*]CC(C1=CC=CC=C1)[*]", "C=CC1=CC=CC=C1", "高抗冲聚苯乙烯，家电/电子外壳"),
        ("Styrene-acrylonitrile", "SAN", "[*]CC(C#N)[*]", "C=CC#N", "苯乙烯-丙烯腈共聚，透明耐化学"),
        ("Recycled PET", "rPET", "[*]O=C(OCC)C1=CC=C(C(=O)O[*])C=C1[*]", "O=C(OCCO)C1=CC=C(C(=O)O)C=C1", "再生 PET（瓶片回收），rHDPE/rPET 梯级再生"),
        ("Epoxy resin", "EP", "[*]OCC1CO1[*]", "C1(CO1)CO", "环氧树脂基体，碳纤维/玻纤复合材料树脂基"),
        ("Polyether ether ketone", "PEEK", "[*]OC1=CC=C(C2=CC=C(OC3=CC=C(C(=O)C4=CC=C(O[*])C=C4)C=C3)C=C2)C=C1[*]", "OC1=CC=C(C2=CC=C(OC3=CC=C(C(=O)C4=CC=C(O)C=C4)C=C3)C=C2)C=C1", "聚醚醚酮，高性能热塑性，CF 增强用于低空经济/机器人"),
        ("Nafion", "Nafion", "[*]OC(F)(F)C(F)(F)OC(F)(F)C(F)(F)S(=O)(=O)O[*]", "O=S(=O)(O)C(F)(F)C(F)(F)OC(F)(F)C(F)(F)F", "全氟磺酸膜，PEM 燃料电池质子交换膜"),
        ("Polybenzimidazole", "PBI", "[*]C1=CC2=NC3=CC=CC=C3N=C2C=C1[*]", "C1=CC2=NC3=CC=CC=C3N=C2C=C1", "聚苯并咪唑，高温 PEM 膜（PBI/H3PO4 体系）"),
        ("Medical-grade PP", "Med-PP", "[*]CC(C)[*]", "C=CC", "医用级聚丙烯，熔喷级（MFR 800-1500）用于口罩/防护过滤层"),
    ]

    ENGINEERING_FILLERS = [
        ("GF30", "玻璃纤维增强 30%", "拉伸强度 ×2-3，HDT +80-100°C"),
        ("GF20", "玻璃纤维增强 20%", "强度与流动性平衡"),
        ("CF20", "碳纤维增强 20%", "高模量低密度，轻量化"),
        ("CF30", "碳纤维增强 30%", "高端结构件，航空航天/低空经济"),
        ("Talc20", "滑石粉填充 20%", "低成本刚性改善"),
        ("FR-APP", "聚磷酸铵阻燃剂", "磷系无卤阻燃，UL94 V-0"),
        ("FR-MCA", "三聚氰胺氰尿酸盐", "PA 用无卤阻燃"),
        ("POE-g-MAH", "马来酸酐接枝弹性体", "增韧改性"),
        ("Nano-CaCO3", "纳米碳酸钙", "增刚增韧"),
        ("Aramid-Fiber", "芳纶纤维", "高强高模，防刺/防护"),
        ("Graphene", "石墨烯填料", "导热导电增强"),
        ("H3PO4", "磷酸掺杂", "PBI 高温膜质子传导"),
    ]

    # ── 工程性能参考表（ADR-0003 / Q7 查表法） ──
    # 每项: (拉伸MPa, 弯曲模量MPa, 缺口冲击kJ/m², HDT°C)。GF 按 30% 玻纤、CF 按 20% 碳纤、
    # Talc 按 20% 填充的典型数据；无增强为纯料典型值。
    # 来源：CAMPUS 塑料数据库典型值；GB/T 1040-2006、GB/T 9341-2008、GB/T 1843-2008、
    # GB/T 1634-2019 参考区间；《工程塑料改性技术》（金发科技内部手册）。
    REFERENCE_PROPERTIES = {
        "PP":      {"T": 32, "F": 1400, "I": 4,  "H": 100},
        "PA6":     {"T": 60, "F": 2000, "I": 7,  "H": 130},
        "PA66":    {"T": 80, "F": 2400, "I": 6,  "H": 180},
        "PC":      {"T": 65, "F": 2200, "I": 12, "H": 130},
        "ABS":     {"T": 45, "F": 2000, "I": 18, "H": 95},
        "PBT":     {"T": 55, "F": 2300, "I": 5,  "H": 150},
        "PET":     {"T": 50, "F": 2400, "I": 4,  "H": 120},
        "PLA":     {"T": 55, "F": 3500, "I": 3,  "H": 60},
        "PBAT":    {"T": 32, "F": 300,  "I": 15, "H": 55},
        "LCP":     {"T": 130, "F": 10000, "I": 8, "H": 280},
        "PPS":     {"T": 75, "F": 3800, "I": 3,  "H": 240},
        "PPSU":    {"T": 70, "F": 2400, "I": 20, "H": 200},
        "POM":     {"T": 65, "F": 2600, "I": 6,  "H": 100},
        "HDPE":    {"T": 28, "F": 900,  "I": 8,  "H": 80},
        "PS":      {"T": 40, "F": 3000, "I": 2,  "H": 90},
        "HIPS":    {"T": 25, "F": 1800, "I": 8,  "H": 85},
        "SAN":     {"T": 70, "F": 3300, "I": 3,  "H": 100},
        "rPET":    {"T": 55, "F": 2400, "I": 4,  "H": 80},
        "EP":      {"T": 60, "F": 3000, "I": 6,  "H": 150},
        "PEEK":    {"T": 95, "F": 3800, "I": 8,  "H": 280},
        "Nafion":  {"T": 25, "F": 600,  "I": 15, "H": 120},
        "PBI":     {"T": 110, "F": 7000, "I": 2, "H": 260},
        "Med-PP":  {"T": 32, "F": 1400, "I": 4,  "H": 90},
    }
    # 增强加成（按骨架族 × 增强类型）。负值表示增强导致韧性/温度下降（脆化、无缺口失效）
    _ENHANCE_BONUS = {
        #  (T, F, I, H)
        "GF": {
            "PA":   (100, 4000, 8,  45),
            "PP":   (60,  2000, 2,  40),
            "PC":   (50,  5000, -4, 15),
            "ABS":  (45,  2500, -4, 15),
            "PBT":  (90,  5000, 5,  50),
            "PET":  (100, 6000, 4,  70),
            "PLA":  (60,  4000, 1,  45),
            "POM":  (40,  5000, 1,  60),
            "HDPE": (30,  1500, 2,  40),
            "PS":   (30,  3000, 0,  35),
            "HIPS": (20,  1500, 1,  25),
            "SAN":  (60,  4000, 1,  45),
            "rPET": (100, 6000, 4,  70),
            "EP":   (120, 8000, 6,  60),
            "PEEK": (80,  7000, 1,  45),
            "LCP":  (100, 5000, 3,  50),
            "PPS":  (100, 7000, 4,  60),
            "PPSU": (50,  3000, -3, 20),
            "POM ": (40,  5000, 1,  60),
            "*":    (60,  3500, 3,  40),
        },
        "CF": {
            "PA":   (80,  5000, 3,  40),
            "PP":   (50,  3000, 0,  30),
            "PC":   (40,  6000, -8, 10),
            "ABS":  (35,  3000, -8, 10),
            "PEEK": (70,  10000, -2, 30),
            "EP":   (120, 12000, 4,  40),
            "PPS":  (90,  9000, 0,  50),
            "*":    (50,  4500, -1, 25),
        },
        "Talc": {
            "*":    (10,  800,  -1, 5),
        },
    }

    def reference_properties(self, abbr: str, filler_name: str):
        """按骨架 × 增强查参考性能（查表法，Q7/ADR-0003）。

        返回 (tensile, flexural, impact, hdt, source)。查不到组合时保守回退：
        基材值 + 10% 幅度，绝不使用派生系数。
        """
        base = self.REFERENCE_PROPERTIES.get(abbr)
        if base is None:
            base = {"T": 50, "F": 2400, "I": 5, "H": 100}
            source = "通用工程塑料典型值（CAMPUS 数据库）"
        else:
            source = "CAMPUS 塑料数据库典型值 / GB-T 1040、9341、1843、1634 参考区间"
        # 增强类型识别
        fname = (filler_name or "").upper()
        if fname.startswith("GF"):
            kind, fill_desc = "GF", "30% 玻纤增强"
        elif fname.startswith("CF"):
            kind, fill_desc = "CF", "20% 碳纤增强"
        elif fname.startswith("TALC"):
            kind, fill_desc = "Talc", "20% 滑石粉填充"
        else:
            kind, fill_desc = "", ""
        if kind:
            # 按骨架族匹配（PA6/PA66/PA12 → PA 族），无族匹配用通配
            family = ""
            for fam in ("PA", "POM", "HDPE", "PPSU", "PEEK", "LCP", "PPS"):
                if abbr.startswith(fam) or abbr == fam:
                    family = fam
                    break
            table = self._ENHANCE_BONUS.get(kind, {})
            bonus = table.get(family) or table.get("*")
            if bonus:
                t_b, f_b, i_b, h_b = bonus
                base = {
                    "T": base["T"] + t_b,
                    "F": base["F"] + f_b,
                    "I": max(1, base["I"] + i_b),
                    "H": base["H"] + h_b,
                }
                source = f"CAMPUS 典型值 + {fill_desc}（{family or '通用'}族，GB-T 参考区间）"
        return base["T"], base["F"], base["I"], base["H"], source


class PolymerCandidateGenerator:
    """Generate polymer electrolyte candidates using LLM + rule-based design."""

    KNOWN_POLYMERS = [
        PolymerCandidate(
            name="Poly(ethylene oxide)", psmiles="Polymer([*]CCO[*])", smiles="CCO",
            monomer_smiles=["C(CO)O"], source="known",
            description="PEO-based SPE, widely studied for Li+ conduction",
            predicted_ionic_conductivity=1e-5,
        ),
        PolymerCandidate(
            name="Poly(vinylidene fluoride)", psmiles="Polymer([*]CC(F)(F)[*])", smiles="C=C(F)F",
            monomer_smiles=["C=C(F)F"], source="known",
            description="PVDF, high dielectric constant",
            predicted_ionic_conductivity=1e-7,
        ),
        PolymerCandidate(
            name="Poly(methyl methacrylate)", psmiles="Polymer([*]CC(C)(C(=O)OC)[*])", smiles="CC(C)(C(=O)OC)",
            monomer_smiles=["CC(C)(C(=O)OC)"], source="known",
            description="PMMA, good mechanical properties",
            predicted_ionic_conductivity=1e-8,
        ),
        PolymerCandidate(
            name="Polyacrylonitrile", psmiles="Polymer([*]CCC#N[*])", smiles="CC(C#N)",
            monomer_smiles=["C=CC#N"], source="known",
            description="PAN, good thermal stability",
            predicted_ionic_conductivity=1e-6,
        ),
        PolymerCandidate(
            name="Poly(propylene carbonate)", psmiles="Polymer([*]CC(C)OC(=O)O[*])", smiles="CC(C)OC(=O)O",
            monomer_smiles=["CC(C)OC(=O)O"], source="known",
            description="PPC, biodegradable SPE candidate",
            predicted_ionic_conductivity=5e-6,
        ),
    ]

    def __init__(
        self,
        config: AgentConfig | None = None,
        llm_api_key: str = "",
        llm_model: str = "LongCat-2.0",
        llm_base_url: str = "https://api.longcat.chat/openai",
        llm_max_tokens: int = 128000,
        llm_provider = None,
    ):
        # 保持旧的位置参数向后兼容：若第一个参数不是 AgentConfig 而是字符串 api_key
        if config is not None and not isinstance(config, AgentConfig):
            llm_api_key = config if isinstance(config, str) else llm_api_key
            config = None

        if config is None:
            config = AgentConfig(
                llm=LLMConfig(
                    api_key=llm_api_key,
                    model=llm_model,
                    base_url=llm_base_url,
                    max_tokens=llm_max_tokens,
                ),
                engine_mode=EngineMode.LEGACY,
            )

        self.config = config
        self._llm_provider = llm_provider
        # 为旧代码保留的属性（初始化后不再随热更新变化）
        self.llm_api_key = config.llm.api_key
        self.llm_model = config.llm.model
        self.llm_base_url = config.llm.base_url.rstrip("/")
        self.llm_max_tokens = config.llm.max_tokens
        self._rules = PolymerDesignRules()

    def generate(self, target_properties: dict | list | None = None,
                 num_candidates: int = 10,
                 material_system: str = "") -> list[PolymerCandidate]:
        # 多目标列表形式：先生成候选，再应用加权评分
        multi_obj_list: list[dict] | None = None
        dict_props: dict | None = None
        if isinstance(target_properties, list):
            multi_obj_list = target_properties if target_properties else None
            # 同时构造一个 dict 形式传给 LLM 作上下文
            dict_props = {"properties": target_properties} if target_properties else None
        else:
            dict_props = target_properties

        # kingfa/高分子研发领域：工程塑料骨架模式（改性塑料/工程塑料/生物降解等）
        # v4.1：material_system 非空 / 无目标 / 目标为高分子工程性能时走工程塑料模式，
        # 避免高分子任务回退到电池电解质候选（KNOWN_POLYMERS）
        if material_system or not dict_props or _is_engineering_target(dict_props):
            engineering = self._generate_engineering_plastics(
                num_candidates, material_system or "改性塑料")
            if engineering:
                if multi_obj_list:
                    engineering = _apply_polymer_multi_objective(engineering, multi_obj_list)
                return engineering

        if self.config.engine_mode == EngineMode.INTERNLM:
            try:
                candidates = self._run_llm_sync(self._generate_with_internlm_async, dict_props, num_candidates)
            except Exception as e:
                logger.warning("InternLM polymer generation failed: %s", e)
                candidates = []
        else:
            candidates = []

        if not candidates:
            candidates = list(self.KNOWN_POLYMERS)
            rule_based = self._generate_rule_based(num_candidates)
            candidates.extend(rule_based)
            if self.config.llm.api_key:
                try:
                    llm_generated = self._run_llm_sync(self._generate_with_llm_async, dict_props, num_candidates)
                    candidates.extend(llm_generated)
                except Exception as e:
                    logger.warning("LLM polymer generation failed: %s", e)

        seen = set()
        unique = []
        for c in candidates:
            key = c.psmiles or c.smiles
            if key not in seen:
                seen.add(key)
                unique.append(c)

        # 多目标加权评分（若启用）
        if multi_obj_list:
            unique = _apply_polymer_multi_objective(unique, multi_obj_list)

        return unique[:num_candidates]

    def _run_llm_sync(self, async_fn, *args):
        """在同步上下文中执行异步 LLM 调用，并强制整体超时。

        若当前已有运行中的事件循环（罕见），直接抛出异常交由上层回退。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            raise RuntimeError("cannot run LLM call from a running event loop")
        return asyncio.run(asyncio.wait_for(async_fn(*args), timeout=POLYMER_LLM_TIMEOUT))

    def generate_derivatives(self, base_polymer: PolymerCandidate, num_variants: int = 5) -> list[PolymerCandidate]:
        variants = []
        modifications = [
            ("with glass fiber", "GF30 玻纤增强"),
            ("with carbon fiber", "CF20 碳纤增强"),
            ("with flame retardant", "阻燃改性"),
            ("with impact modifier", "增韧改性"),
            ("with coupling agent", "偶联剂改性"),
        ]
        for suffix, desc in modifications[:num_variants]:
            variants.append(PolymerCandidate(
                name=f"{base_polymer.name} {suffix}",
                psmiles=base_polymer.psmiles,
                smiles=base_polymer.smiles,
                monomer_smiles=list(base_polymer.monomer_smiles),
                source="derivative",
                description=f"{base_polymer.description} - {desc}",
                data={
                    **(base_polymer.data or {}),
                    "tensile_strength": float(base_polymer.data.get("tensile_strength") or 50.0) + 30,
                },
            ))
        return variants

    def filter_by_rules(self, candidates: list[PolymerCandidate], rules: dict) -> list[PolymerCandidate]:
        filtered = []
        for c in candidates:
            if rules.get("max_molecular_weight") and c.molecular_weight > rules["max_molecular_weight"]:
                continue
            if rules.get("required_groups"):
                has_group = any(g.lower() in c.smiles.lower() for g in rules["required_groups"])
                if not has_group and rules.get("require_all", False):
                    continue
            filtered.append(c)
        return filtered

    def _generate_rule_based(self, num_candidates: int) -> list[PolymerCandidate]:
        candidates = []
        h = int(hashlib.sha256(b"rule_based").hexdigest()[:8], 16)

        for i, (name, psmiles, smiles, abbr, desc) in enumerate(self._rules.BACKBONE_MOTIFS):
            if len(candidates) >= num_candidates:
                break
            conductivity = 1e-6 * (((h >> (i * 2)) & 3) + 1)
            candidates.append(PolymerCandidate(
                name=name, psmiles=f"Polymer({psmiles})", smiles=smiles,
                monomer_smiles=[smiles], source="rule_based", description=desc,
                predicted_ionic_conductivity=conductivity,
            ))

        return candidates

    # ── 工程塑料候选生成（kingfa 领域：改性塑料/工程塑料/生物降解） ──
    def _generate_engineering_plastics(self, num_candidates: int,
                                       material_system: str = "") -> list[PolymerCandidate]:
        """基于工程塑料骨架库 + 增强/阻燃填料组合生成候选配方。

        支撑金发科技类高分子研发场景（PP/PA/PC/ABS 增强阻燃、PBAT/PLA 生物降解、
        LCP/PPS/PPSU 特种工程塑料）。按 material_system 关键词过滤骨架。
        """
        import hashlib as _h
        system = (material_system or "").lower()
        candidates: list[PolymerCandidate] = []
        h = int(_h.sha256(("eng_" + system).encode()).hexdigest()[:8], 16)

        def _match(item: tuple) -> bool:
            name, abbr, _psmiles, _smiles, desc = item
            if not system:
                return True
            hay = (name + " " + abbr + " " + desc).lower()
            # 词边界匹配缩写，避免 "pp" 误命中 "pps/ppsu"、"pa" 误命中 "pbat/pan"；
            # PA6/PA66/PBAT 等数字后缀缩写无天然词边界，需显式枚举
            has_pp = bool(re.search(r"\bpp\b|\bpp30\b|\bpp20\b", system))
            has_pa = bool(re.search(r"\bpa\b|\bpa6\b|\bpa66\b|\bpa12\b|\bpa46\b|\bpa610\b|\bpa1010\b", system))
            if "聚丙烯" in system or has_pp:
                # 医用级 PP 仅归属医疗/熔喷体系，避免混入通用聚丙烯改性
                if "medical-grade" in hay:
                    return "医疗" in system or "熔喷" in system or "防护" in system
                return "polypropylene" in hay or "poly(propylene" in hay or "pp" == abbr.lower()
            if "尼龙" in system or has_pa:
                return "polyamide" in hay
            if "苯乙烯" in system or "苯乙烯类" in system or "abs" in system:
                return any(k in hay for k in ("polystyrene", "hips", "styrene-acrylonitrile", "abs"))
            if "汽车" in system or "工程塑料" in system or "pc" in system:
                return any(k in hay for k in ("polycarbonate", "abs", "pbt", "pet", "pom", "polyphenylene sulfide", "peek"))
            if "阻燃" in system:
                return any(k in hay for k in ("polypropylene", "polyamide", "polycarbonate", "abs", "pbt"))
            if "生物降解" in system or bool(re.search(r"\bpbat\b|\bpla\b", system)):
                return any(k in hay for k in ("polylactic", "pbat", "poly(butylene"))
            if "特种" in system or "lcp" in system or "pps" in system:
                return any(k in hay for k in ("liquid crystal", "polyphenylene sulfide", "polyphenylsulfone", "peek"))
            if "碳纤维" in system or "复材" in system or "复合材料" in system:
                return any(k in hay for k in ("epoxy", "peek", "polyphenylene sulfide"))
            if "氢" in system or "pem" in system or "膜" in system or "燃料电池" in system:
                return any(k in hay for k in ("nafion", "polybenzimidazole"))
            if "医疗" in system or "熔喷" in system or "防护" in system:
                return "medical-grade" in hay or "polypropylene" in hay
            if "再生" in system or "回收" in system or "recycl" in system:
                return "recycled" in hay or "high-density polyethylene" in hay
            return True

        pool = [p for p in self._rules.ENGINEERING_PLASTICS if _match(p)]
        if not pool:
            pool = list(self._rules.ENGINEERING_PLASTICS)

        filler_pool = list(self._rules.ENGINEERING_FILLERS)
        for i, (name, abbr, psmiles, smiles, desc) in enumerate(pool):
            if len(candidates) >= num_candidates:
                break
            # i ≥ 11 时移位会溢出 32 位哈希（恒 0 导致全部同一填料），改用加法扰动
            filler = filler_pool[(h + i * 7) % len(filler_pool)]
            fname, fdesc, feffect = filler
            # 体系适配：生物降解避开玻纤/碳纤（破坏可降解性）
            if "生物降解" in system and "GF" in fname:
                filler = ("POE-g-MAH", "马来酸酐接枝弹性体", "增韧改性")
                fname, fdesc, feffect = filler
            # 医疗/熔喷体系：无增强填料，保持熔喷级纯度
            if ("医疗" in system or "熔喷" in system) and ("GF" in fname or "CF" in fname or "Talc" in fname):
                filler = ("Graphene", "石墨烯填料", "导热导电增强")
                fname, fdesc, feffect = filler
            # 氢能源膜体系：质子传导掺杂（磷酸）
            if ("氢" in system or "pem" in system) and "Nafion" not in fname:
                filler = ("H3PO4", "磷酸掺杂", "PBI 高温膜质子传导")
                fname, fdesc, feffect = filler
            # 碳纤维复材体系：以碳纤维增强为默认
            if ("碳纤维" in system or "复材" in system or "复合材料" in system) and not fname.startswith("CF"):
                filler = ("CF30", "碳纤维增强 30%", "高端结构件，航空航天/低空经济")
                fname, fdesc, feffect = filler
            # ── 工程性能查表（ADR-0003 配套：绝对规格基准同源） ──
            # 参考来源：CAMPUS 塑料数据库典型值 / GB-T 1040、GB-T 9341、GB-T 1843、GB-T 1634
            # 参考区间；GF/CF 加成按 30%/20% 填充的行业典型数据（《工程塑料改性技术》金发科技内部手册）
            # 查询失败时保守回退（基材值 + 10%），杜绝派生系数
            est_tensile, est_flexural, est_impact, est_hdt, est_source = self._rules.reference_properties(
                abbr, fname
            )
            candidates.append(PolymerCandidate(
                name=f"{abbr}/{fname}",
                psmiles=f"Polymer({psmiles})",
                smiles=smiles,
                monomer_smiles=[smiles],
                source="engineering_plastics",
                description=f"{desc}。改性方案：{fname}（{fdesc}，{feffect}）。",
                predicted_ionic_conductivity=0.0,
                data={
                    "formula": f"{abbr}/{fname}",
                    "material_system": material_system or "改性塑料",
                    "tensile_strength": est_tensile,
                    "flexural_modulus": est_flexural,
                    "impact_strength": est_impact,
                    "heat_deflection_temp": est_hdt,
                    "property_source": est_source,
                    "reinforcement": fname,
                    "process": "双螺杆挤出共混 → 注塑/挤出成型",
                },
            ))
        return candidates

    async def _generate_with_llm_async(self, target_properties: dict | None, num_candidates: int) -> list[PolymerCandidate]:
        if not self.config.llm.api_key:
            return []

        prompt = self._build_generation_prompt(target_properties)
        try:
            import httpx
            # base_url may or may not include /v1; build the chat completions endpoint
            base_url = self.config.llm.base_url.rstrip("/")
            if "/v1" not in base_url:
                endpoint = f"{base_url}/v1/chat/completions"
            else:
                endpoint = f"{base_url}/chat/completions"
            # Cap response tokens to keep prompt responses small
            response_max_tokens = min(2000, self.config.llm.max_tokens)
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.config.llm.api_key}"},
                    json={
                        "model": self.config.llm.model,
                        "messages": [
                            {"role": "system", "content": "You are a polymer compounding scientist specializing in engineering plastics and polymer modification (PP/PA/PC/ABS/PBAT compounding, reinforcement and flame retardancy)."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": self.config.llm.temperature,
                        "max_tokens": response_max_tokens,
                    },
                )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return self._parse_llm_response(content, num_candidates)
        except Exception:
            pass

        return []

    async def _generate_with_internlm_async(self, target_properties: dict | None, num_candidates: int) -> list[PolymerCandidate]:
        """Use the InternLM provider to generate polymer candidates."""
        provider = self._llm_provider
        provider_created_locally = False
        if provider is None:
            from ..llm.factory import ProviderFactory
            provider = ProviderFactory.create(self.config)
            provider_created_locally = True

        try:
            prompt = f"""Generate {num_candidates} polymer compounding candidates for plastic modification (reinforced/flame-retardant/biodegradable systems) with target properties: {target_properties}
Return only a JSON list of objects with keys: name, smiles, psmiles, properties (dict).
Example: [{{"name": "PEO", "smiles": "CCO", "psmiles": "[*]CCO[*]", "properties": {{"ionic_conductivity": 1e-5}}}}]"""

            request = ChatRequest(
                model=self.config.internlm.model,
                messages=[
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=0.7,
                max_tokens=4096,
            )
            response = await provider.complete(request)
            content = response.content
            items = self._extract_json_list(content)
            if not items:
                raise ValueError("InternLM returned empty candidate list")

            candidates = []
            for item in items[:num_candidates]:
                props = item.get("properties", {}) or {}
                candidates.append(PolymerCandidate(
                    name=item.get("name", "Unknown"),
                    psmiles=item.get("psmiles", ""),
                    smiles=item.get("smiles", ""),
                    source="internlm_generated",
                    description=item.get("description", ""),
                    predicted_ionic_conductivity=props.get("ionic_conductivity", 0.0),
                ))

            if len(candidates) < num_candidates:
                remaining = num_candidates - len(candidates)
                candidates.extend(await self._generate_with_llm_async(target_properties, remaining))

            return candidates
        finally:
            if provider_created_locally:
                close_fn = getattr(provider, "close", None)
                if close_fn is not None:
                    try:
                        await close_fn()
                    except Exception as close_err:
                        logger.warning("Failed to close temporary LLM provider: %s", close_err)

    def _build_generation_prompt(self, target_properties: dict | None) -> str:
        props_str = json.dumps(target_properties or {"tensile_strength": "high"}, indent=2)
        return f"""Generate novel engineering plastic compounding candidates for polymer modification (reinforced / flame-retardant / impact-modified systems).

Target properties:
{props_str}

For each candidate, provide:
1. Name
2. PSMILES notation
3. SMILES of monomer
4. Brief description of the compounding design rationale (base resin + reinforcement/modifier)

Focus on systems such as:
- Glass/carbon fiber reinforced PP/PA/PC/ABS/PBT
- Flame retardant systems (halogen-free, V-0)
- Impact-modified alloys (PC/ABS, PA/POE)
- High heat deflection temperature engineering plastics

Return as JSON array with fields: name, psmiles, smiles, description"""

    def _parse_llm_response(self, content: str, num_candidates: int) -> list[PolymerCandidate]:
        try:
            json_match = content[content.index("["):content.rindex("]")+1]
            data = json.loads(json_match)
            candidates = []
            for item in data[:num_candidates]:
                candidates.append(PolymerCandidate(
                    name=item.get("name", "Unknown"),
                    psmiles=item.get("psmiles", ""),
                    smiles=item.get("smiles", ""),
                    source="llm_generated",
                    description=item.get("description", ""),
                ))
            return candidates
        except Exception as e:
            logger.warning("LLM response parse failed: %s", e)
            return []

    def _extract_json_list(self, text: str) -> list[dict]:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception:
            pass

        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            data = json.loads(text[start:end])
            if isinstance(data, list):
                return data
        except Exception:
            pass

        return []
