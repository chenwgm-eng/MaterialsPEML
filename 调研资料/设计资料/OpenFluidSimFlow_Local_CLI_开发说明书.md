# OpenFluidSimFlow 本地 CLI 开发说明书

**版本**：V0.1  
**命令行入口**：`ofsim`  
**部署原则**：本地优先、显式依赖、可重跑、可审计

---

## 1. 目标与边界

构建 FluidSim 的可复现 CFD 工作流封装，面向周期边界伪谱法的二维/三维 Navier-Stokes、分层流和浅水模拟，支持单机与 MPI、NetCDF/HDF5 工件管理及定量后处理。

只实现独立的本地工作流封装与公开工具集成，不复制附件涉及的私有服务、远程 GPU Runner、预装路径、二进制、模型权重或授权凭证。

---

## 2. V0.1 能力

- NS2D、NS3D、NS2D/NS3D 分层流和 SW1L 求解器路由
- 网格、域、粘度/超粘度、CFL、初场、强制力和输出周期配置
- 单机、MPI 后端与 fluidfft 可用性检查
- NetCDF 物理场、HDF5 快照、空间平均和 1D/2D 能谱
- 涡量、速度、守恒量、能谱和收敛/稳态分析
- 续跑、参数扫描和运行资源画像

每个任务目录必须保存原始输入、解析后配置、命令行、环境清单、stdout/stderr、结果索引和 SHA-256 哈希。

---

## 3. 模块结构

```text
openfluidsimflow/
├── pyproject.toml
├── environment.yml
├── configs/
├── templates/
├── examples/
├── src/openfluidsimflow/
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
ofsim init ./projects/ns2d_turbulence
ofsim doctor --strict
ofsim run --solver ns2d --config configs/ns2d.yaml
ofsim run --solver ns3d --config configs/ns3d.yaml --mpi-ranks 16
ofsim resume --sim-dir runs/ns2d_001/work/sim
ofsim analyze --sim-dir runs/ns2d_001/work/sim --fields rot ux --spectra
ofsim sweep --base configs/ns2d.yaml --set nu_2=1e-3,5e-4,1e-4
```

---

## 5. 配置

```yaml
solver: ns2d
oper: {nx: 256, ny: 256, Lx: 6.283185, Ly: 6.283185, type_fft: default}
physics: {nu_2: 0.001, nu_4: 0.0}
time: {t_end: 10.0, use_cfl: true, cfl_coef: 0.8, deltat0: 0.001}
initial: {type: noise, seed: 42}
forcing: {enable: false, type: tcrandom, forcing_rate: null}
output: {phys_fields_period_s: 1.0, spectra_period_s: 1.0, spatial_means_period_s: 0.1}
runtime: {mpi_ranks: 1, home_dir: runsafe_home}
```

配置使用 Pydantic 校验；任何未知字段默认报错。恢复执行时必须验证核心输入、配置、引擎版本和势函数/模型文件哈希。

---

## 6. 数据契约

`SimulationSpec`：solver、网格、域、物理参数、初场、强制力、时间和输出。  
`RunStats`：步数、dt、CFL、walltime、FFT backend、MPI ranks、状态。  
`FieldArtifact`：变量名、维度、单位/无量纲定义、时间、NetCDF/HDF5 路径。  
`AnalysisResult`：空间平均、能量/涡量、谱量、拟合区间和收敛诊断。

---

## 7. 关键工作流

1. 在导入 FluidSim 前设置可写 `HOME`，并检查 FFT/MPI backend。  
2. 按问题选择求解器，验证维度、网格和分层/旋转物理参数。  
3. 生成原生 FluidSim Python driver 与完全解析后的参数快照。  
4. 使用 CFL 自适应时间步，定期采集数值稳定性、守恒量和资源指标。  
5. 对 MPI 作业记录 rank 数和 backend；续跑只能使用相同或已验证兼容的分解设置。  
6. 读取 NetCDF 用 xarray；读取嵌套 HDF5 状态快照用 h5py。变量 key 由求解器注册表控制，例如 NS2D 的涡量为 `rot`、速度为 `ux/uy`。

---

## 8. 验证与安全阈值

- 网格、域长度、粘度和终止时间必须为正；CFL 系数在合理区间。  
- 初始条件、强制力与所选求解器匹配，否则拒绝运行。  
- 检测 NaN/Inf、CFL 爆炸、能量非物理爆涨和输出文件损坏。  
- 不将周期伪谱模型直接用于含复杂壁面/非周期几何而不声明模型局限。

---

## 9. 测试与里程碑

**测试**：NS2D 噪声初场、NS3D 小网格、强制湍流、MPI smoke test、续跑、NetCDF/HDF5 读取及 NaN 失败注入。  
**M1（3 天）**：solver 路由、配置编译、单机 NS2D。  
**M2（4 天）**：输出/后处理、续跑和参数扫描。  
**M3（4 天）**：NS3D/分层/SW1L、MPI 与 profile。


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
