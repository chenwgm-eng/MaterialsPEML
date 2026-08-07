# OpenChemProcess 本地 CLI 开发说明书

**版本**：V0.1  
**部署模式**：本地 Conda/Python CLI，结果可追溯、可断点恢复  
**命令行入口**：`ocproc`

---

## 1. 目标

构建反应工程和分离过程计算 CLI，覆盖反应热、扩散、动力学、批式反应器、吸附动力学、液液萃取和 FUG 蒸馏捷径设计。它与 OpenChemProperties 通过标准化的物性输入契约连接。

系统应按附件描述的工作流实现功能等价能力，但只允许使用公开依赖、用户有权使用的数据和独立工程代码；不得复制私有 API、受版权保护的二进制模块、商业数据库内容、模型权重、服务凭证或品牌标识。

---

## 2. 范围

### V0.1 支持

- Hess 定律、用户导入生成焓和 Joback 估算
- Wilke-Chang、Stokes-Einstein、Chapman-Enskog 扩散估计
- Eyring、Arrhenius、Langmuir-Hinshelwood 动力学
- 批式/PFR/CSTR ODE 求解与物料守恒检查
- PFO/PSO 吸附动力学拟合
- Kremser 液液萃取级数估计与可行性预检
- Fenske-Underwood-Gilliland 蒸馏捷径设计

### 明确边界

- 所有结果均保存输入、配置、软件版本、计算日志与单位。
- 任何模型或经验关联式结果必须注明模型、适用范围与不确定性。
- 外部公共数据库只能通过合法 API 或用户自行导入的数据调用。
- 单个失败任务不得中止批量任务，除非显式设置 `fail_fast=true`。

---

## 3. 架构

```text
输入文件 / CLI 参数
       │
       ▼
输入校验与标准化
       │
       ▼
核心计算或仿真引擎
       │
       ├── 参数/模型/数据源路由
       ├── 物理与数值约束检查
       └── 任务工件、日志、失败隔离
       ▼
后处理、质量控制与报告
       │
       ├── CSV / JSON / Parquet
       ├── 图表 / HTML / Markdown
       └── run manifest / checkpoint
```

---

## 4. 项目结构

```text
openchemprocess/
├── pyproject.toml
├── environment.yml
├── configs/
├── data/
├── examples/
├── src/openchemprocess/
│   ├── cli/
│   ├── core/
│   ├── engines/
│   ├── workflows/
│   ├── io/
│   ├── validation/
│   └── utils/
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 5. CLI

```bash
ocproc heat reaction --stoichiometry "A:-1,B:-1,C:1" --formation-enthalpy input/hf.csv
ocproc diffusion liquid --solute ethanol --solvent water --temperature-k 298.15
ocproc reactor batch --model configs/reaction.yaml --t-end-s 7200
ocproc kinetics fit --input uptake.csv --models pfo pso
ocproc extraction kremser --K 3.2 --V-org 1.0 --V-aq 1.0 --x-in 0.10 --x-out 0.01
ocproc distillation fug --input configs/distillation.yaml
```

每次运行建立独立目录：

```text
runs/<run_id>/
├── inputs/
│   ├── resolved_config.yaml
│   ├── input_manifest.json
│   └── environment_manifest.json
├── work/
├── results/
├── checkpoints/
└── logs/
```

---

## 6. 配置规范

```yaml
thermo:
  property_input: ../openchemproperties/results/properties.json
reaction_heat: {method_priority: [user_data, hess, joback]}
reactor: {solver: BDF, rtol: 1e-7, atol: 1e-9}
diffusion: {method_priority: [wilke_chang, stokes_einstein, chapman_enskog]}
extraction: {min_extraction_factor: 1.0}
distillation: {reflux_multiple: 1.5, relative_volatility_method: user_or_vle}
```

配置经 Pydantic 校验后写入 `resolved_config.yaml`。配置、输入与关键数据文件均计算 SHA-256；恢复任务时默认要求哈希一致。

---

## 7. 数据契约

`ReactionHeatResult`：反应式、化学计量、相态、参考温度、delta_h_kj_mol、来源。  
`DiffusionResult`：体系、T/P、method、D_m2_s、参数和不确定性。  
`ReactorResult`：时间、浓度、转化率、选择性、热释放、守恒残差。  
`SeparationResult`：方法、假设、级数/回流比/萃取因子、可行性与敏感性。

所有数值字段必须包含单位后缀或独立 `unit` 字段；所有结构化失败必须包含 `stage`、`error_code`、`message`、`workdir`、`stdout_path`、`stderr_path`。

---

## 8. 工作流

1. 解析反应式与化学计量，检查原子和电荷守恒。  
2. 反应热仅使用具有明确相态与参考温度的生成焓；禁止将 EOS reference enthalpy 当作标准生成焓。  
3. 扩散模型按液体、小分子/胶体、气体路由，并返回经验模型误差提示。  
4. 反应器用 `solve_ivp`，每一步检查非负浓度、物料守恒和事件终止。  
5. Eyring 速率常数需要明确输入 delta_G_dagger 与温度，且记录能垒来源。  
6. Kremser 先计算萃取因子 E；E 小于 1 时报告理论上限，不继续伪造级数。  
7. FUG 依次执行 Fenske、Underwood、Gilliland，并对近共沸、高纯度极限和相对挥发度变化输出警告。

---

## 9. 测试与验收

- Hess 反应热与手工基准一致
- ODE 物料守恒、非负浓度与事件终止
- Eyring/Arrhenius 量纲测试
- Kremser 不可行 E<1 分支
- FUG 的 Nmin、Rmin、R 与级数单调性
- 缺失物性、相态不一致和无效化学计量失败处理

---

## 10. 里程碑

- **M1（3 天）**：反应热、扩散与统一物性输入。  
- **M2（5 天）**：动力学拟合、批式/PFR/CSTR 求解器。  
- **M3（4 天）**：Kremser 与 FUG 分离设计。  
- **M4（2 天）**：敏感性、报告与回归基准。

---

## 11. 冻结条件

- CLI 在干净环境可安装并通过 `doctor --strict`。
- 示例数据可以从输入完整重跑到报告，无隐藏服务依赖。
- 每个结果可追溯至输入、配置、版本、模型/参数和原始日志。
- 单位、数值范围、模型适用范围与失败原因明确可查。
- 测试覆盖核心计算、异常处理、批任务和断点恢复。

---

## 12. 合规边界

本项目是独立的本地重构方案，不是对附件系统、商业数据库、私有接口或受保护实现的复制。接入第三方数据、势函数、参数集、模型和文献时，必须在相应 `manifest` 中记录来源、版本、许可证、访问日期及使用限制。
