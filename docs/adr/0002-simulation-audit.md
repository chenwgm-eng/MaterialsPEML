# ADR-0002: 模拟数据不得冒充实测

- **状态**: 已接受（2026-08-11）
- **背景**: ECML demo 模式把确定性伪随机模拟测量值以 `qc_status=VALID`、`learning_eligible=True`、provenance `evidence_level="measured"` 写入实验记录——模拟数据进入学习池并冒充实测。结果表无 provenance 列，溯源只能靠外键链间接反查。
- **决策**:
  1. `experiment_result_records` 新增 `provenance JSONB` 列（迁移 0059），所有写入路径（人工录入/CSV/ECML）统一记录溯源。
  2. 模拟落库必须 `data_quality="simulated"`、`learning_eligible=False`、provenance 标 `source_type="simulation"`，**不得**使用 `measured` 证据等级。
  3. 模拟/估算/实测三档在 UI 可区分（徽标），数据质量看板可过滤。
- **备选**: 模拟值不落库（被否：demo 模式需要闭环演示数据，但必须诚实标注）；仅改标记不加列（被否：溯源链不闭合）。
- **后果**: demo 模式的实验数据不再被 ML 学习；ECML 反馈分析消费实验数据时按 data_quality 过滤；现有历史记录保持原样（数据量小，可接受）。
