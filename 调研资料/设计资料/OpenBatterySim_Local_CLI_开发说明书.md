# OpenBatterySim 本地 CLI 开发说明书

**版本**：V0.1  
**部署模式**：本地 Conda/Python CLI，结果可追溯、可断点恢复  
**命令行入口**：`obatt`

---

## 1. 目标

构建基于 PyBaMM 与 PyBOP 的锂离子电池本地仿真与参数辨识 CLI，覆盖机理 P2D/DFN、快速 ECM、热行为、退化实验协议和参数拟合。该工具服务于电池材料研发，不把电芯级仿真误用为单一材料本征性质预测。

系统应按附件描述的工作流实现功能等价能力，但只允许使用公开依赖、用户有权使用的数据和独立工程代码；不得复制私有 API、受版权保护的二进制模块、商业数据库内容、模型权重、服务凭证或品牌标识。

---

## 2. 范围

### V0.1 支持

- SPM、SPMe、DFN/P2D 机理模型
- 恒流、CCCV、休止、循环和 C-rate 扫描实验协议
- 等温、lumped、x-full 热模型
- Thevenin ECM 快速仿真与 HPPC
- PyBOP 参数辨识、拟合、验证和不确定性
- 参数集版本管理、材料/电芯尺度边界和结果报告

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
openbatterysim/
├── pyproject.toml
├── environment.yml
├── configs/
├── data/
├── examples/
├── src/openbatterysim/
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
obatt init ./projects/nmc811_cell
obatt doctor --strict
obatt simulate p2d --model dfn --parameter-set Chen2020 --experiment configs/cccv.yaml
obatt simulate ecm --model thevenin --input configs/hppc.yaml
obatt sweep crate --model spme --parameter-set Chen2020 --rates 0.2 0.5 1 2 3
obatt fit --engine pybop --dataset input/cycling.csv --parameters "Negative electrode diffusivity [m2.s-1]" "Exchange-current density [A.m-2]"
obatt report --workdir runs/dfn_001
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
model:
  family: DFN
  parameter_set: Chen2020
  thermal: isothermal
  degradation: false
solver:
  atol: 1e-6
  rtol: 1e-6
  max_step_s: 10
experiment:
  protocol: configs/cccv.yaml
output:
  variables: ["Terminal voltage [V]", "Current [A]", "Discharge capacity [A.h]"]
fit:
  engine: pybop
  split: train_validation
  objective: weighted_rmse
  bounds_source: parameter_manifest
```

配置经 Pydantic 校验后写入 `resolved_config.yaml`。配置、输入与关键数据文件均计算 SHA-256；恢复任务时默认要求哈希一致。

---

## 7. 数据契约

`SimulationRequest`：模型、参数集、协议、热/退化选项、求解器设置。  
`TimeSeriesResult`：time_s、voltage_v、current_a、capacity_ah、soc、temperature_k、状态与事件。  
`ECMResult`：R0/R1/C1 或等效参数、SOC、端电压、拟合残差。  
`FitResult`：参数值、边界、目标函数、训练/验证指标、置信区间、数据和参数集哈希。

所有数值字段必须包含单位后缀或独立 `unit` 字段；所有结构化失败必须包含 `stage`、`error_code`、`message`、`workdir`、`stdout_path`、`stderr_path`。

---

## 8. 工作流

1. 先由用户选择轨道：快速 BMS/HPPC 走 ECM；机理、高倍率、热、退化走 SPM/SPMe/DFN；实测参数反推走 PyBOP。  
2. 验证参数集与目标化学体系是否匹配，例如 NMC/石墨、LFP/石墨、Si 复合体系不可随意混用。  
3. 将实验协议保存为 YAML；每个充放电、恒压、休止动作可复放。  
4. DFN/SPMe 的 SOC 由容量和额定容量计算，不能假设每个模型都有同名 SOC 变量。  
5. 热模型使用正确的输出变量：lumped 与 x-full 的温度变量名称需在变量注册表中映射。  
6. 参数拟合采用训练/验证分割、边界、可识别性检查；不能仅以训练误差宣布参数物理可信。  
7. 扫描电极厚度、孔隙率或容量时执行联动参数检查，防止只改容量或几何造成不物理模型。

---

## 9. 测试与验收

- SPM/SPMe/DFN 基线电压与容量曲线回归
- CCCV 协议动作与终止条件
- 温度模型变量、单位和热边界条件
- C-rate 扫描单调性与异常终止
- ECM HPPC 数据输入、参数拟合和残差
- PyBOP 参数边界、训练验证、不可识别性提示
- 参数集、模型、协议不兼容拒绝运行

---

## 10. 里程碑

- **M1（3 天）**：CLI、参数集 manifest、SPM/SPMe 与标准协议。  
- **M2（5 天）**：DFN、C-rate、CCCV、热模型与结果导出。  
- **M3（4 天）**：Thevenin ECM、HPPC 处理与报告。  
- **M4（5 天）**：PyBOP 拟合、验证、敏感性与可识别性。  
- **M5（3 天）**：材料研发模板、联合结果报告与回归集。

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
