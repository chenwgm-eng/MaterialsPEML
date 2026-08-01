"""材料信息查询客户端 — 封装已验证可用的 SCP server 28 工具。

基于实测（2026-07-28），server 28 (InternAgent) 以下工具真实可用：
- ChemicalStructureAnalyzer: 化合物名 → SMILES + 分子式 + 分子量
- MaterialCompositionAnalyzer: formula → 元素组成分析
- ComprehensiveMaterialAnalyzer: material_id → 综合材料信息（基础级，非 DFT）
- ElectronicPropertyCalculator: SMILES → 价电子数、partial charge（仅分子）
- MolecularDescriptorCalculator: SMILES → 高级分子描述符（logP、TPSA 等）

不在本适配器范围内（因实测不可用或能力未上线）：
- VASP / PySCF / M3GNet / LAMMPS（hub 未暴露）
- scp_query_MetaAnalysis / scp_wait_MetaAnalysis（实测故障）
- 晶体 DFT / 周期性计算（需专题正式上线）

所有方法返回结构化 dict，失败时返回 {"error": "..."} 而非抛异常，
便于 ECML 引擎在调用失败时优雅降级到 InternLM 预测。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# SCP server 28 (InternAgent) 的基础 URL
_SERVER_28_URL = "https://scp.intern-ai.org.cn/api/v1/mcp/28/InternAgent"
_SERVER_28_ID = "28"


class MaterialInfoClient:
    """已验证可用的 SCP 材料信息查询工具封装。

    所有方法为 async，调用 SCP server 28 的真实工具。
    失败时不抛异常，返回 {"error": "..."}，由上层决定降级策略。
    """

    def __init__(self, scp_client):
        """Args:
            scp_client: SCPClientPool 实例（已配置 API key + allowlist）
        """
        self._scp = scp_client

    # ── 候选材料信息补全 ────────────────────────────────────────────────

    async def enrich_candidate(
        self,
        *,
        formula: str = "",
        compound_name: str = "",
        smiles: str = "",
    ) -> dict:
        """补全候选材料的基础信息。

        依次尝试：
        1. 若有 compound_name → ChemicalStructureAnalyzer 获取 SMILES + 分子式 + 分子量
        2. 若有 formula → MaterialCompositionAnalyzer 获取元素组成
        3. 若有 SMILES → MolecularDescriptorCalculator 获取描述符
        4. 若有 formula → ComprehensiveMaterialAnalyzer 获取材料类别

        Returns:
            {
                "smiles": str,            # 若通过 ChemicalStructureAnalyzer 获取
                "molecular_weight": float,
                "molecular_formula": str,
                "composition": dict,      # 元素组成 {symbol: {atomic_number, atomic_mass, ...}}
                "material_class": str,    # "Compound" / "Element" 等
                "descriptors": dict,      # RDKit 描述符
                "source": "scp_server_28",
                "warnings": list[str],
            }
        """
        result: dict[str, Any] = {
            "smiles": smiles,
            "molecular_weight": None,
            "molecular_formula": formula,
            "composition": {},
            "material_class": "",
            "descriptors": {},
            "source": "scp_server_28",
            "warnings": [],
        }

        # 1. 化合物名 → SMILES + 分子量
        if compound_name and not smiles:
            r = await self._call("ChemicalStructureAnalyzer", {"compound_name": compound_name})
            if not r.get("error"):
                result["smiles"] = r.get("smiles", "")
                result["molecular_weight"] = r.get("molecular_weight")
                result["molecular_formula"] = r.get("molecular_formula", formula)
            else:
                result["warnings"].append(f"ChemicalStructureAnalyzer: {r['error']}")

        # 2. formula → 元素组成
        if formula:
            r = await self._call("MaterialCompositionAnalyzer", {"formula": formula})
            if not r.get("error"):
                result["composition"] = r.get("elements", {})
            else:
                result["warnings"].append(f"MaterialCompositionAnalyzer: {r['error']}")

        # 3. SMILES → 描述符
        if result["smiles"]:
            r = await self._call(
                "MolecularDescriptorCalculator", {"smiles": result["smiles"]}
            )
            if not r.get("error"):
                result["descriptors"] = r
            else:
                result["warnings"].append(f"MolecularDescriptorCalculator: {r['error']}")

        # 4. formula → 材料类别
        if formula:
            r = await self._call("ComprehensiveMaterialAnalyzer", {"material_id": formula})
            if not r.get("error"):
                result["material_class"] = r.get("material_class", "")
                # 如果之前没拿到分子量，用这里的
                if result["molecular_weight"] is None:
                    result["molecular_weight"] = r.get("molecular_weight")
            else:
                result["warnings"].append(f"ComprehensiveMaterialAnalyzer: {r['error']}")

        return result

    # ── 单独工具调用 ────────────────────────────────────────────────────

    async def get_structure_by_name(self, compound_name: str) -> dict:
        """化合物名 → SMILES + 分子式 + 分子量。"""
        return await self._call("ChemicalStructureAnalyzer", {"compound_name": compound_name})

    async def get_composition(self, formula: str) -> dict:
        """化学式 → 元素组成分析。"""
        return await self._call("MaterialCompositionAnalyzer", {"formula": formula})

    async def get_material_info(self, material_id: str) -> dict:
        """material_id → 综合材料信息（基础级，非 DFT）。

        注意：此工具对无机晶体（如 Li7La3Zr2O12）仅返回基础信息，
        band_gap 等精确性质需 DFT 或 MP 数据库，本工具会返回提示字符串。
        """
        return await self._call("ComprehensiveMaterialAnalyzer", {"material_id": material_id})

    async def get_electronic_properties(self, smiles: str) -> dict:
        """SMILES → 分子电子性质（价电子数、partial charge）。

        仅适用于分子，不适用于无机晶体。
        """
        return await self._call("ElectronicPropertyCalculator", {"smiles": smiles})

    async def get_molecular_descriptors(self, smiles: str) -> dict:
        """SMILES → 高级分子描述符（logP、TPSA、拓扑指数等）。"""
        return await self._call("MolecularDescriptorCalculator", {"smiles": smiles})

    async def start_meta_analysis(
        self,
        prompt: str,
        analysis_type: str = "material",
        file_list: list | None = None,
    ) -> dict:
        """启动 AI 深度研究任务（异步）。

        注意：scp_start_MetaAnalysis 实测可返回 task_id，但
        scp_query_MetaAnalysis / scp_wait_MetaAnalysis 实测故障（2026-07-28）。
        调用此方法会启动任务并返回 task_id，但当前无法查询结果。
        未来 SCP hub 修复 query/wait 后可复用。

        Returns:
            {"task_id": "session_xxx", "status": "started", "warning": "..."}
        """
        arguments: dict[str, Any] = {"prompt": prompt, "type": analysis_type}
        if file_list is not None:
            arguments["file_list"] = file_list
        r = await self._call("scp_start_MetaAnalysis", arguments)
        if r.get("error"):
            return r
        # 从 structuredContent.scp_output.callback.task_id 提取
        callback = r.get("scp_output", {}).get("callback", {})
        task_id = callback.get("task_id", "")
        if not task_id:
            return {"error": "scp_start_MetaAnalysis returned no task_id", "raw": r}
        return {
            "task_id": task_id,
            "status": "started",
            "warning": "query/wait 接口当前故障，无法查询结果",
        }

    # ── 内部调用封装 ────────────────────────────────────────────────────

    async def _call(self, tool_name: str, arguments: dict) -> dict:
        """调用 SCP 工具，解析 content text 为 dict。

        失败时返回 {"error": "..."}，不抛异常。
        """
        try:
            raw = await self._scp.call_tool(
                server_id=_SERVER_28_ID,
                tool_name=tool_name,
                arguments=arguments,
                server_url=_SERVER_28_URL,
            )
        except Exception as e:
            logger.warning("MaterialInfoClient._call %s failed: %s", tool_name, e)
            return {"error": f"exception: {e}"}

        if raw.get("status") == "error":
            return {"error": raw.get("error", "unknown SCP error")}

        # SCPClientPool.call_tool 返回结构：
        # {"status": "success", "data": {"content": [...], "structuredContent": {...}}}
        # 或 {"result": {"content": [...]}}（兼容旧格式）
        data = raw.get("data", raw.get("result", raw))
        content = data.get("content", [])
        text = ""
        for item in content if isinstance(content, list) else []:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                break

        if not text:
            # 尝试 structuredContent
            structured = data.get("structuredContent", {})
            if structured:
                return structured
            return {"error": "no content in SCP response", "raw": str(raw)[:300]}

        # content text 可能是 JSON 字符串
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 非 JSON，直接返回文本
            return {"text": text, "raw": text[:500]}
