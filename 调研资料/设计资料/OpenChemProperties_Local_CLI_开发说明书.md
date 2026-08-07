# OpenChemProperties 本地 CLI 开发说明书

**版本**：V0.1  
**部署模式**：本地 Conda/Python CLI，结果可追溯、可断点恢复  
**命令行入口**：`ocp`

---

## 1. 目标

构建化学性质、热力学状态、多组分相平衡、闪蒸与溶解度计算的本地工具。它对应附件中的五模块路由：标准常数、指定温压单组分性质、VLE、TPz 闪蒸和溶解度。

系统应按附件描述的工作流实现功能等价能力，但只允许使用公开依赖、用户有权使用的数据和独立工程代码；不得复制私有 API、受版权保护的二进制模块、商业数据库内容、模型权重、服务凭证或品牌标识。

---

## 2. 范围

### V0.1 支持

- 单组分标准常数和 T/P 相关性质查询
- `chemicals`/`thermo` 的公开关联式与物性相关式
- 混合物泡点、露点、等温/等压 VLE
- TPz 闪蒸、相态、汽相分率、各相组成和焓熵
- 气体亨利溶解度、固体 van't Hoff 溶解度及 Hansen/Hildebrand 溶剂筛选
- 物性数据源优先级、来源标记、适用范围和缺失数据报告

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
openchemproperties/
├── pyproject.toml
├── environment.yml
├── configs/
├── data/
├── examples/
├── src/openchemproperties/
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
ocp init ./projects/phase_equilibrium
ocp doctor --strict
ocp pure --name ethanol --temperature-k 350 --pressure-pa 101325
ocp vle bubble --components ethanol water --zs 0.5 0.5 --pressure-pa 101325
ocp flash --components methane ethane propane --zs 0.5 0.3 0.2 --temperature-k 280 --pressure-pa 3500000
ocp solubility gas --solute co2 --solvent water --temperature-k 298.15
ocp report --workdir runs/flash_001
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
runtime: {workers: 1, fail_fast: false}
source_policy:
  allow_remote: false
  preferred: [local_curated, chemicals, thermo, user_import]
pure: {temperature_k: 298.15, pressure_pa: 101325}
vle:
  model_priority: [NRTL, Wilson, UNIQUAC, UNIFAC]
  require_interaction_parameters: false
flash:
  eos: PRMIX
  stability_test: true
  max_iterations: 100
solubility:
  temperature_k: 298.15
  method_priority: [henry, vant_hoff, hansen]
```

配置经 Pydantic 校验后写入 `resolved_config.yaml`。配置、输入与关键数据文件均计算 SHA-256；恢复任务时默认要求哈希一致。

---

## 7. 数据契约

`PurePropertyRecord`：CAS、canonical name、T/P、property_name、value、unit、phase、source、method、validity。  
`VLEResult`：components、zs、T/P、bubble/dew 状态、xs、ys、K_values、activity_model、parameter_source。  
`FlashResult`：T、P、zs、phase_count、vapor_fraction、liquid_fractions、gas_zs、liquid_zs、enthalpy、entropy、EOS。  
`SolubilityResult`：solute、solvent、method、T、value、unit、parameter_source、assumptions。

所有数值字段必须包含单位后缀或独立 `unit` 字段；所有结构化失败必须包含 `stage`、`error_code`、`message`、`workdir`、`stdout_path`、`stderr_path`。

---

## 8. 工作流

1. 标准化组分名称、CAS、SMILES 与摩尔分率，验证组分守恒。  
2. M1 先查询本地或公开许可物性源；缺失时返回 `MISSING_PROPERTY`，不伪造估计值。  
3. M2 在指定 T/P 下用相应关联式计算，超临界、固相或超出关联式温区时显式标记。  
4. M3 先查用户合法导入的 NRTL/Wilson/UNIQUAC 二元参数；缺失时可回退 UNIFAC，并标记 `ESTIMATED_GROUP_CONTRIBUTION`。  
5. M4 使用 PR EOS 进行 TPz 闪蒸；对强缔合、醇/酸、近共沸体系输出模型风险提示，并建议走活度系数 VLE。  
6. M5 依据气/液/固体系路由 Henry、van't Hoff 或溶解度参数法；不得将溶剂筛选相似度冒充绝对溶解度。  
7. 导出长表、计算假设、参数来源和报告。

---

## 9. 测试与验收

- 单组分乙醇、苯、水的单位、相态和温区检查
- 二元 VLE 的组成闭合、泡露点边界和模型回退
- TPz 闪蒸中 `vapor_fraction`、各相组成与物料守恒
- 全液相/全气相下空相对象处理
- Henry、van't Hoff 单位和温度依赖回归
- 无交互参数、超临界、非法组分与无效摩尔分率错误处理

---

## 10. 里程碑

- **M1（3 天）**：CLI、组分标准化、单组分性质和来源追踪。  
- **M2（4 天）**：VLE 与交互参数管理、UNIFAC 回退。  
- **M3（3 天）**：PR TPz 闪蒸、守恒与相稳定性检查。  
- **M4（3 天）**：溶解度模块、报告、回归测试。

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
