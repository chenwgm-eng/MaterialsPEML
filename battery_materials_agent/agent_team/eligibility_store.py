"""Tool Eligibility Rule Store — PostgreSQL 持久化。"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from ..db import get_engine
from .models import ToolEligibilityRule


_ALL_PROFILES = ["standard", "internlm_assisted", "committee_governed"]
_ASSISTED_PROFILES = ["internlm_assisted", "committee_governed"]
_COMMITTEE_PROFILES = ["committee_governed"]


class EligibilityStore:
    """工具资格规则存储：PostgreSQL 持久化（agent_team.tool_eligibility_rules 表）。"""

    def __init__(self, db_path: str = "data/agent_team.db"):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def list_by_agent(self, agent_id: str) -> list[ToolEligibilityRule]:
        """返回指定 agent 的规则（含通配 agent_id='*' 的全局规则）。"""
        rules: list[ToolEligibilityRule] = []
        with self.engine.connect() as conn:
            cur = conn.execute(
                text("SELECT data FROM agent_team.tool_eligibility_rules "
                     "WHERE agent_id = :agent_id OR agent_id = '*' ORDER BY created_at ASC"),
                {"agent_id": agent_id},
            )
            for row in cur.fetchall():
                try:
                    data = row[0]
                    if isinstance(data, str):
                        rules.append(ToolEligibilityRule.model_validate_json(data))
                    else:
                        rules.append(ToolEligibilityRule.model_validate(data))
                except Exception:
                    continue
        return rules

    def list_by_capability(self, capability: str, profile: str) -> list[ToolEligibilityRule]:
        """返回指定能力 + profile 的规则。"""
        rules: list[ToolEligibilityRule] = []
        with self.engine.connect() as conn:
            cur = conn.execute(
                text("SELECT data FROM agent_team.tool_eligibility_rules "
                     "WHERE capability = :capability ORDER BY created_at ASC"),
                {"capability": capability},
            )
            for row in cur.fetchall():
                try:
                    data = row[0]
                    if isinstance(data, str):
                        rule = ToolEligibilityRule.model_validate_json(data)
                    else:
                        rule = ToolEligibilityRule.model_validate(data)
                except Exception:
                    continue
                if profile in rule.profiles:
                    rules.append(rule)
        return rules

    def create(self, rule: ToolEligibilityRule) -> str:
        """创建新规则，返回 rule_id。"""
        if not rule.rule_id:
            rule.rule_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO agent_team.tool_eligibility_rules (rule_id, agent_id, capability, data) "
                     "VALUES (:rule_id, :agent_id, :capability, CAST(:data AS JSONB))"),
                {
                    "rule_id": rule.rule_id, "agent_id": rule.agent_id,
                    "capability": rule.capability, "data": rule.model_dump_json(),
                },
            )
        return rule.rule_id

    def update(self, rule_id: str, rule: ToolEligibilityRule) -> bool:
        """更新规则。"""
        rule.rule_id = rule_id
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("UPDATE agent_team.tool_eligibility_rules SET agent_id = :agent_id, capability = :capability, data = CAST(:data AS JSONB) "
                     "WHERE rule_id = :rule_id"),
                {
                    "agent_id": rule.agent_id, "capability": rule.capability,
                    "data": rule.model_dump_json(), "rule_id": rule_id,
                },
            )
        return cur.rowcount > 0

    def delete(self, rule_id: str) -> bool:
        """删除规则。"""
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM agent_team.tool_eligibility_rules WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
        return cur.rowcount > 0

    def list_all(self) -> list[ToolEligibilityRule]:
        """返回所有规则。"""
        rules: list[ToolEligibilityRule] = []
        with self.engine.connect() as conn:
            cur = conn.execute(
                text("SELECT data FROM agent_team.tool_eligibility_rules ORDER BY created_at ASC")
            )
            for row in cur.fetchall():
                try:
                    data = row[0]
                    if isinstance(data, str):
                        rules.append(ToolEligibilityRule.model_validate_json(data))
                    else:
                        rules.append(ToolEligibilityRule.model_validate(data))
                except Exception:
                    continue
        return rules


def seed_default_eligibility_rules(store: EligibilityStore) -> None:
    """为 11 个默认能力创建种子工具资格规则（local-first + SCP fallback 链）。

    参考 V1.2.2 第 6.1 节。使用 agent_id='*' 表示规则对所有具备该能力的 agent 生效。
    幂等：已存在同 rule_id 的规则会被跳过。
    """
    existing = {r.rule_id for r in store.list_all()}
    defaults = [
        ToolEligibilityRule(
            rule_id="seed_structure_validation",
            agent_id="*",
            capability="structure_validation",
            profiles=list(_ALL_PROFILES),
            allowed_internal_tool_ids=["pymatgen", "rdkit"],
            preferred_binding_order=["local:pymatgen", "local:rdkit"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_compliance_screening",
            agent_id="*",
            capability="compliance_screening",
            profiles=list(_ALL_PROFILES),
            allowed_internal_tool_ids=["smarts_matcher", "reach_checker"],
            preferred_binding_order=[
                "local:smarts_matcher", "local:reach_checker",
                "scp:scp_scitool_chem", "scp:scp_origene_pubchem",
            ],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_property_prediction",
            agent_id="*",
            capability="property_prediction",
            profiles=list(_ALL_PROFILES),
            allowed_internal_tool_ids=["cgcnn", "m3gnet", "polymer_gnn"],
            preferred_binding_order=[
                "local:cgcnn", "local:m3gnet", "local:polymer_gnn",
                "scp:scp_scitool_mat",
            ],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_dft_verification",
            agent_id="*",
            capability="dft_verification",
            profiles=list(_ALL_PROFILES),
            allowed_internal_tool_ids=["ase", "pyscf", "dft_queue"],
            preferred_binding_order=["local:ase", "local:pyscf", "local:dft_queue"],
            max_risk_level="C",
            requires_provenance=True,
            requires_human_review=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_experiment_qc_lookup",
            agent_id="*",
            capability="experiment_qc_lookup",
            profiles=list(_ALL_PROFILES),
            allowed_internal_tool_ids=["lims", "eln", "qc_db"],
            preferred_binding_order=["local:lims", "local:eln", "local:qc_db"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_chemical_descriptors",
            agent_id="*",
            capability="chemical_descriptors",
            profiles=list(_ASSISTED_PROFILES),
            allowed_internal_tool_ids=["rdkit"],
            preferred_binding_order=["local:rdkit", "scp:scp_scitool_chem"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_compound_registry_lookup",
            agent_id="*",
            capability="compound_registry_lookup",
            profiles=list(_ASSISTED_PROFILES),
            allowed_internal_tool_ids=["local_cache"],
            preferred_binding_order=["local:local_cache", "scp:scp_origene_pubchem"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_material_reference_lookup",
            agent_id="*",
            capability="material_reference_lookup",
            profiles=list(_ASSISTED_PROFILES),
            allowed_internal_tool_ids=["materials_project"],
            preferred_binding_order=["local:materials_project", "scp:scp_scitool_mat"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_material_knowledge_query",
            agent_id="*",
            capability="material_knowledge_query",
            profiles=list(_ASSISTED_PROFILES),
            allowed_internal_tool_ids=["graph_store"],
            preferred_binding_order=["local:graph_store", "scp:scp_scigraph_material"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_reaction_engineering_check",
            agent_id="*",
            capability="reaction_engineering_check",
            profiles=list(_ASSISTED_PROFILES),
            allowed_internal_tool_ids=["local_formula"],
            preferred_binding_order=["local:local_formula", "scp:scp_chem_reaction"],
            max_risk_level="B",
            requires_provenance=True,
            fallback_action="local_fallback",
        ),
        ToolEligibilityRule(
            rule_id="seed_bioactivity_risk_lookup",
            agent_id="*",
            capability="bioactivity_risk_lookup",
            profiles=list(_COMMITTEE_PROFILES),
            allowed_internal_tool_ids=[],
            preferred_binding_order=["scp:scp_origene_chembl"],
            max_risk_level="D",
            requires_provenance=True,
            requires_human_review=True,
            fallback_action="request_evidence",
        ),
    ]
    for rule in defaults:
        if rule.rule_id not in existing:
            store.create(rule)
