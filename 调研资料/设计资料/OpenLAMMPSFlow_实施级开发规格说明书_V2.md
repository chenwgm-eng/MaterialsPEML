# OpenLAMMPSFlow 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openlammpsflow`  
**CLI**：`olmp`  
**核心引擎**：LAMMPS；可选 pymatgen、mbuild/foyer、MDAnalysis、OVITO Python  
**定位**：BatteryEMCL Lab 的可追溯分子动力学执行、物理校验、轨迹分析与材料—电芯参数交接层

---

## 0. 文档定位

OpenLAMMPSFlow 是对 LAMMPS 的工作流封装，不是“根据元素自动选择一个力场”的黑箱。它的首要目标是将结构、拓扑、势函数、单位、输入脚本、运行阶段、轨迹、分析结果和科学假设绑定成可审计工件。

该系统特别支持锂电材料中的无机晶体、固态电解质、电极/电解液界面与有机电解液；但任何结果均只在明确势函数和采样条件的适用范围内有效。力场的选择、验证与引用不可被自动化流程替代。

---

## 1. 产品边界

### 1.1 必须交付

- 三条准备路径：无机晶体、分子/聚合物、已有生物/复杂拓扑
- 数据文件、类型映射、拓扑、净电荷、盒、质量和单位的强校验
- 势函数 manifest、文件哈希、元素覆盖、适用范围和许可证管理
- 可组合的最小化、NVT、NPT、NVE、退火、扩散生产阶段
- 语法、物理、协议三层验证以及运行前 dry-run
- 本地 OMP、MPI、可恢复子进程、超时、心跳、checkpoint
- RDF、MSD/扩散系数、密度、RMSD/RMSF、CNA/结构演变等分析
- 面向 OpenPymatgenLab、OpenPackmol、OpenBatterySim 的任务交接
- run manifest、日志、轨迹索引、质量控制和 ELN/LIMS outbox 事件

### 1.2 非目标

- 不自动为任意混合体系“猜测正确力场”或拼接未经验证的 cross-interactions
- 不将短时间 MD 的 MSD 斜率无条件报告为扩散系数
- 不把势函数结果宣称为 DFT/实验验证结果
- 不承担生产 HPC 调度器的所有职责；V2 仅支持可配置本地/MPI launcher
- 不替用户完成电解液化学反应、SEI 生长或热失控的完整预测

---

## 2. 系统架构

```text
OpenPymatgenLab / OpenPackmol / 用户拓扑
                     │
                     ▼
          System Manifest + ForceField Manifest
                     │
                     ▼
      数据准备 -> 输入模板编译 -> 三层验证
                     │
                     ▼
          LAMMPS 运行管理（OMP / MPI）
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
  thermo/log     dump/restart   profile/heartbeat
       │             │             │
       └─────────────┴──────► 轨迹分析与 QC
                                      │
                                      ▼
                            工件仓库 / outbox / 下游参数
```

---

## 3. 目录与文件职责

```text
openlammpsflow/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── runtime_omp.yaml
│   ├── runtime_mpi.yaml
│   ├── inorganic.yaml
│   ├── organic.yaml
│   ├── electrolyte.yaml
│   └── analysis.yaml
├── forcefields/
│   ├── registry.yaml
│   ├── manifests/
│   └── user_supplied/
├── templates/
│   ├── minimize.in.j2
│   ├── nvt.in.j2
│   ├── npt.in.j2
│   ├── diffusion.in.j2
│   ├── rdf.in.j2
│   └── generic_protocol.in.j2
├── schemas/
│   ├── system_manifest.v1.json
│   ├── forcefield_manifest.v1.json
│   ├── protocol.v1.json
│   ├── run_request.v1.json
│   ├── trajectory_metric.v1.json
│   └── task_event.v1.json
├── src/openlammpsflow/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── prepare_cmd.py
│   │   ├── forcefield_cmd.py
│   │   ├── generate_cmd.py
│   │   ├── validate_cmd.py
│   │   ├── run_cmd.py
│   │   ├── resume_cmd.py
│   │   ├── analyze_cmd.py
│   │   ├── export_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── units.py
│   │   └── identifiers.py
│   ├── preparation/
│   │   ├── classifier.py
│   │   ├── inorganic.py
│   │   ├── organic.py
│   │   ├── imported_topology.py
│   │   ├── type_mapping.py
│   │   └── data_validator.py
│   ├── forcefield/
│   │   ├── registry.py
│   │   ├── manifest.py
│   │   ├── compatibility.py
│   │   ├── potential_files.py
│   │   └── parameter_coverage.py
│   ├── protocol/
│   │   ├── schema.py
│   │   ├── compiler.py
│   │   ├── stage_machine.py
│   │   └── templates.py
│   ├── validation/
│   │   ├── syntax.py
│   │   ├── lammps_dryrun.py
│   │   ├── physics.py
│   │   ├── dof.py
│   │   ├── protocol.py
│   │   └── units.py
│   ├── runtime/
│   │   ├── launcher.py
│   │   ├── omp.py
│   │   ├── mpi.py
│   │   ├── monitor.py
│   │   ├── restart.py
│   │   └── log_parser.py
│   ├── analysis/
│   │   ├── trajectory_reader.py
│   │   ├── rdf.py
│   │   ├── msd.py
│   │   ├── diffusion.py
│   │   ├── density.py
│   │   ├── structure.py
│   │   ├── convergence.py
│   │   └── uncertainty.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
│   │   ├── cache.py
│   │   └── checkpoints.py
│   ├── integration/
│   │   ├── task_contract.py
│   │   ├── openpymatgen.py
│   │   ├── openpackmol.py
│   │   ├── openbatterysim.py
│   │   ├── sample_link.py
│   │   └── outbox.py
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
    ├── li_metal_eam/
    ├── lifepo4_buckingham/
    ├── llzo_diffusion/
    ├── electrolyte_opls/
    └── interface_packmol/
```

---

## 4. 环境与运行能力

```yaml
name: openlammpsflow
channels: [conda-forge]
dependencies:
  - python=3.11
  - lammps
  - numpy
  - scipy
  - pandas
  - pyarrow
  - pydantic>=2
  - typer
  - rich
  - pyyaml
  - pymatgen
  - mdanalysis
  - ovito
  - pytest
  - pip
  - pip:
      - structlog
      - orjson
```

`olmp doctor --strict` 必须检测：`lmp` 路径和版本、已编译 packages、OpenMP/MPI 可用性、势函数目录、Python 库、可用分析后端、磁盘空间和默认线程数。不得假设所有 LAMMPS 二进制都含相同 package。

---

## 5. 三条系统准备路径

### 5.1 路径 A：无机晶体与电池固体

适用：金属、合金、离子氧化物、磷酸盐、硫化物、共价晶体、固态电解质。

```text
OpenPymatgenLab task package / CIF / POSCAR
  -> 原子类型映射与电荷策略
  -> LAMMPS data (atomic / charge / full)
  -> 势函数 manifest 校验
  -> LAMMPS 数据与协议包
```

可选势族必须由用户/专家选择并在 manifest 中声明，例如：EAM、Buckingham+Coulomb、Tersoff、Stillinger-Weber、ReaxFF、专用 ML potential。系统只能验证覆盖范围和配置一致性，不能替代势函数基准验证。

### 5.2 路径 B：有机分子、溶剂和聚合物

适用：已完成参数化的有机分子、聚合物、电解液混合物。

```text
OpenPackmol PDB/XYZ + 拓扑/力场参数
  -> mbuild/foyer 或用户提供 LAMMPS data
  -> atom_style full
  -> 键、角、二面角、improper、部分电荷校验
  -> OPLS-AA 或显式命名的其他兼容力场
```

对含 P、Si、Se、Te、过渡金属、离子对或电极界面体系，默认禁止自动以 OPLS-AA 参数化并要求人工确认 `FF012_COMPLEX_CHEMISTRY_REVIEW_REQUIRED`。

### 5.3 路径 C：已有复杂拓扑

适用：CHARMM、AMBER、GROMACS 或其他上游已建立拓扑的系统。

只负责导入/转换、类型映射与 LAMMPS 一致性校验；不负责重新参数化。PSF/PRM、prmtop/inpcrd、GROMACS top/gro 的来源、转换器版本和原始拓扑哈希必须保留。

---

## 6. 领域数据模型

### 6.1 System Manifest

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any

class SystemManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    system_id: str
    system_kind: Literal["inorganic", "organic", "polymer", "electrolyte", "interface", "imported_topology"]
    source_structure_ids: list[str] = Field(default_factory=list)
    input_files: list[dict[str, str]]
    atom_style: Literal["atomic", "charge", "molecular", "full"]
    units: Literal["metal", "real", "si", "lj"]
    atom_type_map: dict[int, dict[str, Any]]
    n_atoms: int = Field(gt=0)
    total_charge_e: float | None = None
    box: dict[str, float]
    topology_counts: dict[str, int]
    periodicity: tuple[bool, bool, bool]
    provenance: list[dict[str, Any]]

class ForceFieldManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    forcefield_id: str
    family: Literal["EAM", "Buckingham_Coulomb", "Tersoff", "SW", "ReaxFF", "OPLS_AA", "CHARMM", "AMBER", "custom"]
    potential_files: list[dict[str, str]]
    supported_elements: list[str]
    supported_atom_types: list[int] | None = None
    units: Literal["metal", "real", "si", "lj"]
    required_lammps_packages: list[str]
    pair_style: str
    pair_coeff: list[str]
    long_range_electrostatics_required: bool
    mixing_rule: str | None = None
    validation_scope: str
    citations: list[str]
    license: str
    sha256: str
```

### 6.2 原子类型映射

```yaml
atom_type_map:
  1: {element: Li, label: Li_plus, mass_g_mol: 6.94, charge_e: 1.0}
  2: {element: O, label: O_oxide, mass_g_mol: 15.999, charge_e: -2.0}
```

元素相同但化学环境不同的原子可以使用不同类型；`element` 不能替代 `atom_type`。所有类型都必须在势函数/拓扑中有定义。

### 6.3 运行状态机

```text
DRAFT
 -> PREPARED
 -> FORCEFIELD_BOUND
 -> INPUT_COMPILED
 -> SYNTAX_VALIDATED
 -> PHYSICS_VALIDATED
 -> PROTOCOL_APPROVED
 -> QUEUED
 -> RUNNING
 -> ANALYZING
 -> COMPLETED

任意阶段 -> REJECTED / FAILED / CANCELLED
RUNNING -> CHECKPOINTED -> QUEUED（恢复）
```

只有 `PROTOCOL_APPROVED` 的请求可启动 LAMMPS。`--override` 必须提供 reason，并生成 `OVERRIDE_USED` 事件。

---

## 7. 势函数治理与兼容性

### 7.1 势函数 manifest 示例

```yaml
forcefield_id: FF-LI-ION-OXIDE-001
family: Buckingham_Coulomb
potential_files:
  - {path: potentials/li_oxide.params, sha256: "...", license: "user-provided"}
supported_elements: [Li, O]
units: metal
required_lammps_packages: [KSPACE]
pair_style: "buck/coul/long 10.0"
pair_coeff:
  - "1 1 0.0 1.0 0.0"
  - "1 2 1000.0 0.3 10.0"
  - "2 2 2000.0 0.2 20.0"
long_range_electrostatics_required: true
mixing_rule: null
validation_scope: "Li-O bulk oxide only; not validated for electrolyte interface"
citations: ["..."]
license: "..."
sha256: "..."
```

### 7.2 强制规则

| 条件 | 规则 |
|---|---|
| EAM 金属 | `units metal`、元素映射、EAM 势文件和 `pair_coeff` 全覆盖 |
| 带电离子体系 | 明确电荷、Coulomb long-range 策略、kspace 参数与截断 |
| `atom_style full` | 需有 bond/angle/dihedral/improper 一致性和对应 style |
| OPLS-AA | 要求 `lj/cut/coul/long`、几何 mixing、PPPM、正确 special_bonds；否则拒绝 |
| ReaxFF | 势文件元素顺序、qeq 设置、时间步和温度控制审查 |
| 混合势 | 必须存在经过审核的 cross-interaction 方案；默认拒绝自动拼接 |

### 7.3 关键禁止项

- 金属体系无依据使用裸 `lj/cut`：`FF001_METAL_LJ_FORBIDDEN`。
- 势函数文件缺少某类型/元素：`FF002_COVERAGE_GAP`。
- 势函数单位与 LAMMPS `units` 不一致：`FF003_UNITS_MISMATCH`。
- 电荷体系无 kspace 或明确短程近似声明：`FF004_ELECTROSTATICS_INCOMPLETE`。
- 使用未经许可或缺来源的势文件：`FF005_PROVENANCE_MISSING`。

---

## 8. 协议 DSL 与输入脚本编译

### 8.1 协议 YAML

```yaml
protocol_id: PR-MD-LI-DIFF-001
system_id: SYS-LLZO-001
forcefield_id: FF-LLZO-001
units: metal
atom_style: charge
stages:
  - id: minimize
    kind: minimize
    energy_tolerance: 1.0e-10
    force_tolerance: 1.0e-8
    max_iterations: 10000
  - id: npt_equilibrate
    kind: dynamics
    ensemble: npt
    temperature_k: 300
    pressure_bar: 1.0
    timestep_ps: 0.001
    steps: 200000
    thermostat_damping_ps: 0.1
    barostat_damping_ps: 1.0
  - id: nvt_production
    kind: dynamics
    ensemble: nvt
    temperature_k: 300
    timestep_ps: 0.001
    steps: 1000000
    dump_every_steps: 1000
analysis_requests: [msd, rdf, density]
```

### 8.2 编译后的 LAMMPS 结构

```lammps
units           metal
atom_style      charge
boundary        p p p
read_data       data.system

pair_style      buck/coul/long 10.0
pair_coeff      ...
kspace_style    pppm 1.0e-5

thermo          1000
thermo_style    custom step temp pe ke etotal press vol density

min_style       cg
minimize        1.0e-10 1.0e-8 10000 100000

reset_timestep  0
velocity        all create 300.0 42 mom yes rot yes dist gaussian
fix             integ all npt temp 300.0 300.0 0.1 iso 1.0 1.0 1.0
run             200000
unfix           integ
```

模板仅负责语法生成；领域规则（单位、势函数、阶段、时间步）必须在编译前校验。

### 8.3 阶段状态机

```text
MINIMIZE_REQUIRED
  -> MINIMIZED
  -> EQUILIBRATING (NPT or NVT)
  -> EQUILIBRATED
  -> PRODUCTION
  -> POSTPROCESSING
```

若协议跳过最小化，必须写 `skip_minimize: true`、原因和审核人。每个 `run` 前必须有 active 积分 fix；每个阶段完成后检查 thermo 指标，失败不自动进入下一阶段。

### 8.4 约束、自由度与温控

- 任何 `fix shake`、`rigid`、`momentum`、冻结 group 都要登记受影响原子数和自由度。
- 温度 compute 与 thermostat group 必须一致，防止冻结原子/刚体导致温度错误。
- 分子体系中的 constraint 不应与不兼容的积分/thermostat 重复施加。
- `dof.py` 输出：总 DOF、约束移除 DOF、温度 DOF、警告。

---

## 9. 三层验证

### 9.1 第一层：静态语法

- 输入脚本命令存在、参数数量正确、变量引用完整
- 所有 include、势函数、data、restart 文件可读
- 由 `lmp -echo none -log none -screen none` 或受控 dry-run 验证可行时执行
- 解析后输出 command AST，避免只做正则匹配

### 9.2 第二层：物理一致性

| 检查 | 示例 |
|---|---|
| 单位 | 势函数、time step、温压阻尼、速度、输出单位一致 |
| 类型覆盖 | data 内每个 atom type 在 pair/bond/angle 系数中可解析 |
| 电荷 | 总电荷、long-range、kspace、cutoff 逻辑完整 |
| 时间步 | 势族/温度/轻原子/反应性体系在允许区间 |
| 体系 | forcefield scope 与 system kind/元素/化学环境一致 |
| 边界 | 非周期方向与 kspace/压力控制组合合理 |
| 初始构型 | 原子重叠、过高能量、盒尺寸、密度检查 |

### 9.3 第三层：协议与收敛

- 最小化是否收敛或达到明确上限。
- 平衡阶段的温度、压力、密度、能量是否进入稳定统计区间。
- 生产段长度是否足以支持所请求分析；例如扩散系数需有明确线性 MSD 区间。
- 是否存在未解释的能量漂移、温度漂移、原子丢失、邻居列表异常。

```yaml
qc_thresholds:
  temperature_relative_deviation: 0.05
  pressure_stationarity_window_steps: 50000
  max_energy_drift_per_atom_per_ns: 0.01
  min_msd_fit_r2: 0.95
  min_diffusion_fit_points: 30
```

阈值是协议可配置的，但修改必须记录原因；不得用宽松阈值掩盖失败。

---

## 10. 运行管理

### 10.1 CLI

```bash
olmp init ./projects/llzo_diffusion
olmp doctor --strict
olmp prepare inorganic --structure llzo.cif --atom-style charge --output system/
olmp prepare organic --input packmol_mixture.pdb --topology topology.json --output system/
olmp forcefield register --manifest forcefields/llzo.yaml
olmp generate --system system/system_manifest.json --protocol configs/llzo_diffusion.yaml
olmp validate --workdir runs/llzo_001 --level all
olmp run --workdir runs/llzo_001 --backend omp --threads 4
olmp run --workdir runs/llzo_001 --backend mpi --ranks 16 --launcher mpirun
olmp resume --workdir runs/llzo_001 --from restart
olmp analyze msd --workdir runs/llzo_001 --species Li
olmp analyze rdf --workdir runs/llzo_001 --pairs Li-O,O-O
olmp export --workdir runs/llzo_001 --target openbatterysim
```

### 10.2 OMP 与 MPI launcher

```yaml
runtime:
  backend: omp
  executable: lmp
  omp_threads: 4
  timeout_s: 0
  heartbeat_interval_s: 60
  stop_grace_s: 30

mpi:
  launcher: mpirun
  ranks: 16
  extra_args: []
```

短任务可用受控 `subprocess.run`；长任务必须用 `Popen` 逐行读取 stdout、写 heartbeat、捕获退出码。禁止在命令末尾使用 `; exit 0` 掩盖 LAMMPS 失败。

### 10.3 运行监控与停止

```text
QUEUED -> STARTING -> RUNNING -> CHECKPOINTING -> COMPLETED
                        │          │
                        ▼          └-> RESUMABLE
                     STALLED
                        │
                        ▼
                     FAILED
```

- `heartbeat` 从最新 log/thermo 写入/进程状态产生。
- 超时先请求 checkpoint/优雅停止，再等待 `stop_grace_s`，最后终止并保留完整日志。
- restart 只能使用同一 data、势函数、关键输入与 LAMMPS 版本兼容性校验通过的情形。

---

## 11. 工件、Manifest 与缓存

```text
runs/<run_id>/
├── inputs/
│   ├── system_manifest.json
│   ├── forcefield_manifest.yaml
│   ├── protocol.resolved.yaml
│   ├── data.system
│   └── potential_files/
├── compiled/
│   ├── in.lammps
│   ├── command_ast.json
│   └── validation_plan.json
├── work/
│   ├── log.lammps
│   ├── thermo.csv
│   ├── dump.*.lammpstrj
│   └── restart.*
├── results/
│   ├── qc.json
│   ├── metrics.parquet
│   ├── rdf.csv
│   ├── msd.csv
│   ├── diffusion.json
│   ├── plots/
│   └── export_package/
├── outbox/events.jsonl
├── logs/
├── manifest.json
└── report.md
```

缓存键：结构/拓扑哈希、forcefield manifest 哈希、协议解析配置、LAMMPS 版本、MPI/OMP 后端和 seed 的哈希组合。不得只按输入脚本文件名缓存。

---

## 12. 轨迹分析

### 12.1 标准分析接口

```bash
olmp analyze rdf --workdir runs/run_001 --pairs Li-O,O-O --r-max-a 10 --bins 200
olmp analyze msd --workdir runs/run_001 --species Li --unwrap-pbc --fit-window-ns 0.2:1.0
olmp analyze diffusion --workdir runs/run_001 --species Li --bootstrap 200
olmp analyze density --workdir runs/run_001
olmp analyze structure --workdir runs/run_001 --method cna
olmp analyze convergence --workdir runs/run_001
```

### 12.2 RDF

输出必须含：物种对、归一化方案、r bins、帧范围、PBC、体积计算方式。不同密度/盒大小/组分的 RDF 不可只看峰高作绝对比较。

### 12.3 MSD 与扩散系数

三维 Einstein 关系：

\[
D = \frac{1}{6} \frac{d}{dt}\langle |\mathbf{r}(t)-\mathbf{r}(0)|^2 \rangle
\]

实现要求：

1. 坐标进行 PBC unwrap；
2. 指定粒子组/物种；
3. 排除平衡期；
4. 在用户指定或自动建议的线性窗口拟合；
5. 输出斜率、\(D\)、R2、样本数、窗口、block/bootstrap 不确定性；
6. 若无可靠线性区间，标记 `ANL021_DIFFUSION_NOT_CONVERGED`，不输出正式 D。

对各向异性材料，支持分量：

\[
D_\alpha = \frac{1}{2}\frac{d}{dt}\langle (r_\alpha(t)-r_\alpha(0))^2 \rangle
\]

### 12.4 离子电导率

Nernst–Einstein 近似仅在明确假设下输出：

\[
\sigma_{NE} = \frac{1}{V k_B T} \sum_i N_i q_i^2 D_i
\]

必须在报告中显示 `ASSUMPTION_NERNST_EINSTEIN_UNCORRELATED_MOTION`；它通常忽略离子相关运动，不能直接等同实验电导率。若实现 Green–Kubo 或 collective MSD，必须作为独立方法与字段输出。

### 12.5 结构与界面分析

- 无机晶体：CNA/PTM、配位数、晶格参数、缺陷计数、RDF。
- 分子电解液：RDF、溶剂化壳、配位、离子团簇、扩散。
- 界面：密度剖面、组分 profile、吸附/停留时间；所有法向方向和 binning 必须记录。

OVITO 与 MDAnalysis 输出相同的 `TrajectoryMetric` schema，不允许用工具名决定字段含义。

---

## 13. 与 BatteryEMCL 的集成

### 13.1 入站任务包

OpenPymatgenLab 输入应包含结构、材料 ID、变换来源、单位和 hash。OpenPackmol 输入应包含组分数、盒、seed、重叠检查与拓扑参数化状态。

### 13.2 出站参数证据

```yaml
parameter_evidence:
  evidence_id: EVD-MD-0001
  property: lithium_diffusion_coefficient
  value: 2.3e-12
  unit: m2/s
  method: MSD_Einstein
  species: Li
  temperature_k: 300
  forcefield_id: FF-LLZO-001
  trajectory_window_ns: [0.2, 1.0]
  fit_r2: 0.97
  uncertainty: {kind: bootstrap_95ci, lower: 1.5e-12, upper: 3.4e-12}
  status: provisional_computational_evidence
  limitations: ["forcefield dependent", "finite-size effects not corrected"]
```

OpenBatterySim 仅可将它作为待审核 parameter override 的证据，不应自动覆盖电芯参数集。

### 13.3 Outbox 事件

```text
md.prepared
md.validation_failed
md.started
md.checkpointed
md.completed
md.analysis_completed
md.diffusion_not_converged
md.parameter_evidence_created
```

每个事件都应关联 material、sample（如有）、system、forcefield、run 和 artifact hash。

---

## 14. 错误码与恢复策略

| 错误码 | 说明 | 可重试 |
|---|---|---|
| `SYS001` | data 文件/结构不完整 | 否 |
| `SYS002` | 原子类型或拓扑不一致 | 否 |
| `FF001`–`FF005` | 势函数治理/覆盖/单位错误 | 否 |
| `INP001` | 编译后脚本语法失败 | 否 |
| `PHY001` | time step 或单位不合理 | 否，需修改协议 |
| `PHY002` | 无 active integration fix | 否 |
| `PHY003` | 生产前未最小化/平衡 | 否，除非显式 override |
| `RUN001` | LAMMPS 非零退出 | 视日志判断 |
| `RUN002` | 超时/卡死 | 是，若有 restart |
| `RUN003` | 磁盘不足 | 是，释放空间后 |
| `ANL021` | 扩散未收敛 | 否，需更长/更稳轨迹 |
| `INT001` | 下游任务包失败 | 是 |

---

## 15. 测试矩阵

### 15.1 单元测试

| 模块 | 场景 | 断言 |
|---|---|---|
| system classifier | 金属、氧化物、电解液、复杂元素 | 路由与人工审查正确 |
| type mapping | 同元素多化学环境 | 映射不丢失类型 |
| FF manifest | 缺元素/类型 | `FF002` |
| units | metal 势 + real 输入 | `FF003` |
| protocol compiler | NVT 无 fix | `PHY002` |
| DOF | rigid + shake | DOF 计算/冲突警告 |
| data validator | 原子重叠 | 拒绝 |
| MSD | 布朗运动合成轨迹 | D 与设定值容差内 |
| diffusion | 非线性 MSD | `ANL021` |
| cache | 势文件 hash 改变 | 缓存失效 |

### 15.2 集成测试

1. 金属 EAM：准备 -> 最小化 -> NPT -> RDF，确保 EAM/metal 规则生效。
2. 离子氧化物：带电 `charge` data、Buckingham+Coulomb、PPPM、热力学输出。
3. LFP/LLZO：从 OpenPymatgenLab 包导入，生成扩散协议与 MD evidence。
4. OPLS 电解液：从 OpenPackmol 包导入，检查 full style、长程静电、special bonds。
5. 强制错误：金属用 LJ、带电体系缺 kspace、生产段无 fix，均必须在运行前失败。
6. restart：人为中断后从 restart 继续，manifest 保留 lineage。
7. batch：三任务中一个坏势文件，其他任务完成，返回部分成功。

### 15.3 性能目标

| 任务 | 规模 | 目标 |
|---|---:|---|
| 输入生成与三层验证 | <= 10k atoms | < 30 秒 |
| 轨迹 MSD/RDF 后处理 | 10k atoms、1k 帧 | < 10 分钟，记录硬件 |
| OMP smoke MD | <= 2k atoms、10k steps | < 10 分钟 |
| MPI smoke MD | 4 ranks | 成功启动并保存一致 manifest |

---

## 16. 实施计划

### M0：基础设施（2 天）

目录、CLI、domain schema、run/artifact store、doctor、错误模型和 fixtures。

### M1：准备与势函数治理（5 天）

三路径 router、System/ForceField manifest、data validator、类型映射、势函数覆盖与单位校验。

### M2：协议编译与三层验证（5 天）

YAML protocol、Jinja 模板、command AST、syntax/physics/DOF/protocol validator、dry-run。

### M3：运行与恢复（4 天）

OMP/MPI launcher、monitor、heartbeat、timeout、restart、log/thermo parser。

### M4：轨迹分析（6 天）

MDAnalysis/OVITO adapter、RDF、MSD、扩散、密度、收敛、不确定性和报告。

### M5：电池材料闭环集成（4 天）

OpenPymatgenLab/OpenPackmol 输入包、OpenBatterySim evidence、sample link、outbox、端到端示例。

---

## 17. Definition of Done

- 任意运行都可回溯 system、forcefield、协议、LAMMPS 版本、输入/势文件哈希和分析配置。
- 无机、有机/聚合物、导入拓扑三条路径都有可运行示例和失败案例。
- 势函数不匹配、单位不一致、缺积分 fix、缺静电处理等错误均在运行前阻断。
- 轨迹分析至少输出方法、帧范围、PBC、拟合窗口、误差与收敛状态。
- 不能收敛的 MSD 不会被包装为扩散系数。
- 计算参数证据带有势函数和条件限制，必须经审核才能影响 OpenBatterySim。
- 本地运行不需要私有服务、固定云路径或隐藏预装资产。

---

## 18. 许可、引用与科学责任

LAMMPS、势函数文件、参数化工具、轨迹与分析库均有各自的许可证和引用要求。每个 forcefield manifest 都必须记录完整来源、适用域和引用；不可把“可运行”理解为“已验证”。对电池体系尤其要记录电极化学态、缺陷、界面、电荷、温压和时间尺度等限制，避免将纳秒级经典 MD 结果直接外推到实验循环寿命或宏观安全性。
