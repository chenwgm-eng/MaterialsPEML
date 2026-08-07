# OpenPackmol 本地 CLI 开发说明书

**版本**：V0.1  
**命令行入口**：`opack`  
**部署原则**：本地优先、显式依赖、可重跑、可审计

---

## 1. 目标与边界

构建 Packmol 的可验证本地封装，用于生成溶液、混合物、界面、溶剂化体系及其他分子动力学初始构型，并将结果稳定交接给 LAMMPS/GROMACS/AMBER 等后续工具。

只实现独立的本地工作流封装与公开工具集成，不复制附件涉及的私有服务、远程 GPU Runner、预装路径、二进制、模型权重或授权凭证。

---

## 2. V0.1 能力

- PDB/XYZ/Tinker 分子模板导入和基础结构校验
- 盒、球、圆柱、平面上下、椭球约束的 Packmol 输入生成
- 组分数、摩尔分数、目标密度到盒尺寸的换算
- 溶剂化与电荷中和数量建议，但不替代力场参数化
- 调用 Packmol、记录随机种子、捕获日志和 restart
- 原子重叠、组分数量、PBC、密度和输出成功状态验证

每个任务目录必须保存原始输入、解析后配置、命令行、环境清单、stdout/stderr、结果索引和 SHA-256 哈希。

---

## 3. 模块结构

```text
openpackmol/
├── pyproject.toml
├── environment.yml
├── configs/
├── templates/
├── examples/
├── src/openpackmol/
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
opack init ./projects/electrolyte_box
opack doctor --strict
opack build --config configs/mixture.yaml --workdir runs/mix_001
opack solvate --solute protein.pdb --solvent water.pdb --shell-a 15 --workdir runs/solv_001
opack interface --lower water.pdb --upper hexane.pdb --config configs/interface.yaml
opack validate --input runs/mix_001/results/mixture.pdb --tolerance-a 2.0
```

---

## 5. 配置

```yaml
packmol: {binary: packmol, tolerance_a: 2.0, seed: 42, maxit: 50, discale: 1.0}
box: {min_a: [0, 0, 0], max_a: [40, 40, 40], pbc: true}
components:
  - {path: water.pdb, count: 800, region: {type: inside_box}}
  - {path: ethanol.pdb, count: 200, region: {type: inside_box}}
validation: {overlap_tolerance_a: 2.0, density_tolerance_fraction: 0.15}
```

配置使用 Pydantic 校验；任何未知字段默认报错。恢复执行时必须验证核心输入、配置、引擎版本和势函数/模型文件哈希。

---

## 6. 数据契约

`ComponentSpec`：模板路径、分子数、质量、电荷、空间约束、固定/旋转约束。  
`PackingResult`：输出文件、实际分子数、盒尺寸、随机种子、Packmol 退出状态、完整日志。  
`PackingQC`：最小原子距离、重叠对数、目标/实际密度、PBC、警告和建议最小化步骤。

---

## 7. 关键工作流

1. 读取每个模板，校验原子数、元素、坐标、分子质量和可选净电荷。  
2. 按用户指定数目或目标密度计算盒体积；对混合物明确分子量和单位。  
3. 将约束编译为 Packmol 输入；平面界面默认强制 `discale >= 1.5` 和更高迭代上限。  
4. 调用 `packmol < input.inp`，保存输入、输出、stdout、stderr 和 seed。  
5. 检查输出文件存在、分子数、重叠与密度；`ENDED WITHOUT PERFECT PACKING` 只能标记为可选起始构型，后续必须能量最小化。  
6. 导出交接 manifest，明确它不含 LAMMPS 原子类型、键角二面角或力场参数。

---

## 8. 验证与安全阈值

- 结构模板必须有有限坐标；禁止空文件、NaN、零原子组分。  
- PBC 盒长度、区域几何和分子数必须为正。  
- 最小原子距离低于阈值时为失败；阈值附近标记 `BORDERLINE`。  
- 中和离子数仅作电荷平衡建议，必须在后续力场和价态检查中再次确认。

---

## 9. 测试与里程碑

**测试**：基本混合物、蛋白溶剂化、液液界面、固定分子、坏模板和重叠检测；计数与质量守恒回归。  
**M1（3 天）**：模板、配置、输入生成和本地引擎调用。  
**M2（3 天）**：密度换算、溶剂化、界面和 QC。  
**M3（2 天）**：LAMMPS 交接 manifest、报告和批任务。


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
