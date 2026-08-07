# OpenChemProcess 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openchemprocess`  
**CLI**：`ochemproc`  
**核心依赖**：SciPy、ChemPy、thermo、chemicals；上游 OpenChemProperties 物性证据包  
**定位**：BatteryEMCL Lab 的反应工程、分离过程、物料/能量衡算、工艺窗口探索与实验/中试数据校准层

---

## 0. 文档定位

OpenChemProcess 是可审计的过程工程计算层。它将化学物质身份、物性、反应网络、设备/单元操作、工况、求解器和实验数据连接为可重跑的流程模型。V2 以单元操作模板和稳态/动态的局部过程模型为主，而非宣称实现完整工业流程模拟器。

本系统适用于电解液混配、溶剂回收、萃取/结晶前评估、反应/浸出/合成路线的动力学探索、热量估算和扩散传质估计。它不替代工厂 HAZOP、SIL、压力容器设计、工艺包验证或完整 Aspen/HYSYS 级商业流程工程。

---

## 1. 目标与边界

### 1.1 V2 必须交付

- 化学计量反应、反应焓、平衡/动力学模型与物种守恒检查
- batch、CSTR、PFR 的基础反应器建模与动态积分
- 单级/多级液液萃取、Kremser 可行性判断、级数/溶剂比扫描
- Fenske–Underwood–Gilliland（FUG）蒸馏捷径估算与适用性门禁
- 液体/气体扩散系数估计、模型误差等级与 MD/实验数据替换机制
- 物料衡算、能量衡算、流股、单元操作和 flowsheet DAG
- 流程收敛、循环 tear stream、残差、边界与物理可行性检查
- 实验/中试数据导入、参数拟合、验证集和审批状态
- OpenChemProperties、OpenLAMMPSFlow、ReactNet、BatteryEMCL 湿数据中间件契约

### 1.2 非目标

- 不自动设计工业装置尺寸、控制系统或安全泄放系统
- 不将 Joback 或经验估算表述为高精度反应热/危害数据
- 不对共沸、强非理想、电解质盐溶液或反应精馏假装 FUG 可靠
- 不用未验证的动力学参数直接指导放大生产
- 不替代工艺安全评审、SDS、环境/排放/法规计算

---

## 2. 架构与数据流

```text
OpenChemProperties              ReactNet / DFT / 实验动力学
物性证据包                                  │
       │                                    ▼
       └───────────────► Process Model Compiler
                                      │
         ┌────────────────────────────┼─────────────────────────┐
         ▼                            ▼                         ▼
   反应器模型                    分离单元                   flowsheet 求解
(batch/CSTR/PFR)           (LLE/萃取/蒸馏)             (物料/能量/循环)
         │                            │                         │
         └────────────────────────────┴──────────────► QC/敏感性/报告
                                                              │
                                                              ▼
                                                   工件仓库 / outbox / ELN
```

---

## 3. 目录与文件职责

```text
openchemprocess/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── reactions.yaml
│   ├── reactors.yaml
│   ├── extraction.yaml
│   ├── distillation.yaml
│   ├── flowsheet.yaml
│   ├── solver.yaml
│   └── calibration.yaml
├── templates/
│   ├── batch_reactor.yaml
│   ├── cstr.yaml
│   ├── pfr.yaml
│   ├── extraction.yaml
│   └── fug_distillation.yaml
├── schemas/
│   ├── component.v1.json
│   ├── stream.v1.json
│   ├── reaction.v1.json
│   ├── unit_operation.v1.json
│   ├── flowsheet.v1.json
│   ├── property_evidence.v1.json
│   ├── process_result.v1.json
│   └── task_event.v1.json
├── src/openchemprocess/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── component_cmd.py
│   │   ├── reaction_cmd.py
│   │   ├── reactor_cmd.py
│   │   ├── extraction_cmd.py
│   │   ├── distillation_cmd.py
│   │   ├── flowsheet_cmd.py
│   │   ├── diffusion_cmd.py
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
│   ├── thermo/
│   │   ├── evidence_adapter.py
│   │   ├── enthalpy.py
│   │   ├── phase_equilibrium.py
│   │   └── model_scope.py
│   ├── reactions/
│   │   ├── stoichiometry.py
│   │   ├── hess.py
│   │   ├── kinetics.py
│   │   ├── eyring.py
│   │   ├── equilibrium.py
│   │   └── validation.py
│   ├── reactors/
│   │   ├── batch.py
│   │   ├── cstr.py
│   │   ├── pfr.py
│   │   ├── energy_balance.py
│   │   └── solver.py
│   ├── separations/
│   │   ├── extraction.py
│   │   ├── kremser.py
│   │   ├── distillation_fug.py
│   │   ├── feasibility.py
│   │   └── flash_adapter.py
│   ├── transport/
│   │   ├── wilke_chang.py
│   │   ├── stokes_einstein.py
│   │   ├── chapman_enskog.py
│   │   └── evidence_override.py
│   ├── flowsheet/
│   │   ├── graph.py
│   │   ├── compiler.py
│   │   ├── solver.py
│   │   ├── tear_stream.py
│   │   ├── balances.py
│   │   └── convergence.py
│   ├── calibration/
│   │   ├── importer.py
│   │   ├── normalizer.py
│   │   ├── fit.py
│   │   ├── validation.py
│   │   └── approval.py
│   ├── validation/
│   │   ├── schema.py
│   │   ├── units.py
│   │   ├── balances.py
│   │   ├── bounds.py
│   │   ├── feasibility.py
│   │   └── scope.py
│   ├── integration/
│   │   ├── chemproperties.py
│   │   ├── reactnet.py
│   │   ├── lammps.py
│   │   ├── eln_bridge.py
│   │   └── outbox.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
│   │   ├── cache.py
│   │   └── checkpoints.py
│   └── report/
│       ├── markdown.py
│       ├── plots.py
│       └── html.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
└── examples/
    ├── batch_reaction/
    ├── lle_extraction/
    ├── fug_distillation/
    ├── electrolyte_mixing/
    └── recycle_flowsheet/
```

---

## 4. 环境与版本

```yaml
name: openchemprocess
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
      - chempy
      - orjson
      - structlog
```

`ochemproc doctor --strict` 必须输出 SciPy、thermo、chemicals、chempy 版本；本地物性证据注册表；可用求解器；单位库；项目目录权限和示例模板完整性。任何外部计算服务只能作为可选 adapter，基础功能必须离线可运行。

---

## 5. 领域数据模型

### 5.1 Component、Stream 与 Reaction

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any

class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str
    chemical_id: str
    name: str
    phase_capability: list[Literal["solid", "liquid", "vapor"]]
    charge: int | None = None

class Stream(BaseModel):
    stream_id: str
    basis: Literal["molar_flow", "mass_flow"]
    total_flow: float = Field(gt=0)
    flow_unit: str
    composition_basis: Literal["mole_fraction", "mass_fraction"]
    composition: dict[str, float]
    temperature_k: float = Field(gt=0)
    pressure_pa: float = Field(gt=0)
    phase_hint: Literal["liquid", "vapor", "solid", "mixed", "unknown"]
    enthalpy_basis: Literal["unknown", "relative", "absolute"] = "unknown"
    provenance: list[dict[str, Any]] = Field(default_factory=list)

class Reaction(BaseModel):
    reaction_id: str
    stoichiometry: dict[str, float]
    basis: Literal["molar"] = "molar"
    reversible: bool = False
    delta_h_standard_j_mol: float | None = None
    delta_h_provenance: dict | None = None
    kinetic_law: dict | None = None
    equilibrium_law: dict | None = None
```

### 5.2 单元操作与 flowsheet

```python
class UnitOperation(BaseModel):
    unit_id: str
    kind: Literal["mixer", "splitter", "heater", "cooler", "flash", "batch", "cstr", "pfr", "extractor", "distillation_fug"]
    inlet_stream_ids: list[str]
    outlet_stream_ids: list[str]
    parameters: dict[str, Any]
    thermo_package_id: str | None = None

class Flowsheet(BaseModel):
    flowsheet_id: str
    components: list[Component]
    streams: list[Stream]
    units: list[UnitOperation]
    recycles: list[dict] = Field(default_factory=list)
    solver: dict[str, Any]
```

所有 composition 必须非负，且在给定容差内和为 1。自动归一化仅允许显式 `normalize=true`，并保留原数值。

---

## 6. 物性证据绑定

OpenChemProcess 只消费 OpenChemProperties 的 `PropertyObservation` 或同 schema 的本地记录。裸数值不允许进入正式模型。

```yaml
property_evidence:
  observation_id: PRP-001
  property_name: viscosity
  value: 0.0025
  unit: Pa*s
  temperature_k: 298.15
  pressure_pa: 101325
  mixture_id: MIX-001
  evidence_grade: A
  source_type: measured
  validity_range: {temperature_k: [293.15, 313.15]}
```

模型编译器必须检查状态匹配、T/P/组成匹配、证据等级、相关式范围和盐效应说明。若过程输入为高盐电解液而物性仅来自无盐溶剂，产生 `THM004_ELECTROLYTE_SCOPE_GAP`，默认拒绝关键设计计算。

---

## 7. 反应热与 Hess 工作流

### 7.1 标准反应焓

\[
\Delta H_r^\circ = \sum_i \nu_i \Delta H_{f,i}^\circ
\]

其中 \(\nu_i\) 为产物正、反应物负的化学计量数。所有生成焓必须具有相态、温度参考、单位和来源。

### 7.2 数据源门禁

| 来源 | 证据等级 | 用途 |
|---|---|---|
| 条件明确的实验/权威热化学数据 | A/B | 基线热量估算 |
| 合法本地整理相关式 | B | 工程估算 |
| Joback | C | 新分子早期筛选 |
| DFT/量子化学 | B/C，取决于验证 | 候选对比、补充 |

`thermo.Chemical.Hf` 不得被直接当作标准生成焓；适配层必须使用字段语义明确、相态清晰的热化学数据。若无法确认，抛出 `RXN001_ENTHALPY_REFERENCE_AMBIGUOUS`。

### 7.3 温度修正

若使用 Kirchhoff 修正，必须有反应物/产物的热容模型与相态路径；否则只报告参考温度下的 \(\Delta H_r^\circ\)，不得伪造任意温度反应热。

---

## 8. 动力学与反应器

### 8.1 动力学模型 schema

```yaml
kinetic_law:
  kind: power_law
  rate_basis: mol_m3_s
  expression: "k * C[A] * C[B]"
  parameters:
    k:
      value: 2.1e-3
      unit: m3/(mol*s)
      temperature_model:
        kind: arrhenius
        A: 1.0e6
        Ea_j_mol: 55000
  validity:
    temperature_k: [298.15, 353.15]
    concentration_mol_m3: [10, 2000]
  provenance: {source_type: measured, source_id: EXP-KIN-001}
```

支持：power-law、Arrhenius、Langmuir-Hinshelwood、Eyring 派生、用户表达式（受限 AST）和吸附 PFO/PSO。禁止执行任意 Python 字符串表达式。

### 8.2 Eyring 接口

\[
k(T) = \frac{k_B T}{h}\exp\left(-\frac{\Delta G^\ddagger}{RT}\right)
\]

若来自 ReactNet/量子化学的 \(\Delta G^\ddagger\)，必须携带温度、标准态、溶剂模型、路径/过渡态身份和计算级别。仅在这些条件匹配时才可映射为速率常数；否则 `KIN008_ACTIVATION_GIBBS_INCOMPATIBLE`。

### 8.3 Batch reactor

\[
\frac{dC_i}{dt}=\sum_j \nu_{ij} r_j(C,T)
\]

实现使用 `scipy.solve_ivp`，可选 BDF/Radau（刚性）或 RK45（非刚性）。求解前：

- 验证计量矩阵维度和元素/电荷守恒（若定义）；
- 验证所有初始浓度非负；
- 验证反应速率单位与体积/浓度基准；
- 验证温度方程是否需要能量衡算。

### 8.4 CSTR

稳态组分衡算：

\[
F_{i,in} - F_{i,out} + V\sum_j\nu_{ij}r_j=0
\]

动态形式应额外定义 holdup、体积、流量与能量方程。稳态求解器从多个初值启动，避免只接受局部根。

### 8.5 PFR

\[
\frac{dF_i}{dV}=\sum_j\nu_{ij}r_j
\]

PFR 必须明示体积坐标、压降模型（若有）、相态、温度/传热边界和可能的刚性。V2 不默认实现两相/多相复杂 PFR；未支持时拒绝。

### 8.6 能量衡算

```yaml
energy_balance:
  enabled: true
  mode: adiabatic  # adiabatic | isothermal | jacket
  heat_transfer:
    ua_w_k: null
    jacket_temperature_k: null
  heat_capacity_source: property_package
```

若反应器设置 adiabatic，但缺热容/反应焓，拒绝 `ENG001_ENERGY_BALANCE_DATA_MISSING`。不得默认“等温”而不报告热移除假设。

---

## 9. 扩散与传质

### 9.1 模型路由

| 场景 | 方法 | 输出等级 |
|---|---|---|
| 稀溶液中小分子 | Wilke–Chang | C，通常工程估算 |
| 胶体/大分子、已知水动力半径 | Stokes–Einstein | C，连续介质假设 |
| 稀薄气体 | Chapman–Enskog | B/C，依参数质量 |
| 有 MD MSD 结果 | OpenLAMMPSFlow evidence | B/C，取决于势/收敛 |
| 有实验数据 | 受控实验 evidence | A/B |

Wilke–Chang：

\[
D = 7.4\times10^{-12}\frac{(\phi M)^{0.5} T}{\mu V_b^{0.6}}
\]

使用前必须明确单位体系、溶剂关联因子 \(\phi\)、黏度、摩尔体积和温度。结果默认 `estimated_uncertainty_class=high`；不得伪装为精确测量。

### 9.2 MD 覆盖规则

若存在经过 QC 的 MD diffusion evidence，允许优先使用，但必须保留：温度、组成、势函数、时间窗口、R2、不确定性和有限尺寸局限。MD 值不应自动覆盖实验值；默认优先级为条件匹配实验 > 已验证 MD > 经验估算。

---

## 10. 液液萃取与 Kremser

### 10.1 输入

```yaml
extraction_id: EXT-001
solute: Li_salt_proxy
feed:
  solute_fraction: 0.02
  carrier_phase: aqueous
solvent:
  phase: organic
  solvent_to_feed_ratio: 2.0
partition_coefficient_K: 3.5
K_provenance: {source_type: measured, temperature_k: 298.15}
target_raffinate_fraction: 0.001
stages: auto
```

### 10.2 可行性门禁

萃取因子：

\[
E = K\frac{V_{org}}{V_{aq}}
\]

当 \(E < 1\) 时，必须先输出理论可达性/警告；不允许直接计算出貌似可行的级数。对于相互溶、反应萃取、浓度依赖 K 或乳化体系，Kremser 只能作为早期近似，结果等级至多 C。

### 10.3 输出

- `E`、分配系数来源、溶剂比、理论级数、raffinate/extract 组成
- 质量守恒残差
- 假设清单：稀溶质、常数 K、平衡级、两相存在
- 敏感性：K 与 S/F 的网格

---

## 11. 蒸馏 FUG 捷径

### 11.1 阶段

```text
Fenske -> Underwood -> Gilliland -> HETP / height estimate
```

### 11.2 输入

```yaml
distillation_id: DST-001
keys: {light_key: DMC, heavy_key: EMC}
feed:
  flow_mol_s: 1.0
  composition: {DMC: 0.5, EMC: 0.5}
  quality_q: 1.0
specifications:
  distillate_light_key_mole_fraction: 0.95
  bottoms_light_key_mole_fraction: 0.05
relative_volatility:
  value: 2.1
  basis: constant_alpha
  source: VLE_MODEL-001
reflux_ratio_multiplier: 1.5
hetp_m: 0.5
```

### 11.3 适用性检查

拒绝或强警告：近共沸、相对挥发度接近 1、极高纯度、强缔合、盐电解液、反应性体系、缺少可信 VLE。`R=1.3R_min` 可能导致大量理论级数；系统应输出数值但必须提示工程可行性，默认建议扫描 1.5–2.0 倍区间。

FUG 仅是捷径估算，不能用作塔径、泛点、传热、控制和最终设备设计。

---

## 12. Flowsheet 编译与求解

### 12.1 流程输入

```yaml
flowsheet_id: FS-001
components: [components.yaml]
streams:
  - {stream_id: S1, total_flow: 1.0, flow_unit: mol/s, composition: {A: 0.5, B: 0.5}, temperature_k: 298.15, pressure_pa: 101325}
units:
  - {unit_id: MIX1, kind: mixer, inlet_stream_ids: [S1, S2], outlet_stream_ids: [S3], parameters: {}}
  - {unit_id: R1, kind: batch, inlet_stream_ids: [S3], outlet_stream_ids: [S4], parameters: {reaction_set: RXN-001}}
recycles: []
solver: {method: least_squares, rtol: 1.0e-8, max_iterations: 100}
```

### 12.2 图和 tear stream

- 无 recycle 的流程必须是 DAG，按拓扑序运行。
- 有 recycle 时识别强连通分量，要求用户指定或系统建议 tear stream。
- tear stream 初值必须满足流量正、组成和为 1、T/P 合理。
- 收敛残差包括流量、组成、T、P、焓（若开启能量衡算）。

### 12.3 质量/元素衡算

每个 unit 和全流程输出：

\[
r_{mass}=\frac{|\dot m_{in}-\dot m_{out}|}{\max(\dot m_{in},\epsilon)}
\]

如果组件有元素式，额外报告元素残差；若反应网络带电，报告电荷守恒。除明确的 purge、相变、反应或外加热/功外，非守恒必须失败。

### 12.4 求解状态机

```text
DRAFT -> VALIDATED -> COMPILED -> SOLVING -> CONVERGED
                                    │          │
                                    ▼          └-> QC_PASSED
                               NOT_CONVERGED
                                    │
                                    └-> FAILED
```

禁止把最大迭代结束当作收敛。输出必须包含初始残差、末残差、迭代次数、tear stream 轨迹、所有变量边界命中和模型警告。

---

## 13. 实验/中试数据校准

### 13.1 目标

支持用 batch 转化率、浓度–时间、出口组成、温度曲线、萃取分配、蒸馏产品组成等数据校准有限数量参数。

### 13.2 配置

```yaml
fit_id: FIT-PROC-001
dataset_ids: [EXP-RXN-001]
model: batch_reactor
parameters:
  - {path: reactions.RXN1.kinetic_law.parameters.k.A, lower: 1e3, upper: 1e10, transform: log10}
  - {path: reactions.RXN1.kinetic_law.parameters.k.Ea_j_mol, lower: 10000, upper: 150000}
objective:
  observations: [concentration_mol_m3, temperature_k]
  weights: {concentration_mol_m3: 1.0, temperature_k: 0.2}
split: {validation_dataset_ids: [EXP-RXN-002]}
optimizer: {name: least_squares, multi_start: 20, seed: 42}
```

### 13.3 拟合门禁

- 参数数量默认最多 5；更多需 expert override。
- 拟合与验证实验必须按 test run 分割。
- 需输出边界命中、敏感性、相关性和多初值结果。
- 无法识别时标记 `FIT_NON_IDENTIFIABLE`，禁止写回正式工艺参数库。

---

## 14. CLI 规范

```bash
ochemproc init ./projects/electrolyte_process
ochemproc doctor --strict

# 反应和反应器
ochemproc reaction validate configs/reactions.yaml
ochemproc reaction enthalpy --reaction configs/reaction_lfp.yaml --temperature-k 298.15
ochemproc reactor batch --config configs/batch_reactor.yaml
ochemproc reactor cstr --config configs/cstr.yaml
ochemproc reactor pfr --config configs/pfr.yaml

# 传质、萃取、蒸馏
ochemproc diffusion estimate --solute A --solvent B --method wilke-chang --temperature-k 298.15
ochemproc extraction kremser --config configs/extraction.yaml
ochemproc distillation fug --config configs/distillation.yaml

# 流程与校准
ochemproc flowsheet validate configs/flowsheet.yaml
ochemproc flowsheet run configs/flowsheet.yaml
ochemproc flowsheet sweep configs/flowsheet.yaml --set "units.EXT1.solvent_to_feed_ratio=1,2,3"
ochemproc data import --input pilot.csv --mapping configs/pilot_mapping.yaml
ochemproc calibrate fit --config configs/calibration.yaml
ochemproc export --workdir runs/FS-001 --target batteryemcl
```

退出码：0 成功；1 批处理部分成功；2 CLI/配置错误；3 输入或单位错误；4 物性/依赖缺失；5 数值求解失败；6 科学适用性/守恒门禁拒绝；7 集成失败。

---

## 15. 工件、Manifest、缓存和 Outbox

```text
runs/<run_id>/
├── inputs/
│   ├── request.yaml
│   ├── flowsheet.resolved.yaml
│   ├── property_evidence_snapshot.jsonl
│   ├── reaction_set.yaml
│   └── experiment_data.parquet
├── compiled/
│   ├── graph.json
│   ├── equations.json
│   └── solver_plan.json
├── work/
│   ├── solver_trace.jsonl
│   ├── checkpoints/
│   └── calibration/
├── results/
│   ├── streams.parquet
│   ├── unit_results.json
│   ├── balances.json
│   ├── convergence.json
│   ├── sensitivity.csv
│   ├── fit_result.json
│   └── export_package/
├── outbox/events.jsonl
├── logs/
├── manifest.json
└── report.md
```

缓存键：flowsheet canonical JSON、物性 observation IDs 与哈希、热力学包、反应/动力学版本、solver 配置、软件版本和随机种子。任一物性证据或反应参数变化都必须失效缓存。

事件：

```text
process.validated
process.started
process.converged
process.not_converged
process.balance_failed
process.model_scope_warning
process.calibration.pending_review
process.calibration.approved
process.package.created
```

---

## 16. 关键错误码

| 错误码 | 含义 |
|---|---|
| `CMP001` | 组成/基准/组分错误 |
| `THM001` | 物性证据缺失 |
| `THM004` | 高盐电解液物性适用性缺口 |
| `RXN001` | 反应焓参考态不清晰 |
| `KIN001` | 动力学单位或表达式无效 |
| `KIN008` | Eyring 活化自由能条件不兼容 |
| `ENG001` | 能量衡算缺少必要数据 |
| `RCT001` | 反应器 ODE/代数求解失败 |
| `EXT001` | Kremser 输入/相平衡假设无效 |
| `DST001` | FUG 适用性不满足 |
| `FLO001` | flowsheet 图/stream 连接错误 |
| `FLO002` | recycle 未收敛 |
| `BAL001` | 质量/元素/电荷衡算失败 |
| `FIT001` | 校准数据缺少条件/来源 |
| `FIT002` | 参数不可识别 |

---

## 17. 测试矩阵

### 17.1 单元测试

| 模块 | 场景 | 断言 |
|---|---|---|
| 化学计量 | 未平衡反应 | 元素/电荷守恒失败 |
| Hess | 相态缺失生成焓 | `RXN001` |
| kinetic AST | 恶意/未知表达式 | 拒绝执行 |
| batch ODE | 一阶不可逆反应 | 与解析解一致 |
| CSTR | 多初值 | 识别多根/报告根 |
| PFR | 常温一阶 | 转化率基准一致 |
| Wilke-Chang | 单位变换 | 数值正确/等级 C |
| Kremser | E < 1 | 输出可行性警告 |
| FUG | alpha 接近 1 | `DST001` 警告/拒绝 |
| flow graph | recycle | 正确生成 tear stream |
| balances | 人工漏流 | `BAL001` |
| cache | 物性哈希变化 | 缓存失效 |

### 17.2 集成测试

1. 反应热 -> batch 等温反应器 -> 转化率/热量报告。
2. 放热 batch + jacket：温度曲线、能量衡算和数据缺失门禁。
3. LLE 萃取：Kremser feasibility、级数扫描、质量守恒。
4. FUG 蒸馏：常规二元挥发性差体系，输出 `Nmin`、`Rmin`、级数与 HETP 高度；近共沸 fixture 必须警告。
5. mixer -> reactor -> separator 的无 recycle flowsheet，拓扑计算与全局质量守恒。
6. recycle flowsheet：tear stream 收敛、残差轨迹与未收敛失败例。
7. 导入中试浓度时间数据 -> 动力学拟合 -> 留出验证 -> approval。
8. 无盐物性用于 LiPF6 浓电解液关键计算必须产生 `THM004`。

### 17.3 性能验收

| 任务 | 规模 | 目标 |
|---|---:|---|
| batch ODE | <= 10 species、2 reactions | < 5 秒 |
| 100 点萃取扫描 | 单溶质 | < 30 秒 |
| FUG 单计算 | 二元/三元简化 | < 10 秒 |
| DAG flowsheet | <= 30 units | < 1 分钟 |
| recycle flowsheet | <= 10 tear vars | < 5 分钟 |

---

## 18. 实施里程碑

### M0：工程骨架（2 天）

CLI、schema、单位、artifact store、manifest、错误模型、doctor 与 fixtures。

### M1：物性绑定与反应（5 天）

Property evidence adapter、反应 schema、Hess、动力学 AST、batch/CSTR/PFR 基础。

### M2：能量与传质（4 天）

能量衡算、Wilke–Chang/Stokes–Einstein/Chapman–Enskog、MD/实验 evidence 覆盖。

### M3：分离单元（5 天）

Kremser、FUG、适用性门禁、参数扫描、结果报告。

### M4：Flowsheet（6 天）

DAG、recycle、tear stream、守恒/收敛、checkpoint、敏感性。

### M5：校准与闭环集成（5 天）

湿数据、参数拟合、验证、审批、outbox、BatteryEMCL 演示流程。

---

## 19. Definition of Done

- 每个过程模型均可追溯到组分身份、物性证据、反应/动力学版本、流程配置与求解器版本。
- 质量、元素、电荷和能量衡算在适用时自动检查，未收敛不可伪装为收敛。
- Kremser/FUG/经验扩散法都有适用范围和结果等级，不在电解液盐体系中夸大精度。
- 反应器解包含初始条件、边界、时间/体积域、求解器诊断和物理非负性检查。
- 拟合使用独立验证数据并报告不可识别性，正式参数写回需审批。
- OpenChemProperties/LAMMPS/ReactNet 的输入均通过 versioned evidence contract，而非裸数值。
- 全部单元、集成、回归与性能测试通过。

---

## 20. 许可、安全与工程责任

软件包、物性数据、动力学数据、实验/中试记录均需保存许可证、来源和使用限制。流程计算结果仅用于研发假设和实验设计，不可直接用作工厂放大、危化审批、设备采购或安全操作指令。涉及可燃、有毒、高压、腐蚀、放热反应或电池电解液时，必须由具备资质的工艺和安全人员审查，并执行实际实验室/工厂的审批制度。
