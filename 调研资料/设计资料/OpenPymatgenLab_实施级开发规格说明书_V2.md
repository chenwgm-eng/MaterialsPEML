# OpenPymatgenLab 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openpymatgenlab`  
**CLI**：`opmat`  
**目标用户**：BatteryEMCL Lab 的无机晶体材料分支、计算材料研究员、材料数据工程师  
**部署模式**：本地 Python/Conda；不依赖固定私有服务；可选择导入用户授权数据或使用合法公共 API

---

## 0. 文档定位

本文件是实施级规格，而不是 API 速查或概念架构。开发人员应能够依据本文件创建仓库、搭建目录、实现 CLI、定义数据模式、编写测试、接入本地材料数据与 BatteryEMCL Lab 湿数据中间件。

OpenPymatgenLab 是无机晶体材料的**结构数据基础设施**，负责可信结构对象、结构变换、相稳定性分析、表面模型、材料数据溯源和计算任务交接。它不负责 DFT 求解、机器学习性质预测或电芯级仿真；这些能力分别由计算引擎、性质模型与 OpenBatterySim 承担。

---

## 1. 产品边界

### 1.1 必须交付

- CIF、POSCAR/CONTCAR、XSF、XYZ、JSON 结构对象的导入、校验、标准化与导出
- `Structure`、`Composition`、`Lattice` 的不可变快照与内容哈希
- primitive / conventional standard structure、空间群、Wyckoff、晶格/密度/配位分析
- 超胞、占位/掺杂、空位、间隙缺陷的受约束生成
- slab、对称等价终止面、真空层、吸附位点候选生成
- 计算条目导入、参考态一致性校验、相图、能量凸包、分解反应
- XRD 模拟、基础弹性张量导入分析
- 运行清单、工件索引、失败隔离、缓存和可恢复批处理
- BatteryEMCL Lab 事件/湿数据中间件的文件契约与本地 outbox 事件

### 1.2 明确不交付

- 不执行 VASP、QE、CP2K、LAMMPS 或 NEB；只生成标准化输入交接包
- 不把 DFT 的带隙、能量、磁性结果视为实验真值
- 不直接抓取受限或商业材料数据库
- 不用结构相似性替代实验可合成性、安全性、成本或电化学性能
- 不在没有电荷补偿策略的情况下自动生成带电缺陷

### 1.3 电池材料应用边界

优先支持正极、负极、无机固态电解质和导电添加剂的晶体结构工作流。聚合物电解质不应被强行转换为周期晶体流程；应路由至高分子表示与分子模拟分支。

---

## 2. 最终集成架构

```text
用户 / Agent / LIMS-ELN 中间件
          │
          ▼
       opmat CLI
          │
          ├── 输入解析：CIF / POSCAR / JSON / entries / CSV
          ├── Schema 验证：结构、能量、元数据、许可证
          ├── Structure Store：不可变对象与哈希
          ├── 分析：标准化、对称性、配位、XRD
          ├── 变换：supercell / dopant / defect / slab
          ├── 热力学：entries -> PhaseDiagram -> hull
          ├── 交接：VASP/QE/LAMMPS/CGCNN 任务包
          └── outbox：事件、报告、审计工件
                    │
   ┌────────────────┼──────────────────┐
   ▼                ▼                  ▼
OpenLAMMPSFlow  性质预测服务      BatteryEMCL 湿数据中间件
```

### 2.1 分层原则

| 层 | 职责 | 禁止事项 |
|---|---|---|
| CLI | 参数解析、退出码、用户可读输出 | 不放科学算法 |
| Domain | 结构 ID、变换请求、结果对象、状态机 | 不直接读写文件 |
| Adapters | pymatgen、spglib、文件格式、可选 API | 不含业务规则 |
| Workflows | 编排、缓存、工件、断点恢复 | 不硬编码路径 |
| Validation | 化学/几何/数据完整性校验 | 不静默修正关键数据 |
| Integration | 任务包与事件 | 不保存第三方密钥 |

---

## 3. 目录与逐文件职责

```text
openpymatgenlab/
├── pyproject.toml
├── environment.yml
├── README.md
├── configs/
│   ├── default.yaml
│   ├── battery_materials.yaml
│   ├── slab.yaml
│   ├── phase_diagram.yaml
│   └── integration.yaml
├── schemas/
│   ├── structure_record.v1.json
│   ├── computed_entry.v1.json
│   ├── task_event.v1.json
│   └── material_sample_link.v1.json
├── src/openpymatgenlab/
│   ├── __init__.py
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── import_cmd.py
│   │   ├── convert_cmd.py
│   │   ├── analyze_cmd.py
│   │   ├── transform_cmd.py
│   │   ├── slab_cmd.py
│   │   ├── phase_cmd.py
│   │   ├── xrd_cmd.py
│   │   ├── export_cmd.py
│   │   ├── batch_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── enums.py
│   │   ├── models.py
│   │   ├── errors.py
│   │   ├── identifiers.py
│   │   └── units.py
│   ├── adapters/
│   │   ├── pymatgen_io.py
│   │   ├── cif_adapter.py
│   │   ├── poscar_adapter.py
│   │   ├── symmetry_adapter.py
│   │   ├── phase_diagram_adapter.py
│   │   ├── surface_adapter.py
│   │   ├── xrd_adapter.py
│   │   └── local_dataset_adapter.py
│   ├── validation/
│   │   ├── structure.py
│   │   ├── chemistry.py
│   │   ├── geometry.py
│   │   ├── entries.py
│   │   └── transforms.py
│   ├── workflows/
│   │   ├── import_structure.py
│   │   ├── standardize.py
│   │   ├── analyze.py
│   │   ├── supercell.py
│   │   ├── substitution.py
│   │   ├── defect.py
│   │   ├── slab.py
│   │   ├── phase_diagram.py
│   │   ├── task_package.py
│   │   └── batch.py
│   ├── store/
│   │   ├── artifact_store.py
│   │   ├── structure_store.py
│   │   ├── cache.py
│   │   └── manifest.py
│   ├── integration/
│   │   ├── task_contract.py
│   │   ├── outbox.py
│   │   ├── sample_link.py
│   │   └── eln_bridge.py
│   ├── report/
│   │   ├── markdown.py
│   │   ├── html.py
│   │   └── plots.py
│   └── utils/
│       ├── hashes.py
│       ├── logging.py
│       ├── paths.py
│       └── json.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
└── examples/
    ├── lfp/
    ├── nmc811/
    ├── llzo/
    └── graphite/
```

---

## 4. 依赖与环境

### 4.1 核心依赖

```yaml
name: openpymatgenlab
channels: [conda-forge]
dependencies:
  - python=3.11
  - pymatgen
  - spglib
  - numpy
  - scipy
  - pydantic>=2
  - typer
  - rich
  - pandas
  - pyarrow
  - pyyaml
  - jsonschema
  - pytest
  - pip
  - pip:
      - orjson
      - structlog
```

### 4.2 可选依赖组

```toml
[project.optional-dependencies]
plot = ["plotly>=5", "kaleido"]
ml = ["torch", "torch-geometric"]
lammps = ["lammps"]
remote = ["requests", "httpx"]
```

`opmat doctor --strict` 必须输出：Python、pymatgen、spglib 版本；可读写格式；可选依赖；本地数据目录；磁盘空间；默认配置哈希。若未安装可选依赖，非相关子命令仍可使用。

---

## 5. 统一标识与数据模型

### 5.1 标识规范

| 标识 | 格式 | 语义 |
|---|---|---|
| `structure_id` | `str_<sha256前16位>` | 标准化结构内容哈希 |
| `material_id` | 用户/中间件定义 | 研发对象，例如候选材料 |
| `sample_id` | LIMS/ELN 样品 ID | 实体样品批次 |
| `transform_id` | `trf_<uuid7>` | 一次结构变换 |
| `entry_id` | `ent_<source>_<id>` | 热力学计算条目 |
| `run_id` | `YYYYMMDDTHHMMSSZ_<slug>` | CLI 运行 |
| `task_id` | `tsk_<uuid7>` | 下游计算任务 |

结构 ID 的哈希输入必须包含：canonical lattice matrix、fractional coordinates、species/occupancy、site properties 的许可白名单、charge、标准化策略版本。不得对文件字节直接哈希来作为等价结构 ID。

### 5.2 Pydantic 数据模型

```python
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["file", "user", "local_dataset", "api", "derived"]
    source_uri: str | None = None
    source_record_id: str | None = None
    license: str | None = None
    retrieved_at: str | None = None
    parent_structure_ids: list[str] = Field(default_factory=list)


class StructureRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    structure_id: str
    material_id: str | None = None
    canonical_structure_json: dict[str, Any]
    original_file_path: str | None = None
    original_format: str
    composition_formula: str
    reduced_formula: str
    nsites: int = Field(gt=0)
    charge: float | None = None
    is_ordered: bool
    standardization: Literal["none", "primitive", "conventional"]
    symmetry_tolerance_a: float = Field(gt=0)
    provenance: Provenance
    warnings: list[str] = Field(default_factory=list)


class ComputedEntryRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    entry_id: str
    composition: str
    energy_ev: float
    energy_per_atom_ev: float
    calculation_method: str
    functional: str | None = None
    hubbard_settings: dict[str, float] | None = None
    correction_scheme: str | None = None
    reference_set_id: str
    source: Provenance


class TaskEvent(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str
    event_type: Literal[
        "structure.imported", "structure.standardized", "structure.transformed",
        "phase_diagram.completed", "task.package.created", "validation.failed"
    ]
    occurred_at: str
    run_id: str
    structure_ids: list[str]
    material_id: str | None = None
    sample_ids: list[str] = Field(default_factory=list)
    artifact_paths: list[str]
    payload: dict[str, Any]
```

### 5.3 结构状态机

```text
RAW_FILE
  -> PARSED
  -> VALIDATED
  -> STANDARDIZED
  -> ANALYZED
  -> TRANSFORMED (可重复)
  -> PACKAGED_FOR_COMPUTE
  -> LINKED_TO_SAMPLE (可选)

任一步 -> INVALID / FAILED
```

`RAW_FILE` 与 `STANDARDIZED` 必须同时保留；不得覆盖原始输入。`INVALID` 的文件和错误日志仍需保存在运行目录，便于审计。

---

## 6. CLI 完整规范

### 6.1 顶层命令

```bash
opmat init PATH
opmat doctor [--strict] [--json]
opmat import FILE [--format auto] [--material-id ID] [--standardize primitive|conventional|none]
opmat convert INPUT --to cif|poscar|json|xyz --output FILE
opmat analyze INPUT [--symprec A] [--angle-tolerance DEG] [--xrd]
opmat transform supercell INPUT --matrix "2,0,0;0,2,0;0,0,1"
opmat transform substitute INPUT --site-selector "Fe" --from Fe --to Mn --fraction 0.125
opmat transform defect vacancy INPUT --species Li --supercell "2,2,1" --charge-state 0
opmat slab INPUT --miller 0,1,0 --min-slab-a 12 --min-vacuum-a 15
opmat phase build --entries entries.jsonl --chemsys Li-Fe-P-O
opmat phase analyze --phase-diagram results/phase_diagram.json --composition LiFePO4
opmat xrd simulate INPUT --wavelength CuKa --two-theta 10:90:0.02
opmat export task-package --structure STRUCTURE.json --engine lammps|vasp|qe|cgcnn
opmat batch run --manifest jobs.csv --workers 1
opmat status RUN_ID
```

### 6.2 全局参数

| 参数 | 默认值 | 规则 |
|---|---:|---|
| `--workdir` | 自动生成 | 必须为空目录或运行目录 |
| `--config` | `configs/default.yaml` | 合并后必须写入 resolved config |
| `--overwrite` | false | 仅允许覆盖明确输出路径 |
| `--json` | false | stdout 输出机器可读 JSON |
| `--log-level` | INFO | DEBUG 不得输出敏感配置 |
| `--fail-fast` | false | 批处理默认失败隔离 |
| `--seed` | 42 | 对随机掺杂/缺陷选择生效 |

### 6.3 退出码

| 代码 | 名称 | 情况 |
|---:|---|---|
| 0 | `SUCCESS` | 全部任务成功 |
| 1 | `PARTIAL_SUCCESS` | 批处理存在失败 |
| 2 | `USAGE_ERROR` | CLI 参数或配置错误 |
| 3 | `INPUT_INVALID` | 结构/条目格式或科学约束无效 |
| 4 | `DEPENDENCY_UNAVAILABLE` | 引擎或可选依赖缺失 |
| 5 | `COMPUTATION_FAILED` | pymatgen/spglib/数值计算失败 |
| 6 | `PROVENANCE_VIOLATION` | 数据来源/许可/参考态不合规 |
| 7 | `INTEGRATION_FAILED` | outbox/下游任务包失败 |

### 6.4 示例：LFP 结构导入与标准化

```bash
opmat import examples/lfp/LiFePO4.cif \
  --material-id MAT-LFP-001 \
  --standardize conventional \
  --symprec 0.1 \
  --workdir runs/lfp_import
```

预期工件：

```text
runs/lfp_import/
├── inputs/LiFePO4.cif
├── results/structure.raw.json
├── results/structure.conventional.json
├── results/structure.conventional.cif
├── results/analysis.json
├── results/validation.json
├── manifest.json
├── report.md
└── logs/opmat.log
```

---

## 7. 输入、标准化与校验

### 7.1 支持格式与策略

| 格式 | 读取 | 写入 | 备注 |
|---|---|---|---|
| CIF | 是 | 是 | 优先保留原始 CIF 与 parser warning |
| POSCAR/CONTCAR | 是 | 是 | 必须保留元素顺序和 selective dynamics 信息（若存在） |
| JSON | 是 | 是 | 使用 StructureRecord 或 pymatgen JSON |
| XYZ | 是 | 是 | 默认非周期；转周期需显式 lattice |
| XSF | 是 | 可选 | 仅依赖 adapter 可用性 |
| LAMMPS data | 仅交接 | 可选 | 由 OpenLAMMPSFlow 负责主解析 |

### 7.2 结构校验顺序

```text
文件存在/大小/编码
  -> 格式解析
  -> nsites > 0
  -> lattice 行列式 > eps（周期结构）
  -> site 坐标有限且落在允许范围
  -> occupancy 在 (0, 1]
  -> 元素/氧化态 token 合法
  -> 距离碰撞检查
  -> 可选电荷/组成检查
  -> 对称性可解析性
```

### 7.3 不允许静默修复

以下行为必须要求显式参数，并在 manifest 中留下变更记录：

- 去除部分占位或无序位点
- 归一化/重整化 occupancy
- 删除溶剂、客体、氢或“异常”原子
- 自动推断电荷补偿
- 强制 primitive/conventional 转换
- 自动合并过近原子

### 7.4 关键错误码

| 错误码 | 触发条件 | 默认修复建议 |
|---|---|---|
| `STR001` | 不支持或无法解析的格式 | 指定 `--format`，或转换为 CIF/POSCAR |
| `STR002` | 晶格奇异/近奇异 | 检查 cell 参数和单位 |
| `STR003` | 坐标 NaN/Inf 或 site 为空 | 修复原始结构文件 |
| `STR004` | 原子碰撞 | 检查占位、坐标、单位或结构模型 |
| `STR005` | 非整数占位无后续策略 | 指定 `--allow-disordered` 或先有序化 |
| `SYM001` | 对称性失败 | 调整 `symprec`，保留低对称结果 |
| `PRV001` | 缺失来源/许可证 | 补充 provenance 元数据 |

---

## 8. 结构标准化与分析

### 8.1 标准化策略

```yaml
standardization:
  default: conventional
  symprec_a: 0.1
  angle_tolerance_deg: 5.0
  preserve_site_properties: [magmom, oxidation_state]
  refuse_disordered_for_dft: true
```

- `primitive`：适用于降低 DFT 单胞成本、能带/DOS 等任务。
- `conventional`：适用于表面、晶面、界面和跨样品比较。
- `none`：保留实验/用户原始表示，用于数据对齐。

标准化前后必须输出：组成、site 数、lattice、体积、空间群、变换矩阵（如可用）、结构匹配结果和 warnings。

### 8.2 分析输出

```json
{
  "structure_id": "str_a1b2c3d4e5f6a7b8",
  "formula": "LiFePO4",
  "spacegroup": {"symbol": "Pnma", "number": 62},
  "lattice": {"a_a": 10.33, "b_a": 6.01, "c_a": 4.69, "volume_a3": 291.2},
  "density_g_cm3": 3.60,
  "nsites": 28,
  "is_ordered": true,
  "coordination_summary": [{"species": "Fe", "cn": 6}],
  "warnings": []
}
```

### 8.3 几何与配位规则

- 周期距离必须调用结构对象的 PBC 距离方法，不得直接相减 Cartesian 坐标。
- 配位数需声明策略：CrystalNN、VoronoiNN 或距离截断；不同策略不得混写为同一实验结论。
- 密度应由晶胞质量和体积计算，单位固定为 g/cm3。
- 对含无序或部分占位结构，所有局部环境指标都必须带 `DISORDER_SENSITIVE` 标记。

---

## 9. 变换工作流

### 9.1 超胞

#### 请求模式

```yaml
operation: supercell
input_structure_id: str_xxx
matrix:
  - [2, 0, 0]
  - [0, 2, 0]
  - [0, 0, 1]
max_sites: 2000
```

#### 校验

- 矩阵必须是 3x3 整数矩阵。
- `abs(det(matrix)) >= 1`。
- 输出 site 数等于输入 site 数乘以 `abs(det)`。
- site 数超过 `max_sites` 则拒绝，防止内存/下游 DFT 爆炸。

### 9.2 掺杂/替位

掺杂必须以**明确位点选择**、**超胞大小**、**目标浓度**和**电荷补偿策略**为输入。

```bash
opmat transform substitute LiFePO4.cif \
  --from Fe --to Mn \
  --site-selector "species == 'Fe'" \
  --fraction 0.125 \
  --supercell 2,1,1 \
  --enumeration ordered \
  --workdir runs/lfp_mn_doping
```

#### 核心算法

```python
def plan_substitution(structure, selector, fraction, supercell, max_configs):
    sc = make_supercell(structure, supercell)
    candidates = select_sites(sc, selector)
    n_replace = round_half_up(fraction * len(candidates))
    if n_replace < 1:
        raise DomainError("TRF021", "supercell too small for requested fraction")
    configs = enumerate_symmetry_distinct_subsets(sc, candidates, n_replace, max_configs)
    return rank_by_minimum_pair_repulsion(configs)
```

V0.1 默认只生成有序近似构型；随机合金、SQS 和有限温度无序需作为后续模块，不得默认假装精确描述实验无序。

### 9.3 空位与间隙缺陷

```yaml
operation: defect
kind: vacancy
species: Li
supercell: [2, 2, 1]
charge_state: 0
charge_compensation:
  mode: explicit_none
```

缺陷记录必须包含：母相结构 ID、超胞矩阵、被移除/插入位点、分数/笛卡尔坐标、电荷态、补偿模式、对称等价类、生成器版本。

若用户指定非零电荷态，V0.1 只生成结构和 DFT 交接元数据，必须提示：形成能还依赖费米能级、化学势、有限尺寸修正和电荷校正，不能在此模块中直接给出“稳定性”结论。

---

## 10. 表面、晶面与吸附位点

### 10.1 slab 命令

```bash
opmat slab LiFePO4.cif \
  --miller 0,1,0 \
  --standardize conventional \
  --min-slab-a 12.0 \
  --min-vacuum-a 15.0 \
  --center-slab \
  --max-normal-search 2 \
  --workdir runs/lfp_010_slab
```

### 10.2 slab 配置

```yaml
slab:
  miller_index: [0, 1, 0]
  min_slab_size_a: 12.0
  min_vacuum_size_a: 15.0
  center_slab: true
  in_unit_planes: true
  primitive: false
  max_normal_search: 2
  symmetrize: false
  max_terminations: 20
```

### 10.3 输出与风险标记

```text
results/
├── parent_conventional.cif
├── slab_001.vasp
├── slab_001.cif
├── slab_001.metadata.json
├── terminations.csv
├── adsorption_sites.sites.json
└── slab_report.md
```

`terminations.csv` 字段：

```text
slab_id,miller_h,miller_k,miller_l,termination_id,nsites,slab_thickness_a,
vacuum_thickness_a,surface_area_a2,is_symmetric,net_charge_estimate,warnings
```

### 10.4 必须提示的物理限制

- `get_slabs()` 可能为空，必须处理空结果，禁止直接取第一项。
- 低 Miller 指数不自动代表实验主要暴露面；需与表面能、动力学、颗粒形貌和实验表征结合。
- slab 净电荷或极性表面不能直接用于总能比较，需下游重构/补偿方案。
- 吸附位点只是几何候选，吸附能需由下游 DFT 或受验证势函数计算。

---

## 11. 相图与能量凸包

### 11.1 条目输入格式

`entries.jsonl` 每行符合 `ComputedEntryRecord`。最小示例：

```json
{"schema_version":"1.0","entry_id":"ent_local_001","composition":"LiFePO4","energy_ev":-123.456,"energy_per_atom_ev":-17.6366,"calculation_method":"DFT","functional":"PBE+U","hubbard_settings":{"Fe":4.0},"correction_scheme":"compatibility_v1","reference_set_id":"li-fe-p-o_pbeu_v1","source":{"source_type":"local_dataset","source_uri":"data/entries.jsonl","license":"internal"}}
```

### 11.2 兼容性门禁

只有满足下列条件的条目可进入同一 hull：

- 相同或明确兼容的 exchange-correlation functional
- Hubbard U 设置相容
- 相同 correction scheme / compatibility pipeline
- 能量单位一致，且为总能或每原子能可无损转换
- 元素化学势参考与版本一致
- 同一 `reference_set_id`

不满足时拒绝：`PD001_INCOMPATIBLE_REFERENCE_SET`。禁止“尽量画一张图”。

### 11.3 工作流伪代码

```python
def build_phase_diagram(entries, chemsys, reference_set_id):
    selected = [e for e in entries if e.reference_set_id == reference_set_id]
    validate_chemsys(selected, chemsys)
    validate_energy_consistency(selected)
    pmg_entries = to_computed_entries(selected)
    pd = PhaseDiagram(pmg_entries)
    stable = [e.entry_id for e in pd.stable_entries]
    return serialize_phase_diagram(pd, stable)


def analyze_composition(pd, composition):
    comp = Composition(composition)
    e_hull = pd.get_e_above_hull(ComputedEntry(comp, 0.0), allow_negative=True)
    decomposition = pd.get_decomposition(comp)
    return e_hull, decomposition
```

实现时不得用 `energy=0` 的虚构条目直接计算真实相的 `e_above_hull`；分析已有条目时应使用它自身计算能量，分析假想组成时必须明确使用的模型能量来源。

### 11.4 输出

```json
{
  "phase_diagram_id": "pd_li_fe_p_o_20260801",
  "chemsys": ["Li", "Fe", "P", "O"],
  "reference_set_id": "li-fe-p-o_pbeu_v1",
  "stable_entry_ids": ["..."],
  "entries_count": 87,
  "excluded_entries": [{"entry_id":"...","reason":"PD001"}],
  "software": {"pymatgen":"..."}
}
```

### 11.5 电池材料解释规则

- `energy_above_hull` 是给定计算框架/化学势下的热力学相稳定性指标，不是循环寿命、倍率、界面稳定性或可规模合成性的直接预测。
- 对锂化/脱锂路径，应使用一致的 Li 化学势和端元；电压曲线计算另属专用工作流。
- 含氧化态变化、磁有序、强关联的过渡金属材料必须在报告中标注方法敏感性。

---

## 12. XRD、弹性与其他分析

### 12.1 XRD 模拟

```bash
opmat xrd simulate LiFePO4.cif \
  --wavelength CuKa \
  --two-theta 10:90:0.02 \
  --output runs/lfp_xrd/results
```

输出：`xrd_peaks.csv`、`xrd_pattern.csv`、`xrd_pattern.png`、`xrd_manifest.json`。

`xrd_peaks.csv`：

```text
h,k,l,two_theta_deg,d_spacing_a,intensity_rel,structure_id,radiation
```

需要明确：模拟 XRD 不包括仪器展宽、择优取向、晶粒尺寸、应变、杂相比例与非晶背景，不能直接当作实验谱图拟合结果。

### 12.2 弹性张量导入分析

只接受显式 Voigt 单位和坐标约定：

```yaml
elastic_tensor:
  unit: GPa
  convention: voigt_6x6
  matrix: [[...], [...], ...]
```

输出 Voigt/Reuss/Hill 模量、各向异性指标与机械稳定性检查；但必须记录张量来自实验、DFT 还是模型预测。

---

## 13. 任务交接包

### 13.1 下游引擎包

```bash
opmat export task-package \
  --structure runs/lfp_import/results/structure.conventional.json \
  --engine lammps \
  --template configs/lammps_lfp.yaml \
  --material-id MAT-LFP-001 \
  --sample-id SMP-LFP-20260801-01
```

```text
results/task_package_lammps/
├── structure.cif
├── structure.json
├── task_request.json
├── provenance.json
├── validation.json
└── README.md
```

### 13.2 `task_request.json`

```json
{
  "schema_version": "1.0",
  "task_id": "tsk_019...",
  "task_type": "lammps.prepare",
  "material_id": "MAT-LFP-001",
  "sample_ids": ["SMP-LFP-20260801-01"],
  "structure_id": "str_a1b2c3d4e5f6a7b8",
  "input_artifacts": ["structure.cif", "structure.json"],
  "requested_properties": ["diffusion_coefficient"],
  "constraints": {"temperature_k": 300},
  "provenance": {"parent_run_id": "..."}
}
```

### 13.3 LIMS/ELN 关联规则

- `material_id` 代表候选材料或组成概念；`sample_id` 代表实际制备批次；二者不可混用。
- 计算结构可关联多个样品，前提是写入关联类型：`nominal_composition_match`、`xrd_refined_structure_match`、`assumed_prototype` 或 `derived_model`。
- 从 ELN 返回的 XRD、电化学、ICP、SEM 等结果必须保留仪器、方法、样品、时间与原始文件哈希；OpenPymatgenLab 只消费结构相关的标准化摘要，不修改原始实验记录。

---

## 14. 事件与本地 Outbox

本地优先模式不要求在线消息队列。每个运行可写 `outbox/events.jsonl`，由 BatteryEMCL 中间件或定时同步器读取。

```json
{"event_id":"evt_...","event_type":"structure.standardized","occurred_at":"2026-08-01T03:00:00Z","run_id":"20260801T030000Z_lfp","structure_ids":["str_..."],"material_id":"MAT-LFP-001","sample_ids":[],"artifact_paths":["results/structure.conventional.json"],"payload":{"spacegroup_number":62}}
```

幂等键为 `event_type + run_id + sorted(structure_ids) + artifact_hash`。同步成功后保留事件并记录 delivery receipt，不删除审计证据。

---

## 15. 可复现性、缓存与恢复

### 15.1 Manifest

```json
{
  "run_id": "20260801T030000Z_lfp",
  "command": "opmat import ...",
  "started_at": "...",
  "finished_at": "...",
  "status": "SUCCESS",
  "inputs": [{"path":"inputs/LiFePO4.cif","sha256":"..."}],
  "config_sha256": "...",
  "environment": {"python":"3.11", "pymatgen":"...", "spglib":"..."},
  "artifacts": [{"path":"results/structure.conventional.json","sha256":"..."}],
  "warnings": []
}
```

### 15.2 缓存键

```text
cache_key = sha256(
  operation_name + schema_version + input_structure_id +
  normalized_parameters_json + pymatgen_version + spglib_version
)
```

缓存仅复用确定性操作。对随机枚举、随机掺杂或将来 ML 模型调用，seed 与模型哈希必须进入缓存键。

---

## 16. 错误模型与重试

```python
class OpenPymatgenLabError(Exception):
    code: str
    stage: str
    retryable: bool
    details: dict
```

| 类别 | 可重试 | 示例 |
|---|---|---|
| CLI/Schema | 否 | 参数错误、未知配置键 |
| 文件/结构 | 否 | CIF 损坏、原子碰撞 |
| 对称性 | 否，需变更参数 | 容差不合适、无序结构 |
| 资源 | 是 | 磁盘暂满、临时 I/O 错误 |
| 可选 API | 是 | 网络超时；本地模式不能阻塞核心流程 |
| 科学一致性 | 否 | 相图 reference set 不一致 |

批运行时生成：

```text
results/batch_summary.csv
job_id,status,error_code,error_message,primary_artifact,run_id
```

---

## 17. 测试矩阵

### 17.1 单元测试

| 模块 | 输入 | 断言 |
|---|---|---|
| CIF parser | 正常 LFP CIF | formula、nsites、lattice 可读 |
| POSCAR parser | selective dynamics POSCAR | 元素顺序/坐标信息保留 |
| Structure hash | 等价结构不同文件格式 | `structure_id` 相同 |
| Standardize | 低/高对称 fixture | primitive/conventional 稳定 |
| Geometry | 人工重叠结构 | `STR004` |
| Supercell | 2x2x1 | site 数与 det 一致 |
| Substitute | Fe -> Mn | 掺杂数与浓度误差规则正确 |
| Defect | Li vacancy | 父结构/位点/provenance 完整 |
| Slab | Miller (0,1,0) | 空 slab 安全处理、真空阈值 |
| Entries | 混合 PBE/PBE+U | `PD001` |
| XRD | Si 标准结构 | 峰位置回归容差 |

### 17.2 集成测试

1. **LFP 导入 -> conventional -> XRD -> LAMMPS task package**：所有文件和事件齐全。
2. **NMC 掺杂枚举**：生成对称不等价构型，不超过配置数量，所有结构可重新导入。
3. **LLZO vacancy**：非零电荷缺陷生成交接包并出现有限尺寸/费米能级警告。
4. **Li-Fe-P-O 相图**：兼容条目生成 hull；插入不兼容条目必须失败。
5. **批 CSV**：一个坏 CIF、两个正常 CIF，退出码为 1，正常任务仍完成。
6. **恢复**：相同输入/配置命中缓存；变更 `symprec` 必须失效缓存。

### 17.3 回归夹具

- `lfp_olivine.cif`
- `nmc_layered.cif`
- `llzo_garnet.cif`
- `graphite.cif`
- `disordered_partial_occupancy.cif`
- `invalid_singular_cell.cif`
- `entries_compatible.jsonl`
- `entries_incompatible_u.jsonl`

夹具必须使用明确、可再分发的来源或项目自建最小示例，并保存许可证。

### 17.4 性能验收

| 操作 | 规模 | 目标 |
|---|---:|---|
| CIF 导入+分析 | <= 200 sites | 普通 CPU < 5 秒 |
| 2x2x2 超胞 | <= 1000 sites | < 15 秒 |
| 100 entry phase diagram | 4 元素系 | < 30 秒 |
| 20 个结构批导入 | <= 200 sites/结构 | < 2 分钟，单 worker |

性能阈值是工程目标，不是科学准确度保证。

---

## 18. 分阶段实施计划

### M0：仓库与契约（2 天）

- 建立 `pyproject`、环境、Typer CLI、日志、run layout
- 实现 Pydantic schema、错误模型、manifest 和 artifact store
- 建立 fixtures 与 CI 本地命令 `pytest`

### M1：结构 I/O 与标准化（4 天）

- CIF/POSCAR/JSON 导入导出
- 结构校验、hash、primitive/conventional、对称性和分析
- `opmat import/convert/analyze/status`

### M2：变换与电池材料模板（5 天）

- supercell、substitution、vacancy、interstitial 基础接口
- LFP/NMC/LLZO/石墨示例
- 完整 provenance 链与变换报告

### M3：slab、XRD 与下游交接（5 天）

- slab/termination/adsorption site 输出
- XRD 计算与图表
- LAMMPS/VASP/QE/CGCNN task package

### M4：相图与数据治理（5 天）

- entries schema、兼容性门禁、phase diagram、hull 分析
- 本地数据适配器、license/provenance 检查

### M5：BatteryEMCL 集成（4 天）

- material/sample link、outbox、事件幂等、ELN 摘要导入
- 端到端演示：候选晶体 -> 计算包 -> 样品关联 -> XRD 对比报告

---

## 19. 验收 Definition of Done

- 开发机不需要私有 URL、Token 或预装特定路径即可运行基础示例。
- 每份结构都有原始文件、标准化结构、哈希、来源和版本化分析报告。
- 掺杂、缺陷、slab 的每一项都可回溯父结构和参数，且不静默假设电荷补偿。
- 相图拒绝不同参考集的条目混用。
- 计算交接包可被 OpenLAMMPSFlow 或标准下游工具读取，不丢失 provenance。
- LIMS/ELN 关联能区分材料概念、实际样品和计算模型。
- 全部测试矩阵通过，且示例 run manifest 可重复生成。

---

## 20. 许可与合规

pymatgen、spglib、外部数据、势函数、实验文件和模型均可能有不同许可证。项目必须在每个数据/任务 manifest 中记录：来源、版本、许可证、获取日期、转换步骤、使用限制和责任人。不得复制附件中指向的私有 Materials Project 镜像或任何未获授权的数据库内容；如需联网数据，使用用户自己的合法 API 配置，并将凭证仅保存在本地环境变量或安全存储中。
