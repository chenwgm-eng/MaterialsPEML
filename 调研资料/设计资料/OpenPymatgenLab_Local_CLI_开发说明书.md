# OpenPymatgenLab 本地 CLI 开发说明书

**版本**：V0.1  
**部署模式**：本地 Conda/Python CLI，结果可追溯、可断点恢复  
**命令行入口**：`opmat`

---

## 1. 目标

构建以 pymatgen 为核心的晶体材料结构处理、格式转换、对称性、相图、表面/缺陷准备和材料数据导入 CLI，为无机电池材料分支提供标准化 CIF/POSCAR/Structure 数据层。

系统应按附件描述的工作流实现功能等价能力，但只允许使用公开依赖、用户有权使用的数据和独立工程代码；不得复制私有 API、受版权保护的二进制模块、商业数据库内容、模型权重、服务凭证或品牌标识。

---

## 2. 范围

### V0.1 支持

- CIF、POSCAR、CONTCAR、XYZ 等结构读写和转换
- 晶格、组成、配位、距离、密度和氧化态基础分析
- primitive/conventional 标准化、空间群与对称性分析
- 超胞、掺杂、缺陷和表面 slab 生成
- 计算条目导入和相图/能量凸包分析
- 用户提供或合法 API 获取的数据缓存与 provenance

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
openpymatgenlab/
├── pyproject.toml
├── environment.yml
├── configs/
├── data/
├── examples/
├── src/openpymatgenlab/
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
opmat init ./projects/lfp
opmat doctor --strict
opmat convert --input LiFePO4.cif --output POSCAR
opmat analyze --input LiFePO4.cif --symprec 0.1
opmat supercell --input LiFePO4.cif --matrix 2 2 1 --output supercell.cif
opmat slab --input LiFePO4.cif --miller 0 1 0 --min-slab-a 12 --min-vacuum-a 15
opmat phase-diagram --entries input/entries.json --chemsys Li-Fe-P-O
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
structure:
  symprec: 0.1
  angle_tolerance: 5.0
  primitive: true
  oxidation_state_guess: true
surface:
  min_slab_size_a: 10.0
  min_vacuum_size_a: 15.0
  max_miller_index: 2
phase_diagram:
  energy_unit: eV_per_atom
  reference_state: computed_entry
remote_data:
  enabled: false
  cache_dir: data/cache
```

配置经 Pydantic 校验后写入 `resolved_config.yaml`。配置、输入与关键数据文件均计算 SHA-256；恢复任务时默认要求哈希一致。

---

## 7. 数据契约

`StructureRecord`：formula、reduced_formula、lattice、sites、spacegroup、input_hash、source。  
`AnalysisRecord`：density_g_cm3、volume_a3、coordination、symmetry、warnings。  
`PhaseDiagramRecord`：chemsys、entries、stable_entries、energy_above_hull_ev_atom、decomposition。  
`SlabRecord`：Miller 指数、终止面、slab/vacuum 厚度、表面积、结构路径。

所有数值字段必须包含单位后缀或独立 `unit` 字段；所有结构化失败必须包含 `stage`、`error_code`、`message`、`workdir`、`stdout_path`、`stderr_path`。

---

## 8. 工作流

1. 读取结构并执行格式、占位率、原子重叠和晶格有效性检查。  
2. 按配置做 primitive 或 conventional 标准化，但始终保存原始结构。  
3. 对称性分析使用明确 `symprec`；结果对容差敏感时输出警告。  
4. 超胞、掺杂和缺陷生成必须记录原子映射、占位率和电荷补偿策略。  
5. slab 生成记录晶面、终止、真空层及偶极风险；不能将低指数面默认视作真实主暴露面。  
6. 相图只接受具有一致参考态的条目；混合计算方法的能量必须拒绝或显式校正。

---

## 9. 测试与验收

- CIF/POSCAR 往返转换与组成守恒
- 空间群和晶格标准化回归
- 超胞原子数比例、掺杂浓度和缺陷电荷规则
- slab 最小厚度/真空和 Miller 参数验证
- 相图能量单位与参考态不一致拒绝
- 缺失占位、坏 CIF 和非周期结构错误处理

---

## 10. 里程碑

- **M1（3 天）**：结构 I/O、分析、对称性和 CLI。  
- **M2（4 天）**：超胞、掺杂、缺陷与 slab。  
- **M3（4 天）**：计算条目、相图和凸包。  
- **M4（2 天）**：电池材料模板、报告和回归测试。

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
