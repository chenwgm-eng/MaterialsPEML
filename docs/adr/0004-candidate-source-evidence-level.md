# ADR-0004: 候选来源的可信度档映射（LLM 生成按"模型预测"展示）

- **状态**: 已接受（2026-08-23）
- **背景**: 前端 CandidateList 此前从 `data.property_source` 字段**存在性**推导可信度徽标（有查表来源 → estimated，否则 → predicted），这是与后端无关的第二事实来源：LLM 生成候选（internlm_generated / llm_generated）会被误判档位；ADR-0001 的四档语义在展示层分叉。同时后端从未输出权威可信度字段，前端被迫自行猜测。
- **决策**:
  1. **领域决策（2026-08-23）**：LLM 生成的候选属性按**模型预测**（predicted）展示——LLM 是带训练数据的模型产物，区别于手调系数的描述符启发式；结构数据库/查表/规则启发式来源一律**工程估算**（estimated）。
  2. 权威映射唯一落在后端 `candidate_store.CANDIDATE_SOURCE_EVIDENCE_LEVEL`（来源 → 档位），经 `CandidateRecord.evidence_level` computed_field 随所有候选 API 序列化输出。
  3. 解析优先级：候选 `data.evidence_level` 显式标注（逐条逃生通道）> 来源映射 > 默认 estimated（承接 ADR-0001 保守取向：无法证明是真实权重模型的不得称预测）。
  4. 前端徽标只消费该字段，禁止从任何其他字段二次推导。
- **备选**: 保留前端推导并修正规则（被否：语义仍分叉，新增页面必复现）；LLM 来源也标 estimated（被否：与手调启发式不加区分，掩盖了生成路径差异）。
- **后果**: 仅作用于序列化边界，不进入存储内容与 content_hash 去重；历史候选经 source 列即时生效、无需回填；**新增来源类型必须登记映射表**，未登记的保守落 estimated 并可被逐条标注覆盖。回归测试锁定于 test_grilling_features.TestCandidateEvidenceLevel。
