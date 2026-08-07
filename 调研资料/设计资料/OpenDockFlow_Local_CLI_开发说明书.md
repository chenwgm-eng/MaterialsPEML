# OpenDockFlow 本地 CLI 开发说明书

**版本**：V0.1  
**命令行入口**：`odock`  
**部署原则**：本地优先、显式依赖、可重跑、可审计

---

## 1. 目标与边界

构建本地开源蛋白-小分子对接工作流，包括受体/配体输入检查、DiffDock 类本地推理适配器、批量虚拟筛选、位姿文件标准化及置信度排序。其输出是结合位姿候选和模型置信度，不是结合亲和力、Kd 或 delta_G。

只实现独立的本地工作流封装与公开工具集成，不复制附件涉及的私有服务、远程 GPU Runner、预装路径、二进制、模型权重或授权凭证。

---

## 2. V0.1 能力

- PDB/mmCIF 受体、SMILES/SDF/MOL2 配体输入和批量 CSV 校验
- 可插拔本地开源对接推理适配器，默认不绑定私有部署
- 单复合体、批筛选和可恢复任务队列
- Top-N SDF 位姿、模型置信度、运行参数和失败清单
- 基于置信度的排序、聚类、结构完整性检查和结果报告
- 可选对接后评分接口，但与位姿置信度严格分列

每个任务目录必须保存原始输入、解析后配置、命令行、环境清单、stdout/stderr、结果索引和 SHA-256 哈希。

---

## 3. 模块结构

```text
opendockflow/
├── pyproject.toml
├── environment.yml
├── configs/
├── templates/
├── examples/
├── src/opendockflow/
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
odock init ./projects/kinase_screen
odock doctor --strict
odock prepare receptor --input protein.pdb --output receptor_prepared.pdb
odock dock single --protein receptor_prepared.pdb --ligand "CC(=O)Oc1ccccc1C(=O)O" --config configs/fast.yaml
odock dock batch --input complexes.csv --config configs/screen.yaml --workers 1
odock analyze --workdir runs/batch_001 --top 20 --threshold 0.0
odock export --workdir runs/batch_001 --format sdf,csv,html
```

---

## 5. 配置

```yaml
engine: {adapter: local_diffusion_docking, model_manifest: models/docking_manifest.json, device: cpu}
sampling: {samples_per_complex: 10, inference_steps: 20, temp_sampling_tor: 7.04}
input: {ligand_mass_range_da: [100, 1000], allow_covalent: false, max_peptide_residues: 20}
batch: {workers: 1, fail_fast: false, timeout_s_per_complex: 3600}
analysis: {confidence_threshold: 0.0, cluster_rmsd_a: 2.0}
```

配置使用 Pydantic 校验；任何未知字段默认报错。恢复执行时必须验证核心输入、配置、引擎版本和势函数/模型文件哈希。

---

## 6. 数据契约

`ComplexInput`：complex_id、protein_path 或 sequence、ligand 输入、预处理状态和哈希。  
`DockingPose`：rank、SDF 路径、姿势坐标、confidence、采样 seed、模型 manifest 哈希。  
`ComplexResult`：状态、运行时间、所有位姿、失败原因、适用性警告。  
`ScreenSummary`：complex_id、best_confidence、rank、pose_path、聚类数、status。

---

## 7. 关键工作流

1. 检查受体结构、链、残基、缺失原子/非标准残基提示，以及配体 RDKit 化学有效性。  
2. 验证适用范围：主要针对小分子和短肽；对蛋白-蛋白、共价体系、大肽、膜蛋白等明确拒绝或标记超域。  
3. 将每个复合体拆分到独立工作目录，保存输入副本与可重复 seed。  
4. 调用本地推理适配器，输出多份姿势 SDF 和原始模型分数。  
5. 执行 SDF 可读性、配体重原子数、键连通性、碰撞与 pose 聚类检查。  
6. 只按“位姿置信度”解读 score；如接入 GNINA/MMGBSA/FEP 等后评分，必须另列字段与方法版本，不能将其混入扩散模型置信度。

---

## 8. 验证与安全阈值

- 高置信度不等于高亲和力，报告顶部必须显示此限制。  
- 缺失蛋白结构或序列、无效配体、模型 manifest 缺失均为结构化错误。  
- 模型权重必须来自用户有权使用的本地文件并记录哈希/许可。  
- 结果必须供实验或更高阶计算验证，不能用于直接生物活性结论。

---

## 9. 测试与里程碑

**测试**：单对接、批 CSV、SMILES/SDF、无效受体、无效配体、超域输入、超时、部分失败、姿势/分数排序回归。  
**M1（3 天）**：输入 schema、预处理、模型 manifest 与 CLI。  
**M2（5 天）**：单任务 adapter、位姿/分数工件和恢复。  
**M3（4 天）**：批筛选、QC、聚类与报告。  
**M4（3 天）**：可选后评分接口、基准集与局限声明。


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
