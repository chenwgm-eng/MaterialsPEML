# 候选状态机：ready_for_experiment 为终态，不可归档为 rejected

候选材料在两层研发流程中沿状态机流转（screening→feasible→process_planning→process_confirmed→ready_for_experiment），其中 `ready_for_experiment` 定义为终态（无任何合法后继），即使该候选最终未执行实验也不允许回退到 rejected 归档。

## 背景

初始设计允许 `process_confirmed → rejected`（可淘汰），但对 `ready_for_experiment` 未定义任何后继（`CANDIDATE_ALLOWED_TRANSITIONS` 中为空集）。前端曾出现"已推进至可实验的候选仍尝试确认工艺方案"的非法迁移（工单 ERR-MSN5W7IS-08），根因是按钮未按候选状态门控，而非状态机本身。

## 决策

- `ready_for_experiment` 保持终态：不可转 rejected、不可回退 process_confirmed。
- 淘汰/归档操作仅允许在 `screening / feasible / process_planning / process_confirmed` 状态执行。
- 前端所有候选状态联动按钮（确认工艺方案、推进至可实验、归档）必须按状态机门控，后端校验作为最后防线（409 + 明确提示），不做"容忍式"放行。

## 考虑过的替代方案

- **允许 ready_for_experiment → rejected（可归档）**：被否决。已下达实验任务单、已生成的样品与放行卡均引用该候选，终态归档会破坏数据溯源链，且"已批准可实验"与"已淘汰"语义互斥。
- **后端静默忽略非法推进**：被否决。会掩盖"候选已终态但工艺方案未确认"这类真实数据不一致，违背"回退/状态必须透明"的平台原则。

## 后果

- 无法直接删除或归档已推进至可实验的候选；如需处置，应先处理其关联实验任务/放行卡，或保留为历史记录。
- 前端需在候选进入终态后隐藏/禁用"确认工艺方案"与"归档"入口，避免用户触发 409 后困惑。
