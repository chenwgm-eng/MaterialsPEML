# ADR-0005: AI 发起动作的服务端身份判定（X-Execution-Context）

- **状态**: 已接受（2026-08-23，分阶段实施）
- **背景**: T-031 高危门禁（AI 建实验单 / AI 发布配方 / AI 放行样品）此前唯一触发信号是请求体自报的 `ai_initiated` 布尔——任何持 RESEARCHER token 的调用方（或被提示注入的 Agent）省略该标志即可绕过人工确认直接执行，"AI 动作需审批"形同自律条款。控制平面已有 HMAC 签名的 ExecutionContext 与 IdentityManager（含验签/有效期/委托链深度校验），但未接入 HTTP 层。
- **决策**:
  1. Agent 侧 HTTP 调用可携带 `X-Execution-Context` 头：内容为 IdentityManager `derive_child()` 签发、含 agent_id 的子 ExecutionContext（JSON）。
  2. `execution_context_middleware` 经既有 `validate_context()` 校验（签名+有效期+委托链+角色合法）后，置 `request.state.ai_principal=True`；校验失败按普通用户处理并告警（可用性取向），门禁本体对评估异常保持 fail-closed。
  3. 门禁统一走 `_is_ai_initiated(request, payload_flag)`：**验签凭证为权威信号 > 请求体 ai_initiated 自报（迁移期冗余）**。三处高危端点已接入。
  4. 第二阶段（待办）：Agent 凭证签发流程与工具化 → 全量接入后废弃请求体 `ai_initiated` 字段 → 制定签名密钥轮换策略。
- **备选**: 直接拒绝携带无效凭证的请求（被否：Agent 侧尚未改造，先断现有集成不可取）；在 auth/tokens.py 新增独立 Agent token 类型（备选方案 B：长期更干净但涉及认证面变更，若第二阶段发现头方案不足再评估）。
- **后果**: 服务端可不信任请求体区分人/AI，审计操作者绑定签名后的 agent 身份；中间件对无效头仅降级不阻断，攻击面收敛依赖第二阶段完成废弃。相关实现：api.py `_is_ai_initiated`、execution_context_middleware；fail-closed 缺口修复见 agent_team/executor.py。
