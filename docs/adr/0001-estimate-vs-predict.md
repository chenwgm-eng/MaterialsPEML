# ADR-0001: "预测"与"估算"术语分层

- **状态**: 已接受（2026-08-11）
- **背景**: 描述符线性模型（PROPERTY_MODELS 的 intercept/weights 手调系数）此前以 `descriptor_linear` 标签、confidence 0.65-0.92 产出"预测值"，且高置信会触发 `simulated` 数据质量语义。审计发现：权重无训练数据、confidence 仅是"描述符覆盖度"代理、无 provenance。向审查者呈现时，"预测"声称不可辩护。
- **决策**: 术语按证据强度分层：
  - 有真实权重/训练数据的模型（当前仅 Tg、介电常数走 PolymerGNN）→ **模型预测**（predicted）。
  - 启发式（其余 8 个工程性能属性）→ **工程估算**（estimated）：模型标签 `descriptor_heuristic`，confidence 上限 0.5，evidence_level="estimated"，provenance 带 source 说明。
  - 模拟实验值（demo）→ **模拟值**（simulated，见 ADR-0002）。
- **备选**: 保留"预测"并附加免责声明（被否：审计不友好，语义仍然名不副实）。
- **后果**: 前端候选详情/预测表需区分显示"估算"徽标；排序/筛选功能不受影响；ECML 达标判定语义不变。
