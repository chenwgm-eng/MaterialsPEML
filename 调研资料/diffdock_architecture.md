# DiffDock 系统架构文档

> 技能名: `diffdock` | 模型: DiffDock-L (2024)
> 预装环境: `diffdock` conda env (PyTorch 1.13 CPU + torch-geometric 2.2)
> 生成日期: 2026-08-01

---

## 1. 系统总览

DiffDock 是**扩散模型分子对接**工具，预测蛋白质-配体结合位姿 (3D 构象) 和置信度评分。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 3 reference + 3 scripts + 2 assets | 三种工作流 + 置信度解读 + 参数定制 |
| **DiffDock 引擎** | `/opt/DiffDock/` (预装) | 深度学习推理 (CPU) |
| **ESM2** | NAS 缓存模型 (2.5GB) | 蛋白质序列嵌入 |

**关键区分**: DiffDock 预测**结合位姿**和**置信度**，不预测结合亲和力 (ΔG/Kd)。

---

## 2. 文件架构

```
diffdock/
├── SKILL.md                          # 主入口: 三种工作流 + 参数定制
├── scripts/
│   ├── prepare_batch_csv.py          # 批 CSV 创建/验证
│   ├── analyze_results.py            # 置信度分析与排序
│   └── setup_check.py                # 环境诊断
├── references/
│   ├── confidence_and_limitations.md # 置信度解读与局限
│   ├── parameters_reference.md       # 完整参数参考
│   └── workflows_examples.md         # 完整工作流示例
└── assets/
    ├── batch_template.csv             # 批处理 CSV 模板
    └── custom_inference_config.yaml   # 配置模板 (4 种预设)
```

---

## 3. 预装环境

| 项目 | 路径 |
|------|------|
| DiffDock 源码 | `/opt/DiffDock/` |
| Conda 环境 | `diffdock` (Python 3.9) |
| ESM2 模型 | `/app/workspaces/.models/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt` |
| ESM2 回归 | `.../esm2_t33_650M_UR50D-contact-regression.pt` |

**运行**: `source /root/miniconda3/bin/activate diffdock && python /opt/DiffDock/inference.py ...`
**仅 CPU**: 每个小复合体 ~5-10 min

---

## 4. 三种工作流

### 工作流 1: 单个蛋白-配体对接

```bash
python -m inference \
  --config default_inference_args.yaml \
  --protein_path protein.pdb \
  --ligand "CC(=O)Oc1ccccc1C(=O)O" \
  --out_dir results/single/
```

输出: `rank_1.sdf` ~ `rank_N.sdf` + `confidence_scores.txt`

### 工作流 2: 批量处理 (虚拟筛选)

```csv
complex_name,protein_path,ligand_description,protein_sequence
complex1,protein1.pdb,CC(=O)Oc1ccccc1C(=O)O,
complex2,,COc1ccc(C#N)cc1,MSKGEELFT...
```

```bash
python -m inference \
  --config default_inference_args.yaml \
  --protein_ligand_csv batch_input.csv \
  --out_dir results/batch/ --batch_size 10
```

### 工作流 3: 结果分析

```bash
python scripts/analyze_results.py results/batch/ --top 5 --threshold 0.0 --export summary.csv
```

---

## 5. 置信度评分

| 分数范围 | 置信级别 | 解读 |
|----------|----------|------|
| **> 0** | 高 | 强预测，可能准确 |
| **-1.5 ~ 0** | 中 | 合理预测，需验证 |
| **< -1.5** | 低 | 不确定，必须验证 |

**置信度 ≠ 亲和力**: 高置信度意味模型对结构的确定，不意味强结合。

---

## 6. 关键参数

```yaml
samples_per_complex: 10      # 采样密度 (难例: 20-40)
inference_steps: 20          # 推理步数 (高精度: 25-30)
temp_sampling_tor: 7.04      # 扭转温度 (柔性: 8-10, 刚性: 5-6)
```

四种预设: High Accuracy / Fast Screening / Flexible Ligands / Rigid Ligands

---

## 7. 调用关系图

```
用户输入 (PDB + SMILES/SDF)
    │
    ├─→ prepare_batch_csv.py (批模式)
    │
    ├─→ /opt/DiffDock/inference.py
    │   ├── ESM2 嵌入 (蛋白质序列 → NAS 缓存模型)
    │   ├── DiffDock-L 扩散推理 (CPU, ~5-10 min/complex)
    │   └── 输出: rank_N.sdf + confidence_scores.txt
    │
    └─→ analyze_results.py → 统计摘要 + CSV 导出

补充工具链: GNINA (评分), MM/GBSA (亲和力), FEP/TI (自由能)
```

## 附录: 局限

- **适用**: 小分子配体 (100-1000 Da), 药物样有机化合物, 小肽 (<20 残基)
- **不适用**: 蛋白-蛋白对接, 大肽 (>20 残基), 共价对接, 亲和力预测, 膜蛋白
