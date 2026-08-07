# OpenMultiwfnFlow 实施级开发规格说明书

**版本**：V2.0（深度重写）  
**项目代号**：`openmultiwfnflow`  
**CLI**：`omwfn`  
**核心引擎**：Multiwfn；可选本地 VMD 渲染  
**定位**：BatteryEMCL Lab 的波函数分析、ESP/轨道/实空间性质提取、Cube 工件治理、可复现可视化与计算证据交接层

---

## 0. 文档定位

OpenMultiwfnFlow 以 Multiwfn 为分析引擎，将波函数文件、分析菜单脚本、解析器、网格数据、渲染配置和派生指标组织为可追溯的计算工件。系统的核心原则是：图像是分析的呈现，而不是证据本身；任何结论都必须绑定计算方法、波函数文件、分析定义、阈值和数值输出。

V2 支持 ESP 表面分析、HOMO/LUMO 与前线轨道摘要、密度/ESP/轨道 Cube 生成、局域原子表面统计、批处理和本地 VMD 渲染包。它不执行量子化学电子结构计算，不替代 Gaussian/ORCA/Q-Chem，也不应将单点轨道能级直接等同于可观测氧化还原电位、反应活性或电池稳定性。

---

## 1. 目标与边界

### 1.1 V2 必须交付

- `.fchk`、`.molden`、`.wfn`、`.wfx` 等波函数/轨道文件登记、格式检查、hash、来源和方法元数据
- ESP 表面统计、ESP 区间面积分布、局域原子表面统计、可选 density/ESP Cube
- HOMO/LUMO、相邻轨道摘要、占据数、轨道能量、轨道 Cube 与数值索引
- Multiwfn 菜单脚本的受控管道执行、超时、日志、版本记录与输出解析
- Cube 网格预算、大小预估、压缩/索引、保留策略、强制禁止无界批量生成
- 本地 VMD 渲染任务包、参数锁定、渲染日志和 PNG/TIFF/SVG 输出登记
- 批处理任务隔离、部分成功、汇总表与失败原因
- 面向 ReactNet、OpenChemProperties、OpenLAMMPSFlow、ELN/LIMS 的计算证据包
- 明确的解释边界、引用记录与人类审查状态

### 1.2 非目标

- 不执行 DFT、HF、MP2、CC 或分子动力学本身
- 不自动“证明”亲核/亲电性、氧化稳定性、反应速率、键解离或电池性能
- 不将负的 LUMO、HOMO–LUMO gap 或 ESP 极值直接映射为实验电位
- 不允许任意用户菜单命令在非隔离环境中不加审查执行
- 不依赖远程专有渲染服务；远程渲染仅可作为用户显式配置的可选后端

---

## 2. 总体架构

```text
量子化学任务 / 用户上传文件 / ReactNet
                    │
                    ▼
    Wavefunction Manifest + Method Provenance Validator
                    │
                    ▼
  Analysis Request -> Multiwfn Script Compiler -> PIPE Runner
                    │                                  │
                    ▼                                  ▼
           Parser / Normalizer                    logs / command trace
                    │
      ┌─────────────┼──────────────┐
      ▼             ▼              ▼
  scalar tables   Cube registry   Render package
      │             │              │
      └─────────────┴──────────────┴──► QC / evidence / outbox / report
```

---

## 3. 目录与文件职责

```text
openmultiwfnflow/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── default.yaml
│   ├── esp.yaml
│   ├── orbitals.yaml
│   ├── cube.yaml
│   ├── render.yaml
│   ├── batch.yaml
│   └── retention.yaml
├── assets/
│   └── vmd/
│       ├── esp_render.tcl.j2
│       ├── orbital_render.tcl.j2
│       └── common_style.tcl
├── schemas/
│   ├── wavefunction_manifest.v1.json
│   ├── analysis_request.v1.json
│   ├── multiwfn_command.v1.json
│   ├── cube_manifest.v1.json
│   ├── scalar_result.v1.json
│   ├── render_manifest.v1.json
│   ├── evidence_package.v1.json
│   └── task_event.v1.json
├── src/openmultiwfnflow/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── inspect_cmd.py
│   │   ├── esp_cmd.py
│   │   ├── orbital_cmd.py
│   │   ├── cube_cmd.py
│   │   ├── render_cmd.py
│   │   ├── batch_cmd.py
│   │   ├── custom_cmd.py
│   │   ├── export_cmd.py
│   │   └── status_cmd.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── identifiers.py
│   │   └── paths.py
│   ├── wavefunction/
│   │   ├── detector.py
│   │   ├── metadata.py
│   │   ├── validator.py
│   │   ├── geometry.py
│   │   └── provenance.py
│   ├── multiwfn/
│   │   ├── executable.py
│   │   ├── command_model.py
│   │   ├── script_compiler.py
│   │   ├── pipe_runner.py
│   │   ├── output_parser.py
│   │   └── version_guard.py
│   ├── analysis/
│   │   ├── esp.py
│   │   ├── orbital.py
│   │   ├── atom_surface.py
│   │   ├── cube.py
│   │   ├── scalar_qc.py
│   │   └── interpretation.py
│   ├── cube_store/
│   │   ├── grid_budget.py
│   │   ├── inspector.py
│   │   ├── compress.py
│   │   ├── registry.py
│   │   └── retention.py
│   ├── render/
│   │   ├── vmd.py
│   │   ├── tcl_compiler.py
│   │   ├── local_runner.py
│   │   ├── image_qc.py
│   │   └── package.py
│   ├── batch/
│   │   ├── planner.py
│   │   ├── runner.py
│   │   ├── summary.py
│   │   └── retry.py
│   ├── validation/
│   │   ├── request.py
│   │   ├── menu_policy.py
│   │   ├── outputs.py
│   │   └── scientific_scope.py
│   ├── integration/
│   │   ├── reactnet.py
│   │   ├── chemproperties.py
│   │   ├── lammps.py
│   │   ├── sample_link.py
│   │   └── outbox.py
│   ├── store/
│   │   ├── artifacts.py
│   │   ├── manifests.py
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
    ├── esp_molden/
    ├── orbitals_fchk/
    ├── cube_budget/
    ├── batch_library/
    └── local_vmd_render/
```

---

## 4. 环境与诊断

```yaml
name: openmultiwfnflow
channels: [conda-forge]
dependencies:
  - python=3.11
  - numpy
  - pandas
  - scipy
  - pydantic>=2
  - typer
  - rich
  - pyyaml
  - pillow
  - pytest
  - pip
  - pip:
      - structlog
      - orjson
```

Multiwfn 和 VMD 不是强制由 conda 提供的依赖。`omwfn doctor --strict` 必须检测 `MULTIWFN_BIN` 或 PATH 中的 Multiwfn、版本字符串、可写工作目录、可用磁盘、可选 VMD 可执行文件和模板完整性。不得假设 Gaussian 16 或任何量子化学程序已经存在；该系统只消费已生成的文件。

---

## 5. 波函数文件治理

### 5.1 Wavefunction Manifest

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any

class WavefunctionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    wavefunction_id: str
    path: str
    sha256: str
    format: Literal["fchk", "molden", "wfn", "wfx", "other"]
    file_size_bytes: int = Field(gt=0)
    n_atoms: int | None = Field(default=None, gt=0)
    total_charge: int | None = None
    multiplicity: int | None = Field(default=None, gt=0)
    method: str | None = None
    basis_set: str | None = None
    software: str | None = None
    software_version: str | None = None
    geometry_source_id: str | None = None
    calculation_type: Literal["single_point", "optimization", "frequency", "unknown"]
    provenance_status: Literal["complete", "partial", "unknown"]
    source_task_id: str | None = None
    citations: list[str] = Field(default_factory=list)
```

### 5.2 最低准入

- 文件格式可识别、非空、hash 可计算。
- 可解析的元素/原子数与预期几何（如有）一致。
- 需要轨道分析时必须包含 MO 信息；需要 ESP 时必须具有可用电子密度/波函数信息。
- 若方法、基组、charge/multiplicity 未知，可运行部分描述性分析，但所有证据等级降级并带 `PRV001_METHOD_METADATA_INCOMPLETE`。
- 输入文件复制或只读链接到 run 目录，原始文件不可被 Multiwfn 改写。

### 5.3 文件格式限制

Molden 文件的 MO、基函数和坐标表示可能因上游软件而异。解析器必须保留 Multiwfn 导入日志；若存在明显解析告警或 orbitals 数量异常，标记 `WVF004_IMPORT_SUSPECT`，禁止生成高置信轨道结论。

---

## 6. 分析请求模型

```yaml
analysis_id: ANL-ESP-001
wavefunction_id: WVF-001
kind: esp_surface
surface:
  type: electron_density_isosurface
  isovalue_au: 0.001
metrics:
  - global_esp_statistics
  - esp_area_distribution
  - atom_local_surface_statistics
cube:
  enabled: true
  fields: [density, electrostatic_potential]
  grid:
    spacing_a: 0.15
    padding_a: 5.0
  storage_policy: compressed
interpretation_policy:
  allow_qualitative_labels: true
  prohibit_property_prediction: true
```

任何数值比较必须保证同一表面定义、等值面值、网格策略、单位、电子结构方法和构型选择；不同条件下的 ESP 极值不可脱离这些元数据直接排名。

---

## 7. Multiwfn 管道执行

### 7.1 运行器

沙箱/无 PTY 环境必须使用标准输入管道：

```python
proc = subprocess.Popen(
    [multiwfn_bin, input_file],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    cwd=workdir,
)
stdout, _ = proc.communicate(input=menu_script, timeout=timeout_s)
```

不得依赖 `pexpect.spawn` 或模拟终端交互。运行器保存：二进制路径、版本、菜单脚本文本/哈希、开始/结束时间、退出码、完整 stdout、超时状态和输出文件清单。

### 7.2 命令模型与白名单

内置分析不直接暴露“任意菜单序列”，而通过结构化动作编译：

```yaml
steps:
  - {action: surface_analysis, surface: density_0.001}
  - {action: esp_area_bins, min: -0.08, max: 0.08, bins: 80}
  - {action: atom_local_surface_statistics}
  - {action: export_cube, field: density, spacing_a: 0.15}
```

自定义模式必须启用 `--custom-script`、`--acknowledge-unsafe-menu-script` 并在隔离工作目录运行。禁止脚本含 shell escape、相对路径跳出 run 目录或删除命令；`menu_policy.py` 做静态拒绝。

### 7.3 版本兼容

Multiwfn 菜单路径可能随版本变化。每个内置 recipe 绑定一个或多个经过测试的版本区间；`doctor` 与运行前 probe 不能识别时抛出 `MWF003_UNSUPPORTED_MULTIWFN_VERSION`，禁止静默执行错误菜单序列。

---

## 8. ESP 分析工作流

### 8.1 阶段与输出

| 阶段 | 目的 | 结构化输出 |
|---|---|---|
| 表面统计 | 指定密度等值面上的 ESP 最小/最大/平均等 | `esp_surface_summary.json` |
| 面积分布 | 各 ESP 区间的表面积/分数 | `esp_area_bins.csv` |
| 原子局部统计 | 每原子分区的表面统计 | `atom_surface_stats.csv` |
| 可选 Cube | density 与 ESP 三维场 | `cube_manifest.json` |

### 8.2 表面定义

默认电子密度等值面为 0.001 au，但该值必须作为请求参数写入结果。表面变化会改变 ESP 极值和面积分布；因此“ESP 更正/更负”的结论只能在同一 surface definition 下表达。

### 8.3 结果模式

```json
{
  "analysis_id":"ANL-ESP-001",
  "surface":{"kind":"electron_density_isosurface","isovalue_au":0.001},
  "esp":{"min_au":-0.042,"max_au":0.061,"mean_au":0.003},
  "units":{"esp":"a.u.","area":"bohr2"},
  "wavefunction_id":"WVF-001",
  "method_context":{"method":"...","basis_set":"..."},
  "status":"COMPLETED_WITH_PROVENANCE_WARNING"
}
```

### 8.4 解释边界

ESP 描述的是指定理论与等值面下的静电势分布，可支持对电荷分布/潜在相互作用位点的定性讨论。它不单独给出溶液相反应性、Li+ 配位强度、电解液氧化稳定性或实际界面电势；相关结论需配合溶剂模型、构象采样、能量计算或实验验证。

---

## 9. 轨道分析工作流

### 9.1 轨道请求

```yaml
analysis_id: ANL-ORB-001
kind: frontier_orbitals
wavefunction_id: WVF-001
selection:
  below_homo: 3
  above_lumo: 3
cube:
  enabled: true
  grid: {spacing_a: 0.18, padding_a: 4.0}
  isovalues: [-0.03, 0.03]
```

### 9.2 输出

```csv
orbital_index,occupation,energy_hartree,energy_ev,label,cube_id,status
...
```

HOMO、LUMO 标识必须由 occupation/电子数和波函数类型判定，不能只按“文件中的最后两个轨道”猜测。开壳层体系需要输出 alpha/beta 前线轨道；若未支持该文件语义，抛出 `ORB004_OPEN_SHELL_ASSIGNMENT_UNRESOLVED`。

### 9.3 能隙

\[
\Delta E_{HL}=E_{LUMO}-E_{HOMO}
\]

仅在同一单点计算、明确轨道定义下报告。该数是计算轨道能隙而非光学带隙、反应活化能或稳定性评分；报告必须包含方法、基组、构型和单位。

### 9.4 Cube 等值面

轨道正/负相位必须使用对称等值面和明确色标。渲染图需要显示等值面值而非仅显示“HOMO/LUMO”，防止跨图不可比。

---

## 10. Cube 数据治理

### 10.1 网格预算

Cube 的点数近似：

\[
N_{grid}=N_xN_yN_z
\]

体积约为：

\[
S \approx N_{grid}\times b
\]

其中 \(b\) 为每网格点的文本/二进制存储预算。实际 Cube 文本开销较大，系统必须以保守上界估算，不可只按 8 bytes 浮点数估算。

### 10.2 默认门禁

```yaml
cube_budget:
  max_grid_points: 20000000
  max_estimated_bytes: 2000000000
  max_cubes_per_analysis: 10
  max_batch_total_bytes: 20000000000
  action_on_exceed: reject_with_resolution_options
```

超过预算时，系统给出减小 padding、加粗 spacing、减少轨道数、分批生成、只保留数值摘要等选项。禁止在批处理时默默生成 TB 级 Cube。

### 10.3 Cube Manifest

```yaml
cube_id: CUBE-001
field: electrostatic_potential
wavefunction_id: WVF-001
analysis_id: ANL-ESP-001
grid:
  origin_a: [-5.0, -5.0, -5.0]
  dimensions: [180, 180, 180]
  spacing_a: [0.15, 0.15, 0.15]
units: au
file:
  path: results/cubes/totesp.cub.gz
  sha256: "..."
  compression: gzip
  bytes: 12345678
retention: keep
```

### 10.4 保留策略

- `keep`：关键论文/交接工件，保留原始 Cube 与 hash。
- `compress`：gzip/zstd 后存档；渲染使用解压副本。
- `summary_only`：保留数值统计、渲染图与 manifest，删除可再生 Cube（必须保留可重跑菜单脚本）。
- `ephemeral`：用于试运行，任务完成后受控清理。

任何删除都需在 manifest 中留下 `derived_from` 和再生成配置。

---

## 11. 本地 VMD 渲染

### 11.1 原则

VMD 是可选的本地后端。渲染任务只读取生成的 PDB/XYZ 与 Cube，不允许 Tcl 模板访问 run 目录以外路径、网络或 shell。图像可用于说明空间分布，但数值结论必须来自结构化结果文件。

### 11.2 Render Manifest

```yaml
render_id: RND-ESP-001
backend: local_vmd
inputs:
  geometry: results/geometry.pdb
  cubes: [results/cubes/density.cub.gz, results/cubes/esp.cub.gz]
style:
  molecule_representation: CPK
  density_isovalue: 0.001
  color_field: esp
  color_range_au: [-0.05, 0.05]
  resolution_px: [2400, 1800]
  renderer: tachyon_internal
output_format: png
camera: {projection: orthographic, orientation: [0, 0, 0]}
```

不同分子的比较渲染必须固定色标、密度等值面、构象取向和分辨率，或在报告中明确不具有视觉可比性。

### 11.3 图像 QC

- 文件存在、分辨率与 manifest 一致、非零大小。
- 可检测全透明/全黑/全白等明显渲染失败。
- 记录 VMD 版本、Tcl hash、renderer 和输入 cube hash。
- 图像默认标记 `illustrative_visualization`，不得作为孤立证据导出。

---

## 12. 批处理与恢复

### 12.1 批任务输入

```csv
job_id,wavefunction_path,analysis_kind,config_path,material_id,sample_id
JOB-001,inputs/mol1.fchk,esp_surface,configs/esp.yaml,MAT-001,
JOB-002,inputs/mol2.molden,frontier_orbitals,configs/orbitals.yaml,MAT-002,SMP-002
```

### 12.2 隔离与状态机

```text
PLANNED -> VALIDATED -> QUEUED -> RUNNING -> PARSING -> QC -> COMPLETED
                                    │                    │
                                    ▼                    └-> COMPLETED_WITH_WARNINGS
                                  FAILED
```

每个 job 独立工作目录和超时；单项失败不得终止其他独立任务。批处理汇总必须列出成功、警告、失败、文件大小、Cube 占用、结果路径和错误码。

### 12.3 缓存

缓存键包括波函数 hash、Multiwfn 版本、分析 recipe、表面/网格参数、菜单脚本 hash 和解析器版本。只改变渲染参数时可复用 Cube/数值分析，但不可复用图像。

---

## 13. 计算证据与下游交接

### 13.1 Evidence Package

```yaml
evidence_id: EVD-WFN-001
kind: esp_surface_statistics
value:
  esp_min_au: -0.042
  esp_max_au: 0.061
context:
  wavefunction_id: WVF-001
  method: "B3LYP-D3/def2-SVP"
  phase_model: gas_phase
  geometry_id: GEO-001
  density_isovalue_au: 0.001
quality:
  parser_status: passed
  provenance_status: complete
  evidence_grade: computational_provisional
limitations:
  - single_conformation
  - gas_phase
  - no_explicit_solvent
interpretation_allowed:
  - qualitative_electrostatic_comparison_with_matched_protocol
interpretation_prohibited:
  - direct_redox_potential_prediction
  - electrolyte_stability_claim
artifacts: [esp_surface_summary.json, esp_area_bins.csv]
```

### 13.2 下游规则

- ReactNet 可读取前线轨道/ESP 作为候选筛选特征，但不可自动剪枝化学机制。
- OpenChemProperties 不能用 ESP 替代实验物性。
- OpenLAMMPSFlow 不直接从 ESP 获得力场电荷；量化电荷拟合需独立、明确的参数化流程。
- BatteryEMCL 的材料决策只能读取为 `computational_provisional` 证据，需与实验/更高层理论共同审核。

---

## 14. CLI 规范

```bash
omwfn init ./projects/wfn_analysis
omwfn doctor --strict
omwfn inspect inputs/molecule.fchk --metadata configs/calculation_metadata.yaml
omwfn esp run inputs/molecule.molden --config configs/esp.yaml --workdir runs/esp_001
omwfn orbital run inputs/molecule.fchk --below-homo 3 --above-lumo 3 --workdir runs/orb_001
omwfn cube inspect runs/esp_001/results/cubes/totesp.cub.gz
omwfn render esp --workdir runs/esp_001 --backend local-vmd --config configs/render.yaml
omwfn batch run jobs.csv --workers 2 --continue-on-error
omwfn custom run inputs/molecule.wfx --script commands/user_recipe.mf --acknowledge-unsafe-menu-script
omwfn export --workdir runs/esp_001 --target reactnet
omwfn status runs/esp_001
```

退出码：0 成功；1 批处理部分成功；2 CLI/配置错误；3 波函数/身份/元数据无效；4 Multiwfn/VMD 依赖缺失；5 引擎执行失败；6 QC、网格预算或科学适用性拒绝；7 下游交接失败。

---

## 15. 工件、Manifest 与 Outbox

```text
runs/<run_id>/
├── inputs/
│   ├── wavefunction.manifest.json
│   ├── source_wavefunction/  # copy or read-only link
│   ├── analysis_request.yaml
│   └── metadata.yaml
├── commands/
│   ├── recipe.resolved.yaml
│   ├── multiwfn.menu.txt
│   └── render.tcl
├── work/
│   ├── multiwfn.stdout.log
│   ├── multiwfn.stderr.log
│   └── temporary/
├── results/
│   ├── scalar/
│   │   ├── esp_surface_summary.json
│   │   ├── esp_area_bins.csv
│   │   ├── atom_surface_stats.csv
│   │   └── orbitals.csv
│   ├── cubes/
│   │   ├── cube_manifest.jsonl
│   │   └── *.cub.gz
│   ├── renders/
│   │   ├── render_manifest.yaml
│   │   └── *.png
│   ├── qc.json
│   └── evidence_package.yaml
├── outbox/events.jsonl
├── manifest.json
└── report.md
```

事件类型：

```text
wavefunction.registered
multiwfn.analysis_started
multiwfn.analysis_completed
multiwfn.analysis_failed
multiwfn.cube_budget_exceeded
multiwfn.render_completed
multiwfn.batch_partial_success
multiwfn.evidence_created
```

---

## 16. 错误码

| 错误码 | 含义 |
|---|---|
| `WVF001` | 波函数文件不存在/为空/格式不支持 |
| `WVF002` | 原子数、元素或几何不一致 |
| `WVF003` | 缺 MO 或必要波函数数据 |
| `WVF004` | 导入可疑/解析告警严重 |
| `PRV001` | 方法/基组/电荷等元数据不完整 |
| `MWF001` | Multiwfn 二进制缺失/不可执行 |
| `MWF003` | Multiwfn 版本不受支持 |
| `MWF004` | 菜单脚本超时或非零退出 |
| `MWF005` | 输出模式未解析/结果不完整 |
| `CUB001` | 网格/大小超预算 |
| `CUB002` | Cube 几何或 hash 不一致 |
| `ORB004` | 开壳层前线轨道无法解析 |
| `RND001` | VMD 缺失/模板失败/图像无效 |
| `BCH001` | 批任务配置或隔离失败 |
| `SCI001` | 请求超出科学解释政策 |
| `HND001` | 证据包/下游契约不完整 |

---

## 17. 测试矩阵

### 17.1 单元测试

| 模块 | 场景 | 断言 |
|---|---|---|
| 文件检测 | fchk/molden/wfx/空文件 | 正确识别或 `WVF001` |
| provenance | 方法缺失 | `PRV001` 与等级降级 |
| command compiler | ESP recipe | 稳定菜单脚本 hash |
| policy | 包含 shell escape 的 custom script | 拒绝 |
| version guard | 不匹配版本 | `MWF003` |
| parser | ESP 正常/缺字段日志 | 结构化结果或 `MWF005` |
| orbital assignment | closed/open shell fixture | 正确/`ORB004` |
| cube budget | 过大网格 | `CUB001` |
| cube manifest | gzip/hash | 可验证 |
| render QC | 空白 PNG | `RND001` |
| cache | grid spacing 改变 | 缓存失效 |

### 17.2 集成测试

1. Molden ESP：注册 -> 四阶段 ESP -> 表面统计、area bins、原子统计、可选 Cube。
2. FCHK 轨道：HOMO-3 至 LUMO+3 -> `orbitals.csv` -> 对称等值面 Cube manifest。
3. 网格预算：请求大 padding/细 spacing，必须在 Multiwfn 前被阻断。
4. 本地 VMD：输入 Cube -> 渲染 -> 图像与 render manifest QC。
5. 批任务：两个有效文件、一个坏文件；有效任务完成，汇总中报告部分失败。
6. 自定义菜单：安全脚本成功；越界路径或 shell-like 指令被拒绝。
7. evidence export：ReactNet 接收 provisional evidence，且包含禁止解释项。

### 17.3 性能目标

| 任务 | 规模 | 目标 |
|---|---:|---|
| 文件登记与预检 | <= 100 MB | < 30 秒 |
| ESP 数值分析 | 小分子、无 Cube | < 10 分钟，依硬件记录 |
| 单轨道 Cube | <= 5M grid points | < 15 分钟 |
| 20 个小分子批 ESP | 2 workers、无 Cube | < 3 小时，部分成功可恢复 |
| 本地渲染 | 1 geometry + 2 cubes | < 10 分钟 |

---

## 18. 实施里程碑

### M0：基础设施（2 天）

CLI、schema、artifact/manifest、doctor、错误模型、波函数 fixtures。

### M1：文件治理与 Multiwfn runner（4 天）

格式探测、metadata/provenance、version guard、PIPE runner、内置菜单 recipe 与日志解析骨架。

### M2：ESP 与轨道分析（5 天）

ESP 四阶段、轨道摘要、closed/open-shell 检查、结构化解析、scalar QC。

### M3：Cube 治理与渲染（4 天）

网格预算、manifest、压缩/保留、本地 VMD 包、图像 QC。

### M4：批处理与交接（4 天）

job 隔离、部分成功、汇总、ReactNet/ChemProperties/LAMMPS contracts、outbox。

### M5：回归与科学治理（3 天）

版本锁定、结果基线、引用/解释限制、端到端示例与文档。

---

## 19. Definition of Done

- 每个分析结果均可追溯波函数 hash、格式、方法/基组/charge/multiplicity、Multiwfn 版本、菜单脚本和解析器版本。
- ESP、轨道和 Cube 的表面/网格/等值面参数完整保存，跨任务比较可审计。
- 超预算 Cube、可疑输入和不兼容 Multiwfn 版本均在计算前阻断。
- 批任务隔离且支持部分成功；所有输出有明确 run 状态和错误码。
- 图像永远与数值工件、渲染参数和输入 hash 绑定，且不作为独立科学证据。
- 下游只能获得带条件和解释限制的 provisional computational evidence。
- 全部单元、集成、回归及性能测试通过。

---

## 20. 引用、许可与科学责任

使用 Multiwfn 生成或发表的结果必须依据其官方引用要求记录并在报告中提供相应引用；V2 的元数据模板应包含 Multiwfn 及原始量子化学软件的版本和引用。波函数、Cube、图像、模型输入及用户实验关联数据都必须遵守所属许可与访问权限。OpenMultiwfnFlow 的结果适用于透明、可复现的电子结构后处理；针对电池稳定性、材料选择和化学反应的最终判断必须结合更充分的理论、采样和实验验证。
