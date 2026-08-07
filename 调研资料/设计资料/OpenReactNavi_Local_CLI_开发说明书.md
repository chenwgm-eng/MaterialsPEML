# OpenReactNavi 本地 CLI 开发说明书

**版本**：V0.1  
**项目名**：`openreactnavi`  
**定位**：本地优先的逆合成路线规划、证据检索与路线审计 CLI  
**命令行入口**：`ornavi`

---

## 1. 目标与边界

OpenReactNavi 以目标分子 SMILES 为输入，生成多步逆合成候选树/路线，给出每一步反应转化、反应物建议、路线评分、可购性或目录命中信息，以及可审计的文献/专利证据包。

它应实现与所附 ReactNavi 架构**功能等价**的能力：目标结构规范化、受约束的多步逆合成搜索、Top-N 模板或模型提案、树搜索、路线排序、JSON/PNG/HTML/Markdown 报告输出。不得复制其 Cython 二进制、私有 HTTP 服务、对象存储链接、专有模型权重、内部模板库、鉴权机制或品牌标识。

V0.1 不以“完全自动给出可直接实验复现的合成工艺”为承诺。每个建议必须区分为模型生成、规则推断、文献证实和专利证实四种证据等级。

---

## 2. 功能范围

### 2.1 V0.1 支持

- 输入 SMILES、InChI 或 SDF；统一转换为 canonical SMILES
- RDKit 分子校验、元素/原子数/电荷约束
- 单步逆合成提案接口：规则模板、开源模型、外部本地模型均可插拔
- 多步 AND-OR 路线搜索：Beam Search 优先，预留 MCTS
- 可配置最大深度、最大迭代、候选模板数、扩展预算和返回路线数
- Building block 目录检索：本地 CSV/SDF/SQLite
- 路线去重、环路检测、复杂度/可购性/置信度评分
- 反应 SMILES、路线树 JSON、GraphML、HTML、Markdown 输出
- 文献与专利证据导入/关联：本地 BibTeX、RIS、CSV、手动录入
- 断点续跑、运行清单、全部候选与剔除原因记录

### 2.2 V0.1 不支持

- 调用或复现原 ReactNavi 的私有 API、云端对象存储和授权服务
- 将模型建议自动声明为文献事实
- 自动确定实验级别工艺参数、收率、放大可行性或法规合规性
- 商业数据库数据抓取或规避访问控制
- 真实采购下单
- Web 前端和多用户服务

---

## 3. 总体架构

```text
目标 SMILES / InChI / SDF
          │
          ▼
RDKit 标准化、有效性与可合成性预检查
          │
          ▼
单步逆合成提案器（模板/本地模型/规则）
          │
          ▼
AND-OR 搜索树扩展
          │
          ├── 深度、迭代和时间预算
          ├── 环路/重复/非法产物过滤
          └── Building Block 终止判定
          ▼
路线评分与 Pareto 排序
          │
          ▼
证据链接与人工审计队列
          │
          ├── route.json / tree.json
          ├── routes.csv / reactions.csv
          ├── route_*.svg/png
          ├── retrosynthesis.html
          └── summary.md
```

---

## 4. 系统目录

```text
openreactnavi/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── search.yaml
│   ├── scoring.yaml
│   ├── catalog.yaml
│   └── evidence.yaml
├── data/
│   ├── catalogs/
│   ├── templates/
│   ├── benchmarks/
│   └── references/
├── src/openreactnavi/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── plan_cmd.py
│   │   ├── single_step_cmd.py
│   │   ├── catalog_cmd.py
│   │   ├── evidence_cmd.py
│   │   ├── report_cmd.py
│   │   └── status_cmd.py
│   ├── core/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── chemistry.py
│   │   └── identifiers.py
│   ├── standardize/
│   │   ├── input.py
│   │   ├── rdkit_ops.py
│   │   └── atom_mapping.py
│   ├── proposals/
│   │   ├── base.py
│   │   ├── template_engine.py
│   │   ├── rule_engine.py
│   │   ├── local_model.py
│   │   ├── ensembles.py
│   │   └── filters.py
│   ├── search/
│   │   ├── andor_graph.py
│   │   ├── beam.py
│   │   ├── mcts.py
│   │   ├── expansion.py
│   │   ├── terminal.py
│   │   ├── deduplicate.py
│   │   └── checkpoint.py
│   ├── scoring/
│   │   ├── route_score.py
│   │   ├── complexity.py
│   │   ├── purchasability.py
│   │   ├── confidence.py
│   │   └── pareto.py
│   ├── catalog/
│   │   ├── schema.py
│   │   ├── importer.py
│   │   ├── sqlite_store.py
│   │   └── lookup.py
│   ├── evidence/
│   │   ├── schema.py
│   │   ├── importers.py
│   │   ├── matcher.py
│   │   └── audit.py
│   ├── io/
│   │   ├── artifacts.py
│   │   ├── json_store.py
│   │   ├── csv_export.py
│   │   ├── render.py
│   │   └── report_html.py
│   └── utils/
│       ├── hashes.py
│       ├── logging.py
│       ├── time.py
│       └── paths.py
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 5. CLI 规范

```bash
# 初始化项目
ornavi init ./projects/target_a

# 环境与模型/模板/目录检查
ornavi doctor --strict

# 仅运行一轮单步断键提案
ornavi single-step \
  --target "COc1ccc(CCN)cc1" \
  --config configs/search.yaml \
  --workdir runs/target_a

# 多步逆合成路线规划
ornavi plan \
  --target "COc1ccc(CCN)cc1" \
  --config configs/search.yaml \
  --catalog data/catalogs/building_blocks.sqlite \
  --workdir runs/target_a \
  --resume

# 导入本地目录
ornavi catalog import \
  --input vendor_catalog.csv \
  --output data/catalogs/building_blocks.sqlite

# 导入文献或专利证据
ornavi evidence import --input references.bib --workdir runs/target_a
ornavi evidence audit --workdir runs/target_a

# 生成离线报告
ornavi report --workdir runs/target_a
```

### 5.1 关键参数

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `max_paths` | 10 | 最终输出路线数 |
| `max_depth` | 6 | 逆合成最大步数 |
| `max_iterations` | 2000 | 树搜索扩展上限 |
| `template_max_count` | 20 | 每个目标的候选逆反应上限 |
| `expansion_time_s` | 900 | 搜索总时间预算 |
| `beam_width` | 50 | 每层保留状态数 |
| `max_precursors_per_step` | 4 | 单步最大前体数 |
| `max_heavy_atoms` | 80 | 单个中间体重原子上限 |

---

## 6. 配置文件

### 6.1 `configs/search.yaml`

```yaml
project:
  name: target_a
  seed: 42

input:
  allowed_elements: [H, C, N, O, F, Cl, Br, I, S, P, B, Si]
  max_heavy_atoms: 80
  allow_radicals: false
  neutralize_when_possible: false

proposal:
  engines: [template, rules]
  template_library: data/templates/retro_templates.jsonl
  template_max_count: 20
  min_step_confidence: 0.05
  allow_unmapped_reactions: false

search:
  algorithm: beam
  max_paths: 10
  max_depth: 6
  max_iterations: 2000
  expansion_time_s: 900
  beam_width: 50
  max_precursors_per_step: 4
  stop_on_catalog_hit: true
  allow_partial_routes: true
  checkpoint_every_iterations: 100

terminal:
  require_catalog_hit: true
  max_terminal_heavy_atoms: 16
  allow_common_reagents: true

filters:
  valence: true
  atom_conservation: true
  reject_duplicate_precursors: true
  reject_cycles: true
  reject_unwanted_protecting_groups: false

output:
  draw_routes: true
  max_draw: 10
  include_rejected: true
```

### 6.2 `configs/scoring.yaml`

```yaml
weights:
  step_confidence: 0.45
  catalog_availability: 0.25
  route_depth: 0.10
  molecular_complexity: 0.10
  reaction_risk: 0.10

penalties:
  missing_catalog_precursor: 1.0
  low_confidence_step: 0.5
  protected_group: 0.2
  ring_strain: 0.3
  duplicate_transform: 0.5

ranking:
  mode: pareto_then_weighted
  retain_pareto_fronts: 3
```

---

## 7. 数据模型

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MoleculeNode:
    molecule_id: str
    canonical_smiles: str
    mapped_smiles: str | None
    inchi_key: str | None
    heavy_atom_count: int
    is_catalog_hit: bool
    catalog_ids: tuple[str, ...]
    complexity_score: float | None


@dataclass(frozen=True)
class RetroStep:
    step_id: str
    product_smiles: str
    precursor_smiles: tuple[str, ...]
    reaction_smiles: str
    template_id: str | None
    proposal_engine: str
    confidence: float
    conditions_hint: str | None
    evidence_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteRecord:
    route_id: str
    target_smiles: str
    steps: list[RetroStep]
    terminal_molecules: list[MoleculeNode]
    depth: int
    route_score: float
    confidence_score: float
    catalog_coverage: float
    complexity_score: float
    status: str
    evidence_summary: dict[str, int]
```

### 7.1 证据等级

```text
E0 = 无证据，仅搜索算法/规则建议
E1 = 模板或模型预测
E2 = 已匹配本地反应数据库记录
E3 = 已关联论文、专利或内部实验记录
E4 = 人工审阅确认且可复核
```

任何模型输出默认最低为 `E1`，不得自动标记为文献证实。

---

## 8. 单步提案接口

文件：`proposals/base.py`

```python
from abc import ABC, abstractmethod


class RetroProposalEngine(ABC):
    name: str

    @abstractmethod
    def propose(
        self,
        target_smiles: str,
        max_candidates: int,
        context: dict,
    ) -> list[RetroStep]:
        """返回按置信度排序的候选逆反应。"""
```

### 8.1 模板引擎

- 读取本地 JSONL 或 SQLite 模板库
- 使用 RDKit Reaction SMARTS 运行逆向变换
- 保存模板 ID、模板来源、匹配原子、产物和前体
- 每个目标只保留 `template_max_count` 条候选

### 8.2 规则引擎

V0.1 内置有限的可解释规则：

- 酯键断裂
- 酰胺键断裂
- Suzuki、Buchwald、Sonogashira 类 C-C/C-N 偶联的结构性拆分
- 保护基安装/脱除逆向拆分
- 醇/羰基互变的氧化还原前体提示
- SN2 型碳-杂原子键断裂

规则引擎只能生成“逆合成候选”，不能伪造反应条件、收率或文献引用。

### 8.3 本地模型插件

接口可兼容本地部署的开源单步逆合成模型。模型插件必须：

- 在 `model_manifest.json` 中保存模型名称、版本、权重哈希、训练数据许可和推理参数
- 返回原始模型分数及温度/归一化方法
- 不可访问私有 ReactNavi 服务或模型

---

## 9. AND-OR 搜索

### 9.1 状态定义

- **OR 节点**：一个待拆解的目标分子
- **AND 节点**：一个单步反应；其全部前体必须可获得或继续拆解
- **终止节点**：命中目录、被定义为常见试剂，或达到小分子终止阈值

### 9.2 Beam Search 伪代码

```python
def plan(target: MoleculeNode, config: SearchConfig) -> list[RouteRecord]:
    frontier = [initial_state(target)]
    completed = []

    for depth in range(config.max_depth):
        expanded = []
        for state in frontier:
            focus = state.select_unresolved_molecule()
            for step in proposer.propose(focus.canonical_smiles, config.template_max_count, {}):
                child = state.apply(step)
                if filters.reject(child):
                    continue
                child.refresh_terminal_status(catalog)
                child.compute_partial_score()
                if child.is_complete():
                    completed.append(child)
                else:
                    expanded.append(child)

        frontier = keep_top_unique(expanded, width=config.beam_width)
        checkpoint.write(depth, frontier, completed)
        if not frontier or budget.exhausted():
            break

    return rank_routes(completed, config.max_paths)
```

### 9.3 必须实现的过滤

- 分子有效性和 RDKit sanitize
- 元素、原子数、电荷约束
- 无效价态
- 同一分子沿祖先路径重复出现的循环
- 单步前体重复
- 前体数超过配置上限
- 与既有路线同构的重复路线
- 单步置信度低于阈值

---

## 10. 目录与终止判定

### 10.1 本地目录格式

```text
vendor_id,smiles,name,cas,price,currency,purity,pack_size,source,updated_at
BB000001,CCO,Ethanol,64-17-5,20.0,CNY,0.995,500mL,internal,2026-01-01
```

### 10.2 SQLite 索引

```sql
CREATE TABLE building_blocks (
  vendor_id TEXT PRIMARY KEY,
  canonical_smiles TEXT NOT NULL,
  inchikey TEXT,
  name TEXT,
  cas TEXT,
  price REAL,
  currency TEXT,
  purity REAL,
  pack_size TEXT,
  source TEXT,
  updated_at TEXT
);
CREATE INDEX idx_building_blocks_smiles ON building_blocks(canonical_smiles);
CREATE INDEX idx_building_blocks_inchikey ON building_blocks(inchikey);
```

### 10.3 终止优先级

1. 精确 canonical-SMILES 命中目录
2. InChIKey 命中目录
3. 用户定义的常用试剂白名单
4. 重原子数不高于 `max_terminal_heavy_atoms` 且允许 partial route
5. 否则继续展开

---

## 11. 路线评分

路线评分不是单一模型分数。V0.1 使用可解释的加权评分并保留子项：

\[
S_{route} =
w_c S_{confidence} +
w_a S_{availability} -
w_d P_{depth} -
w_x P_{complexity} -
w_r P_{risk}
\]

- `confidence`：各步置信度的几何平均或对数和
- `availability`：终止前体命中目录的比例
- `depth`：路线步数惩罚
- `complexity`：SAScore、重原子数、环数等的综合增量
- `risk`：低置信度、保护基、陌生模板和高分支数惩罚

必须同时导出 Pareto 前沿，避免仅以一个加权总分排除“更短但成本高”或“更稳但步骤多”的路线。

---

## 12. 证据审计

### 12.1 本地证据输入

```bash
ornavi evidence import --input references.bib --workdir runs/target_a
ornavi evidence import --input patents.csv --workdir runs/target_a
ornavi evidence import --input internal_experiments.csv --workdir runs/target_a
```

### 12.2 `evidence.csv`

```text
evidence_id
source_type
citation
url_or_identifier
reaction_smiles
product_smiles
reactant_smiles
conditions_text
yield_text
confidence
matched_step_id
match_method
review_status
notes
```

### 12.3 审计报告要求

- 明确列出每一步证据等级
- 区分“反应转化匹配”与“底物完全匹配”
- 不允许从相似反应自动推断真实条件
- 所有推断性条件必须标记 `SPECULATIVE`
- 导出需要人工核对的步骤清单

---

## 13. 输出规范

```text
runs/target_a/
├── inputs/
│   ├── target.json
│   ├── resolved_config.yaml
│   └── run_manifest.json
├── search/
│   ├── proposals.csv
│   ├── rejected_proposals.csv
│   ├── tree.json
│   ├── checkpoints/
│   └── routes.json
├── evidence/
│   ├── evidence.csv
│   └── audit.csv
├── results/
│   ├── routes.csv
│   ├── reactions.csv
│   ├── terminal_precursors.csv
│   ├── retrosynthesis.graphml
│   ├── retrosynthesis.html
│   ├── route_001.svg
│   ├── route_001.png
│   └── summary.md
└── logs/
    └── plan.log
```

`routes.csv` 最低字段：

```text
route_id
rank
target_smiles
depth
route_score
confidence_score
catalog_coverage
complexity_score
terminal_count
evidence_level_min
evidence_level_summary
status
route_json_path
image_path
```

`reactions.csv` 最低字段：

```text
route_id
step_index
step_id
product_smiles
precursor_smiles_json
reaction_smiles
template_id
proposal_engine
confidence
conditions_hint
evidence_level
matched_evidence_id
```

---

## 14. Checkpoint 与可复现性

每隔固定迭代数输出：

```text
search/checkpoints/iter_000100/
├── frontier.json
├── completed.json
├── visited_molecules.json
├── visited_routes.json
├── search_stats.json
└── checksum.sha256
```

恢复时必须校验：目标结构哈希、配置哈希、模板库哈希、目录哈希和模型清单哈希。任一核心输入改变时默认拒绝恢复，除非显式 `--force-resume`。

---

## 15. 测试与验收

### 15.1 单元测试

- SMILES/InChI/SDF 标准化
- 反应模板匹配与产物/前体映射
- 非法价态、循环、重复路线过滤
- 目录导入和精确结构命中
- 路线评分、Pareto 排序
- checkpoint 写入、读取和哈希校验
- 证据匹配和等级规则

### 15.2 集成测试

- `ornavi init` 创建项目
- `ornavi doctor --strict` 检查 RDKit 和本地模板/目录
- 简单酯/酰胺目标产生可解释单步拆分
- 两步受限搜索生成至少一条完整目录终止路线
- 中断后 `--resume` 不重复扩展
- `ornavi report` 生成可离线打开 HTML

### 15.3 V0.1 冻结条件

- 无需任何私有网络服务即可执行完整示例
- 目标、配置、模板和目录版本均记录在运行清单中
- 每条路线可回溯到每一步提案和每个过滤决定
- 每一步明确证据等级，模型预测不冒充文献事实
- 输出路线可复现且 checkpoint 可恢复

---

## 16. 合规边界

本项目只采用独立实现、公开论文、用户有权使用的本地模板库和开放模型。不得反编译、提取或使用 ReactNavi 的私有二进制、API、对象存储文件、服务账户、模型权重、模板数据库或名称标识。