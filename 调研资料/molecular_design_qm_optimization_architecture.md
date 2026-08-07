# 分子设计、高精度量子化学计算、多目标优化与主动学习 — 深度技术架构

> 版本: 2026-08-01 | 覆盖 13 个材料研发技能 + 3 个基础设施组件
> 验证状态: 所有接口签名均通过运行时 introspection 验证

---

## 目录

1. [系统总览](#1-系统总览)
2. [分子设计子系统](#2-分子设计子系统)
   - [2.1 生成引擎](#21-生成引擎)
   - [2.2 评估引擎](#22-评估引擎)
   - [2.3 完整设计管线](#23-完整设计管线)
3. [高精度量子化学计算子系统](#3-高精度量子化学计算子系统)
   - [3.1 计算层次与精度矩阵](#31-计算层次与精度矩阵)
   - [3.2 本地 XTB 管线](#32-本地-xtb-管线)
   - [3.3 云端 GPU DFT 管线 (VOLCQC)](#33-云端-gpu-dft-管线-volcqc)
   - [3.4 过渡态搜索与反应网络](#34-过渡态搜索与反应网络)
   - [3.5 波函数分析管线](#35-波函数分析管线)
4. [多目标优化子系统](#4-多目标优化子系统)
   - [4.1 基础设施矩阵](#41-基础设施矩阵)
   - [4.2 优化器实现](#42-优化器实现)
   - [4.3 多目标编排架构](#43-多目标编排架构)
5. [主动学习子系统](#5-主动学习子系统)
   - [5.1 代理模型](#51-代理模型)
   - [5.2 采集函数](#52-采集函数)
   - [5.3 完整主动学习循环](#53-完整主动学习循环)
6. [跨系统集成: 端到端管线](#6-跨系统集成-端到端管线)
7. [附录: 接口速查表](#7-附录-接口速查表)

---

## 1. 系统总览

四个子系统在全局架构中的位置:

```
                        ┌──────────────────────────┐
                        │    分子设计 (生成)          │
                        │  reactnavi + reactnet +    │
                        │  rdkit/BRICS + esmfold2    │
                        └───────────┬──────────────┘
                                    │ 候选分子池
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                主动学习循环 (Agent 编排层)                       │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐  │
│  │ 代理模型              │    │ 采集函数                      │  │
│  │ sklearn GPR / torch  │◄───│ EI / UCB / Committee /      │  │
│  │ Matern 5/2 + RBF     │    │ Thompson Sampling            │  │
│  └─────────┬───────────┘    └──────────┬──────────────────┘  │
│            │ 预测 + 不确定性              │ 选择下一批            │
│            ▼                            ▼                     │
│  ┌─────────────────────┐    ┌─────────────────────────────┐  │
│  │ 多目标优化器          │    │ 实验设计                      │  │
│  │ differential_        │    │ latin hypercube / sobol /  │  │
│  │ evolution + Pareto   │    │ random + 批量 AL             │  │
│  └─────────┬───────────┘    └──────────────────────────────┘  │
└────────────┼──────────────────────────────────────────────────┘
             │ 评估请求
             ▼
┌──────────────────────────────────────────────────────────────┐
│                   评估层 (技能调用)                              │
│                                                              │
│  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 高精度 QM 计算     │  │ 性质预测      │  │ 动力学仿真     │  │
│  │                  │  │              │  │               │  │
│  │ dp-yamo (DFT)    │  │ MPA (42性质) │  │ battery-sim   │  │
│  │ reactnet (TS)    │  │ chem-prop    │  │ lammps (MD)   │  │
│  │ multiwfn (分析)   │  │ diffdock     │  │ fluidsim (CFD)│  │
│  └──────────────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 分子设计子系统

### 2.1 生成引擎

#### 2.1.1 逆合成驱动 (reactnavi)

**入口**: `reactnavi.tools.retrosynthesis_toolkit.call_retrosynthesis`

```python
from reactnavi.tools.retrosynthesis_toolkit import call_retrosynthesis

# 精确签名 (Cython 编译, 通过 docstring 验证)
result = call_retrosynthesis(
    target_smiles="CN(C)C1CCCCC1",    # 目标 SMILES
    output_dir="runs_precursor",       # 本地结果目录
    max_paths=10,                      # 返回路线数
    max_depth=6,                       # 最大搜索深度 (≤7)
    max_iterations=2000,               # 迭代预算
    template_max_count=20,             # 每步 Top-N 模板
    expansion_time=900,                # 搜索时间预算 (s)
    session_id="prod-test-session",
    request_timeout=1200               # HTTP 超时
)
# → POST http://101.126.18.187:8100/api/v1/multi-step
# → 下载 TOS 结果: summary.json + multi_step_pathway_N.png
```

**输出解析**:
```python
# summary.json 结构
{
    "tree": {
        "chemical": {"smiles": "...", "in_stock": bool},
        "reaction": {
            "reaction_smiles": "R>>P",
            "ff_score": 0.85,          # 模型搜索置信度 (非质量指标)
            "conditions": "...",        # 预测反应条件
            "reactants": [              # 递归前驱体
                {"chemical": {...}, "reaction": {...}}
            ]
        }
    }
}
```

#### 2.1.2 反应枚举驱动 (reactnet)

**入口**: `reactnet.netgen.producer.gen_prods.EnumerateReactions`

```python
from reactnet.netgen.producer.gen_prods import EnumerateReactions

enum = EnumerateReactions(
    max_break_bonds=2,                 # 最大断键数
    max_form_bonds=2,                  # 最大成键数
    lewis_score_paticence=0.1,        # Lewis 容忍度
    threshold=20,                      # 成键评分截断
    n_workers=4                        # 并行线程
)

mapped_reactant, products = enum.run("CCO")
# → products: [(product_smiles, rxn_hash), ...]
#   保留原子映射, 支持多片段产物 (如 "FP(F)(F)(F)F.[F-]")
```

**内部算法管线**:
```
分子图 → 断键组合枚举 → 成键组合枚举 → Lewis 评分
    → 金属配位重附着 (Li/Na/B/K) → 化合价过滤 → 环/稠环筛分
    → 原子映射保留 → (产物SMILES, hash)
```

#### 2.1.3 RDKit 骨架操作

```python
from rdkit import Chem
from rdkit.Chem import BRICS, AllChem, Descriptors
from rdkit.Chem import rdMolDescriptors

# BRICS 分解 → 合成砌块
mol = Chem.MolFromSmiles("c1ccccc1C(=O)NC")
fragments = BRICS.BRICSDecompose(mol)
# → {'[1*]C(=O)[6*]', '[3*]c1ccccc1[3*]', '[6*]N[0*]'}

# 重组: BRICS.Build(fragments) → 组合空间

# Morgan 指纹 (2048-bit) — 用于代理模型
fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)

# 217 种描述符 — 用于特征工程
mw = Descriptors.MolWt(mol)
logp = Descriptors.MolLogP(mol)
```

#### 2.1.4 蛋白质结构 (esmfold2)

```python
# Mira compute: POST /v1/fold {sequence, config}
# 输出: PDB 结构 + pLDDT/PAE 置信度
# GPU: 1×A100, 并发 1
```

---

### 2.2 评估引擎

#### 2.2.1 MPA 性质预测 (42 种)

```python
# Mira: mira_inference_call(slug="mpa-613bf0")
# POST /api/v1/predict
{
    "property_name": "BP_K",
    "smiles": ["CCO", "c1ccccc1"],
    "num_confs": 1,
    "batch_size": 8
}
# → {"prediction_list": [354.61, 381.33]} (原始物理单位)

# GPU 变体: axiom-mpa-gpu-service-ef6584 (1×A30, 支持在线微调)
```

#### 2.2.2 DiffDock 结合位姿

```python
# /opt/DiffDock/inference.py (diffdock conda env)
# 输入: protein.pdb + SMILES/SDF
# 输出: rank_N.sdf + confidence_scores.txt

# 置信度: >0 高 | -1.5~0 中 | <-1.5 低
# ⚠️ 置信度 ≠ 结合亲和力 (需 GNINA/MM-GBSA 补充)
```

#### 2.2.3 实验性质验证 (chem-properties)

```python
# M1: 标准常数 → DIPPR/Perry's (~340 化合物)
# M2: T/P 依赖 → query_chemicals.py <name> <T_K> [P_Pa]
# M5: 溶解度 → Henry/van't Hoff/Hansen/Hildebrand
```

---

### 2.3 完整设计管线

```
                目标定义
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 逆合成        反应枚举        RDKit 骨架操作
 (reactnavi)   (reactnet)     (BRICS/Recap)
    │               │               │
    └───────┬───────┴───────┬───────┘
            ▼               ▼
         候选分子池 (SMILE 集合)
            │
    ┌───────┼───────────────┐
    ▼       ▼               ▼
  MPA     diffdock      chem-prop
 (42性质) (结合位姿)     (实验数据)
    │       │               │
    └───────┴───────────────┘
            ▼
    ┌─────────────────────────┐
    │ 高精度 QM 验证 (按需)    │
    │ dp-yamo DFT + reactnet  │
    └──────────┬──────────────┘
               ▼
         Pareto 前沿 → 最优候选
```

---

## 3. 高精度量子化学计算子系统

### 3.1 计算层次与精度矩阵

| 级别 | 引擎 | 方法 | 典型时间 | 典型误差 | 适用场景 |
|------|------|------|----------|----------|----------|
| **MM** | MMFF94 | rcs_v2 力场驱动 | 秒级 | — | 构象初始猜测 |
| **SQM** | xtb (GFN2-xTB) | 半经验 | 秒-分钟 | ~2-5 kcal/mol (能垒) | 高通量筛选, 构象搜索 |
| **SQM** | xtb (g-xTB) | 半经验 (SP修正) | 秒-分钟 | 优于 GFN2 | 推荐默认, SP 矫正 |
| **SQM+** | xtb + GBSA/ALPB | 半经验 + 隐式溶剂 | 分钟 | ~3-8 kcal/mol (ΔG_solv) | 溶液相热化学 |
| **DFT** | gpu4pyscf (wb97x-d4/def2-svpd) | GPU DFT | 10 min-8 hr | ~1-2 kcal/mol | 发表级精度 |
| **DFT+** | gpu4pyscf (wb97x-d4/def2-tzvp) | 大基组 DFT | 1-24 hr | ~0.5-1 kcal/mol | 基准级 |
| **Post-HF** | 不可用 | — | — | — | 需外部计算 |

### 3.2 本地 XTB 管线

```python
from yamo import yamol
from reactnet.config import Config

# === 管线入口 ===
mol = yamol("CCO")
charge = mol.q                    # yamol 自动推导电荷 (禁止手工设定)
mult = mol.unpair + 1             # 自旋多重度 = 未配对电子 + 1

# === 阶段 1: 构象采样 ===
# 方式 A: 本地 CREST (dp-yamo)
crest = mol.conf_sample(method="crest", nproc=10, quick_mode="quick")
# mol.geo  = 最低能量构象 (Å)
# mol.energy = 绝对能量 (Hartree)
# mol.confs  = 构象列表 (每个 yamol 含绝对能量)
energies = [c.energy for c in mol.confs]  # Hartree

# 方式 B: Mira 云端 (crest_sampling)
# compute_submit(compute_type="crest_sampling", input_path="mols.csv")

# === 阶段 2: XTB 几何优化 ===
mol.opt()                          # Config.XTB.lot='gxtb' (默认)
mol.opt(solvent="h2o")             # 隐式溶剂 (GBSA/ALPB)

# === 阶段 3: 性质评估 ===
# 单点能
mol.evaluate("energy")             # Hartree
# 热化学
mol.evaluate("thermal", solvent="h2o")
# 氧化还原
result = mol.evaluate("redox", method="xtb", solvent="h2o")
# PCET
result = mol.evaluate("redox_pcet", method="xtb",
                       pcet_mode="reduction", pH=7.0)
# 极化率
mol.evaluate("polarizability", method="dft")
# 原子电荷
mol.evaluate("atomic_charges", method="dft")  # Mulliken + CHELPG

# === 格式导出 ===
mol.to_xyz("opt.xyz")
mol.to_molden("orbitals.molden")   # → multiwfn 分析
```

**g-xTB 自动回退**: `lot='gxtb'` 默认; 若 xtb 二进制不支持 `--gxtb`, 自动回退 GFN2 并发出 `RuntimeWarning`。

### 3.3 云端 GPU DFT 管线 (VOLCQC)

```python
from yamo.wrappers import VOLCQC
from yamo.parsers import to_xyz_string

# === 单分子 DFT ===
xyz = to_xyz_string(mol.elements, mol.geo)

volcqc = VOLCQC(
    functional="wb97x-d4",          # 泛函
    basis="def2-svpd",              # 基组 (已验证签名)
    auxbasis="def2-tzvp-jkfit",     # 密度拟合辅助基组
    charge=mol.q,                   # ⚠️ 必须从 yamol 推导
    multiplicity=mol.unpair + 1,
    solvation_model="SMD",          # 隐式溶剂模型
    solvent="water",
    grid_level=5,                   # DFT 积分网格 (0-9)
    pal=16,                         # GPU 并行度
    mem=4000,                       # 内存 (MB)
    walltime=14400                  # 超时 (秒)
)

# 加载分子 — 支持批量
volcqc.load_molecules(from_list=[xyz], molecule_names=["mol1"])

# === 任务类型 ===
# 几何优化
volcqc.execute(task_type="pysisyphus", jobtype="opt")
# TS 优化
volcqc.execute(task_type="pysisyphus", jobtype="tsopt",
               tsopt_settings={"hessian_recalc": 3})
# IRC
volcqc.execute(task_type="pysisyphus", jobtype="irc")
# 单点 + 分子轨道保存
volcqc.execute(task_type="sp",
               prop_settings={"save_mo": True})

# === 结果提取 ===
# sp/opt: 直接访问
E = volcqc.get_energy("mol1")                # Hartree
E, G = volcqc.get_final_structure("mol1")    # (elements, geometry)
dipole = volcqc.get_dipole("mol1")           # Debye
homo, lumo = volcqc.get_homo_lumo("mol1")    # Eh

# pysisyphus (TS/IRC): 必须通过 get_pysis
pysis = volcqc.get_pysis("mol1")
ts_E, ts_G = pysis.get_final_structure()

# 热化学
thermal = volcqc.get_thermal_properties("mol1")
# → {H, G, S, ZPE, ...}

# 批量 DFT (所有分子一次 execute)
all_xyz = [to_xyz_string(m.elements, m.geo) for m in molecules]
volcqc.load_molecules(from_list=all_xyz,
                      molecule_names=[f"mol_{i}" for i in range(N)])
volcqc.execute(task_type="pysisyphus", jobtype="opt")
# ⚠️ 禁止逐分子提交 execute — 必须一批 load_molecules + 一次 execute

# 错误检查
if volcqc.calculation_terminated_normally("mol1"):
    E = volcqc.get_energy("mol1")
else:
    print(f"DFT 失败: {volcqc.get_completion_status('mol1')}")
```

**accreditation 策略**:
- 默认 `ak`, `sk` 已内嵌在 VOLCQC 构造器中
- 提交到 Volcengine QC 云平台 (gpu4pyscf on A30 GPU)

### 3.4 过渡态搜索与反应网络

#### 3.4.1 单反应 TS 搜索

```python
from reactnet.core.reaction import Reaction

rxn = Reaction(
    reaction="[CH3:1][O:2][H:3]>>[CH2:1]=[O:2].[H:3]",
    name="dehydration",
    charge=0, multiplicity=1,
    rcs_method="rcs_v2"
)

# 完整管线: RCS→GSM→TSOPT→IRC (@ xTB)
results = rxn.locate_ts(do_sampling=True)
# → {TSs: [{DE_F, DE_B, TS_SPE, TSGeo, IRC_DE_F, IRC_DE_B, atom_mapped_smiles}]}
# 能垒: kcal/mol | 能量: Hartree | 几何: Å

# 管线内部:
# 1. rcs_v2 (reaction_tools.rcs_v2, MMFF94 力场)
# 2. GSM (Config.PYGSM, pyGSM, xTB/g-xTB 计算器)
# 3. TSOPT (Config.PYSIS.TSOPT, pysisyphus)
# 4. IRC (Config.PYSIS.IRC, 步长 0.1 Bohr)
```

#### 3.4.2 批量 TS 搜索 (Mira 云端)

```python
# Mira: run_ts_search (xTB/g-xTB only, CPU)
# 输入: reactions=["R>>P"] 或 xyz_zip
# 输出: IRC-record-processed.txt (barrier kcal/mol, TS_SPE Hartree)

# → 结果: final_TSs.p pickle
```

#### 3.4.3 xTB→DFT 精修 (Step R)

```python
# 从完成 xTB 作业下载 final_TSs.p
# → 本地 DFT 驱动:
# python -m reactnet.workflows.yarp_qc <config.yaml>
#   └─ _yarp_qc.main(params)
#       └─ QcBatchJob (volcqc 提交) → DFT TSOPT + IRC
# 输出: DFT/yarp_results-processed.txt (IRC_DE_F, IRC_DE_B, ref_barrier)

# ⚠️ yarp_qc 总是 TSOPT + IRC (无 tsopt-only 模式)
# ⚠️ 仅改变能量, 不重新生长网络
```

#### 3.4.4 反应网络 (Mira 云端)

```python
# mira_inference_call(slug="reactnet-19d712")
# POST /api/v1/jobs/run_network
{
    "reactants": ["CCO"],
    "layers": 2,                    # ≤3
    "bimolecular": False,
    "barrier_threshold": 70.0,      # kcal/mol
    "max_species_per_layer": 2,
    "max_break_bonds": 1,
    "max_form_bonds": 1,
    "lot": "gxtb"
}
# 自动触发 ReactomeForge 图谱生成 (graph_state: PENDING→RUNNING→READY)
```

### 3.5 波函数分析管线

```python
# VOLCQC → .molden → multiwfn
volcqc.execute(task_type="sp", prop_settings={"save_mo": True})
# → gen_molden → orbitals.molden

# === ESP 分析 (4 阶段) ===
# scripts/run_esp_local.py molecule.molden
# Stage 1: Multiwfn 12→0 (整体分子表面 ESP 统计)
# Stage 2: 9→all→range→15→3 (ESP 区间面积分布)
# Stage 3: 11→n→2 (原子局部 ESP 统计)
# Stage 4: 5→1 + 5→12 (density.cub + totesp.cub, 可选)

# === HOMO/LUMO 轨道 ===
# scripts/run_homo_lumo_local.sh molecule.fchk
# → results/Orb_Val_Sum.csv + orb*.cub

# === VMD 渲染 (Mira GPU) ===
# run_vmd_render.py esp --analysis-dir <dir> --confirmed --dry-run
# → mira_inference_upload_file("vmd-runner-5f2a38") → BMP
```

---

## 4. 多目标优化子系统

### 4.1 基础设施矩阵

| 组件 | 来源 | 能力 | 签名 |
|------|------|------|------|
| `scipy.optimize.minimize` | scipy | 局部优化 (梯度/无梯度) | `minimize(fun, x0, method, bounds, constraints, ...)` |
| `scipy.optimize.differential_evolution` | scipy | 全局优化 (无梯度, 112 CPU) | `differential_evolution(func, bounds, strategy='best1bin', maxiter=1000, popsize=15, workers=1, ...)` |
| `scipy.optimize.dual_annealing` | scipy | 模拟退火全局优化 | `dual_annealing(func, bounds, maxiter=1000, ...)` |
| `sklearn.gaussian_process.GaussianProcessRegressor` | sklearn | 代理模型 (贝叶斯优化) | `GPR(kernel=None, alpha=1e-10, optimizer='fmin_l_bfgs_b', n_restarts_optimizer=0, ...)` |
| `sklearn.gaussian_process.kernels.RBF` | sklearn | 径向基核 | `RBF(length_scale=1.0)` |
| `sklearn.gaussian_process.kernels.Matern` | sklearn | Matérn 核 | `Matern(length_scale=1.0, nu=1.5/2.5)` |
| `sklearn.gaussian_process.kernels.ConstantKernel` | sklearn | 常数核 (信号方差) | `ConstantKernel(constant_value=1.0)` |
| `sklearn.gaussian_process.kernels.WhiteKernel` | sklearn | 白噪声核 (观测噪声) | `WhiteKernel(noise_level=1.0)` |
| `torch.nn` | PyTorch 2.11 | 神经网络代理模型 | `nn.Sequential(...)` |
| RDKit Morgan FP | rdkit | 2048-bit 分子指纹 | `rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, 2, 2048)` |
| RDKit Descriptors | rdkit | 217 种分子描述符 | `Descriptors.MolWt, .MolLogP, ...` |

**不可用** (需 Agent 编排替代):

| 缺失组件 | 等效编排 |
|----------|---------|
| ax / botorch | sklearn GPR + 自写 EI/UCB 采集函数 |
| optuna | scipy.differential_evolution + 自写试验管理 |
| NSGA-II / MOEA/D | 自写 Pareto 支配排序 + scipy 全局优化 |
| modAL / libact | 自写 AL 循环 + sklearn GPR |

### 4.2 优化器实现

#### 4.2.1 单目标贝叶斯优化 (GPR + EI)

```python
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from scipy.stats import norm
from scipy.optimize import differential_evolution

class BayesianOptimizer:
    """贝叶斯优化器: GPR 代理 + EI 采集 (单目标)"""

    def __init__(self, bounds, n_init=10):
        # 复合核: 信号方差 × Matérn 5/2 + 噪声
        self.kernel = (
            ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3)) *
            Matern(length_scale=1.0, nu=2.5, length_scale_bounds=(1e-2, 1e2)) +
            WhiteKernel(noise_level=1e-5)
        )
        self.model = GaussianProcessRegressor(
            kernel=self.kernel,
            alpha=1e-6,               # 观测噪声水平
            n_restarts_optimizer=10,   # 核超参多次重启
            normalize_y=True
        )
        self.bounds = np.array(bounds)
        self.X = []
        self.y = []

    def expected_improvement(self, X_candidates):
        """EI 采集函数"""
        mu, sigma = self.model.predict(X_candidates, return_std=True)
        y_best = np.max(self.y)  # 最大化

        with np.errstate(divide='warn'):
            Z = (mu - y_best) / sigma
            ei = (mu - y_best) * norm.cdf(Z) + sigma * norm.pdf(Z)
        ei[sigma < 1e-9] = 0.0
        return ei

    def suggest(self, candidate_pool, batch_size=1):
        """选择下一批评估点"""
        scores = self.expected_improvement(candidate_pool)
        idx = np.argsort(scores)[-batch_size:]
        return candidate_pool[idx], scores[idx]

    def update(self, X_new, y_new):
        """更新代理模型"""
        self.X.extend(X_new)
        self.y.extend(y_new)
        self.model.fit(np.array(self.X), np.array(self.y))

    def optimize_acquisition(self, n_restarts=20):
        """用全局优化器最大化采集函数 (连续设计空间)"""
        def neg_acq(x):
            x = np.atleast_2d(x)
            return -self.expected_improvement(x)[0]

        result = differential_evolution(
            neg_acq,
            bounds=self.bounds,
            popsize=15,
            maxiter=1000,
            tol=1e-6,
            polish=True
        )
        return result.x, -result.fun
```

#### 4.2.2 多目标 Pareto 支配排序

```python
def pareto_front(points, objectives_directions):
    """
    计算 Pareto 前沿

    points: N×M 矩阵 (N 个点, M 个目标)
    objectives_directions: M 个 'min' 或 'max'
    """
    N = len(points)
    dominated = np.zeros(N, dtype=bool)

    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            # 检查 j 是否支配 i
            better_or_equal = True
            strictly_better = False
            for k, direction in enumerate(objectives_directions):
                if direction == 'min':
                    if points[j][k] > points[i][k]:
                        better_or_equal = False; break
                    if points[j][k] < points[i][k]:
                        strictly_better = True
                else:  # 'max'
                    if points[j][k] < points[i][k]:
                        better_or_equal = False; break
                    if points[j][k] > points[i][k]:
                        strictly_better = True
            if better_or_equal and strictly_better:
                dominated[i] = True
                break

    return ~dominated

# 示例: 3 目标
# objectives = {"barrier": "min", "solubility": "max", "steps": "min"}
# pareto_mask = pareto_front(results_matrix, ["min", "max", "min"])
```

#### 4.2.3 多目标 UCB 采集

```python
def multi_objective_UCB(model, X_candidates, objectives, beta=2.0):
    """
    多目标 UCB: 对每个目标独立预测, 加权组合

    model: 多输出 GPR (n_targets=K)
    X_candidates: 候选池
    objectives: {'obj_name': 'min'/'max'}
    beta: 探索-利用权衡
    """
    mu, sigma = model.predict(X_candidates, return_std=True)
    # mu: (N, K), sigma: (N, K)

    ucbs = np.zeros((len(X_candidates), len(objectives)))
    for k, direction in enumerate(objectives.values()):
        sign = -1 if direction == 'min' else +1
        ucbs[:, k] = sign * (mu[:, k] + sign * beta * sigma[:, k])

    # 标量化: 加权和 (等权默认)
    weights = np.ones(len(objectives)) / len(objectives)
    return ucbs @ weights
```

### 4.3 多目标编排架构

```
┌─────────────────────────────────────────────────────────────┐
│  多目标优化编排器                                              │
│                                                             │
│  class MultiObjectiveOrchestrator:                           │
│                                                             │
│    objectives = {                                            │
│        "barrier":     {"direction": "min",                    │
│                        "evaluator": reactnet_evaluate},      │
│        "solubility":  {"direction": "max",                    │
│                        "evaluator": MPA_predict},            │
│        "synthesizability": {"direction": "min",               │
│                             "evaluator": reactnavi_eval},    │
│    }                                                         │
│                                                             │
│    def evaluate(self, molecule):                             │
│        """一次评估触发多个技能调用"""                           │
│        results = {}                                          │
│        if "barrier" in active:                                │
│            rxn = Reaction(f"{molecule}>>...")                 │
│            ts_result = rxn.locate_ts()                        │
│            results["barrier"] = min(ts["DE_F"]                │
│                                     for ts in ts_result["TSs"])│
│        if "solubility" in active:                             │
│            pred = MPA_predict("log_solubility_water_molL",    │
│                               [molecule])                     │
│            results["solubility"] = pred[0]                    │
│        if "synthesizability" in active:                       │
│            route = call_retrosynthesis(molecule)              │
│            results["steps"] = route["num_reactions"]          │
│        return results                                         │
│                                                             │
│    def run(self, initial_pool, max_evals=100):                │
│        """主循环"""                                           │
│        pareto_points = []                                     │
│        for iteration in range(max_evals):                     │
│            # 1. 代理模型预测                                   │
│            # 2. 多目标采集                                     │
│            # 3. 选择候选                                       │
│            # 4. 真实评估 (技能调用)                             │
│            # 5. 更新 Pareto 前沿                               │
│            # 6. 更新代理模型                                   │
│        return pareto_points                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 主动学习子系统

### 5.1 代理模型

#### 5.1.1 GPR 代理 (精确接口)

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel, RBF

# 推荐核 (分子性质建模)
kernel = (
    ConstantKernel(1.0, (1e-3, 1e3)) *
    Matern(length_scale=1.0, nu=2.5, length_scale_bounds=(1e-2, 1e2)) +
    WhiteKernel(noise_level=1e-5)
)

# 多目标: 独立 GPR
models = {
    "barrier":     GaussianProcessRegressor(kernel=kernel, alpha=1e-6,
                                            n_restarts_optimizer=10,
                                            normalize_y=True),
    "solubility":  GaussianProcessRegressor(kernel=kernel, alpha=1e-6,
                                            n_restarts_optimizer=10,
                                            normalize_y=True),
}

# 分子输入: Morgan 指纹 (2048-bit)
X = np.array([fp_array_1, fp_array_2, ...])   # (N, 2048)
y_barrier    = np.array([12.5, 25.3, ...])    # (N,)
y_solubility = np.array([-2.1, -0.8, ...])    # (N,)

for name, model in models.items():
    model.fit(X, eval(f"y_{name}"))
```

#### 5.1.2 PyTorch 神经网络代理 (备选)

```python
import torch
import torch.nn as nn

class MolecularSurrogate(nn.Module):
    """分子性质多输出代理模型"""
    def __init__(self, input_dim=2048, hidden=256, n_outputs=3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, n_outputs)
        )
        # 输出: (barrier, solubility, steps)

    def forward(self, x):
        return self.net(x)

    def predict_with_uncertainty(self, x, n_samples=10):
        """MC Dropout 不确定性估计"""
        self.train()  # 保持 dropout
        preds = torch.stack([self(x) for _ in range(n_samples)])
        return preds.mean(0), preds.std(0)
```

### 5.2 采集函数

| 函数 | 公式 | 用途 | 实现 |
|------|------|------|------|
| **Expected Improvement (EI)** | `E[max(f(x)-y*, 0)]` | 单目标, 默认 | `(mu-y_best)*Phi(Z) + sigma*phi(Z)` |
| **Upper Confidence Bound (UCB)** | `mu + beta*sigma` | 探索利用可调 | β=2 默认 |
| **Probability of Improvement (PI)** | `P(f(x) > y* + ξ)` | 保守探索 | `Phi((mu-y_best-xi)/sigma)` |
| **Thompson Sampling** | 后验采样 | 批量并行 | 从 GP 后验采样 |
| **Query by Committee** | `var(f_i(x))` | 多模型分歧 | 多模型预测方差 |

```python
def thompson_sampling(model, X_candidates, n_samples=1):
    """Thompson 采样: 从 GP 后验采样路径"""
    y_samples = model.sample_y(X_candidates, n_samples=n_samples,
                                random_state=None)
    idx = np.argmax(y_samples, axis=0)
    return X_candidates[idx]

def query_by_committee(models, X_candidates):
    """委员会查询: 多模型预测方差"""
    preds = np.array([m.predict(X_candidates) for m in models])
    var = np.var(preds, axis=0)
    return np.argmax(var)

def probability_of_improvement(model, X_candidates, xi=0.01):
    """PI 采集函数"""
    mu, sigma = model.predict(X_candidates, return_std=True)
    y_best = np.max(model.y_train_)
    Z = (mu - y_best - xi) / sigma
    return norm.cdf(Z)
```

### 5.3 完整主动学习循环

```python
class ActiveLearningLoop:
    """
    主动学习循环: 代理模型 + 采集函数 + 技能评估

    每个 evaluate() 调用可能触发:
    - dp-yamo (DFT 计算, ~10 min - 8 hr)
    - reactnet (TS 搜索, ~10-30 min)
    - MPA (性质预测, ~秒)
    - diffdock (分子对接, ~5-10 min)
    """

    def __init__(self, objectives, initial_pool_size=20, batch_size=5):
        self.objectives = objectives
        self.batch_size = batch_size
        self.X_train = []       # 分子指纹
        self.y_train = {k: [] for k in objectives}  # 多目标
        self.iteration = 0
        self.history = []

        # 初始化代理模型
        self.models = {}
        for name in objectives:
            kernel = ConstantKernel(1.0) * Matern(nu=2.5) + WhiteKernel(1e-5)
            self.models[name] = GaussianProcessRegressor(
                kernel=kernel, alpha=1e-6, n_restarts_optimizer=10,
                normalize_y=True
            )

    def initialize(self, candidate_pool):
        """Latin Hypercube 初始化采样"""
        n_init = min(len(candidate_pool), 20)
        indices = LatinHypercubeSampling(len(candidate_pool[0]), n_init)
        self._evaluate_batch([candidate_pool[i] for i in indices])

    def _evaluate_batch(self, molecules):
        """批量评估 (顺序调用技能, 避免资源竞争)"""
        for mol in molecules:
            result = self._orchestrate_evaluation(mol)
            fp = morgan_fingerprint(mol)
            self.X_train.append(fp)
            for k, v in result.items():
                self.y_train[k].append(v)
            self.history.append({"mol": mol, **result})
            self.iteration += 1

    def _orchestrate_evaluation(self, smiles):
        """编排多技能评估"""
        results = {}
        for obj_name in self.objectives:
            if obj_name == "barrier":
                rxn = Reaction(reaction=f"{smiles}>>...")
                ts = rxn.locate_ts(do_sampling=True)
                results["barrier"] = min(t["DE_F"] for t in ts["TSs"])
            elif obj_name == "solubility":
                pred = mira_inference_call(slug="mpa-613bf0",
                    path="/api/v1/predict", method="POST",
                    json_body={"property_name": "log_solubility_water_molL",
                              "smiles": [smiles]})
                results["solubility"] = pred["prediction_list"][0]
            elif obj_name == "binding_confidence":
                # DiffDock 评估
                results["binding_confidence"] = diffdock_score(smiles, protein)
        return results

    def step(self, candidate_pool):
        """单步主动学习迭代"""
        # 1. 更新所有代理模型
        X = np.array(self.X_train)
        for name, model in self.models.items():
            y = np.array(self.y_train[name])
            model.fit(X, y)

        # 2. 多目标采集
        fp_pool = np.array([morgan_fingerprint(m) for m in candidate_pool])
        scores = np.zeros(len(candidate_pool))
        for name, model in self.models.items():
            direction = self.objectives[name]["direction"]
            mu, sigma = model.predict(fp_pool, return_std=True)
            sign = -1 if direction == "min" else +1
            scores += sign * (sign * mu + 2.0 * sigma)  # UCB
        scores /= len(self.models)

        # 3. 选择下一批 (UCB + 多样性)
        selected_idx = self._select_diverse(fp_pool, scores, self.batch_size)
        selected = [candidate_pool[i] for i in selected_idx]

        # 4. 真实评估
        self._evaluate_batch(selected)
        return selected

    def _select_diverse(self, fp_pool, scores, k):
        """Top-k + 最小相似度过滤"""
        from sklearn.metrics.pairwise import cosine_similarity
        ranked = np.argsort(scores)[::-1]
        selected = []
        for idx in ranked:
            if len(selected) >= k:
                break
            if len(selected) == 0:
                selected.append(idx)
            else:
                sims = cosine_similarity(
                    [fp_pool[idx]], fp_pool[selected]
                ).max()
                if sims < 0.95:  # 排除高度相似
                    selected.append(idx)
        return selected

    def get_pareto_front(self):
        """从历史记录提取 Pareto 前沿"""
        points = np.array([
            [h[obj] for obj in self.objectives] for h in self.history
        ])
        directions = [self.objectives[obj]["direction"]
                      for obj in self.objectives]
        mask = pareto_front(points, directions)
        return [self.history[i] for i in range(len(mask)) if mask[i]]

    def convergence_check(self, window=10):
        """检查 Pareto 超体积是否收敛"""
        if len(self.history) < window * 2:
            return False
        recent = self.history[-window:]
        previous = self.history[-2*window:-window]
        # 简化的超体积变化检测
        recent_best = min(h["barrier"] for h in recent)
        prev_best = min(h["barrier"] for h in previous)
        return abs(recent_best - prev_best) < 0.1  # < 0.1 kcal/mol
```

---

## 6. 跨系统集成: 端到端管线

### 6.1 完整管线: 从分子设计到 Pareto 最优

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 分子空间生成                                             │
│                                                                 │
│  reactnavi.call_retrosynthesis("target_smiles")                  │
│  → 合成路线 → 中间体池                                           │
│                                                                 │
│  reactnet.EnumerateReactions("reactant").run()                   │
│  → 反应产物空间                                                  │
│                                                                 │
│  rdkit BRICS.BRICSDecompose(mol) + BRICS.Build(fragments)       │
│  → 骨架跃迁空间                                                  │
│                                                                 │
│  pymatgen SubstitutionTransformation({"Fe":"Mn"})                │
│  → 元素替换空间                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                    候选分子池 (SMILES 集合, 通常 10²-10⁶)
                              │
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: 快速初筛 (低成本评估)                                      │
│                                                                 │
│  chem-properties M1: query_chemicals.py <name>                   │
│  → 实验数据库中是否存在? (Tb, Tm, logP, ...)                     │
│                                                                 │
│  MPA: POST /api/v1/predict                                       │
│  → 42 种性质批量预测 (秒级, GPU)                                   │
│                                                                 │
│  RDKit 描述符: MolWt, MolLogP, TPSA, RotBonds, HBA/HBD          │
│  → Lipinski / Veber / REOS 过滤                                  │
│                                                                 │
│  chem-price: 可购买性检查 (100+ 供应商)                            │
│                                                                 │
│  过滤后池: 10¹-10³ 个候选                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: 主动学习优化循环                                           │
│                                                                 │
│  初始化: Latin Hypercube 采样 N_init=20                          │
│                                                                 │
│  while not converged and budget > 0:                            │
│      for each molecule in batch:                                │
│          │                                                       │
│          ├─ 中精度: yamo→XTB opt→energy (秒-分钟)                │
│          │                                                       │
│          ├─ [关键分子] 高精度:                                   │
│          │   volcqc = VOLCQC(functional="wb97x-d4",              │
│          │                   basis="def2-svpd", ...)            │
│          │   volcqc.load_molecules(...)                          │
│          │   volcqc.execute(task_type="sp")                     │
│          │   → DFT 单点能                                        │
│          │                                                       │
│          ├─ [TS 搜索] reactnet.Reaction.locate_ts()             │
│          │   → DE_F, DE_B (kcal/mol)                            │
│          │                                                       │
│          └─ [对接] DiffDock inference                            │
│              → confidence + pose                                │
│                                                                 │
│      update GP models                                            │
│      compute acquisition (EI/UCB/Thompson)                       │
│      select next batch                                           │
│      update Pareto front                                         │
│                                                                 │
│  输出: Pareto 最优分子集                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: 最终验证                                                 │
│                                                                 │
│  Pareto 前沿上的候选 → 高精度 DFT 全面评估:                        │
│                                                                 │
│  volcqc.execute(task_type="pysisyphus", jobtype="opt")          │
│  volcqc.execute(task_type="pysisyphus", jobtype="tsopt")        │
│  volcqc.execute(task_type="pysisyphus", jobtype="irc")          │
│                                                                 │
│  multiwfn ESP 分析 → 静电势分布                                   │
│  multiwfn HOMO/LUMO → 前线轨道                                    │
│                                                                 │
│  lammps MD 验证 → 热力学稳定性                                    │
│  battery-sim → 电化学性能                                         │
│                                                                 │
│  → 最终报告: 3-5 个最优候选 + 全精度数据                          │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 评估成本模型

| 评估类型 | 调用技能 | 典型时间 | 每分子成本 |
|----------|---------|----------|-----------|
| 快速初筛 | MPA (GPU) | ~1-2 s | $0.001 |
| 实验验证 | chem-properties | ~0.1 s | $0 |
| XTB 优化 | dp-yamo (本地) | ~30 s | $0.01 |
| DFT SP | VOLCQC (GPU) | ~5-15 min | $0.5-2 |
| DFT opt | VOLCQC (GPU) | ~30-60 min | $2-10 |
| DFT TS+IRC | VOLCQC (GPU) | ~1-4 hr | $10-50 |
| TS 搜索 (xTB) | reactnet (本地) | ~10-30 min | $0.1 |
| 对接 (单配体) | DiffDock (CPU) | ~5-10 min | $0.05 |
| MD (短) | lammps (CPU) | ~5-30 min | $0.1-0.5 |

**主动学习预算估算**:
- 100 次评估 × ($2 DFT SP + $0.1 TS + $0.05 对接) ≈ $200-300
- 加上初始池 DFE 和最终验证 DFT opt ≈ 另 $100-200
- **总计**: $300-500 可完成一轮中等规模的分子设计→优化→验证

---

## 7. 附录: 接口速查表

### A. 技能调用接口

| 技能 | 入口 | 调用方式 |
|------|------|----------|
| reactnavi | `call_retrosynthesis(smiles, output_dir, ...)` | 本地阻塞 (HTTP→TOS) |
| reactnet | `Reaction(reaction).locate_ts()` | 本地 (xTB subprocess) |
| reactnet (批) | `mira_inference_upload_file("reactnet-19d712", ...)` | Mira 云端 |
| reactnet (网) | `mira_inference_call("reactnet-19d712", "run_network", ...)` | Mira 云端 |
| dp-yamo | `yamol(smiles).opt()` / `.conf_sample()` / `.evaluate()` | 本地 (xtb subprocess) |
| dp-yamo (DFT) | `VOLCQC(...).load_molecules(...).execute(...)` | Mira 云端 (volcqc) |
| dp-yamo (构象) | `compute_submit(compute_type="crest_sampling", ...)` | Mira 云端 |
| MPA | `mira_inference_call("mpa-613bf0", "/api/v1/predict", ...)` | Mira GPU |
| diffdock | `subprocess(["bash","-c","source activate diffdock && python /opt/DiffDock/inference.py ..."])` | 本地 conda |
| chem-properties | `python scripts/query_chemicals.py <name>` | 本地脚本 |
| pymatgen | `Structure.from_file()`, `SpacegroupAnalyzer()`, MP API | 本地 + HTTP |
| lammps | `lmp -sf omp -in script.in` | 本地 subprocess |
| multiwfn | `python scripts/run_esp_local.py` / `run_homo_lumo_local.sh` | 本地 subprocess |
| VMD render | `mira_inference_upload_file("vmd-runner-5f2a38", ...)` | Mira GPU |
| battery-sim | `pybamm.Simulation(model, param).solve()` | 本地 |
| chem-process | `thermo/chemicals/chempy` 函数调用 | 本地 |
| fluidsim | `Simul(params).time_stepping.start()` | 本地 |

### B. 分子表示格式

| 格式 | 技能 | 用途 |
|------|------|------|
| SMILES | yamol, rdkit, MPA, reactnavi | 通用分子表示 |
| XYZ | yamol, reactnet, dp-yamo | 3D 几何 (Å) |
| PDB | pymatgen, diffdock, lammps, packmol | 蛋白/晶体结构 |
| SDF | diffdock, rdkit | 配体+位姿 |
| CIF | pymatgen | 晶体学 |
| Molden | multiwfn | 波函数分析 |
| FCHK | multiwfn (Gaussian 格式) | 轨道可视化 |
| Morgan FP (2048-bit) | sklearn GPR, torch NN | 代理模型输入 |
| RDKit Descriptors (217) | sklearn GPR, torch NN | 代理模型特征工程 |
| InChI/InChIKey | yamol, chem-properties | 唯一分子标识 |

### C. 能垒定义速查

| 来源 | 字段 | 含义 |
|------|------|------|
| `Reaction.locate_ts()` | `DE_F` / `DE_B` | xTB 前向/后向能垒 (kcal/mol) |
| `IRC-record-processed.txt` | `barrier` | xTB 批量 TS 搜索能垒 (kcal/mol) |
| `NetGen_record.txt` | `IRC_DE_F` | IRC 端点参考能垒 (kcal/mol) |
| `NetGen_record.txt` | `DE_F` | 独立优化反应物参考能垒 (kcal/mol) |
| `NetGen_record.txt` | `DE_source` | `IRC` 或 `R_OPT` — 网络采用的参考 |
| `reaction_data.csv` | `barrier` | ReactomeForge 方向归一化完整 IRC 能垒 |
| `reaction_data.csv` | `barrier_original` | ReactNet pool 原始值 |
| `yarp_results-processed.txt` | `IRC_DE_F` / `IRC_DE_B` | DFT 精修后能垒 (kcal/mol) |
| `yarp_results-processed.txt` | `ref_barrier` | 最低能量构象参考能垒 |
