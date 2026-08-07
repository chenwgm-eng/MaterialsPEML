# OpenLAMMPSFlow 本地 CLI 开发说明书

**版本**：V0.1  
**命令行入口**：`olmp`  
**部署原则**：本地优先、显式依赖、可重跑、可审计

---

## 1. 目标与边界

构建从结构/拓扑准备到 LAMMPS 输入生成、静态与物理验证、分阶段运行、轨迹分析的本地分子动力学工作流。它重点服务无机电池材料、电解液和聚合物体系，但不替用户自动选择未经验证的力场。

只实现独立的本地工作流封装与公开工具集成，不复制附件涉及的私有服务、远程 GPU Runner、预装路径、二进制、模型权重或授权凭证。

---

## 2. V0.1 能力

- 无机晶体、金属、氧化物、共价材料的 pymatgen 数据路径
- 有机/聚合物的 mbuild/foyer 或用户导入拓扑路径
- LAMMPS data/input 生成，minimize、NVT、NPT、NVE 阶段模板
- 力场、units、atom_style、pair_style、kspace 和 DOF 静态规则检查
- `lmp` 本地/OMP/MPI 任务执行、断点和性能日志
- RDF、MSD、扩散系数、RMSD/RMSF、CNA 等轨迹后处理

每个任务目录必须保存原始输入、解析后配置、命令行、环境清单、stdout/stderr、结果索引和 SHA-256 哈希。

---

## 3. 模块结构

```text
openlammpsflow/
├── pyproject.toml
├── environment.yml
├── configs/
├── templates/
├── examples/
├── src/openlammpsflow/
│   ├── cli/
│   ├── core/
│   ├── adapters/
│   ├── workflows/
│   ├── validation/
│   ├── analysis/
│   ├── render/
│   └── io/
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

```text
runs/<run_id>/
├── inputs/       # 用户输入、resolved_config、manifest
├── work/         # 引擎中间文件
├── logs/         # commands、stdout、stderr、events
├── results/      # 面向用户的表格、图像、结构/轨迹
└── report.md
```

---

## 4. CLI

```bash
olmp init ./projects/lifsi_electrolyte
olmp prepare inorganic --structure LiFePO4.cif --atom-style charge
olmp prepare organic --topology system.data --forcefield-manifest forcefield.json
olmp generate --protocol configs/npt_production.yaml --data system.data
olmp validate --input in.production --data system.data --strict
olmp run --input in.production --backend omp --threads 4
olmp analyze msd --trajectory dump.lammpstrj --data system.data --species Li
```

---

## 5. 配置

```yaml
system: {kind: inorganic, units: metal, atom_style: charge}
forcefield: {family: buckingham_coulomb, files: [potentials.json], sha256: required}
protocol:
  stages:
    - {name: minimize, style: minimize}
    - {name: npt_equil, ensemble: npt, temperature_k: 300, pressure_bar: 1}
    - {name: production, ensemble: nvt, steps: 1000000}
runtime: {backend: omp, threads: 4, timeout_s: 0}
analysis: {rdf: true, msd: true, unwrap_pbc: true}
```

配置使用 Pydantic 校验；任何未知字段默认报错。恢复执行时必须验证核心输入、配置、引擎版本和势函数/模型文件哈希。

---

## 6. 数据契约

`SystemManifest`：结构来源、原子类型、拓扑、单位、总电荷、盒和原子数。  
`ForceFieldManifest`：势函数、参数文件、元素/类型映射、适用体系、许可证、哈希。  
`RunRecord`：阶段、输入脚本、引擎版本、步数、温压能量轨迹、退出码。  
`TrajectoryMetric`：时间、指标、单位、拟合区间、扩散系数及拟合质量。

---

## 7. 关键工作流

1. 按无机、分子/聚合物或已有生物拓扑选择数据路径，禁止用同一自动规则跨体系参数化。  
2. 读取 data 文件，检查元素、原子类型、键拓扑、总电荷、盒和质量。  
3. 生成阶段化输入：最小化 -> 平衡 -> 生产；每个 `run` 前必须存在匹配的积分 `fix`。  
4. 在执行前运行语法、单位、力场、截断、长程静电、时间步和自由度验证。  
5. 短任务可本地 OMP；长任务以可恢复子进程或 MPI 提交，实时写入 thermo 日志。  
6. 后处理明确 PBC unwrap、时间窗口、拟合方式和误差，避免用未平衡轨迹拟合扩散。

---

## 8. 验证与安全阈值

- 金属体系拒绝无依据的纯 LJ 势；有电荷体系要求相容的长程静电设置。  
- `atom_style` 与 data/forcefield/pair_style 必须一致。  
- 生产动力学前需要最小化与平衡阶段，除非 `--override` 并写入原因。  
- 温度、压力、密度、能量漂移和总电荷须通过可配置阈值；不通过时结果标记 `INVALID_FOR_PROPERTY`。

---

## 9. 测试与里程碑

**测试**：EAM 金属、Buckingham 氧化物、OPLS 有机体系、错误 atom_style、缺失 fix、错误 units、MSD 合成轨迹回归。  
**M1（4 天）**：manifest、脚本生成和静态验证。  
**M2（5 天）**：运行管理、日志、NVT/NPT 工作流。  
**M3（4 天）**：MDAnalysis/OVITO 后处理与扩散分析。  
**M4（3 天）**：MPI、性能 profile 和电池材料模板。


---

## 10. 冻结条件

- `doctor --strict` 能验证必需引擎、Python 包、模型/势函数和格式支持。
- 所有示例从原始输入到报告可离线重跑。
- 所有核心输出都附输入与配置哈希、引擎版本和单位。
- 批处理可隔离任务失败，并输出结构化错误表。
- 所有“预测”与“实验/物理计算”结论清楚区分，不夸大可信度。

---

## 11. 合规边界

仅接入用户有权使用的开源软件、公开模型、公开势函数和数据。第三方工具、力场、结构文件、训练权重和渲染资产必须在 `manifest` 中记录版本、来源和许可证；不得绕过访问控制或复制私有实现。
