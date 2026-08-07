# OpenReactNet 本地 CLI 开发说明书

**版本**：V0.1  
**部署模式**：Local CLI / Conda 环境 / 单机优先  
**Python**：3.11  
**项目代号**：`openreactnet`  
**命令行入口**：`orn`

---

## 1. 项目目标

构建一个可在本地工作站运行的自动化反应网络发现系统。用户输入反应物 SMILES 或 XYZ，系统自动生成候选反应、进行化学规则筛选、构象采样、低层级量化计算、过渡态搜索、IRC 验证、能垒筛选和多层反应网络扩展。

V0.1 的定位不是替代所有商业量化软件，也不复制 ReactNet 的 Cython 二进制、远程 API、授权机制或内部算法细节；目标是采用公开可用的 Python 库与计算化学工具，构建输入输出和工作流能力等价的本地可复现系统。

---

## 2. V0.1 范围

### 2.1 支持范围

- 闭壳层有机小分子
- 初始元素集合：H、C、N、O、F、Cl、Br、I、S、P
- 单重态默认，支持配置总电荷和自旋多重度
- 单或多反应物体系
- 最多 1 根断键和 1 根成键的候选枚举
- xTB/GFN2-xTB 低成本计算
- CREST 构象采样，可配置关闭
- pyGSM 反应路径搜索
- Pysisyphus TS 优化与 IRC
- PySCF 可选 DFT 单点能或精修
- 1–3 层反应网络扩展
- CSV、JSON、XYZ、SDF、HTML 离线报告
- 单进程可复现运行，后续支持多进程

### 2.2 暂不支持

- 金属催化和配位化学
- 显式溶剂、复杂离子对
- 开壳层体系
- 自动微观动力学求解
- Web UI、云端 API、用户系统
- GPU 或 ML 势函数作为必要依赖
- 未经量化验证的机器学习 TS 直接入网

---

## 3. 总体架构

```text
输入 SMILES / XYZ
      │
      ▼
标准化与原子映射
      │
      ▼
反应枚举（键断裂/形成）
      │
      ▼
化学规则筛选与去重
      │
      ▼
反应物/产物构象生成与预优化
      │
      ▼
TS 初猜（RCS/插值/GSM）
      │
      ▼
TS 优化 + 频率检查
      │
      ▼
双向 IRC 验证
      │
      ▼
能垒与反应能计算
      │
      ▼
网络选择、分层扩展、断点续跑
      │
      ├── CSV/Parquet 结果
      ├── XYZ/SDF 结构工件
      ├── JSON checkpoint
      └── Cytoscape.js HTML 网络图
```

---

## 4. 目录结构

```text
openreactnet/
├── README.md
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── enumerate.yaml
│   ├── ts_xtb.yaml
│   ├── network_xtb.yaml
│   └── dft_pyscf.yaml
├── examples/
│   ├── sn2/
│   └── simple_network/
├── src/openreactnet/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── enumerate_cmd.py
│   │   ├── ts_cmd.py
│   │   ├── network_cmd.py
│   │   ├── refine_cmd.py
│   │   ├── report_cmd.py
│   │   └── clean_cmd.py
│   ├── core/
│   │   ├── enums.py
│   │   ├── models.py
│   │   ├── molecule.py
│   │   ├── species.py
│   │   ├── complex.py
│   │   ├── reaction.py
│   │   └── validation.py
│   ├── config/
│   │   ├── schema.py
│   │   ├── loader.py
│   │   ├── defaults.py
│   │   └── manifest.py
│   ├── enumerate/
│   │   ├── standardize.py
│   │   ├── mapper.py
│   │   ├── graph_edits.py
│   │   ├── generator.py
│   │   ├── filters.py
│   │   ├── valence.py
│   │   ├── ring_rules.py
│   │   ├── deduplicate.py
│   │   └── scoring.py
│   ├── engines/
│   │   ├── base.py
│   │   ├── command.py
│   │   ├── xtb.py
│   │   ├── crest.py
│   │   ├── pygsm.py
│   │   ├── pysisyphus.py
│   │   ├── pyscf.py
│   │   └── orca.py
│   ├── workflows/
│   │   ├── conformer.py
│   │   ├── geometry.py
│   │   ├── ts_guess.py
│   │   ├── ts_optimize.py
│   │   ├── frequency.py
│   │   ├── irc.py
│   │   ├── validate_ts.py
│   │   ├── reaction_energy.py
│   │   └── refine.py
│   ├── network/
│   │   ├── graph.py
│   │   ├── frontier.py
│   │   ├── selector.py
│   │   ├── grow.py
│   │   ├── paths.py
│   │   └── checkpoint.py
│   ├── io/
│   │   ├── artifacts.py
│   │   ├── xyz.py
│   │   ├── sdf.py
│   │   ├── csv_export.py
│   │   ├── json_store.py
│   │   ├── report_html.py
│   │   └── tables.py
│   ├── runtime/
│   │   ├── executor.py
│   │   ├── serial.py
│   │   ├── process_pool.py
│   │   ├── retry.py
│   │   └── resource.py
│   └── utils/
│       ├── hashes.py
│       ├── logging.py
│       ├── paths.py
│       ├── subprocess.py
│       ├── time.py
│       └── units.py
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 5. 依赖与安装

### 5.1 `environment.yml`

```yaml
name: openreactnet
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - rdkit
  - xtb
  - crest
  - openbabel
  - numpy
  - scipy
  - pandas
  - networkx
  - pydantic>=2
  - pydantic-settings
  - pyyaml
  - typer
  - rich
  - jinja2
  - plotly
  - pytest
  - pytest-cov
  - ruff
  - mypy
  - pip:
      - pysisyphus
      - pygsm
      - pyscf
      - -e .
```

### 5.2 安装命令

```bash
mamba env create -f environment.yml
mamba activate openreactnet
pip install -e ".[dev]"
orn doctor
```

---

## 6. CLI 命令规范

### 6.1 顶层命令

```text
orn init
orn doctor
orn enumerate
orn ts-search
orn network
orn refine
orn report
orn status
orn clean
```

### 6.2 初始化项目

```bash
orn init ./projects/sn2_demo
```

生成目录：

```text
sn2_demo/
├── configs/
├── inputs/
│   └── reactants.yaml
├── runs/
├── results/
├── checkpoints/
├── logs/
└── .orn/
    ├── project.json
    └── environment_manifest.json
```

### 6.3 环境检查

```bash
orn doctor
orn doctor --strict
orn doctor --json > doctor_report.json
```

检查 Python、RDKit、xTB、CREST、pyGSM、Pysisyphus、PySCF、ORCA（可选）、CPU、内存和临时目录，并执行一个小型 xTB 健康检查。

### 6.4 反应枚举

```bash
orn enumerate \
  --reactants "CCl.[OH-]" \
  --charge -1 \
  --multiplicity 1 \
  --config configs/enumerate.yaml \
  --workdir runs/sn2 \
  --overwrite
```

输出：

```text
runs/sn2/
├── inputs/
│   ├── resolved_config.yaml
│   └── reactants.json
├── enumeration/
│   ├── candidate_reactions.csv
│   ├── rejected_reactions.csv
│   ├── reaction_index.json
│   └── structures/
│       ├── rxn_000001_reactants.sdf
│       └── rxn_000001_products.sdf
└── logs/
    └── enumerate.log
```

### 6.5 TS 搜索

```bash
orn ts-search \
  --reaction-id rxn_000001 \
  --workdir runs/sn2 \
  --config configs/ts_xtb.yaml
```

每条反应独立目录：

```text
runs/sn2/reactions/rxn_000001/
├── 00_metadata/
├── 01_reactants/
├── 02_products/
├── 03_conformers/
├── 04_ts_guess/
├── 05_ts_opt/
├── 06_frequency/
├── 07_irc/
├── 08_analysis/
├── logs/
└── result.json
```

### 6.6 网络发现

```bash
orn network \
  --reactants "CCl.[OH-]" \
  --config configs/network_xtb.yaml \
  --workdir runs/sn2_network \
  --resume
```

执行顺序：初始化物种池和前沿池；按层枚举候选；规则筛选和去重；TS/IRC 验证；能垒筛选；扩展网络；写入 checkpoint；满足终止条件后生成报告。

### 6.7 DFT 精修

```bash
orn refine \
  --input runs/sn2_network/results/accepted_reactions.csv \
  --config configs/dft_pyscf.yaml \
  --workdir runs/sn2_network
```

### 6.8 报告生成

```bash
orn report --workdir runs/sn2_network
```

输出：

```text
runs/sn2_network/results/
├── species.csv
├── reactions.csv
├── reactiondata.csv
├── accepted_reactions.csv
├── rejected_reactions.csv
├── ts_results.csv
├── failures.csv
├── network.graphml
├── network.json
├── reactionnetwork.html
└── summary.md
```

---

## 7. 配置文件

### 7.1 `configs/enumerate.yaml`

```yaml
project:
  name: default_enumeration
  random_seed: 42

runtime:
  workers: 1
  fail_fast: false
  keep_scratch: false

input:
  charge: 0
  multiplicity: 1
  sanitize_smiles: true
  atom_mapping: true

enumeration:
  max_break_bonds: 1
  max_form_bonds: 1
  max_candidates_per_parent: 300
  allow_radicals: false
  allow_disconnected_products: true
  enumerate_inter_molecular_bonds: true

filters:
  valence: true
  aromaticity: true
  ring: true
  fused_ring: true
  charge_balance: true
  duplicate: true
  unsupported_elements: true
  max_ring_size: 8
  reject_strained_small_rings: true
  reject_unphysical_bond_orders: true

scoring:
  enabled: true
  retain_top_k: 200
  lewis_penalty_weight: 1.0
  bond_change_penalty_weight: 0.5
```

### 7.2 `configs/ts_xtb.yaml`

```yaml
project:
  name: ts_xtb

runtime:
  workers: 1
  timeout_seconds: 14400
  retry_count: 1
  keep_scratch: false

resources:
  nprocs: 8
  memory_gb: 8
  scratch_root: ./scratch

chemistry:
  charge: 0
  multiplicity: 1
  solvent: null

conformer:
  enabled: true
  engine: crest
  max_conformers: 30
  energy_window_kcal_mol: 8.0
  rmsd_threshold_angstrom: 0.25
  preopt_engine: xtb

low_level:
  engine: xtb
  method: gfn2-xtb
  accuracy: 1.0
  electronic_temperature: 300
  optimization_max_cycles: 300

ts_guess:
  method: gsm
  candidate_count: 5
  gsm_engine: pygsm
  gsm_nodes: 11
  gsm_max_iterations: 50
  convergence_tolerance: 0.005
  max_displacement_angstrom: 0.10

ts_optimization:
  engine: pysisyphus
  max_cycles: 100
  hessian_recalc: 3
  gradient_threshold: 0.0003

frequency:
  enabled: true
  required_imaginary_count: 1
  min_imaginary_frequency_cm1: -50.0

irc:
  enabled: true
  step_length_bohr: 0.1
  max_cycles: 500
  endpoint_rmsd_threshold_angstrom: 0.5
  endpoint_bond_change_match: true

selection:
  max_barrier_kcal_mol: 60.0
  require_irc_pass: true
  require_frequency_pass: true
```

### 7.3 `configs/network_xtb.yaml`

```yaml
project:
  name: default_network
  random_seed: 42

runtime:
  workers: 1
  fail_fast: false
  resume: true
  checkpoint_every_layer: true

network:
  max_layers: 3
  max_species_total: 250
  max_species_per_layer: 100
  max_reactions_per_layer: 300
  max_accepted_reactions_per_layer: 100
  retain_closure_reactions: true
  stop_when_no_new_species: true

enumeration:
  max_break_bonds: 1
  max_form_bonds: 1
  max_candidates_per_parent: 200

selection:
  max_barrier_kcal_mol: 40.0
  max_reaction_energy_kcal_mol: 30.0
  retain_top_k_per_species: 5
  retain_top_k_per_layer: 100
  require_irc_pass: true
  require_frequency_pass: true

deduplication:
  species_key: canonical_mapped_smiles
  reaction_key: canonical_reaction_smiles
  geometry_rmsd_threshold_angstrom: 0.5

checkpoint:
  directory: checkpoints
  write_graphml: true
  write_json: true
```

### 7.4 `configs/dft_pyscf.yaml`

```yaml
runtime:
  workers: 1
  timeout_seconds: 43200

resources:
  nprocs: 8
  memory_gb: 16

dft:
  engine: pyscf
  method: rks
  functional: wb97x-d
  basis: 6-31g(d)
  dispersion: null
  grid_level: 5
  use_gpu: false
  solvent: null

refinement:
  optimize_geometry: false
  frequency: false
  single_point_only: true
  recompute_reactants: true
  recompute_products: true
  recompute_ts: true
```

---

## 8. 核心数据模型

### 8.1 状态与失败码

文件：`src/openreactnet/core/enums.py`

```python
from enum import StrEnum


class ReactionStatus(StrEnum):
    ENUMERATED = "ENUMERATED"
    FILTERED_OUT = "FILTERED_OUT"
    CONFORMER_READY = "CONFORMER_READY"
    TS_GUESS_READY = "TS_GUESS_READY"
    TS_OPTIMIZING = "TS_OPTIMIZING"
    TS_OPTIMIZED = "TS_OPTIMIZED"
    FREQUENCY_PASSED = "FREQUENCY_PASSED"
    IRC_RUNNING = "IRC_RUNNING"
    IRC_PASSED = "IRC_PASSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class FailureCode(StrEnum):
    INVALID_SMILES = "INVALID_SMILES"
    UNSUPPORTED_ELEMENT = "UNSUPPORTED_ELEMENT"
    VALENCE_VIOLATION = "VALENCE_VIOLATION"
    RING_RULE_REJECTED = "RING_RULE_REJECTED"
    DUPLICATE_REACTION = "DUPLICATE_REACTION"
    CONFORMER_FAILED = "CONFORMER_FAILED"
    XTB_FAILED = "XTB_FAILED"
    GSM_FAILED = "GSM_FAILED"
    TSOPT_FAILED = "TSOPT_FAILED"
    FREQUENCY_FAILED = "FREQUENCY_FAILED"
    MULTIPLE_IMAGINARY_FREQUENCIES = "MULTIPLE_IMAGINARY_FREQUENCIES"
    IRC_FAILED = "IRC_FAILED"
    IRC_ENDPOINT_MISMATCH = "IRC_ENDPOINT_MISMATCH"
    BARRIER_TOO_HIGH = "BARRIER_TOO_HIGH"
    TIMEOUT = "TIMEOUT"
    EXTERNAL_ENGINE_ERROR = "EXTERNAL_ENGINE_ERROR"
```

### 8.2 `SpeciesRecord`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpeciesRecord:
    species_id: str
    canonical_smiles: str
    mapped_smiles: str
    charge: int
    multiplicity: int
    atom_count: int
    elements: tuple[str, ...]
    xyz_path: str | None = None
    sdf_path: str | None = None
    energy_hartree: float | None = None
    relative_energy_kcal_mol: float | None = None
    source_layer: int = 0
    parent_reaction_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.3 `ReactionRecord`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReactionRecord:
    reaction_id: str
    reactant_species_ids: tuple[str, ...]
    product_species_ids: tuple[str, ...]
    reactant_smiles: tuple[str, ...]
    product_smiles: tuple[str, ...]
    reaction_smiles: str
    mapped_reaction_smiles: str
    bond_changes: tuple[tuple[int, int, str], ...]
    charge: int
    multiplicity: int
    layer: int
    status: str
    is_closure_reaction: bool = False
    enum_score: float | None = None
    barrier_kcal_mol: float | None = None
    reaction_energy_kcal_mol: float | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.4 `TSResult`

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class TSResult:
    reaction_id: str
    status: str
    ts_xyz_path: str | None
    ts_energy_hartree: float | None
    imaginary_frequency_cm1: float | None
    imaginary_frequency_count: int | None
    irc_forward_species_id: str | None
    irc_reverse_species_id: str | None
    irc_forward_match: bool | None
    irc_reverse_match: bool | None
    barrier_forward_kcal_mol: float | None
    barrier_reverse_kcal_mol: float | None
    reaction_energy_kcal_mol: float | None
    workflow_seconds: float | None
    failure_code: str | None
    metadata: dict[str, Any]
```

---

## 9. 枚举模块规范

### 9.1 输入标准化

文件：`enumerate/standardize.py`

职责：解析 SMILES、检查元素白名单、生成 canonical SMILES、保留电荷、执行原子映射并返回 `SpeciesRecord`。

```python
def standardize_reactants(
    reactant_smiles: list[str],
    charge: int,
    multiplicity: int,
) -> list[SpeciesRecord]:
    ...
```

### 9.2 键编辑生成

文件：`enumerate/graph_edits.py`

必须支持：删除单/双/三键；添加合法单/双/三键；分子内与分子间成键；记录 `bond_changes`；默认禁止直接修改芳香体系内部键。

```python
def generate_bond_edits(
    mols: list,
    max_break_bonds: int,
    max_form_bonds: int,
) -> list["BondEdit"]:
    ...
```

### 9.3 固定过滤顺序

1. RDKit sanitize
2. 元素白名单
3. 电荷守恒
4. 原子数守恒
5. 价态检查
6. 不合理键级检查
7. 小环与稠环规则
8. 芳香性规则
9. 分子碎片规则
10. canonical mapped reaction-SMILES 去重
11. 枚举评分排序和 top-k 截断

```python
from dataclasses import dataclass


@dataclass
class FilterDecision:
    passed: bool
    rule_name: str
    reason_code: str | None
    message: str | None
```

---

## 10. 计算引擎接口

文件：`engines/base.py`

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class CalculationEngine(ABC):
    name: str

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def optimize(
        self,
        xyz_path: Path,
        workdir: Path,
        charge: int,
        multiplicity: int,
        settings: dict[str, Any],
    ) -> "OptimizationResult":
        ...

    @abstractmethod
    def single_point(
        self,
        xyz_path: Path,
        workdir: Path,
        charge: int,
        multiplicity: int,
        settings: dict[str, Any],
    ) -> "SinglePointResult":
        ...
```

### 10.1 xTB

- 调用 `xtb input.xyz --gfn 2 --opt ...`
- 解析总能量、优化几何、梯度和收敛状态
- 保存命令、stdout 和 stderr
- 外部计算失败必须转成结构化结果
- 支持 `--chrg`、`--uhf`、`--parallel` 和溶剂参数

### 10.2 CREST

- 执行构象采样
- 解析 `crest_conformers.xyz`
- 通过能量窗口和 RMSD 去重
- 返回按能量排序的构象

### 10.3 pyGSM

- 输入反应物/产物几何
- 建立路径节点
- 输出最高能节点或多个候选 TS 几何
- 保存全路径结构及路径能量

### 10.4 Pysisyphus

- TS 优化
- 频率分析
- 正反向 IRC
- 输出收敛、频率、IRC 端点
- 每次运行保留独立输入文件和日志

---

## 11. TS 工作流规范

文件：`workflows/ts_optimize.py`

```python
def run_ts_workflow(
    reaction: ReactionRecord,
    config: "TSWorkflowConfig",
    artifact_store: "ArtifactStore",
) -> TSResult:
    """
    1. 准备反应物与产物三维结构
    2. 构象采样和预优化
    3. 匹配反应物/产物构象
    4. GSM 或插值生成多个 TS 猜测
    5. 逐一执行 TSOPT
    6. 执行频率分析
    7. 满足单虚频后执行双向 IRC
    8. 匹配 IRC 端点与目标物种
    9. 计算能垒和反应能
    10. 写入所有工件和结果
    """
```

### 11.1 成功判定

仅同时满足以下条件时标记 `IRC_PASSED`：

- TS 优化收敛
- 虚频数量恰好为 1
- 唯一虚频小于最小阈值
- IRC 两端分别匹配目标反应物和产物
- 原子映射与键变化约束匹配
- 正向能垒不超过阈值
- 所有能量使用一致参考态和单位

### 11.2 失败策略

- 构象失败：`CONFORMER_FAILED`
- GSM 失败：`GSM_FAILED`，允许线性插值重试一次
- TSOPT 失败：依次更换 TS 猜测
- 多虚频：`MULTIPLE_IMAGINARY_FREQUENCIES`
- 无虚频：`FREQUENCY_FAILED`
- IRC 端点不匹配：`IRC_ENDPOINT_MISMATCH`
- 超时：`TIMEOUT`
- 失败不得删除中间工件

---

## 12. 能量与单位规范

文件：`utils/units.py`

```python
HARTREE_TO_KCAL_MOL = 627.509474
```

\[
\Delta E_{\mathrm{rxn}} =
(E_{\mathrm{products}} - E_{\mathrm{reactants}})
\times 627.509474
\]

\[
\Delta E^\ddagger_{\mathrm{forward}} =
(E_{\mathrm{TS}} - E_{\mathrm{reactants}})
\times 627.509474
\]

\[
\Delta E^\ddagger_{\mathrm{reverse}} =
(E_{\mathrm{TS}} - E_{\mathrm{products}})
\times 627.509474
\]

内部能量统一以 Hartree 存储；展示和筛选使用 kcal/mol。字段必须带单位后缀，例如 `_hartree`、`_kcal_mol`。

---

## 13. 网络模型规范

### 13.1 图结构

- 节点：`SpeciesRecord`
- 反应：`ReactionRecord`
- 使用 `networkx.MultiDiGraph`
- 多反应物/产物的超边通过独立反应节点表达

```text
species:sp_000001 ──reactant──> reaction:rxn_000001
species:sp_000002 ──reactant──> reaction:rxn_000001
reaction:rxn_000001 ──product──> species:sp_000003
```

### 13.2 Core/Edge 状态

```python
class SpeciesPool:
    accepted: dict[str, SpeciesRecord]
    frontier: set[str]
    rejected: dict[str, SpeciesRecord]


class ReactionPool:
    accepted: dict[str, ReactionRecord]
    pending: dict[str, ReactionRecord]
    rejected: dict[str, ReactionRecord]
    failed: dict[str, ReactionRecord]
```

### 13.3 单层增长

```python
def grow_one_layer(state: "NetworkState", layer: int) -> "NetworkState":
    parents = state.species_pool.frontier
    candidates = enumerate_reactions(parents, layer=layer)
    filtered = apply_filters(candidates)
    evaluated = run_ts_workflow_batch(filtered)
    accepted = select_reactions(evaluated)

    state.add_accepted(accepted)
    state.update_frontier_from_products(accepted)
    state.write_checkpoint(layer)
    return state
```

### 13.4 准入规则

- `status == IRC_PASSED`
- 正向能垒不高于 `max_barrier_kcal_mol`
- 反应能不高于 `max_reaction_energy_kcal_mol`
- 非重复反应
- 满足元素、原子数和电荷规则
- 每个父物种只保留最低能垒的 top-k 反应
- 每层只保留 top-k 反应
- 已存在产物标记为 `is_closure_reaction=True`

---

## 14. Checkpoint 规范

```text
checkpoints/
├── layer_000/
│   ├── manifest.json
│   ├── species_pool.json
│   ├── reaction_pool.json
│   ├── network_state.json
│   ├── network.graphml
│   └── checksum.sha256
├── layer_001/
└── layer_002/
```

`manifest.json`：

```json
{
  "project_id": "sn2_network",
  "layer": 1,
  "created_at": "2026-08-01T10:00:00+08:00",
  "config_hash": "sha256:...",
  "input_hash": "sha256:...",
  "species_total": 18,
  "reactions_total": 27,
  "accepted_reactions": 8,
  "frontier_species": 6,
  "status": "COMPLETED"
}
```

恢复规则：自动选择最高完成层；配置哈希不一致默认拒绝恢复；`--force-resume` 必须写入覆盖原因；成功反应不得重复运行；失败反应仅在 `--retry-failed` 下重试。

---

## 15. 输出数据表

### 15.1 `reactiondata.csv`

```text
reaction_id
reaction_hash
reactant_smiles
product_smiles
mapped_reaction_smiles
bond_changes_json
layer
status
barrier_kcal_mol
barrier_original_kcal_mol
reverse_barrier_kcal_mol
reaction_energy_kcal_mol
selection_round
is_closure_reaction
frequency_cm1
frequency_count
irc_forward_match
irc_reverse_match
ts_xyz_path
failure_code
failure_message
workflow_seconds
created_at
```

### 15.2 `species.csv`

```text
species_id
canonical_smiles
mapped_smiles
charge
multiplicity
atom_count
elements
source_layer
parent_reaction_id
energy_hartree
relative_energy_kcal_mol
xyz_path
sdf_path
is_frontier
created_at
```

### 15.3 `failures.csv`

```text
reaction_id
layer
stage
failure_code
failure_message
engine
command
workdir
stdout_path
stderr_path
retry_count
created_at
```

### 15.4 `ts_results.csv`

```text
reaction_id
ts_status
ts_energy_hartree
ts_xyz_path
imaginary_frequency_cm1
imaginary_frequency_count
irc_forward_species_id
irc_reverse_species_id
irc_forward_match
irc_reverse_match
barrier_forward_kcal_mol
barrier_reverse_kcal_mol
reaction_energy_kcal_mol
workflow_seconds
failure_code
```

---

## 16. 工件存储规范

```text
<reaction_workdir>/<stage>/
├── input.xyz
├── input.yaml
├── command.txt
├── stdout.log
├── stderr.log
├── output.xyz
├── parsed_result.json
├── metadata.json
└── DONE
```

`DONE` 只在外部命令返回成功、输出存在、输出可解析且最小字段齐全时创建。失败时创建 `FAILED.json`：

```json
{
  "failure_code": "TSOPT_FAILED",
  "message": "Maximum optimization cycles reached",
  "return_code": 1,
  "engine": "pysisyphus",
  "command_path": "command.txt",
  "stdout_path": "stdout.log",
  "stderr_path": "stderr.log",
  "created_at": "2026-08-01T10:00:00+08:00"
}
```

---

## 17. HTML 网络报告

输出：`results/reactionnetwork.html`

必须包含：

- 总物种、候选反应、已验证反应、成功率、失败数
- 按层级或相对能量着色的网络图
- 依据能垒反向映射的边宽
- 物种详情：SMILES、电荷、自旋、能量、结构路径
- 反应详情：反应式、键变化、TS 能量、虚频、IRC、能垒、工件路径
- 层级、状态、最大能垒和 closure reaction 筛选
- CSV、GraphML、JSON 的本地下载链接
- 无后端依赖，浏览器可离线打开

---

## 18. 测试计划

### 18.1 单元测试

| 模块 | 用例 |
|---|---|
| `standardize.py` | 合法/非法 SMILES、元素白名单、电荷保留、canonical SMILES |
| `graph_edits.py` | 成键、断键、跨分子成键、非法索引 |
| `valence.py` | C/N/O/S/P/卤素常见合法与非法价态 |
| `ring_rules.py` | 小环、稠环过滤 |
| `deduplicate.py` | 等价 reaction-SMILES 去重 |
| `units.py` | Hartree 与 kcal/mol 转换 |
| `checkpoint.py` | 写入、读取、哈希不一致恢复拒绝 |
| `selector.py` | 能垒、top-k、闭环反应、层数选择 |
| `csv_export.py` | 字段完整性、单位、空值 |

### 18.2 集成测试

| 场景 | 目标 |
|---|---|
| `orn init` | 创建完整项目结构 |
| `orn doctor` | mock 与真实环境正确报告 |
| `orn enumerate` | 产生候选与拒绝清单 |
| xTB 单点能 | 解析能量和输出结构 |
| CREST 构象 | 返回排序构象或结构化失败 |
| TS mock | 覆盖成功、TSOPT 失败、虚频失败、IRC 失配 |
| `orn network --resume` | 从最后 checkpoint 恢复 |
| `orn report` | 生成 CSV、GraphML、HTML |

### 18.3 基准体系

- 卤代烃与亲核试剂的 SN2 取代
- 简单质子转移
- 小分子消除
- 小分子加成或异构化
- 简单 Diels–Alder，作为后期集成测试

统计指标：候选生成数、筛选误杀率、TS 成功率、IRC 成功率、总耗时和失败类型分布。

---

## 19. 里程碑与验收

### M1：项目骨架（2–3 天）

交付：可安装包；`orn init`；`orn doctor`；Pydantic 配置；日志与工件目录；数据模型；最小测试。

验收：

```bash
mamba activate openreactnet
pip install -e ".[dev]"
orn init ./demo
orn doctor --strict
```

### M2：反应枚举（4–7 天）

交付：RDKit 标准化、映射、键编辑、筛选、`orn enumerate`、CSV/SDF。

验收：

```bash
orn enumerate \
  --reactants "CCl.[OH-]" \
  --config configs/enumerate.yaml \
  --workdir runs/sn2
```

### M3：xTB 与构象（3–5 天）

交付：xTB 单点/优化、CREST 构象、命令封装、失败处理。

验收：水、乙醇和氯甲烷可完成优化并生成结构化结果。

### M4：TS 与 IRC（7–14 天）

交付：pyGSM、Pysisyphus、频率、IRC、`orn ts-search`。

验收：至少一个 SN2 或小分子反应完成 TS 收敛、单虚频和双向 IRC 匹配。

### M5：网络增长与报告（5–8 天）

交付：Core/Edge 图、分层扩展、checkpoint、`orn network`、`orn report`、HTML。

验收：一个 1–2 层受限网络可完成，中断后可恢复且不重复计算。

### M6：DFT 精修（3–5 天）

交付：PySCF 单点能、xTB/DFT 对照、`orn refine`。

验收：已接受反应能够输出精修能垒对照与全部输入参数。

---

## 20. 编码约束

- Python 3.11
- 所有公开函数有类型标注
- 外部程序只允许 `subprocess.run(..., shell=False)`
- 禁止拼接 shell 字符串
- 禁止吞掉异常，必须形成结构化失败结果
- 禁止在工作流写死配置阈值
- 禁止工作流直接使用全局变量
- 非 `fail_fast=true` 情形下，单条反应失败不得中止全批次
- 每次运行都要保存 `resolved_config.yaml`、`environment_manifest.json`、`run_manifest.json`
- 每条反应拥有稳定、可重复的 `reaction_id`
- 任一结果都能从工件目录重建
- 时间使用带时区的 ISO 8601
- 能量字段必须带单位后缀

---

## 21. M1 初始化代码骨架

### 21.1 `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "openreactnet"
version = "0.1.0"
description = "Local CLI reaction-network discovery and transition-state workflow"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.7",
  "pydantic-settings>=2.2",
  "PyYAML>=6.0",
  "typer>=0.12",
  "rich>=13.7",
  "numpy>=1.26",
  "pandas>=2.2",
  "networkx>=3.2",
  "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.5",
  "mypy>=1.10",
]

[project.scripts]
orn = "openreactnet.cli.app:app"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### 21.2 `src/openreactnet/cli/app.py`

```python
import typer

from openreactnet.cli.doctor_cmd import doctor
from openreactnet.cli.enumerate_cmd import enumerate_reactions
from openreactnet.cli.init_cmd import init_project
from openreactnet.cli.network_cmd import run_network
from openreactnet.cli.refine_cmd import refine
from openreactnet.cli.report_cmd import report
from openreactnet.cli.ts_cmd import ts_search

app = typer.Typer(
    name="orn",
    help="OpenReactNet: local reaction-network discovery CLI.",
    no_args_is_help=True,
)

app.command("init")(init_project)
app.command("doctor")(doctor)
app.command("enumerate")(enumerate_reactions)
app.command("ts-search")(ts_search)
app.command("network")(run_network)
app.command("refine")(refine)
app.command("report")(report)
```

### 21.3 `src/openreactnet/cli/init_cmd.py`

```python
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def init_project(
    project_dir: Path = typer.Argument(..., help="Target project directory."),
) -> None:
    directories = (
        "configs",
        "inputs",
        "runs",
        "results",
        "checkpoints",
        "logs",
        ".orn",
    )

    if project_dir.exists() and any(project_dir.iterdir()):
        raise typer.BadParameter(f"Directory is not empty: {project_dir}")

    for relative_path in directories:
        (project_dir / relative_path).mkdir(parents=True, exist_ok=True)

    (project_dir / ".orn" / "project.json").write_text(
        '{\n  "name": "' + project_dir.name + '",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    console.print(f"[green]Initialized OpenReactNet project:[/green] {project_dir}")
```

### 21.4 `src/openreactnet/core/models.py`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunManifest:
    run_id: str
    command: str
    started_at: str
    config_path: str
    config_hash: str
    working_directory: str
    environment_manifest_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 21.5 `tests/unit/test_init_cmd.py`

```python
from typer.testing import CliRunner

from openreactnet.cli.app import app


def test_init_creates_project_structure(tmp_path):
    runner = CliRunner()
    project_dir = tmp_path / "demo"

    result = runner.invoke(app, ["init", str(project_dir)])

    assert result.exit_code == 0
    assert (project_dir / "configs").exists()
    assert (project_dir / "runs").exists()
    assert (project_dir / ".orn" / "project.json").exists()
```

---

## 22. 首次开发任务清单

1. 建立项目目录与 `pyproject.toml`
2. 完成 `orn init`
3. 完成 `orn doctor` 和环境清单
4. 定义状态枚举、失败码、数据模型
5. 实现 YAML 配置加载、覆盖、校验和配置哈希
6. 实现运行目录、日志和工件存储
7. 实现 RDKit SMILES 标准化
8. 实现单键断裂/成键候选生成
9. 实现价态、环、重复反应过滤
10. 完成 `orn enumerate` 和 CSV 输出
11. 接入 xTB 单点和优化
12. 接入 CREST 构象
13. 先建立 TS 工作流 mock 测试，再接 pyGSM
14. 接入 Pysisyphus TSOPT、频率和 IRC
15. 完成网络状态机、checkpoint 和恢复
16. 完成报告与 Cytoscape.js HTML
17. 最后接入 PySCF 精修和多进程

---

## 23. V0.1 冻结条件

- `orn doctor --strict` 在目标机器稳定通过
- `orn enumerate` 对基准反应输出稳定可重复
- 至少一个基准反应完整通过 TS、单虚频和双向 IRC
- 至少一个 1–2 层网络可以完整生成且可从 checkpoint 恢复
- 所有失败任务进入 `failures.csv` 并指向真实日志和工件
- `reactiondata.csv`、`species.csv`、`ts_results.csv` 字段冻结
- `reactionnetwork.html` 能离线打开
- 修改 YAML 参数不要求修改业务逻辑
- 新机器可按 README 在无远程服务条件下重跑示例

---

## 24. 合规边界

本项目仅基于公开论文、开放依赖与独立工程实现构建。禁止复制、反编译、提取或复用 ReactNet 的受版权保护二进制模块、专有服务协议、授权校验、模型权重、内部参数或品牌标识。目标是可验证的功能等价替代，而非源代码或服务的逐字复制。
