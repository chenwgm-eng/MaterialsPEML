# OpenChemProperties 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openchemproperties`  
**CLI**：`ochemprop`  
**核心依赖**：`chemicals`、`thermo`、本地数据快照；可选用户授权的外部数据连接器  
**定位**：BatteryEMCL Lab 的化学物质身份、温压依赖物性、混合物热力学、相平衡、溶解度与实验校准基础设施

---

## 0. 文档定位

OpenChemProperties 不是“查一个数值”的脚本集合，而是一个可审计的物性证据系统：每一个数值必须绑定化学身份、相态、温度、压力、组成、模型/相关式、来源、单位、适用范围和不确定性状态。

它优先支持电解液溶剂、锂盐、添加剂、反应副产物和工艺溶剂。对浓电解液、离子液体、强缔合混合物和电极界面，本系统必须显式表达模型外推限制，而不能把通用 VLE/EOS 输出伪装为准确电池电解液预测。

---

## 1. 目标与边界

### 1.1 必须交付

- 化学物质身份解析：名称、CAS、InChIKey、SMILES、分子式、多同义词与冲突处理
- 单组分常数及 T/P 依赖物性：密度、黏度、蒸气压、热容、导热、表面张力、介电常数等
- 多组分液相与汽液平衡：泡点、露点、活度系数、液相/气相组成
- 等温/等压/绝热闪蒸与相分率结果
- 气体 Henry、固体 van't Hoff、溶剂相容性/Hansen-Hildebrand 的溶解度辅助
- 来源优先级、证据等级、相关式区间、单位转换、模型选择和警告
- 实验湿数据导入、校准、偏差分析和候选物性批准工作流
- 对 OpenChemProcess、OpenPackmol、OpenLAMMPSFlow、OpenBatterySim 的参数交接包
- 本地 artifact、manifest、outbox、批处理、错误码和测试基准

### 1.2 非目标

- 不绕过商业数据库、许可限制或网站访问控制
- 不将公开条目自动视为可用于生产配方或安全评估的最终证据
- 不对浓盐电解液承诺普适的 VLE、黏度、电导率或溶解度预测
- 不把 PR EOS 用于氢键共沸、强极性液体或离子溶液时的结果当作高可信真值
- 不代替 SDS、危险化学品评估、法规合规或实验室安全审查

---

## 2. 总体架构

```text
用户 / Agent / ELN-LIMS / 本地数据快照
                    │
                    ▼
               ochemprop CLI
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
物质身份解析      数据证据层      模型路由与单位层
     │              │              │
     └───────► PropertyRequest ◄───┘
                       │
    ┌──────────────────┼─────────────────────┐
    ▼                  ▼                     ▼
纯组分相关式     VLE/活度系数             Flash/EOS/溶解度
    │                  │                     │
    └──────────────────┴───────────► QC 与不确定性
                                             │
                                             ▼
                         工件仓库 / 参数审批 / outbox / 下游任务包
```

---

## 3. 目录与文件职责

```text
openchemproperties/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── pure_properties.yaml
│   ├── vle.yaml
│   ├── flash.yaml
│   ├── solubility.yaml
│   ├── electrolyte.yaml
│   └── data_import.yaml
├── data/
│   ├── identity_aliases.parquet
│   ├── property_sources_registry.yaml
│   ├── local_correlations/
│   └── fixtures/
├── schemas/
│   ├── chemical_identity.v1.json
│   ├── property_observation.v1.json
│   ├── property_request.v1.json
│   ├── mixture_definition.v1.json
│   ├── model_result.v1.json
│   ├── experiment_series.v1.json
│   └── task_event.v1.json
├── src/openchemproperties/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── identity_cmd.py
│   │   ├── pure_cmd.py
│   │   ├── mixture_cmd.py
│   │   ├── vle_cmd.py
│   │   ├── flash_cmd.py
│   │   ├── solubility_cmd.py
│   │   ├── data_cmd.py
│   │   ├── calibrate_cmd.py
│   │   ├── export_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── units.py
│   │   └── identifiers.py
│   ├── identity/
│   │   ├── resolver.py
│   │   ├── aliases.py
│   │   ├── canonicalizer.py
│   │   └── validation.py
│   ├── evidence/
│   │   ├── registry.py
│   │   ├── local_store.py
│   │   ├── citations.py
│   │   ├── source_priority.py
│   │   └── provenance.py
│   ├── pure/
│   │   ├── constants.py
│   │   ├── correlations.py
│   │   ├── phase.py
│   │   ├── property_router.py
│   │   └── quality.py
│   ├── mixtures/
│   │   ├── composition.py
│   │   ├── activity_models.py
│   │   ├── vle.py
│   │   ├── flash.py
│   │   ├── eos.py
│   │   └── electrolyte_scope.py
│   ├── solubility/
│   │   ├── henry.py
│   │   ├── vant_hoff.py
│   │   ├── solubility_parameters.py
│   │   └── fit.py
│   ├── calibration/
│   │   ├── importer.py
│   │   ├── normalizer.py
│   │   ├── outliers.py
│   │   ├── correlation_fit.py
│   │   └── approval.py
│   ├── validation/
│   │   ├── request.py
│   │   ├── identity.py
│   │   ├── ranges.py
│   │   ├── phase.py
│   │   ├── model_scope.py
│   │   └── composition.py
│   ├── integration/
│   │   ├── process_package.py
│   │   ├── packmol_package.py
│   │   ├── lammps_package.py
│   │   ├── battery_package.py
│   │   ├── sample_link.py
│   │   └── outbox.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
│   │   ├── cache.py
│   │   └── snapshots.py
│   └── report/
│       ├── markdown.py
│       ├── html.py
│       └── plots.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
└── examples/
    ├── ec_emc/
    ├── dmc_emc_liPF6/
    ├── co2_solubility/
    └── solvent_screening/
```

---

## 4. 环境与数据策略

```yaml
name: openchemproperties
channels: [conda-forge]
dependencies:
  - python=3.11
  - pip
  - numpy
  - scipy
  - pandas
  - pyarrow
  - pydantic>=2
  - typer
  - rich
  - pyyaml
  - pint
  - pytest
  - pip:
      - chemicals
      - thermo
      - orjson
      - structlog
```

`ochemprop doctor --strict` 必须验证 `chemicals`/`thermo` 版本、可用本地数据快照、单位库、相关式注册表、输出目录权限和外部连接器是否显式启用。基础工作流默认离线；外部数据连接器必须由用户安装并提供合法凭证。

---

## 5. 化学身份治理

### 5.1 Canonical Chemical Identity

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class ChemicalIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    chemical_id: str
    preferred_name: str
    cas: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    formula: str | None = None
    molecular_weight_g_mol: float | None = Field(default=None, gt=0)
    charge: int | None = None
    aliases: list[str] = Field(default_factory=list)
    identity_status: Literal["verified", "ambiguous", "user_asserted", "unresolved"]
    provenance: list[dict] = Field(default_factory=list)
```

`chemical_id` 由稳定身份键产生：优先 InChIKey，其次 CAS；无可靠身份时使用 `user:<uuid7>` 并标记 `user_asserted`。名称不构成唯一主键。

### 5.2 身份解析流程

```text
用户输入名称 / CAS / SMILES / InChIKey
    -> 语法和 checksum 检查
    -> 本地 alias 表匹配
    -> 多候选消歧（CAS、分子式、分子量、SMILES）
    -> canonical identity
    -> 写入 identity resolution report
```

例如 `EC` 必须提示可能代表 ethylene carbonate、ethyl cellulose 或其他缩写；只有证据充分才自动映射为电解液中的 ethylene carbonate。`γ-butyrolactone` 等命名变体应保存原始输入和 canonical alias，不应悄悄删改而不留记录。

### 5.3 错误码

| 错误码 | 含义 | 行为 |
|---|---|---|
| `ID001` | 身份未解析 | 拒绝进入计算 |
| `ID002` | 多候选歧义 | 要求 CAS/SMILES/用户选择 |
| `ID003` | CAS 校验失败 | 拒绝或 user_asserted 模式 |
| `ID004` | 成分与身份冲突 | 拒绝 |
| `ID005` | 盐/离子电荷不完整 | 要求组成或离子形式 |

---

## 6. 数据证据模型

### 6.1 物性观测记录

```python
class PropertyObservation(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    observation_id: str
    chemical_id: str | None = None
    mixture_id: str | None = None
    property_name: str
    value: float
    unit: str
    temperature_k: float | None = None
    pressure_pa: float | None = None
    phase: Literal["solid", "liquid", "vapor", "supercritical", "unknown"]
    composition_basis: Literal["mole_fraction", "mass_fraction", "molality", "molarity", "none"]
    composition: dict[str, float] | None = None
    method: str | None = None
    uncertainty: dict | None = None
    source_type: Literal["measured", "correlation", "eos", "group_contribution", "estimated"]
    source_ref: str
    validity_range: dict | None = None
    evidence_grade: Literal["A", "B", "C", "D"]
```

### 6.2 证据等级

| 等级 | 含义 | 允许用途 |
|---|---|---|
| A | 可追溯的原始实验数据，方法/条件明确 | 校准、关键决策候选 |
| B | 权威整理或明确相关式，区间与来源完整 | 工程估算与对照 |
| C | 基团贡献/EOS/经验预测 | 早期筛选、敏感性分析 |
| D | 缺区间、身份不完整或外推严重 | 仅展示，不得驱动决策 |

### 6.3 来源优先级

默认：用户受控实验数据（条件匹配） > 合法本地权威数据快照 > 带范围的已验证相关式 > 公开数据库摘要 > 基团贡献/通用 EOS。优先级不是绝对：若实验条件不匹配或方法不清晰，必须降级。

---

## 7. 请求与单位契约

### 7.1 Property Request

```yaml
request_id: PRP-0001
kind: pure_property
chemical: {cas: "96-49-1"}
property: viscosity
state:
  temperature_k: 298.15
  pressure_pa: 101325
  phase_hint: liquid
unit: Pa*s
policy:
  min_evidence_grade: B
  allow_estimation: false
  allow_extrapolation: false
```

### 7.2 单位规范

内部 SI：K、Pa、kg/m3、Pa*s、W/(m*K)、J/(mol*K)、N/m、m2/s。用户输入输出可以转换，但 manifest 必须记录原单位、换算规则与标准单位。

| 性质 | 规范单位 |
|---|---|
| 密度 | kg/m3 |
| 动力黏度 | Pa*s |
| 运动黏度 | m2/s |
| 蒸气压 | Pa |
| 热容 | J/(mol*K) 或 J/(kg*K)，字段必须明确 basis |
| 导热率 | W/(m*K) |
| 表面张力 | N/m |
| 介电常数 | 无量纲 |
| 溶解度 | 显式 basis：mole fraction/molality/molarity/g/L |

禁止仅存 `Cp`、`viscosity`、`solubility` 之类无单位字段。

---

## 8. 单组分物性工作流

### 8.1 路由

```text
identity resolved
  -> 检查 requested T/P/phase
  -> 查询本地 observation/correlation registry
  -> 检查有效范围
  -> 选择最高等级有效证据
  -> 若无：允许估算？选择模型并标记等级 C/D
  -> phase/物理定义检查
  -> 单位转换、结果与 provenance 输出
```

### 8.2 常用物性与定义门禁

| 物性 | 关键条件 | 禁止/警告 |
|---|---|---|
| 蒸气压 | 液-汽平衡、低于临界点 | 超临界时标记无定义 |
| 汽化焓 | 相变存在 | 超临界时无定义 |
| 表面张力 | 液相界面 | 超临界或固体条件不输出 |
| 黏度 | 相态、T/P、组分 | 高盐电解液不可用纯溶剂值替代 |
| 介电常数 | 频率、T、组成 | 需明确静态/频率条件 |
| 密度 | T/P、相态 | 混合物不可直接按纯组分查询 |

### 8.3 相关式适用性

每条 correlation 必须有：

```yaml
correlation_id: CORR-ANTOINE-001
property: vapor_pressure
form: Antoine
coefficients: {A: 6.9, B: 1200, C: 220}
temperature_range_k: [280, 360]
pressure_unit_native: mmHg
source_ref: "..."
validation_status: reviewed
```

若 `T` 不在范围内且 `allow_extrapolation=false`，抛出 `RNG001_OUTSIDE_CORRELATION_RANGE`。若允许外推，必须输出 `EXTRAPOLATED`、距离范围、证据等级降级与不可用于关键决策提示。

---

## 9. 混合物定义与活度模型

### 9.1 Mixture Definition

```yaml
mixture_id: MIX-EC-EMC-001
basis: mole_fraction
components:
  - chemical: {cas: "96-49-1", name: ethylene_carbonate}
    fraction: 0.3
  - chemical: {cas: "623-53-0", name: ethyl_methyl_carbonate}
    fraction: 0.7
normalization_tolerance: 1.0e-8
salt:
  chemical: {name: LiPF6}
  concentration: {value: 1.0, unit: mol/L}
state: {temperature_k: 298.15, pressure_pa: 101325}
```

### 9.2 组成校验

- 同一 basis 中组分分数必须非负且和为 1（在容差内）。
- 自动归一化只在 `--normalize` 显式指定时允许，并写入原/新组成。
- 盐浓度与溶剂摩尔分数不可混为一张无 basis 的向量；电解液应拆分 `solvent_mixture` 与 `salt_specification`。
- 盐解离状态、浓度尺度、密度依赖关系不明时，拒绝生成摩尔分数近似。

### 9.3 活度系数路由

```text
若有同体系、同模型、可追溯的二元参数：Wilson/NRTL/UNIQUAC
  否则：若组分可分组且适用 -> UNIFAC（等级 C）
  否则：拒绝精确 VLE 声称，返回数据缺口
```

所有 VLE 结果必须携带：活度模型、参数来源、温度区间、二元参数矩阵、组分顺序和未覆盖 pair。

---

## 10. VLE、泡点与露点

### 10.1 CLI

```bash
ochemprop vle bubble --mixture configs/ec_emc.yaml --temperature-k 298.15
ochemprop vle dew --mixture configs/ec_emc.yaml --pressure-pa 101325
ochemprop vle isothermal --mixture configs/mixture.yaml --temperature-k 350 --grid 101
ochemprop vle validate --model nrtl --parameters data/nrtl_ec_emc.yaml
```

### 10.2 求解流程

```python
def bubble_pressure(T, x, model):
    gamma = model.gammas(T, x)
    psat = [pure.psat(i, T) for i in components]
    p = sum(xi * gi * pi for xi, gi, pi in zip(x, gamma, psat))
    y = normalize([xi * gi * pi / p for xi, gi, pi in zip(x, gamma, psat)])
    return p, y
```

真实实现需要考虑模型与相态范围，必要时考虑 Poynting、vapor fugacity 修正；V2 默认明确 `ideal_vapor_assumption`。不应以此实现处理高压、反应性或电解质溶液 VLE。

### 10.3 电解液限制

碳酸酯 + LiPF6 等浓盐电解液不应直接把“无盐 EC/EMC VLE”作为盐溶液 VLE。运行时输出：

```text
ELECTROLYTE_SCOPE_LIMITED:
  salt_effects_on_activity: not modeled
  result_usage: solvent_baseline_only
  required_for_decision: measured_or_electrolyte_specific_model
```

---

## 11. Flash 与 EOS

### 11.1 模型路由

| 场景 | 默认方法 | 限制 |
|---|---|---|
| 非极性/中等极性气液混合物 | PR/PRMIX FlashVL | 需核对二元交互参数 |
| 强极性/缔合液体 VLE | 活度系数模型优先 | PR 不作为最终依据 |
| 低压常规液体 | 活度系数 + 理想气相近似 | 写明假设 |
| 高盐电解液 | 不自动 Flash | 要求专用模型/实验数据 |

### 11.2 Flash CLI

```bash
ochemprop flash tp --mixture configs/mixture.yaml --temperature-k 350 --pressure-pa 101325
ochemprop flash ph --mixture configs/mixture.yaml --pressure-pa 101325 --enthalpy-j-mol -12000
ochemprop flash sweep --mixture configs/mixture.yaml --temperature-k 300:450:5 --pressure-pa 101325
```

### 11.3 结果模式

```json
{
  "flash_id":"FLS-0001",
  "specification":{"T_K":350,"P_Pa":101325,"zs":[0.5,0.5]},
  "model":{"kind":"PRMIX","assumptions":["non_associating_fluid"]},
  "phase_count":2,
  "vapor_fraction":0.34,
  "liquids":[{"fraction":0.66,"zs":[0.61,0.39]}],
  "gas":{"zs":[0.29,0.71]},
  "status":"MODEL_SCOPE_WARNING"
}
```

实现必须读取 `result.VF`，而不是不存在或语义不同的 `result.V`；全液相时 `gas` 可能为空，不能无条件访问。

---

## 12. 溶解度工作流

### 12.1 三条模型路径

| 问题 | 方法 | 最低所需数据 |
|---|---|---|
| 气体溶于液体 | Henry 定律 | `kH(T)`、定义形式、液体组成 |
| 固体溶于液体 | van't Hoff / 融合焓近似 | 熔点、融合焓、活度模型/理想假设 |
| 溶剂筛选 | Hansen/Hildebrand | 溶解度参数、目标材料参数、经验阈值 |

### 12.2 Henry 模型

```yaml
henry:
  definition: "p_over_x"
  kH_pa: 2.1e8
  temperature_k: 298.15
  source_ref: "..."
  temperature_model: vanthoff
  delta_h_solution_j_mol: -12000
```

Henry 常数存在多种定义；任何输入都必须有 `definition`。缺失定义时抛出 `SOL001_HENRY_DEFINITION_MISSING`。

### 12.3 固体溶解度

简化理想解近似可写为：

\[
\ln(x_i \gamma_i) = -\frac{\Delta H_{fus}}{R}\left(\frac{1}{T} - \frac{1}{T_m}\right)
\]

输出必须说明是否设 \(\gamma_i = 1\)，并标记是否忽略固相多晶型、盐溶剂化、反应、离子化和共晶。

### 12.4 电解液材料限制

LiPF6、LiTFSI 等盐在碳酸酯/醚类溶剂中的溶解度和离子电导率涉及离子缔合、溶剂化、反应与水分敏感性。V2 仅允许：导入实验溶解度、存储条件、做局部经验拟合、进行透明的溶剂筛选指标；不得以普通 van't Hoff 或 Hansen 参数单独发布精确盐溶解度结论。

---

## 13. 实验湿数据校准

### 13.1 导入格式

```text
sample_id,mixture_id,property_name,value,unit,temperature_k,pressure_pa,method,instrument_id,timestamp,raw_file
```

```bash
ochemprop data import --input experiments/viscosity.csv --mapping configs/viscometer.yaml
ochemprop data qc --dataset EXP-PROP-001
ochemprop calibrate fit --dataset EXP-PROP-001 --property viscosity --model andrade
ochemprop calibrate approve --fit FIT-PROP-001 --reviewer expert_01
```

### 13.2 校准状态机

```text
RAW -> NORMALIZED -> QC_PASSED -> FITTED -> VALIDATED -> PENDING_REVIEW -> APPROVED
                         │              │
                         └-> QC_FAILED  └-> REJECTED
```

### 13.3 最低 QC

- 样品/混合物身份和组成可追溯
- 温度、压力、单位和仪器方法存在
- 重复样本统计、明显异常值和适用区间显示
- 原始文件哈希保留
- 拟合、验证和留出数据分离

局部拟合只对实验覆盖的温度/组成区域有效；外推需重新走 evidence gate。

---

## 14. 下游任务包

### 14.1 Process 包

```yaml
property_package:
  package_type: process_thermo_input
  mixture_id: MIX-EC-EMC-001
  properties:
    - {name: density, value: 1280, unit: kg/m3, temperature_k: 298.15, evidence_grade: B}
    - {name: viscosity, value: 0.0025, unit: Pa*s, temperature_k: 298.15, evidence_grade: A}
  limitations: ["salt_effects_not_modeled"]
```

### 14.2 Packmol / LAMMPS 包

提供组分身份、摩尔/质量分数、分子量、目标密度、温度、是否含盐、参数化状态，不直接产生力场或 partial charges。

### 14.3 BatterySim 包

只传递明确物性证据，如密度、热容、导热率、离子电导率实验曲线；不自动把溶剂物性折算成电芯级有效参数。

---

## 15. CLI 规范

```bash
ochemprop init ./projects/electrolyte_props
ochemprop doctor --strict

# 身份与纯组分
ochemprop identity resolve "ethylene carbonate"
ochemprop identity resolve --cas 96-49-1
ochemprop pure get --chemical 96-49-1 --property density --temperature-k 298.15
ochemprop pure get --chemical ethanol --property vapor_pressure --temperature-k 350 --allow-extrapolation

# 混合物与相平衡
ochemprop mixture validate configs/ec_emc.yaml
ochemprop vle bubble --mixture configs/ec_emc.yaml --temperature-k 350
ochemprop flash tp --mixture configs/solvents.yaml --temperature-k 350 --pressure-pa 101325

# 溶解度与数据
ochemprop solubility henry --gas CO2 --solvent dimethyl_carbonate --temperature-k 298.15 --data configs/henry.yaml
ochemprop solubility solid --solute compound.yaml --solvent ec_emc.yaml --temperature-k 298.15
ochemprop data import --input tests.csv --mapping configs/instrument.yaml
ochemprop calibrate fit --dataset EXP-001 --property viscosity --model andrade
ochemprop export --workdir runs/PRP-0001 --target openchemprocess
```

退出码：0 成功；1 批处理部分成功；2 CLI/配置错误；3 身份/输入/单位错误；4 依赖或数据缺失；5 求解失败；6 模型适用性/证据门禁拒绝；7 下游交接失败。

---

## 16. 工件、Manifest、缓存与事件

```text
runs/<run_id>/
├── inputs/
│   ├── request.yaml
│   ├── resolved_config.yaml
│   ├── identity_snapshot.json
│   ├── mixture.normalized.yaml
│   └── experimental_data.parquet
├── work/
│   ├── model_inputs.json
│   └── solver_trace.jsonl
├── results/
│   ├── property_observations.jsonl
│   ├── model_result.json
│   ├── qc.json
│   ├── comparison.csv
│   ├── calibration.json
│   └── export_package/
├── outbox/events.jsonl
├── logs/
├── manifest.json
└── report.md
```

缓存键包含：identity hash、property、T/P、phase、mixture normalized composition、模型/相关式 ID、系数版本、`chemicals`/`thermo` 版本和外推策略。不得因为名称字符串相同就命中缓存。

事件类型：

```text
chemical.resolved
property.computed
property.model_scope_warning
mixture.validated
vle.completed
flash.completed
solubility.completed
experiment.imported
calibration.pending_review
calibration.approved
property.package.created
```

---

## 17. 验证、错误模型与结果语言

### 17.1 关键错误码

| 代码 | 说明 |
|---|---|
| `ID001`–`ID005` | 身份、CAS、电荷、歧义问题 |
| `UNT001` | 单位缺失或不可转换 |
| `CMP001` | 组成分数错误/无 basis |
| `RNG001` | 超出相关式有效范围 |
| `PH001` | 请求相态下物性无定义 |
| `VLE001` | 活度模型或二元参数缺失 |
| `FLS001` | Flash 无收敛/相状态不一致 |
| `SOL001` | Henry 定义缺失 |
| `SOL002` | 固体溶解度关键数据缺失 |
| `ELC001` | 浓电解液模型超出适用范围 |
| `CAL001` | 实验数据缺少样品/条件/原始文件 |
| `PRV001` | 来源或许可证缺失 |

### 17.2 报告措辞规范

允许：

- “在 298.15 K、给定组成和所选相关式下，估算值为……”
- “该值来自实验数据/相关式/模型，证据等级为……”
- “浓盐效应未建模，结果仅用于无盐溶剂基线。”

禁止：

- “该电解液的真实黏度就是……”（若为估算）
- “该模型证明盐可溶/电解液稳定。”
- “相平衡预测已验证。”（无独立实验对照）

---

## 18. 测试矩阵

### 18.1 单元测试

| 模块 | 输入 | 断言 |
|---|---|---|
| identity resolver | EC 歧义名称 | `ID002` 或用户确认 |
| CAS | 校验错误 CAS | `ID003` |
| units | cP -> Pa*s | 正确转换与 provenance |
| phase guard | 超临界请求 Psat | `PH001` |
| correlation range | T 超范围 | `RNG001` |
| mixture | 分数和不为 1 | `CMP001` |
| Flash adapter | 全液相 | 不访问空 gas；正确读取 VF |
| Henry | 无 definition | `SOL001` |
| electrolyte guard | LiPF6 普通 VLE | `ELC001` |
| cache | 相关式系数变更 | 缓存失效 |

### 18.2 集成测试

1. 纯组分：身份 -> 298.15 K 密度/黏度 -> 有效范围和来源报告。
2. EC/EMC 无盐混合物：组成校验 -> 活度模型 -> 泡点/露点 -> 工件完整。
3. 强极性体系：PR Flash 产生模型适用性警告而不是高等级结果。
4. 气体 Henry：不同定义转换完整，输出正确单位。
5. 电解液实验黏度：导入 -> QC -> Andrade 拟合 -> 留出验证 -> 审批。
6. 批处理：一个 unresolved chemical、两个有效请求，部分成功且输出错误表。
7. 下游：已批准密度/黏度包可由 OpenChemProcess 读取，且保留 evidence grade。

### 18.3 性能目标

| 任务 | 规模 | 目标 |
|---|---:|---|
| 单组分物性查询 | 本地数据 | < 2 秒 |
| 二元泡点点计算 | 1 个 T | < 5 秒 |
| 101 点 VLE 扫描 | 二元系统 | < 2 分钟 |
| TP Flash | <= 10 组分 | < 10 秒 |
| 10k 实验点校准预处理 | CSV/Parquet | < 1 分钟 |

---

## 19. 实施里程碑

### M0：基础与身份（3 天）

CLI、Pydantic schema、单位层、identity resolver、artifact/manifest/outbox 和 fixtures。

### M1：纯组分证据（4 天）

本地 source registry、correlation router、phase/range guard、纯组分查询与报告。

### M2：混合物与 VLE（5 天）

MixtureDefinition、组成校验、IPDB/活度模型 adapter、泡点/露点、模型适用性门禁。

### M3：Flash 与溶解度（5 天）

FlashVL adapter、全相态处理、Henry、van't Hoff、Hansen/Hildebrand、浓电解液限制。

### M4：湿数据与校准（5 天）

数据导入、QC、相关式拟合、验证、审批状态机与证据等级。

### M5：闭环集成（3 天）

OpenChemProcess/Packmol/LAMMPS/BatterySim 包、sample link、端到端报告和回归基准。

---

## 20. Definition of Done

- 每个物性结果都包含化学身份、相态、T/P、组成/基准、单位、方法、来源、有效范围和证据等级。
- 未解析身份、错误单位、错误组成、超出相关式范围和不合适模型均在运行前或结果中明确阻断/标记。
- VLE、Flash、Henry 和溶解度的模型假设可复现；空相、数组索引与定义差异被安全处理。
- 浓盐电解液不能用普通溶剂模型伪装为精确结论。
- 实验数据保留原始哈希、样品/方法/仪器/条件和审批链。
- 下游系统收到带证据等级与限制的参数包，而不是裸数值。
- 所有 unit、integration、regression、性能测试通过。

---

## 21. 许可、数据与安全边界

所有本地数据快照、相关式系数、商业/公开数据库条目、实验数据和软件库都须保留来源与许可证。外部查询仅能通过用户获得授权的连接器完成，且不得把 LIMS/ELN 原始湿数据上传至未经批准的服务。该系统提供物性信息管理与模型估算，不替代安全数据表、危害评估、压力容器设计、危化品管理或实验安全委员会审查。
