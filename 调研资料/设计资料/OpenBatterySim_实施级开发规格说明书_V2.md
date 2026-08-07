# OpenBatterySim 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openbatterysim`  
**CLI**：`obatt`  
**核心引擎**：PyBaMM、PyBOP、本地 Thevenin ECM 适配器  
**定位**：BatteryEMCL Lab 的电芯级机理仿真、快速 BMS 仿真、实测数据参数辨识与实验闭环对比基础设施

---

## 0. 文档定位

本文是实施级规格。它规定 OpenBatterySim 的目录、领域模型、CLI、实验协议语言、参数集治理、模型路由、数值求解、ECM、PyBOP 拟合、数据中间件接入、测试矩阵与验收条件。

本项目将“材料候选”与“电芯行为”分开：晶体结构、扩散系数、界面性质等可以作为参数证据进入模型，但 PyBaMM/PyBOP 的输出仍然是给定电芯架构、参数集和工况下的模型结果，不是单一材料的固有性能认证。

---

## 1. 目标与边界

### 1.1 三条执行轨道

| 轨道 | 引擎 | 主要用途 | 不应回答的问题 |
|---|---|---|---|
| 机理电化学 | PyBaMM SPM/SPMe/DFN | 曲线、倍率、极化、热、机理敏感性 | 单一材料绝对优劣、量产寿命承诺 |
| 快速电路 | Thevenin ECM | BMS 原型、HPPC、工况快速回放 | 电极内部浓度/反应机理 |
| 参数辨识 | PyBOP | 将实测曲线用于受约束参数拟合 | 在不可识别数据上宣称唯一真实参数 |

### 1.2 V2 必须交付

- 参数集清单、版本、化学体系与适用范围门禁
- SPM、SPMe、DFN 的统一运行接口
- 恒流、恒压、CCCV、休止、循环、C-rate 扫描、温度扫描协议
- isothermal、lumped、x-full 热模型的配置与输出变量映射
- 可选退化模型的显式开关、兼容性检查与结果标签
- Thevenin ECM 仿真、HPPC 数据解析、参数拟合和验证
- PyBOP 拟合任务、数据切分、参数边界、目标函数、可识别性检查
- 实测电池数据导入、单位标准化、样品/电芯/设备/方法溯源
- 长表/宽表/Parquet/JSON/Markdown 结果和 outbox 事件
- 缓存、checkpoint、失败隔离与回归测试

### 1.3 非目标

- 不替代 BMS 生产级实时控制器或功能安全验证
- 不使用无来源参数集合成“虚拟电芯”并对外宣称实验级预测
- 不自动将实验曲线归因到单一电极材料或单一失效机理
- 不在无实测校准的情况下承诺寿命、热失控风险或安全边界
- 不把拟合参数解释为可转移到其他尺寸、极片、SOC 窗口或温度的物理常数

---

## 2. 总体架构

```text
BatteryEMCL Agent / 用户 / ELN-LIMS 中间件
                       │
                       ▼
                   obatt CLI
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
参数集治理         协议编译          实验数据导入
       │               │                │
       └───────► 模型路由 ◄─────────────┘
                        │
     ┌──────────────────┼──────────────────────┐
     ▼                  ▼                      ▼
PyBaMM SPM/SPMe/DFN  Thevenin ECM           PyBOP fitting
     │                  │                      │
     └──────────────┬───┴───────────────┬──────┘
                    ▼                   ▼
               结果抽取            QC / 统计 / 比较
                    │                   │
                    └─────────► 工件仓库 / Outbox
                                           │
                                           ▼
                                  LIMS-ELN / ECML 闭环
```

---

## 3. 目录与模块职责

```text
openbatterysim/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── model_spm.yaml
│   ├── model_spme.yaml
│   ├── model_dfn.yaml
│   ├── thermal.yaml
│   ├── degradation.yaml
│   ├── ecm.yaml
│   ├── fit.yaml
│   └── battery_materials.yaml
├── parameter_sets/
│   ├── registry.yaml
│   ├── Chen2020.manifest.yaml
│   ├── Prada2013.manifest.yaml
│   └── custom/
├── protocols/
│   ├── cccv_standard.yaml
│   ├── hppc.yaml
│   ├── crate_sweep.yaml
│   └── cycle_life.yaml
├── schemas/
│   ├── cell_definition.v1.json
│   ├── test_protocol.v1.json
│   ├── experiment_data.v1.json
│   ├── simulation_result.v1.json
│   ├── fit_result.v1.json
│   └── task_event.v1.json
├── src/openbatterysim/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── params_cmd.py
│   │   ├── protocol_cmd.py
│   │   ├── simulate_cmd.py
│   │   ├── sweep_cmd.py
│   │   ├── ecm_cmd.py
│   │   ├── data_cmd.py
│   │   ├── fit_cmd.py
│   │   ├── compare_cmd.py
│   │   ├── report_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── enums.py
│   │   ├── models.py
│   │   ├── errors.py
│   │   ├── units.py
│   │   └── identifiers.py
│   ├── registry/
│   │   ├── parameter_sets.py
│   │   ├── variable_registry.py
│   │   ├── model_capabilities.py
│   │   └── compatibility.py
│   ├── protocol/
│   │   ├── schema.py
│   │   ├── compiler.py
│   │   ├── pybamm_experiment.py
│   │   ├── waveform.py
│   │   └── validator.py
│   ├── engines/
│   │   ├── pybamm_factory.py
│   │   ├── pybamm_solver.py
│   │   ├── ecm_thevenin.py
│   │   ├── pybop_adapter.py
│   │   └── result_extractor.py
│   ├── data/
│   │   ├── importer.py
│   │   ├── normalizer.py
│   │   ├── resampling.py
│   │   ├── segmentation.py
│   │   └── quality.py
│   ├── analysis/
│   │   ├── metrics.py
│   │   ├── soc.py
│   │   ├── sensitivity.py
│   │   ├── identifiability.py
│   │   └── comparison.py
│   ├── integration/
│   │   ├── material_parameter_link.py
│   │   ├── sample_link.py
│   │   ├── outbox.py
│   │   └── eln_bridge.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
│   │   ├── checkpoints.py
│   │   └── cache.py
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
    ├── nmc_graphite_cccv/
    ├── lfp_graphite_rate/
    ├── hppc_ecm/
    └── pybop_fit/
```

---

## 4. 环境与版本治理

### 4.1 环境文件

```yaml
name: openbatterysim
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
  - matplotlib
  - pytest
  - pip:
      - pybamm
      - pybop
      - orjson
      - structlog
```

### 4.2 `obatt doctor --strict`

输出并验证：

- Python、PyBaMM、PyBOP、NumPy、SciPy 版本
- 可用参数集及其 manifest 完整性
- PyBaMM 变量注册表版本
- 可选求解器与系统线性代数后端
- 读写目录、磁盘空间、默认 timeout
- 已安装的模型能力：热、退化、ECM、拟合

不允许在运行中只记录 `pybamm` 而不记录具体版本；变量名称和参数接口可能随版本变化。

---

## 5. 领域模型与标识

### 5.1 实体层级

```text
MaterialCandidate（材料候选）
    └── ElectrodeFormulation（电极配方）
          └── CellDesign（电芯设计）
                └── PhysicalCell（实际电芯/测试对象）
                      └── TestRun（一次实验）
                            └── MeasurementSeries（原始与标准化曲线）

SimulationRequest（模型请求）
    └── SimulationRun（一次模型运行）
          └── SimulationResult（时序结果）

FitRequest（拟合请求）
    └── FitRun（优化过程）
          └── FitResult（参数后验/最佳解/验证）
```

`material_id`、`formulation_id`、`cell_design_id`、`cell_id`、`sample_id` 不可互换。仅有材料名称时不能假装已经定义了电芯几何、负载量、N/P、温度边界和测试协议。

### 5.2 Pydantic 模型

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["parameter_set", "experiment", "literature", "computed", "user"]
    source_id: str | None = None
    source_uri: str | None = None
    license: str | None = None
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"


class CellDefinition(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    cell_design_id: str
    chemistry_family: Literal["NMC_graphite", "LFP_graphite", "NCA_graphite", "custom"]
    positive_material_id: str | None = None
    negative_material_id: str | None = None
    parameter_set_id: str
    nominal_capacity_ah: float = Field(gt=0)
    voltage_lower_v: float
    voltage_upper_v: float
    geometry: Literal["pouch", "cylindrical", "coin", "custom"]
    temperature_reference_k: float = Field(gt=0)
    provenance: list[Provenance]


class ProtocolStep(BaseModel):
    step_id: str
    action: Literal["rest", "cc", "cv", "cccv", "drive_cycle"]
    direction: Literal["charge", "discharge", "none"]
    current_a: float | None = None
    c_rate: float | None = None
    voltage_v: float | None = None
    duration_s: float | None = None
    until: list[str] = Field(default_factory=list)
    temperature_k: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentSeries(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    series_id: str
    cell_id: str
    sample_ids: list[str] = Field(default_factory=list)
    protocol_id: str
    time_s: list[float]
    voltage_v: list[float]
    current_a: list[float]
    temperature_k: list[float] | None = None
    capacity_ah: list[float] | None = None
    instrument_id: str | None = None
    method_id: str | None = None
    raw_file_sha256: str
    provenance: Provenance
```

### 5.3 输出变量规范

统一输出以下最小变量；不存在的变量填空并写入 `availability_reason`：

```text
time_s
step_index
cycle_index
voltage_v
current_a
power_w
charge_capacity_ah
discharge_capacity_ah
throughput_capacity_ah
soc_fraction
negative_surface_concentration_mol_m3
positive_surface_concentration_mol_m3
x_averaged_cell_temperature_k
heat_generation_w
solver_status
```

不要硬编码 PyBaMM 原始变量名。`variable_registry.py` 建立“规范名称 -> 当前 PyBaMM 名称/提取函数/前置能力”的版本化映射。

---

## 6. 参数集治理

### 6.1 参数集 manifest

```yaml
parameter_set_id: Chen2020
provider: pybamm
version: "pinned-by-environment"
chemistry:
  positive_electrode: NMC811
  negative_electrode: graphite
  cell_reference: LG_M50_21700
supported_models: [SPM, SPMe, DFN]
supported_options:
  thermal: [isothermal, lumped]
  degradation: []
validations:
  temperature_range_k: [273.15, 333.15]
  c_rate_guidance: "baseline only; validate above 1C"
known_limitations:
  - "Do not use as an LFP parameterization"
  - "Do not infer degradation without a degradation-capable parameter set"
license: "see upstream parameter source"
source: "PyBaMM parameter set"
```

### 6.2 初始注册表

| 参数集 ID | 正极 | 负极 | 推荐用途 | 限制 |
|---|---|---|---|---|
| `Chen2020` | NMC811 | 石墨 | 通用基线、DFN/SPMe | 不能替代 LFP 或 Si 体系 |
| `Chen2020_composite` | NMC811 | 石墨+Si | 复合负极敏感性 | 需核实模型选项兼容 |
| `OKane2022` | NMC811 | 石墨 | SEI/镀锂/裂纹研究 | 退化参数与协议强耦合 |
| `Prada2013` | LFP | 石墨 | LFP 基线 | 不用于 NMC 电压窗口 |
| `OKane2022_graphite_SiOx_halfcell` | 半电池 | 石墨+SiOx | SiOx 退化研究 | 不可直接当全电池 |

### 6.3 兼容性门禁

```python
def validate_request(request, manifest):
    assert request.model_family in manifest.supported_models
    assert request.thermal in manifest.supported_options["thermal"]
    if request.degradation and not request.degradation.issubset(manifest.supported_options["degradation"]):
        raise DomainError("PAR004", "degradation option unsupported by parameter set")
    assert_voltage_window_matches(request, manifest)
    assert_cell_chemistry_matches(request, manifest)
```

- 将 NMC 参数集用于 LFP，或反之，必须拒绝 `PAR001_CHEMISTRY_MISMATCH`。
- 使用退化选项时，参数集必须声明支持；不允许“开关打开就算模拟退化”。
- 用户覆盖参数时写入 `parameter_overrides.yaml`，每个字段必须有 value、unit、reason、provenance、review_status。

---

## 7. 模型路由与能力矩阵

### 7.1 选择规则

| 研究目标 | 默认模型 | 升级条件 |
|---|---|---|
| 低倍率快速筛选 | SPM | 浓差极化、热或 1C 以上关注时升级 SPMe/DFN |
| 1–3C 的速度/精度平衡 | SPMe | 需要完整电解液/颗粒耦合或发表级机理时升级 DFN |
| 高倍率、局部浓度、热、退化 | DFN | 需足够参数、算力和验证数据 |
| HPPC/BMS、实时工况 | ECM | 需要机理解释时回到 PyBaMM |
| 参数反演 | 与目标物理一致的 PyBaMM 或 ECM | 数据不足先做可识别性检查 |

### 7.2 模型能力 manifest

```yaml
DFN:
  supports: [cc, cv, cccv, thermal_isothermal, thermal_lumped, thermal_x_full, degradation_optional]
  required_parameter_groups: [geometry, transport, kinetics, ocp, thermal]
  expected_runtime_class: high
SPMe:
  supports: [cc, cv, cccv, thermal_isothermal, thermal_lumped]
  required_parameter_groups: [geometry, transport, kinetics, ocp]
  expected_runtime_class: medium
SPM:
  supports: [cc, cv, cccv, thermal_isothermal]
  required_parameter_groups: [particle_diffusion, kinetics, ocp]
  expected_runtime_class: low
TheveninECM:
  supports: [cc, drive_cycle, hppc, thermal_lumped_optional]
  required_parameter_groups: [ocv_soc, r0_soc_temp, r1_soc_temp, c1_soc_temp]
  expected_runtime_class: very_low
```

---

## 8. 实验协议 DSL 与状态机

### 8.1 YAML 协议格式

```yaml
protocol_id: PRT-CCCV-NMC-001
version: "1.0"
cell_design_id: CD-NMC811-GR-001
initial_soc_fraction: 0.5
ambient_temperature_k: 298.15
steps:
  - step_id: discharge_1
    action: cc
    direction: discharge
    c_rate: 0.2
    until: ["voltage <= 2.5 V"]
  - step_id: rest_1
    action: rest
    direction: none
    duration_s: 600
  - step_id: charge_1
    action: cc
    direction: charge
    c_rate: 0.2
    until: ["voltage >= 4.2 V"]
  - step_id: hold_1
    action: cv
    direction: charge
    voltage_v: 4.2
    until: ["abs(current) <= 0.05 A"]
  - step_id: rest_2
    action: rest
    direction: none
    duration_s: 600
repeat:
  count: 3
```

### 8.2 协议编译规则

```text
DRAFT -> VALIDATED -> COMPILED -> RUNNING -> COMPLETED
                         │             │
                         └-> REJECTED  └-> TERMINATED / FAILED
```

校验规则：

- `cc` 必须有 `current_a` 或 `c_rate`，不可同时缺失。
- `cv` 必须有 `voltage_v` 和至少一个结束条件/最大时长。
- `rest` 必须有 duration 或结束条件。
- 每个动作都要有安全终止条件，至少包含电压边界、时间边界或原始测试程序的可追溯限制。
- `c_rate` 转电流使用参数集/电芯定义中的 `nominal_capacity_ah`，并记录换算值。
- 所有方向、符号和 PyBaMM experiment 文本生成规则只能由一个 compiler 实现。

### 8.3 协议危险组合

| 规则 | 错误/警告 |
|---|---|
| 充电上限高于参数集声明上限 | `PRT003_VOLTAGE_LIMIT`，拒绝 |
| 放电下限低于参数集声明下限 | `PRT003_VOLTAGE_LIMIT`，拒绝 |
| CV 无 cutoff 且无 max duration | `PRT004_UNBOUNDED_CV`，拒绝 |
| 超出温度验证区间 | `PRT005_TEMPERATURE_EXTRAPOLATION`，警告或拒绝 |
| 协议与半电池/全电池不匹配 | `PRT006_CELL_CONTEXT_MISMATCH`，拒绝 |

---

## 9. PyBaMM 执行实现

### 9.1 工厂接口

```python
class PyBaMMFactory:
    def create_model(self, family: str, options: dict): ...
    def load_parameters(self, parameter_set_id: str, overrides: dict): ...
    def create_experiment(self, protocol: CompiledProtocol): ...
    def create_solver(self, solver_config: SolverConfig): ...
```

### 9.2 请求对象

```yaml
simulation_id: SIM-20260801-0001
model_family: DFN
parameter_set_id: Chen2020
thermal: lumped
degradation: []
protocol_path: protocols/cccv_standard.yaml
solver:
  method: auto
  rtol: 1.0e-6
  atol: 1.0e-6
  max_step_s: 10
output:
  canonical_variables: [time_s, voltage_v, current_a, discharge_capacity_ah, x_averaged_cell_temperature_k]
```

### 9.3 执行伪代码

```python
def run_pybamm(req: SimulationRequest) -> SimulationArtifacts:
    manifest = registry.get(req.parameter_set_id)
    validate_request(req, manifest)
    protocol = protocol_compiler.compile(req.protocol)
    model = factory.create_model(req.model_family, req.options)
    params = factory.load_parameters(req.parameter_set_id, req.overrides)
    sim = pybamm.Simulation(model, parameter_values=params, experiment=protocol.as_pybamm())
    solution = sim.solve(solver=factory.create_solver(req.solver))
    records = extractor.to_canonical_records(solution, req)
    qc = validate_solution(records, req)
    return artifact_writer.write(records, qc)
```

### 9.4 SOC 规范

对于 DFN/SPMe，不假设存在同名 `State of charge` 变量。默认由累计放电容量和额定容量计算：

\[
SOC(t) = SOC_0 - \frac{Q_{discharge}(t) - Q_{charge}(t)}{Q_{nominal}}
\]

`SOC_0` 必须来源于协议、实验预处理或明确假设；如果采用容量归一化，结果字段必须写 `soc_method=capacity_normalized_estimate`。出现容量衰减时，不得将固定额定容量 SOC 当作真实电极化学计量 SOC。

### 9.5 热模型规则

| thermal | 使用场景 | 必填参数 | 规范输出 |
|---|---|---|---|
| `isothermal` | 快速电化学基线 | reference temperature | 温度字段可为常数/不可用 |
| `lumped` | 均匀电芯温度 | volume、cooling area、heat transfer coefficient | `x_averaged_cell_temperature_k` |
| `x-full` | 厚度方向热梯度 | 额外热输运参数 | 映射的平均/场变量 |

热时间序列的变量提取必须通过 registry；不得固定读取 `Cell temperature [K]` 并假定所有模型都可用。

### 9.6 退化规则

退化运行必须在输出中写：

```text
degradation_enabled
mechanisms
parameter_set_id
parameter_overrides_hash
cycle_count
calendar_time_s
result_interpretation_limitations
```

一条 3 圈的模拟不应被表述为寿命预测；长期循环外推需要实测校准、累计误差评估和独立验证。

---

## 10. Thevenin ECM

### 10.1 模型方程

一阶 Thevenin 模型：

\[
V_t = OCV(SOC, T) - I R_0(SOC, T) - V_1
\]

\[
\frac{dV_1}{dt} = -\frac{V_1}{R_1 C_1} + \frac{I}{C_1}
\]

符号约定必须统一：本项目默认 `I > 0` 为放电。所有导入数据若采用相反符号，必须在 normalizer 显式转换并记录。

### 10.2 ECM 参数表

```text
soc_fraction,temperature_k,ocv_v,r0_ohm,r1_ohm,c1_f,source,fit_method
0.0,298.15,3.00,0.020,0.010,2000,HPPC-001,least_squares
```

### 10.3 HPPC 导入与分段

```bash
obatt data import --input hppc_raw.csv --mapping configs/instrument_mapping.yaml
obatt ecm segment-hppc --series EXP-HPPC-001 --config configs/hppc.yaml
obatt ecm fit --series EXP-HPPC-001 --model thevenin_1rc
obatt ecm validate --fit FIT-ECM-001 --series EXP-HPPC-VAL-001
```

分段器应识别 rest、脉冲、恢复段；无法可靠分段时输出 `ECM011_PULSE_SEGMENTATION_FAILED`，禁止静默给出参数。

### 10.4 ECM 验收输出

- 模拟与实测时间序列
- 总体 RMSE、MAE、最大绝对误差
- 按 SOC 窗口、温度、脉冲类型分组误差
- 参数连续性/正值检查
- 拟合与验证数据严格分开

---

## 11. PyBOP 参数辨识

### 11.1 拟合任务配置

```yaml
fit_id: FIT-DFN-001
engine: pybop
model_family: SPMe
parameter_set_id: Chen2020
experiment_series_ids: [EXP-RATE-001, EXP-RATE-002]
fit_parameters:
  - name: Negative electrode diffusivity [m2.s-1]
    lower: 1.0e-16
    upper: 1.0e-12
    transform: log10
    provenance: literature_range
  - name: Negative electrode exchange-current density [A.m-2]
    lower: 0.1
    upper: 100
    transform: log10
objective:
  metrics: [voltage_rmse]
  weights: {voltage: 1.0}
split:
  strategy: by_test_run
  validation_series_ids: [EXP-RATE-003]
optimizer:
  name: CMAES
  max_evaluations: 300
seed: 42
```

### 11.2 门禁

- 拟合参数数目不得超过数据能够支持的程度；V0.1 先限制为 1–5 个核心参数。
- 任何参数必须有单位、上下界、变换和来源。
- 禁止同一条曲线同时作为拟合和验证数据。
- 仅用 0.1C 曲线拟合高倍率扩散/动力学参数时标记 `FIT012_WEAK_EXCITATION`。
- 优化失败、边界黏附、不同初值多峰时必须报告，不能仅输出“最佳值”。

### 11.3 可识别性与不确定性

V2 最低实现：

1. 多初值重复优化；
2. 参数边界命中率；
3. 局部有限差分灵敏度矩阵；
4. 参数相关性/条件数；
5. bootstrap 或 profile-like 扰动区间（可选）。

```text
IDENTIFIABLE：多初值收敛一致、验证误差稳定、相关性可接受
WEAKLY_IDENTIFIABLE：可拟合但参数区间宽/相关性高
NON_IDENTIFIABLE：不同参数组合等价，禁止作为物理常数写回参数集
```

### 11.4 输出模型

```json
{
  "fit_id": "FIT-DFN-001",
  "status": "WEAKLY_IDENTIFIABLE",
  "best_parameters": [{"name":"...","value":2.1e-14,"unit":"m2/s","at_bound":false}],
  "objective_train": {"voltage_rmse_v":0.018},
  "objective_validation": {"voltage_rmse_v":0.031},
  "multi_start_summary": {"runs":12,"converged":10},
  "identifiability": {"condition_number":12000,"warnings":["FIT013"]},
  "provenance": {"parameter_set_id":"Chen2020","data_hashes":["..."]}
}
```

---

## 12. 实验湿数据接入

### 12.1 原始数据最小列

```text
timestamp,time_s,voltage_v,current_a,temperature_k,capacity_ah,cycle_index,step_index
```

导入器接受仪器原始列名映射，但标准化后只写规范列。例：

```yaml
source: cycler_vendor_x
columns:
  time_s: "Test_Time(s)"
  voltage_v: "Voltage(V)"
  current_a: "Current(A)"
  capacity_ah: "Capacity(Ah)"
units:
  current_a: A
  voltage_v: V
```

### 12.2 数据质量状态机

```text
RAW -> PARSED -> UNIT_NORMALIZED -> TIME_MONOTONIC -> SEGMENTED -> QC_PASSED
                                                   └-> QC_WARNING / QC_FAILED
```

QC 必须检查：时间单调、重复时间点、空值、单位、异常跃迁、符号一致性、SOC/容量边界、明显仪器断线。原始文件永不覆盖。

### 12.3 实验与仿真对齐

- 只允许在明确步骤边界后对齐；不可直接把完整循环按索引相减。
- 对齐策略：时间插值、容量域重采样、固定 SOC 对齐，必须写入结果。
- 比较时输出每段误差而非仅一个全局 RMSE。
- 仪器环境温度、夹具、静置、截止策略缺失时，报告 `CONTEXT_INCOMPLETE`。

---

## 13. 材料参数关联

OpenPymatgenLab、OpenLAMMPSFlow 或性质模型可以给出候选参数证据，例如晶格、扩散趋势、热导率估计；它们不能直接覆盖 PyBaMM 参数集。

```yaml
parameter_override:
  parameter_name: "Negative electrode diffusivity [m2.s-1]"
  value: 1.5e-14
  unit: m2/s
  source_type: computed
  source_task_id: tsk_xxx
  source_material_id: MAT-GR-001
  transformation: "unit_checked"
  applicability: "graphite electrode at 298.15 K; provisional"
  review_status: pending_expert_review
```

只有 `review_status=approved` 的 override 才可进入正式参数组；所有未批准 override 仅可用于 sandbox run，并在报告顶部标识。

---

## 14. 工件、Manifest 与 Outbox

### 14.1 运行目录

```text
runs/<run_id>/
├── inputs/
│   ├── request.yaml
│   ├── resolved_config.yaml
│   ├── parameter_manifest.yaml
│   ├── protocol.compiled.yaml
│   └── experimental_data_snapshot.parquet
├── work/
│   ├── solver_inputs/
│   ├── checkpoints/
│   └── optimizer/
├── results/
│   ├── timeseries.parquet
│   ├── timeseries.csv
│   ├── summary.json
│   ├── qc.json
│   ├── metrics.csv
│   ├── plots/
│   └── fit_result.json
├── outbox/events.jsonl
├── logs/
│   ├── obatt.log
│   ├── stdout.log
│   └── stderr.log
├── manifest.json
└── report.md
```

### 14.2 Manifest 必填项

```json
{
  "run_id":"...",
  "command":"obatt simulate p2d ...",
  "status":"SUCCESS",
  "input_hashes":{},
  "config_hash":"...",
  "parameter_set_id":"Chen2020",
  "parameter_manifest_hash":"...",
  "protocol_hash":"...",
  "engine_versions":{"pybamm":"...","pybop":"..."},
  "model_family":"DFN",
  "thermal":"lumped",
  "degradation":[],
  "artifact_hashes":{},
  "warnings":[]
}
```

### 14.3 事件

```text
simulation.started
simulation.completed
simulation.failed
experiment.imported
experiment.qc_failed
fit.started
fit.completed
fit.non_identifiable
parameter_override.pending_review
```

事件使用本地 `outbox/events.jsonl`；幂等键为 event type、run id、主要 artifact hash 的组合。

---

## 15. 数值、物理与业务验证

### 15.1 求解器 QC

| 检查 | 失败处理 |
|---|---|
| 解不存在或提前终止 | `SOL001`，保存最后状态和 solver log |
| NaN/Inf | `SOL002`，失败 |
| 时间序列不单调 | `SOL003`，失败 |
| 电压超合理硬阈值 | `SOL004`，警告/失败按配置 |
| 容量负值或不一致 | `SOL005`，失败 |
| 温度不合理 | `SOL006`，警告并提示热参数 |
| C-rate 与容量换算不符 | `SOL007`，失败 |

### 15.2 参数扫描联动规则

| 扫描 | 必须同步处理 |
|---|---|
| 电极厚度 | 额定容量、活性材料量、几何相关参数 |
| 孔隙率 | active material volume fraction、传输参数适用性评估 |
| 颗粒半径 | 扩散时间尺度、比表面积相关量 |
| 额定容量 | C-rate 转换电流，不自动修改几何 |
| 热边界 | cooling area、volume、heat transfer coefficient 的单位/几何一致性 |

任何只修改一个字段且违反联动规则的 sweep 应创建 `SWP003_INCONSISTENT_GEOMETRY`，要求用户确认覆盖。

### 15.3 业务结果措辞门禁

报告模板禁止使用“证明材料更优”“预测寿命为 X 年”“模型验证了安全性”。允许：

- “在该参数集、协议与模型假设下，模拟显示……”
- “该结果对参数 X 高敏感，需实测校准。”
- “该拟合在留出测试集上的电压 RMSE 为……”

---

## 16. CLI 规范

```bash
# 项目与参数
obatt init ./projects/nmc811_baseline
obatt doctor --strict
obatt params list
obatt params show Chen2020
obatt params validate --parameter-set Chen2020 --model DFN --thermal lumped

# 协议
obatt protocol validate protocols/cccv_standard.yaml --cell configs/cell.yaml
obatt protocol compile protocols/cccv_standard.yaml --output compiled_protocol.yaml

# PyBaMM
obatt simulate p2d --model SPM --parameter-set Chen2020 --protocol protocols/cccv_standard.yaml
obatt simulate p2d --model SPMe --parameter-set Chen2020 --protocol protocols/crate_sweep.yaml
obatt simulate p2d --model DFN --parameter-set Prada2013 --thermal lumped --protocol protocols/cccv_standard.yaml
obatt sweep crate --model SPMe --parameter-set Chen2020 --rates 0.2,0.5,1,2,3
obatt sweep parameter --request req.yaml --set "Negative electrode thickness [m]=8e-5,1e-4"

# ECM
obatt data import --input raw/hppc.csv --mapping configs/cycler_x.yaml --cell-id CELL-001
obatt ecm segment-hppc --series EXP-001
obatt ecm fit --series EXP-001 --model thevenin_1rc
obatt ecm simulate --fit FIT-ECM-001 --protocol protocols/hppc.yaml

# 拟合与比较
obatt fit run --config configs/fit.yaml
obatt fit inspect FIT-DFN-001
obatt compare --simulation SIM-001 --experiment EXP-001 --alignment capacity
obatt report --workdir runs/SIM-001
```

退出码：0 全成功；1 批处理部分成功；2 参数/配置错误；3 数据/协议无效；4 依赖不可用；5 求解失败；6 参数集/科学一致性违规；7 集成/工件错误。

---

## 17. 测试矩阵

### 17.1 单元测试

| 模块 | 场景 | 断言 |
|---|---|---|
| 参数 registry | NMC 参数用于 LFP 请求 | `PAR001` |
| protocol compiler | CV 无截止 | `PRT004` |
| C-rate | C/5 与 5Ah | 电流为 1 A |
| SOC | 充放电容量序列 | 符号与边界正确 |
| variable registry | thermal 不同选项 | 正确变量或 availability reason |
| ECM | 常参 1RC | ODE 解析/数值一致 |
| data normalizer | 相反电流符号原始数据 | 显式转换记录 |
| QC | 重复时间/NaN | 错误或警告正确 |
| fit config | 无边界参数 | 拒绝 |
| cache | 参数/协议版本改变 | 正确失效 |

### 17.2 集成测试

1. `Chen2020 + SPM + CCCV` 生成完整 timeseries、manifest 和报告。
2. `Prada2013 + DFN + lumped thermal` 生成规范温度变量。
3. LFP 请求 NMC 参数集必须拒绝。
4. 3 个 C-rate 的 SPMe 扫描产生独立子运行和聚合结果。
5. HPPC 导入 -> 分段 -> ECM 拟合 -> 留出验证完整闭环。
6. PyBOP 两参数拟合，检查多初值、验证集和 identifiability 输出。
7. 一个坏实验文件加两个好文件的 batch，退出码为 1 且好任务完成。
8. material parameter override 未批准时，正式运行拒绝、sandbox 运行标记。

### 17.3 回归基准

- NMC/石墨 CCCV 基线：曲线长度、终止电压、容量、时间在版本容差内。
- LFP/石墨低倍率放电：平台区和容量输出稳定。
- 1RC ECM 合成数据：参数误差低于预设阈值。
- 拟合 fixture：不同初值下可识别案例收敛至相近区间；不可识别案例必须标记。

### 17.4 性能验收

| 任务 | 规模 | 目标 |
|---|---:|---|
| SPM 单 CCCV | 3 个循环 | 普通 CPU < 2 分钟 |
| SPMe 5 个倍率 | 0.2–3C | < 20 分钟 |
| DFN 单循环 | 常规参数 | < 30 分钟，记录环境 |
| ECM 10,000 点 | 1RC | < 5 秒 |
| 两参数拟合 | 100 次评估 | < 1 小时，依设备记录 |

---

## 18. 实施里程碑

### M0：基础设施（2 天）

- 仓库、环境、CLI、run layout、manifest、错误模型、schemas
- 参数集 registry 与 `doctor`

### M1：协议与 PyBaMM 基线（5 天）

- CellDefinition、protocol DSL、compiler、SPM/SPMe/DFN 工厂
- canonical variable registry、结果导出和 QC

### M2：热、扫描与参数治理（5 天）

- thermal options、sweep planner、联动规则、parameter override 审批状态
- NMC/LFP/Si 体系门禁

### M3：ECM 与实测数据（5 天）

- 原始数据 mapping、QC、HPPC 分段、1RC Thevenin、验证报告

### M4：PyBOP 拟合（6 天）

- fit config、多初值、训练/验证、敏感性、可识别性、结果 schema

### M5：BatteryEMCL 集成（4 天）

- material/sample/cell/test run 关联、outbox、ELN 摘要导入
- 端到端演示：电芯测试数据 -> 拟合 -> sandbox 参数更新 -> 仿真比较

---

## 19. 验收 Definition of Done

- 不依赖私有 API 或固定云路径即可跑通示例。
- 每次仿真都绑定明确的参数集、协议、模型、热/退化选项与版本哈希。
- 不匹配化学体系和不支持模型选项在运行前被拒绝。
- 实验数据导入保存原始文件、字段映射、单位、QC、样品/电芯/设备来源。
- PyBOP 输出训练和验证误差、边界命中、多初值与可识别性，而非只有“最佳参数”。
- ECM 与 PyBaMM 结果明确注明适用范围，且姿态/拟合分数不被解释为材料本征性能。
- 全部回归、集成、性能测试通过，工件可被中间件读取。

---

## 20. 许可与合规

PyBaMM、PyBOP、参数集、实测数据和下游模型均需单独记录版本、来源与许可证。严禁将第三方电芯测试数据、供应商参数或受限数据自动上传到外部服务。所有模型结论必须与实验验证和业务审批流程区分；正式研发决策应由候选优先级委员会、实验偏差评审和外部证据采纳机制在 BatteryEMCL Lab 中完成。
