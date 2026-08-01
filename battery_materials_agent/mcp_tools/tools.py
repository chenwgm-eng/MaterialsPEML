"""MCP-compatible tool definitions for the battery materials agent."""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from pydantic import BaseModel, Field
from typing import Any, Callable, Literal
from functools import partial

from .alias_registry import AliasRegistry

logger = logging.getLogger(__name__)


class MCPToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class MCPTool(BaseModel):
    name: str
    description: str
    parameters: list[MCPToolParameter] = Field(default_factory=list)
    source: Literal["local", "scp", "internlm"] = "local"
    availability: Literal["always", "conditional", "disabled"] = "always"
    risk_level: str = ""


class SCPToolProxy:
    """Wraps the full SCP invocation chain: authorize → validate → call → normalize → provenance → audit."""

    def __init__(self, internal_name: str, client_pool, catalog, policy, adapter, audit_store):
        self.internal_name = internal_name
        self._client_pool = client_pool
        self._catalog = catalog
        self._policy = policy
        self._adapter = adapter
        self._audit_store = audit_store

    async def __call__(self, args: dict) -> dict:
        from ..integrations.audit_store import ProvenanceDecorator
        from ..integrations.models import ExternalInvocation
        from .scp_policy import PolicyDeniedError

        binding = self._catalog.get(self.internal_name)
        user_role = args.pop("_user_role", "researcher")
        ecml_step = args.pop("_ecml_step", None)
        correlation_id = args.pop("_correlation_id", str(uuid.uuid4()))
        actor_id = args.pop("_actor_id", None)
        project_id = args.pop("_project_id", None)
        run_id = args.pop("_run_id", None)
        # 允许调用方（如工具自测端点）指定服务器上真实存在的远端工具名；
        # 缺省回退到绑定配置的 remote_tool_name
        remote_tool_name = args.pop("_remote_tool_name", None) or binding.remote_tool_name
        if not remote_tool_name or not binding.server_id:
            return {
                "status": "error",
                "message": f"SCP 工具 '{self.internal_name}' 未配置远端服务器绑定"
                f"（server_id={binding.server_id!r}, remote_tool_name={remote_tool_name!r}），"
                "无法执行远程调用。请在能力契约页面为其配置 server 映射。",
            }

        invocation_id = str(uuid.uuid4())
        start = time.monotonic()

        try:
            # Step 1: Authorize
            self._policy.authorize(self.internal_name, user_role, ecml_step)

            # Step 2: Validate and map input
            mapped_args = self._adapter.validate_and_map_input(args, binding)

            # Step 3: Call remote (pass per-provider server_url so the client
            # hits the correct endpoint, not just the global base_url).
            raw_result = await self._client_pool.call_tool(
                binding.server_id, remote_tool_name, mapped_args,
                server_url=binding.server_url or None,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if raw_result.get("status") == "error":
                logger.error(
                    "SCP call failed: tool=%s server=%s error=%s",
                    self.internal_name, binding.server_id,
                    raw_result.get("error", "unknown"),
                )
                self._audit_store.append(ExternalInvocation(
                    invocation_id=invocation_id,
                    correlation_id=correlation_id,
                    project_id=project_id,
                    run_id=run_id,
                    actor_id=actor_id,
                    provider="scp",
                    capability=self.internal_name,
                    status="failed",
                    input_redacted={"tool": self.internal_name, "args_keys": list(args.keys())},
                    output_summary={"error": raw_result.get("error", "unknown")},
                    error_code=raw_result.get("error", "unknown"),
                    latency_ms=elapsed_ms,
                ))
                return {"status": "error", "message": raw_result.get("error", "SCP call failed")}

            # Step 4: Normalize output
            data = raw_result.get("data", {})
            normalized = self._adapter.normalize_output(data, binding)

            # Step 5: Attach provenance
            evidence_level = "auxiliary"
            if binding.risk_level.value == "A":
                evidence_level = "computed"
            elif binding.risk_level.value == "B":
                evidence_level = "auxiliary"

            ProvenanceDecorator.attach(
                normalized,
                source_type="scp",
                provider="scp",
                model_or_tool=remote_tool_name,
                duration_ms=elapsed_ms,
                evidence_level=evidence_level,
            )

            # Step 6: Audit
            self._audit_store.append(ExternalInvocation(
                invocation_id=invocation_id,
                correlation_id=correlation_id,
                project_id=project_id,
                run_id=run_id,
                actor_id=actor_id,
                provider="scp",
                capability=self.internal_name,
                status="success",
                input_redacted={"tool": self.internal_name, "args_keys": list(args.keys())},
                output_summary={"status": "success"},
                latency_ms=elapsed_ms,
            ))

            # Surface the audit invocation_id so upstream callers (ECML engine,
            # compliance node) can append it to ECMLState.external_invocation_ids.
            normalized["invocation_id"] = invocation_id
            return normalized

        except PolicyDeniedError as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "SCP policy denied: tool=%s error=%s", self.internal_name, e,
            )
            self._audit_store.append(ExternalInvocation(
                invocation_id=invocation_id,
                correlation_id=correlation_id,
                project_id=project_id,
                run_id=run_id,
                actor_id=actor_id,
                provider="scp",
                capability=self.internal_name,
                status="blocked",
                input_redacted={"tool": self.internal_name},
                error_code=str(e),
                latency_ms=elapsed_ms,
            ))
            return {"status": "blocked", "message": str(e)}

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "SCP proxy unexpected error: tool=%s error=%s",
                self.internal_name, e, exc_info=True,
            )
            self._audit_store.append(ExternalInvocation(
                invocation_id=invocation_id,
                correlation_id=correlation_id,
                project_id=project_id,
                run_id=run_id,
                actor_id=actor_id,
                provider="scp",
                capability=self.internal_name,
                status="failed",
                input_redacted={"tool": self.internal_name},
                output_summary={"error": str(e)},
                error_code=str(e),
                latency_ms=elapsed_ms,
            ))
            return {"status": "error", "message": str(e)}


class MCPToolRegistry:
    """Registry of MCP-compatible tools for the battery materials agent."""

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._handlers: dict[str, Callable] = {}
        self._async_handlers: dict[str, Callable] = {}
        self._alias_registry = AliasRegistry()
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        self.register(MCPTool(
            name="route_material",
            description="判断材料类型并路由到对应的处理分支（晶体/聚合物/有机小分子）",
            parameters=[
                MCPToolParameter(name="material_input", type="object", description="材料输入数据（名称、SMILES、PSMILES、化学式等）"),
            ],
        ))

        self.register(MCPTool(
            name="generate_crystal_candidates",
            description="从 Materials Project 与 GNoME 数据集生成晶体候选材料",
            parameters=[
                MCPToolParameter(name="elements", type="array", description="目标元素列表"),
                MCPToolParameter(name="num_candidates", type="integer", description="候选数量", required=False, default=10),
            ],
        ))

        self.register(MCPTool(
            name="generate_polymer_candidates",
            description="生成聚合物电解质候选材料（基于 LLM + 分子设计规则）",
            parameters=[
                MCPToolParameter(name="target_properties", type="object", description="目标性质", required=False),
                MCPToolParameter(name="num_candidates", type="integer", description="候选数量", required=False, default=10),
            ],
        ))

        self.register(MCPTool(
            name="predict_crystal_properties",
            description="使用 CGCNN / M3GNet 预测晶体材料的物理性质",
            parameters=[
                MCPToolParameter(name="features", type="object", description="晶体特征（化学式、结构等）"),
                MCPToolParameter(name="property_name", type="string", description="要预测的性质名称"),
            ],
        ))

        self.register(MCPTool(
            name="predict_polymer_properties",
            description="使用 PolymerGNN 预测聚合物材料的物理性质",
            parameters=[
                MCPToolParameter(name="features", type="object", description="聚合物特征（SMILES/PSMILES）"),
                MCPToolParameter(name="property_name", type="string", description="要预测的性质名称"),
            ],
        ))

        self.register(MCPTool(
            name="check_synthesis_feasibility",
            description="使用 ASKCOS 逆合成引擎评估目标分子的合成可行性",
            parameters=[
                MCPToolParameter(name="smiles", type="string", description="目标分子的 SMILES 表达式"),
            ],
        ))

        self.register(MCPTool(
            name="verify_dft",
            description="使用 RDKit / PySCF / ASE 对材料进行 DFT 精确计算验证",
            parameters=[
                MCPToolParameter(name="smiles", type="string", description="目标分子的 SMILES 表达式"),
                MCPToolParameter(name="property_name", type="string", description="要验证的性质名称"),
            ],
        ))

        self.register(MCPTool(
            name="get_experiment_results",
            description="从实验数据仓库查询湿实验测试结果",
            parameters=[
                MCPToolParameter(name="formula", type="string", description="材料化学式", required=False),
                MCPToolParameter(name="experiment_type", type="string", description="实验类型", required=False),
            ],
        ))

        self.register(MCPTool(
            name="subscribe_experiment_updates",
            description="订阅新实验结果的实时推送通知",
            parameters=[
                MCPToolParameter(name="callback_url", type="string", description="回调 URL"),
            ],
        ))

        self.register(MCPTool(
            name="design_formula",
            description="基于企业物料库生成工业化配方（BOM/BOP），评估合规性与量产成本",
            parameters=[
                MCPToolParameter(name="target_material", type="object", description="目标材料信息（含目标属性、候选 SMILES 等）", required=False),
            ],
        ))

    def register(self, tool: MCPTool, handler: Callable | None = None, async_handler: Callable | None = None):
        self._tools[tool.name] = tool
        if handler:
            self._handlers[tool.name] = handler
        if async_handler:
            self._async_handlers[tool.name] = async_handler

    def unregister(self, name: str):
        self._tools.pop(name, None)
        self._handlers.pop(name, None)
        self._async_handlers.pop(name, None)

    def get_tool(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[MCPTool]:
        return list(self._tools.values())

    def execute(self, name: str, **kwargs) -> Any:
        handler = self._handlers.get(name)
        if not handler:
            raise ValueError(f"No handler registered for tool: {name}")
        return handler(**kwargs)

    def execute_async(self, name: str, arguments: dict) -> Any:
        """Execute a tool asynchronously (for SCP tools).

        The handler is expected to accept a single positional dict argument
        (matching SCPToolProxy.__call__(args: dict)) and return a coroutine.
        """
        handler = self._async_handlers.get(name)
        if not handler:
            raise ValueError(f"No async handler registered for tool: {name}")
        return handler(arguments)

    def register_scp_tools(self, catalog, client_pool, policy, adapters: dict, audit_store):
        """Register all enabled SCP tool bindings as MCP tools."""
        from .scp_adapters import SCPAdapter
        from .scp_catalog import RiskLevel

        adapter_map = {
            "molecule_descriptor_v1": adapters.get("molecule_descriptor"),
            "toxicity_v1": adapters.get("toxicity_assessment"),
            "literature_search_v1": adapters.get("literature_search"),
            "protocol_draft_v1": adapters.get("protocol_draft"),
            "material_transform_v1": adapters.get("material_transform"),
        }
        # 透传适配器：output_mapping 为空的绑定（如 Intern Discovery 默认 SCP）
        # 无需输入输出转换，直接透传参数与结果。
        passthrough_adapter = SCPAdapter()

        for binding in catalog.list_enabled():
            adapter = adapter_map.get(binding.output_mapping)
            if adapter is None:
                adapter = passthrough_adapter

            availability = "always"
            if binding.risk_level == RiskLevel.C:
                availability = "conditional"
            elif binding.risk_level == RiskLevel.D:
                availability = "disabled"

            proxy = SCPToolProxy(
                internal_name=binding.internal_name,
                client_pool=client_pool,
                catalog=catalog,
                policy=policy,
                adapter=adapter,
                audit_store=audit_store,
            )

            tool = MCPTool(
                name=binding.internal_name,
                description=f"SCP: {binding.remote_tool_name} (risk={binding.risk_level.value})",
                source="scp",
                availability=availability,
                risk_level=binding.risk_level.value,
            )
            self.register(tool, async_handler=proxy)

    def to_mcp_manifest(self) -> dict:
        tools = []
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "source": tool.source,
                "availability": tool.availability,
                "risk_level": tool.risk_level,
                "parameters": {
                    "type": "object",
                    "properties": {
                        p.name: {
                            "type": p.type,
                            "description": p.description,
                            **({"default": p.default} if p.default is not None else {}),
                        }
                        for p in tool.parameters
                    },
                    "required": [p.name for p in tool.parameters if p.required],
                },
            })
        return {"tools": tools}

    def resolve_alias(self, alias: str, profile: str) -> list[str]:
        """解析别名到候选 binding 列表。

        委托给 AliasRegistry。返回 binding 名称列表。
        """
        if self._alias_registry is None:
            return []
        return self._alias_registry.resolve(alias, profile)

    def get_alias_registry(self) -> AliasRegistry:
        """返回内部语义工具别名注册表实例。"""
        return self._alias_registry
