# OpenPackmol 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openpackmol`  
**CLI**：`opack`  
**核心引擎**：Packmol  
**定位**：BatteryEMCL Lab 的分子体系初始构型构建层，用于电解液、溶剂化离子、聚合物/溶剂混合物、液液界面和后续 LAMMPS/GROMACS/AMBER 模拟的可追溯起点

---

## 0. 文档定位

OpenPackmol 将“给定若干分子文件，把它们塞进盒子”升级为可审计工作流：配方/计数/密度/电荷/空间约束明确化，Packmol 输入可复现，输出接受结构、计数、重叠、密度、边界和交接完整性验证。

Packmol 仅生成几何初始构型；它不参数化力场、不生成键角二面角、不计算合理能量、不保证热力学平衡，也不能证明离子溶剂化或界面结构真实。任何 Packmol 输出在进入 MD 生产阶段前必须由 OpenLAMMPSFlow 或其他 MD 引擎完成拓扑/力场检查与能量最小化。

---

## 1. 目标与边界

### 1.1 V2 必须交付

- PDB/XYZ/Tinker 模板导入、原子/分子计数、质量、电荷与坐标校验
- 按分子数、摩尔分数、质量分数、目标密度、盐浓度生成配方
- 正交盒、球、圆柱、平面上下、椭球、固定物体与原子级约束 DSL
- 基本混合物、溶剂化、界面、分区/双层等模板工作流
- Packmol 输入编译、随机种子、运行日志、restart/增量构建
- 最小原子距离、跨周期重叠、分子计数、密度、区域占据、PBC、净电荷 QC
- LAMMPS/GROMACS/AMBER 交接 manifest；明确不含拓扑/力场参数
- 物性/配方证据与 BatteryEMCL 样品/材料/实验关联、outbox 事件

### 1.2 非目标

- 不自动分配 OPLS、GAFF、CHARMM、ReaxFF 或任何力场参数
- 不将 PDB residue name 当作化学身份或净电荷的唯一依据
- 不因“没有完全堆积”而自动宣称结果可用于生产 MD
- 不为浓盐电解液自动推断离子解离、配位或化学反应
- 不负责从 Packmol 直接转换至任意引擎的完整拓扑，除非另有明确 adapter

---

## 2. 总体架构

```text
OpenChemProperties / 用户配方 / ELN 样品信息
                     │
                     ▼
           Recipe + Component Template Registry
                     │
                     ▼
    count/density/charge/region planner -> Packmol DSL compiler
                     │
                     ▼
                packmol subprocess
                     │
                     ▼
      output parser -> geometry QC -> handoff manifest / outbox
                     │
          ┌──────────┴───────────┐
          ▼                      ▼
  OpenLAMMPSFlow             GROMACS/AMBER adapter
```

---

## 3. 目录与文件职责

```text
openpackmol/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── mixture.yaml
│   ├── solvation.yaml
│   ├── interface.yaml
│   ├── electrolyte.yaml
│   └── validation.yaml
├── templates/
│   ├── basic_mixture.yaml
│   ├── solvation_shell.yaml
│   ├── liquid_liquid_interface.yaml
│   ├── layered_electrolyte.yaml
│   └── incremental_build.yaml
├── schemas/
│   ├── molecule_template.v1.json
│   ├── component_spec.v1.json
│   ├── packing_recipe.v1.json
│   ├── packing_result.v1.json
│   ├── packing_qc.v1.json
│   ├── lammps_handoff.v1.json
│   └── task_event.v1.json
├── src/openpackmol/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── template_cmd.py
│   │   ├── recipe_cmd.py
│   │   ├── build_cmd.py
│   │   ├── solvate_cmd.py
│   │   ├── interface_cmd.py
│   │   ├── validate_cmd.py
│   │   ├── export_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── units.py
│   │   └── identifiers.py
│   ├── templates/
│   │   ├── parser.py
│   │   ├── identity.py
│   │   ├── geometry.py
│   │   ├── mass.py
│   │   └── charge.py
│   ├── recipe/
│   │   ├── composition.py
│   │   ├── density.py
│   │   ├── ion_balance.py
│   │   ├── region_planner.py
│   │   └── validator.py
│   ├── constraints/
│   │   ├── models.py
│   │   ├── box.py
│   │   ├── sphere.py
│   │   ├── cylinder.py
│   │   ├── plane.py
│   │   ├── ellipsoid.py
│   │   └── compiler.py
│   ├── engine/
│   │   ├── input_compiler.py
│   │   ├── runner.py
│   │   ├── output_parser.py
│   │   └── restart.py
│   ├── validation/
│   │   ├── input.py
│   │   ├── counts.py
│   │   ├── overlaps.py
│   │   ├── density.py
│   │   ├── regions.py
│   │   ├── pbc.py
│   │   └── charge.py
│   ├── integration/
│   │   ├── chemproperties.py
│   │   ├── lammps_handoff.py
│   │   ├── sample_link.py
│   │   └── outbox.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
│   │   └── cache.py
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
    ├── ec_emc_electrolyte/
    ├── lifsi_dme/
    ├── water_ethanol/
    ├── liquid_liquid_interface/
    └── solvation_shell/
```

---

## 4. 环境与诊断

```yaml
name: openpackmol
channels: [conda-forge]
dependencies:
  - python=3.11
  - packmol
  - numpy
  - scipy
  - pandas
  - pydantic>=2
  - typer
  - rich
  - pyyaml
  - pytest
  - pip
  - pip:
      - MDAnalysis
      - structlog
      - orjson
```

`opack doctor --strict` 应检查 Packmol 二进制与版本、支持的输入/输出格式、本地模板目录、写权限、可用磁盘、Python 解析库与默认验证阈值。不能假设 Packmol 的安装位置或将任何预装二进制路径写死。

---

## 5. 领域数据模型

### 5.1 MoleculeTemplate

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any

class MoleculeTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    template_id: str
    chemical_id: str | None = None
    source_path: str
    format: Literal["pdb", "xyz", "tinker"]
    molecule_name: str
    atoms_per_molecule: int = Field(gt=0)
    molecular_weight_g_mol: float | None = Field(default=None, gt=0)
    net_charge_e: float | None = None
    residue_name: str | None = None
    coordinates_unit: Literal["angstrom"] = "angstrom"
    geometry_hash: str
    identity_status: Literal["verified", "user_asserted", "unknown"]
    provenance: list[dict[str, Any]] = Field(default_factory=list)

class RegionSpec(BaseModel):
    kind: Literal["box", "sphere", "cylinder", "plane", "ellipsoid"]
    mode: Literal["inside", "outside", "above", "below"]
    parameters: dict[str, float]

class ComponentSpec(BaseModel):
    component_id: str
    template_id: str
    count: int = Field(gt=0)
    regions: list[RegionSpec]
    fixed: dict[str, float] | None = None
    center: bool = False
    atom_constraints: list[dict] = Field(default_factory=list)

class PackingRecipe(BaseModel):
    recipe_id: str
    mode: Literal["mixture", "solvation", "interface", "advanced"]
    tolerance_a: float = Field(gt=0)
    components: list[ComponentSpec]
    pbc_box_a: list[float] | None = None
    seed: int | None = None
    maxit: int = Field(default=20, gt=0)
    discale: float = Field(default=1.0, gt=0)
    target_density_kg_m3: float | None = Field(default=None, gt=0)
    provenance: list[dict] = Field(default_factory=list)
```

### 5.2 PackingResult 与 QC

```python
class PackingResult(BaseModel):
    run_id: str
    recipe_id: str
    output_path: str
    packmol_exit_code: int
    packmol_status: Literal["success", "partial_packing", "failed"]
    seed: int | None
    actual_component_counts: dict[str, int]
    box_a: list[float] | None
    stdout_path: str
    stderr_path: str

class PackingQC(BaseModel):
    passed: bool
    min_interatomic_distance_a: float
    overlap_pairs_count: int
    actual_density_kg_m3: float | None
    density_error_fraction: float | None
    total_charge_e: float | None
    pbc_checked: bool
    region_violations: list[dict]
    warnings: list[str]
```

---

## 6. 配方、分子数与盒尺寸

### 6.1 配方输入方式

系统支持且一次只选择一个主配方基准：

- 显式 `count`
- 溶剂 `mole_fraction` + 总分子数
- 溶剂 `mass_fraction` + 总质量/目标体积
- 目标密度 + 组成 + 总分子数
- 盐浓度 + 溶剂基准 + 盒/体积

若用户混用但未声明优先级，抛出 `RCP001_OVERCONSTRAINED_RECIPE`。

### 6.2 质量与体积计算

总质量：

\[
m = \sum_i \frac{N_i M_i}{N_A}
\]

目标体积：

\[
V = \frac{m}{\rho}
\]

正交盒边长（立方近似）：

\[
L = \sqrt[3]{V}
\]

实现时必须进行 SI 到 Å 的转换，并记录中间值。目标密度来自 OpenChemProperties 时，必须携带温度、压力、组成、盐效应与 evidence grade。

### 6.3 整数计数规划

```python
def allocate_counts(mole_fractions, total_molecules):
    raw = {k: v * total_molecules for k, v in mole_fractions.items()}
    floor = {k: int(x) for k, x in raw.items()}
    remainder = total_molecules - sum(floor.values())
    for k in sorted(raw, key=lambda x: raw[x] - floor[x], reverse=True)[:remainder]:
        floor[k] += 1
    return floor
```

输出应包含目标/实际摩尔分数、相对误差与分子数。小体系中，如果整数化误差超过阈值（默认 2%），报告 `RCP004_COMPOSITION_ROUNDING_HIGH`，建议扩大体系。

### 6.4 盐浓度与离子

当给定盐浓度 \(c\) 和盒体积 \(V\) 时：

\[
N_{salt} = \mathrm{round}(c V N_A)
\]

其中体积单位必须转换为 L。盐的“一个化学式单位”与实际离子模板数必须明确。例如 LiPF6 可作为一个整体模板或 Li+ 与 PF6- 两个模板；两种表示不可混用。

离子中和只做电荷账本：

\[
N_{counter} = \left|\frac{Q_{system}}{q_{counter}}\right|
\]

若不是整数或存在多价离子，系统必须拒绝自动中和并要求显式配方。电中性不代表正确离子浓度、活度或溶剂化结构。

---

## 7. 空间约束 DSL

### 7.1 Box

```yaml
region:
  kind: box
  mode: inside
  parameters: {x0: 0, y0: 0, z0: 0, x1: 40, y1: 40, z1: 40}
```

要求 `x1>x0`、`y1>y0`、`z1>z0`。若启用 PBC，盒与全局 PBC 必须一致或明确是局部子区域。

### 7.2 Sphere / Cylinder / Ellipsoid

```yaml
region:
  kind: cylinder
  mode: inside
  parameters: {x: 20, y: 20, z0: 0, z1: 40, radius: 10}
```

每种约束在编译前验证正半径、端点顺序、椭球轴长和局部/全局坐标系。V2 禁止隐式坐标单位。

### 7.3 Plane interface

```yaml
region:
  kind: plane
  mode: below
  parameters: {a: 0, b: 0, c: 1, d: 0}
```

若任一组件使用 `above/below plane`：

```yaml
packmol:
  discale: 1.5
  maxit: 50
```

否则 `CNS006_PLANAR_CONSTRAINT_TUNING_REQUIRED`。平面法向量不得为零；上下区域的重叠/空隙风险必须在 QC 报告显示。

### 7.4 固定与原子级约束

固定对象必须显式记录位置、欧拉角、坐标系和是否居中。原子级约束使用模板原子索引；索引必须在 `1..atoms_per_molecule` 内，输出应附原子索引到元素/名称的映射，避免模板更新后静默漂移。

---

## 8. Packmol 输入编译

### 8.1 生成示例

```text
tolerance 2.0
filetype pdb
output results/mixture.pdb
seed 42
pbc 0. 0. 0. 40. 40. 40.
maxit 20

structure inputs/EC.pdb
  number 300
  inside box 0. 0. 0. 40. 40. 40.
end structure

structure inputs/EMC.pdb
  number 700
  inside box 0. 0. 0. 40. 40. 40.
end structure
```

### 8.2 编译规则

- 所有引用路径在运行目录内相对化，防止不可重现的绝对路径。
- 输入保留渲染前 recipe、rendered `packmol.inp` 和 SHA-256。
- `seed` 未提供时由系统生成并立即写入 manifest；不得让随机性不可追溯。
- output 只能写入 `runs/<id>/results/`，禁止覆盖用户任意文件。
- 对大体系将 `maxit`、`nloop`、restart 策略写入配置，不能靠人工修改生成文件。

### 8.3 运行器

```python
result = subprocess.run(
    [packmol_binary],
    input=packmol_input_text,
    text=True,
    capture_output=True,
    cwd=workdir,
    timeout=timeout_s,
    check=False,
)
```

stdout、stderr、输入、输出、退出码、解析状态都必须保存。超时或非零退出不得删除部分输出，留给 QC/诊断。

---

## 9. 输出验证与质量控制

### 9.1 成功状态解释

| Packmol 状态 | 系统状态 | 后续动作 |
|---|---|---|
| 正常完成且输出存在 | `success` | 进入完整 QC |
| `ENDED WITHOUT PERFECT PACKING` 且输出存在 | `partial_packing` | 可进入受限 QC；强制能量最小化标签 |
| 非零退出/无输出 | `failed` | 不生成 handoff 包 |

`partial_packing` 不是成功等价物。只有当计数、结构与重叠 QC 合格，且用户接受最小化前置条件，才能标记为 `USABLE_AS_PREMINIMIZATION_INPUT`。

### 9.2 最小距离与重叠

使用 cell list / KDTree 做周期边界下最近邻检查。对每对原子：

```text
if distance_pbc < overlap_tolerance(pair): overlap
```

默认全局阈值 2.0 Å 仅适合作为粗筛，必须允许元素对/力场类型对覆盖；如 H–H 与重原子对应有不同合理阈值。报告输出最小距离、发生对、分子/原子标识、距离和坐标。

### 9.3 分子计数验证

依据模板原子数和 component 顺序解析输出，检查：

\[
N_{observed,i}=N_{requested,i}
\]

若输出 PDB 丢失 residue/chain 标签，采用连续原子块和模板 hash 交叉验证；无法可靠验证时 `QC003_COMPONENT_COUNT_UNCERTAIN`，禁止生成正式交接包。

### 9.4 密度验证

\[
\rho_{actual}=\frac{m_{total}}{V_{box}}
\]

输出目标密度、实际密度、温度（若目标有定义）、相对偏差、质量来源和是否包含盐。初始堆积密度与平衡 MD 密度不同，报告必须写 `INITIAL_GEOMETRIC_DENSITY_ONLY`。

### 9.5 区域、PBC 与电荷验证

- 每个组件的代表点/原子满足其 region constraint；固定对象单独核验。
- PBC 盒必须正、输出坐标必须可映射进盒。
- 净电荷只在所有模板有可验证 `net_charge_e` 时计算；否则 `QC006_TOTAL_CHARGE_UNKNOWN`。
- 对界面体系输出 z-density profile 与组分泄漏率，但不将初始分层误称为稳定界面。

---

## 10. 电解液构建工作流

### 10.1 配方示例

```yaml
recipe_id: RCP-EC-EMC-LIPF6-001
mode: mixture
state: {temperature_k: 298.15, pressure_pa: 101325}
solvents:
  basis: mole_fraction
  total_molecules: 1000
  components:
    - {template_id: EC, fraction: 0.3}
    - {template_id: EMC, fraction: 0.7}
salt:
  representation: dissociated_ions
  cation_template_id: Li_plus
  anion_template_id: PF6_minus
  concentration: {value: 1.0, unit: mol/L}
box:
  mode: target_density
  target_density_evidence_id: PRP-DENS-001
tolerance_a: 2.0
seed: 42
```

### 10.2 电解液专用门禁

- 目标密度必须明确盐浓度/无盐基准；否则 `ELP001_SALT_DENSITY_SCOPE_UNKNOWN`。
- Li+ 与阴离子模板的电荷必须可验证，计数必须电中性。
- 不能以 Packmol 初始结构中的邻近离子数量解释溶剂化数或离子缔合。
- 交接 OpenLAMMPSFlow 时需要额外 `topology_status`：`not_parameterized`、`partially_parameterized`、`parameterized_verified`。

---

## 11. 溶剂化与界面工作流

### 11.1 溶剂化

```bash
opack solvate --solute solute.pdb --solvent water.pdb --shell-a 15 \
  --solute-charge-e 4 --counterion chloride.pdb --workdir runs/solv_001
```

溶剂壳厚度为几何设计参数；默认建议 10–15 Å 仅作起点，并非任何体系的充分溶剂化保证。若用户提供溶质电荷和 counterion，系统生成电荷账本；若离子数非整数或模板电荷未知则拒绝。

### 11.2 液液界面

```bash
opack interface --lower water.pdb --upper hexane.pdb \
  --lower-count 1000 --upper-count 200 \
  --plane-z 0 --box-a "40,40,60" --workdir runs/interface_001
```

初始界面必须启用 `discale >= 1.5`、`maxit >= 50`。输出应包含每一侧区域定义、密度剖面、初始混入程度和后续 NPT/NVT 平衡建议。不能基于 Packmol 结构计算界面张力或宣称相分离稳定。

---

## 12. 与 OpenLAMMPSFlow 的交接

### 12.1 Handoff Manifest

```json
{
  "schema_version":"1.0",
  "handoff_id":"HND-0001",
  "source_run_id":"...",
  "coordinate_file":"results/mixture.pdb",
  "coordinate_sha256":"...",
  "box_a":[40,40,40],
  "pbc":[true,true,true],
  "components":[
    {"component_id":"EC","template_id":"...","count":300,"chemical_id":"...","net_charge_e":0},
    {"component_id":"Li_plus","template_id":"...","count":12,"net_charge_e":1}
  ],
  "total_charge_e":0,
  "topology_status":"not_parameterized",
  "packing_qc_path":"results/qc.json",
  "required_next_steps":["assign_forcefield","generate_topology","energy_minimization"],
  "limitations":["packmol_coordinates_only","initial_geometric_density_only"]
}
```

### 12.2 不允许的隐含承诺

交接包不得声称包含：LAMMPS atom types、partial charges、键角二面角、cross-interactions、合理初始能量、平衡密度或已验证离子电导率。下游必须读取 `required_next_steps`，并拒绝跳过能量最小化，除非有审计 override。

---

## 13. CLI 规范

```bash
opack init ./projects/electrolyte_box
opack doctor --strict
opack template inspect templates/EC.pdb
opack recipe validate configs/ec_emc_lipf6.yaml
opack recipe plan configs/ec_emc_lipf6.yaml --show-counts --show-box
opack build --config configs/ec_emc_lipf6.yaml --workdir runs/pack_001
opack validate --workdir runs/pack_001 --checks all
opack solvate --solute protein.pdb --solvent water.pdb --shell-a 15
opack interface --config configs/water_hexane.yaml
opack export --workdir runs/pack_001 --target openlammpsflow
opack status runs/pack_001
```

退出码：0 成功；1 批任务部分成功；2 CLI/配置错误；3 模板/配方/约束无效；4 Packmol/依赖不可用；5 Packmol 运行失败；6 QC/科学一致性失败；7 交接/集成失败。

---

## 14. 工件、Manifest、缓存与 Outbox

```text
runs/<run_id>/
├── inputs/
│   ├── recipe.original.yaml
│   ├── recipe.resolved.yaml
│   ├── component_templates/
│   ├── property_evidence_snapshot.json
│   └── count_density_plan.json
├── compiled/
│   ├── packmol.inp
│   └── constraint_map.json
├── work/
│   ├── packmol.stdout.log
│   ├── packmol.stderr.log
│   └── restart/
├── results/
│   ├── mixture.pdb
│   ├── mixture.xyz
│   ├── component_counts.json
│   ├── qc.json
│   ├── overlap_pairs.csv
│   ├── density.json
│   ├── region_report.json
│   └── lammps_handoff.json
├── outbox/events.jsonl
├── manifest.json
└── report.md
```

缓存键：模板 geometry hash、recipe canonical JSON、计数/盒规划、约束、Packmol 版本、seed、validation config。若不固定 seed，不得启用结果缓存。

事件：

```text
packing.planned
packing.started
packing.completed
packing.partial_packing
packing.qc_failed
packing.handoff_created
```

---

## 15. 错误码

| 错误码 | 含义 |
|---|---|
| `TPL001` | 模板不可解析/空/坐标非有限 |
| `TPL002` | 原子数、质量或电荷不完整 |
| `RCP001` | 配方过约束/主基准冲突 |
| `RCP002` | 摩尔/质量分数错误 |
| `RCP004` | 小体系组成整数化误差过大 |
| `RCP005` | 目标密度或状态条件缺失 |
| `ION001` | 电荷不守恒或离子计数非整数 |
| `CNS001` | 约束几何非法 |
| `CNS006` | 平面约束缺 `discale/maxit` |
| `RUN001` | Packmol 非零退出/超时 |
| `QC001` | 原子重叠超阈值 |
| `QC003` | 组分计数不可可靠确认 |
| `QC005` | 区域约束违反 |
| `QC006` | 总电荷未知 |
| `HND001` | 下游交接缺少必需 manifest 字段 |

---

## 16. 测试矩阵

### 16.1 单元测试

| 模块 | 场景 | 断言 |
|---|---|---|
| template parser | 有效/空/NaN PDB | 正确读取或 `TPL001` |
| count allocator | 0.3/0.7，1000 分子 | 300/700 |
| rounding | 小总分子数 | `RCP004` |
| density planner | 已知质量/密度 | 盒尺寸单位正确 |
| ion balance | 单价/二价/非整数 | 正确或 `ION001` |
| constraint compiler | 零法向量平面 | `CNS001` |
| interface guard | plane 未设 discale | `CNS006` |
| overlap checker | PBC 边界近邻 | 检测到 overlap |
| counts | PDB residue 丢失 | 不确定状态而非误通过 |
| cache | seed 改变 | 缓存失效 |

### 16.2 集成测试

1. 水/乙醇基本混合物：配方 -> 输入 -> Packmol -> 计数、密度、重叠 QC。
2. EC/EMC 电解液：摩尔分数、目标密度、Li+/PF6- 电荷账本、handoff manifest。
3. 蛋白/小分子溶剂化：固定溶质、溶剂壳、离子中和、区域 QC。
4. 水/正己烷界面：上/下平面、discale/maxit、density profile。
5. `ENDED WITHOUT PERFECT PACKING` fixture：仅在 QC 合格时产生预最小化标签，绝不标为普通成功。
6. 输出重叠 fixture：handoff 被阻断。
7. 交接 OpenLAMMPSFlow：必须包含 `topology_status` 与 required next steps。

### 16.3 性能目标

| 任务 | 规模 | 目标 |
|---|---:|---|
| 配方规划与输入编译 | <= 10 组分 | < 5 秒 |
| 基础 Packmol 混合物 | <= 5k 原子 | < 5 分钟，依硬件记录 |
| overlap QC | <= 20k 原子 | < 2 分钟 |
| 100 个 recipe 批规划 | 无 Packmol 执行 | < 2 分钟 |

---

## 17. 实施里程碑

### M0：工程骨架（2 天）

CLI、schema、run layout、模板解析、manifest、错误模型、doctor、fixtures。

### M1：配方与密度规划（4 天）

Composition、count allocation、质量/盒体积、盐浓度、电荷账本、OpenChemProperties evidence adapter。

### M2：约束与 Packmol 编译（4 天）

五类区域 DSL、固定/原子约束、input compiler、runner、日志和超时。

### M3：QC 与交接（5 天）

PBC overlap、计数、密度、区域/电荷 QC、partial packing 状态机、LAMMPS handoff。

### M4：高级模板与集成（4 天）

溶剂化、界面、增量 build、sample link、outbox、端到端电解液示例。

---

## 18. Definition of Done

- 所有输出均能回溯模板、配方、密度证据、盒/计数算法、seed、Packmol 版本和约束。
- 分子数、最小距离、密度、区域、PBC 和已知电荷均经 QC；不确定项明确标记。
- `ENDED WITHOUT PERFECT PACKING` 绝不被静默当作标准成功。
- 高盐电解液的密度/离子计数模型限制被明确表达。
- 向 OpenLAMMPSFlow 的交接包不会伪称已经参数化或平衡，且强制列出后续最小化/力场步骤。
- 全部 unit、integration、regression、性能测试通过。

---

## 19. 许可、安全与科学责任

Packmol、模板分子结构、化学身份数据、物性证据与下游力场均要记录许可证和来源。初始构型构建不替代危险化学品兼容性判断、实验安全、离子盐水敏性控制或材料设备评审。对于实际电解液与电池体系，任何配方和浓度建议都需通过受控实验、样品批次记录及安全评审确认。
