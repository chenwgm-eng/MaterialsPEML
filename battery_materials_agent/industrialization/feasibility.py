"""工业可行性筛选 - 替代原 Industrialize 步骤的二元判断。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any
import logging

from .raw_material_db import RawMaterialDB
from .compliance_checker import ComplianceAndCostNode

logger = logging.getLogger(__name__)


class FeasibilityRisk(BaseModel):
    """风险项。"""
    risk_type: str  # supplier_single_source / cost_uncertainty / ehs / compliance / equipment / supply_chain
    severity: str  # low / medium / high
    mitigation: str = ""


class IndustrialFeasibilityResult(BaseModel):
    """工业可行性筛选结果。"""
    status: str  # PASS / PASS_WITH_RISKS / REVIEW / BLOCK
    feasibility_score: float = 0.0  # 0-100
    hard_blockers: list[str] = Field(default_factory=list)
    risks: list[FeasibilityRisk] = Field(default_factory=list)
    cost_estimate: float = 0.0  # 0727b：估算成本（货币+单位由上下文决定）
    compliance_status: str = "pass"  # pass / review / block
    equipment_fit: str = "pass"  # pass / requires_new_equipment
    candidate_enhancements: dict[str, Any] = Field(default_factory=dict)


class IndustrialFeasibilityScreening:
    """工业可行性筛选服务 - 先验约束 + 可行性评分。"""

    def __init__(self, raw_material_db: RawMaterialDB, compliance_node: ComplianceAndCostNode, config=None):
        self.db = raw_material_db
        self.compliance_node = compliance_node
        self.cost_threshold = 500.0
        if config is not None:
            self.cost_threshold = getattr(config, 'cost_threshold', 500.0)

    def screen(self, candidates: list[dict]) -> list[tuple[dict, IndustrialFeasibilityResult]]:
        """对候选列表执行工业化筛选，返回 (candidate, result) 对。"""
        results = []
        for candidate in candidates:
            result = self._screen_single(candidate)

            # 将筛选结果写入候选的增强字段
            if result.status == "BLOCK":
                candidate["reject_reasons"] = result.hard_blockers
            else:
                candidate["feasibility_score"] = result.feasibility_score
                candidate["feasibility_status"] = result.status
                candidate["estimated_cost"] = result.cost_estimate
                if result.risks:
                    candidate["feasibility_risks"] = [r.model_dump() for r in result.risks]

            results.append((candidate, result))
        return results

    def evaluate_single(self, candidate: dict) -> IndustrialFeasibilityResult:
        """对单个候选执行工业化可行性评估（公共方法）。

        与 _screen_single 的区别：本方法不修改 candidate 对象，
        仅返回评估结果。适用于批量预测等不需要副作用的场景。
        """
        return self._screen_single(candidate)

    def _screen_single(self, candidate: dict) -> IndustrialFeasibilityResult:
        """对单个候选执行工业化筛选。"""
        hard_blockers: list[str] = []
        risks: list[FeasibilityRisk] = []
        cost_estimate = 0.0

        # 1. 先验约束检查
        smiles = candidate.get("smiles") or candidate.get("psmiles") or ""
        formula = candidate.get("formula") or candidate.get("name") or ""

        # 检查 SMARTS 黑名单
        if smiles:
            rdkit_available = False
            try:
                from rdkit import Chem
                rdkit_available = True
            except ImportError:
                pass

            if rdkit_available:
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:
                    blacklist = self.compliance_node.blacklist_smarts
                    for smarts_pattern in blacklist:
                        pattern = Chem.MolFromSmarts(smarts_pattern)
                        if pattern and mol.HasSubstructMatch(pattern):
                            hard_blockers.append(f"候选含禁用结构：{smarts_pattern}")

        # 2. 成本估算
        candidate_cost = candidate.get("estimated_cost", 0.0)
        if candidate_cost > 0:
            cost_estimate = candidate_cost
        elif smiles:
            # 尝试从物料库查找相似物料估算成本
            try:
                substitutes = self.db.find_substitutes(smiles, threshold=0.3)
                if substitutes:
                    cost_estimate = substitutes[0].unit_cost
            except Exception:
                pass

        if cost_estimate > self.cost_threshold * 3:
            hard_blockers.append(f"成本超目标 3 倍：估算 {cost_estimate:.2f} 元/kg")
        elif cost_estimate > self.cost_threshold:
            risks.append(FeasibilityRisk(
                risk_type="cost_uncertainty",
                severity="medium",
                mitigation="建议采购询价确认实际成本",
            ))

        # 3. 物料可得性
        material_available = False
        if smiles:
            try:
                substitutes = self.db.find_substitutes(smiles, threshold=0.3)
                if substitutes:
                    material_available = True
                    if len(substitutes) == 1:
                        risks.append(FeasibilityRisk(
                            risk_type="supplier_single_source",
                            severity="medium",
                            mitigation="开发第二供应商",
                        ))
            except Exception:
                pass

        if not material_available and smiles:
            risks.append(FeasibilityRisk(
                risk_type="supply_chain",
                severity="high",
                mitigation="物料库中无匹配替代材料，需开发供应商",
            ))

        # 4. 合规检查
        compliance_status = "pass"
        try:
            # 用 compliance_node 检查（如果有 BOM）
            bom = candidate.get("industrial_recipe", {}).get("bom", {})
            if bom:
                # 将 candidate 中的 bom 转为 dict 格式
                if isinstance(bom, list):
                    bom_dict = {item.get("material_name", f"item_{i}"): item.get("mass_fraction", 0) for i, item in enumerate(bom)}
                else:
                    bom_dict = bom
                report = self.compliance_node.evaluate(bom_dict)
                if not report.is_passed:
                    hard_blockers.extend(report.fatal_errors)
                    compliance_status = "block"
                if report.warnings:
                    compliance_status = "review" if compliance_status != "block" else "block"
        except Exception as e:
            logger.warning("Compliance check failed: %s", e)

        # 5. 计算可行性评分
        score = 100.0
        if hard_blockers:
            score = 0.0
        else:
            # 扣分项
            if not material_available and smiles:
                score -= 30
            if cost_estimate > self.cost_threshold:
                score -= 20
            if compliance_status == "review":
                score -= 15
            for risk in risks:
                if risk.severity == "high":
                    score -= 15
                elif risk.severity == "medium":
                    score -= 8
                elif risk.severity == "low":
                    score -= 3
            score = max(0.0, min(100.0, score))

        # 6. 确定状态
        if hard_blockers:
            status = "BLOCK"
        elif score >= 70:
            status = "PASS"
        elif score >= 50:
            status = "PASS_WITH_RISKS"
        else:
            status = "REVIEW"

        return IndustrialFeasibilityResult(
            status=status,
            feasibility_score=score,
            hard_blockers=hard_blockers,
            risks=risks,
            cost_estimate=cost_estimate,
            compliance_status=compliance_status,
            equipment_fit="pass",
        )
