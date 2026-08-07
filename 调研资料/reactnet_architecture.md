# ReactNet 系统架构文档

> 版本: `reactnet` v0.1.10 (Python 包) + `reactnet` Skill (SKILL.md)
> 生成日期: 2026-08-01

---

## 目录

1. [系统总览](#1-系统总览)
2. [文件架构](#2-文件架构)
3. [模块详解](#3-模块详解)
   - [3.1 reactnet (顶层)](#31-reactnet-顶层)
   - [3.2 reactnet.core — 核心分子与反应类](#32-reactnetcore--核心分子与反应类)
   - [3.3 reactnet.config — 全局配置](#33-reactnetconfig--全局配置)
   - [3.4 reactnet.netgen — 网络生成引擎](#34-reactnetnetgen--网络生成引擎)
   - [3.5 reactnet.reaction_tools — 反应分析工具](#35-reactnetreaction_tools--反应分析工具)
   - [3.6 reactnet.workflows — 计算工作流引擎](#36-reactnetworkflows--计算工作流引擎)
   - [3.7 reactnet.tools — 命令行工具入口](#37-reactnettools--命令行工具入口)
   - [3.8 reactnet.auth / io / log — 支撑模块](#38-reactnetauth--io--log--支撑模块)
4. [Skill 层架构 (SKILL.md + references)](#4-skill-层架构-skillmd--references)
5. [完整调用关系图](#5-完整调用关系图)
6. [Mira 云端 API 架构](#6-mira-云端-api-架构)
7. [数据流](#7-数据流)
8. [关键算法管线](#8-关键算法管线)

---

## 1. 系统总览

ReactNet 是一个**化学反应网络自动发现与过渡态搜索平台**，由两层组成：

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | `SKILL.md` + 5 个 reference `.md` + 1 个脚本 + 1 个 YAML 模板 | 用户交互路由、工作流编排、Mira 云端任务管理 |
| **Python 包层** | `reactnet` (v0.1.10, 90+ 文件, 多数为 Cython 编译) | 核心计算引擎、分子表示、反应枚举、过渡态搜索、网络生成、DFT 精修 |

**运行环境**:
- **本地**: `predict_ts()`, `Reaction.locate_ts()`, `EnumerateReactions`, DFT 精修 (`yarp_qc`)
- **Mira 云端** (slug: `reactnet-19d712`): `run_network` (反应网络), `run_ts_search` (批量 TS 搜索), ReactomeForge (图谱生成)

**计算级别**:
- **xTB / g-xTB**: 所有本地和云端 TS 搜索、网络生成的默认级别
- **DFT (PySCF/GPU4PySCF)**: 仅本地，通过 `VOLCQC` (单反应) 或 `yarp_qc` (批量/网络) 从 xTB 收敛 TS 出发精修

---

## 2. 文件架构

### 2.1 Skill 目录 (`/app/skills/reactnet/`)

```
reactnet/
├── SKILL.md                          # 主入口: 路由逻辑、预飞问题、快速决策指南
├── scripts/
│   └── summarize_graph_reactions.py  # CSV→Markdown 图谱反应清单格式化器 (242 行)
└── references/
    ├── API.md                         # 本地 API 文档 (406 行)
    ├── MIRA_API.md                    # Mira REST 端点文档 (398 行)
    ├── NETWORK.md                     # 反应网络生成规则 (326 行)
    ├── WORKFLOWS.md                   # 批量 TS 搜索工作流 (284 行)
    └── ts_search_config.yaml          # 完整 YAML 配置模板 (263 行)
```

### 2.2 Python 包目录 (`/root/miniconda3/lib/python3.11/site-packages/reactnet/`)

```
reactnet/
├── __init__.py                        # 顶层: 导出 + API key 检查 + 便利导入
├── config.py                          # 全局配置类 _ConfigClass (570+ 行)
├── auth.py                            # 许可证/API key 管理
├── io.py                              # hash/name 互转工具
├── log.py                             # 日志 + Messenger (邮件/飞书通知)
│
├── core/                              # ⭐ 核心分子与反应类
│   ├── __init__.py                    # 导出: Reaction, Species, Complex, Molecule
│   ├── core_utils.cpython-311.so      # [Cython] 核心工具
│   ├── reaction.cpython-311.so        # [Cython] Reaction 类 (locate_ts, run_gsm, get_ts_guess)
│   └── species.cpython-311.so         # [Cython] Complex/Species 类 (optimize, conf_sample, single_point)
│
├── netgen/                            # ⭐ 网络生成引擎
│   ├── __init__.py                    # 导出: CoreEdgeReactionModel
│   ├── calculator/
│   │   ├── __init__.py
│   │   ├── dft_cal.cpython-311.so     # [Cython] 能垒计算器
│   │   └── get_params.cpython-311.so  # [Cython] 参数获取
│   ├── producer/                      # ⭐ 反应枚举器
│   │   ├── __init__.py                # 导出: RunReactions, EnumerateReactions, get_reactants
│   │   ├── gen_prods.cpython-311.so   # [Cython] Enumeration & RunReactions 类
│   │   ├── enumeration.cpython-311.so # [Cython] 核心枚举算法
│   │   ├── atom_mapping.cpython-311.so
│   │   ├── check_rxns.cpython-311.so
│   │   ├── post_processing.cpython-311.so
│   │   ├── simple_metal.cpython-311.so
│   │   └── test_atom_mapping.cpython-311.so
│   ├── crn.cpython-311.so             # [Cython] CoreEdgeReactionModel 网络模型
│   ├── data.cpython-311.so            # [Cython] 数据结构
│   ├── dijkstra.cpython-311.so        # [Cython] 最短路径算法
│   └── growth_rules.cpython-311.so    # [Cython] 网络增长规则
│
├── reaction_tools/                    # ⭐ 反应分析工具箱
│   ├── __init__.py
│   ├── rcs.cpython-311.so             # [Cython] RCS (Reaction Conformer Sampling)
│   ├── rcs_v2.cpython-311.so          # [Cython] RCS v2 (推荐)
│   ├── D2.cpython-311.so              # [Cython] 双端对接/反应路径
│   ├── gen_graph.cpython-311.so       # [Cython] 图谱生成
│   ├── reaction_analysis.cpython-311.so # [Cython] IRC 验证与分析
│   ├── volcqc.cpython-311.so          # [Cython] Volcengine QC 客户端封装
│   └── shuttle/
│       ├── __init__.py
│       ├── proton_shuttle.cpython-311.so
│       └── test_workflow.cpython-311.so
│
├── workflows/                         # ⭐ 计算工作流引擎
│   ├── __init__.py                    # 导出: qc_jobs, main_functions, sieve
│   ├── yarp_ts_search.py              # CLI 入口: python -m reactnet.workflows.yarp_ts_search
│   ├── yarp_qc.py                     # CLI 入口: python -m reactnet.workflows.yarp_qc
│   ├── yarp_xtb.py                    # CLI 入口: xTB 批量搜索
│   ├── yarp_xtb_ray.py                # CLI 入口: Ray 并行版
│   ├── _yarp_ts_search.cpython-311.so # [Cython] 批量 TS 搜索主逻辑 (~1MB)
│   ├── _yarp_qc.cpython-311.so        # [Cython] DFT 精修主逻辑
│   ├── _yarp_xtb.cpython-311.so       # [Cython] xTB 批量搜索主逻辑 (~1MB)
│   ├── _yarp_xtb_ray.cpython-311.so   # [Cython] Ray 并行 xTB 搜索
│   ├── main_functions.cpython-311.so  # [Cython] analyze_outputs, postprocess_reactions 等
│   ├── mol_opt.cpython-311.so         # [Cython] 分子优化 (RP_optimize, TS_prediction)
│   ├── qc_jobs.cpython-311.so         # [Cython] QcBatchJob DFT 批量作业
│   ├── qc_jobs_ray.cpython-311.so     # [Cython] Ray 并行版
│   ├── sieve.cpython-311.so           # [Cython] 分子筛分过滤
│   ├── utils.cpython-311.so           # [Cython] 工具函数 (xyz_write, xyz_parse 等)
│   └── ray_logger.cpython-311.so      # [Cython] Ray 日志
│
├── tools/                             # 命令行工具
│   ├── __init__.py
│   ├── reactot.cpython-311.so         # [Cython] predict_ts (React-OT API 客户端)
│   ├── run_network.cpython-311.so     # [Cython] run_network CLI 驱动
│   └── cleanup_layer_scratch.cpython-311.so
│
├── kinetics/                          # 动力学模块
│   ├── __init__.py
│   ├── kincal.cpython-311.so          # [Cython] 动力学常数计算
│   ├── fit_to_arrhenius.cpython-311.so
│   └── tunneling.cpython-311.so       # [Cython] 隧道效应校正
│
├── thermochem/                        # 热化学模块
│   ├── __init__.py
│   ├── thermo.cpython-311.so
│   ├── symm.cpython-311.so
│   └── utils.cpython-311.so
│
├── solver/                            # 求解器模块
│   ├── __init__.py
│   ├── model.cpython-311.so
│   ├── parser.cpython-311.so
│   └── integrator.cpython-311.so
│
└── cli/                               # (非顶层导出) CLI 配置
    ├── __init__.py
    ├── config.py
    └── cleanup.py
```

---

## 3. 模块详解

### 3.1 reactnet (顶层)

**文件**: `__init__.py`

**导出符号**:

| 符号 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `Reaction` | class | `core.reaction` | 化学反应类，核心 TS 搜索 |
| `Species` | class | `core.species` | 原子物种（分子/离子/自由基） |
| `Complex` | class | `core.species` | 分子复合物（多分子体系） |
| `Molecule` | class | `core.species` | 单分子 |
| `CoreEdgeReactionModel` | class | `netgen.crn` | 核心-边缘反应网络模型 |
| `Config` | singleton | `config` | 全局配置管理器 |
| `Messenger` | class | `log` | 邮件/飞书通知 |
| `set_api_key()` | function | `auth` | API key 设置 |
| `get_license_info()` | function | `auth` | 许可证信息 |
| `check_api_key()` | function | `auth` | API key 验证 |

**导入链**:
```
reactnet.__init__
  ├── auth (最早，API key 检查)
  ├── netgen, reaction_tools, workflows, core (模块导入)
  ├── core → Reaction, Species, Complex, Molecule
  ├── netgen → CoreEdgeReactionModel
  ├── config → Config
  └── log → Messenger
```

---

### 3.2 reactnet.core — 核心分子与反应类

#### 3.2.1 `Reaction` 类

**源文件**: `core/reaction.cpython-311.so` [Cython]

**构造函数**:
```python
Reaction(
    reaction: Optional[str] = None,        # 反应 SMILES ("R>>P") 或 XYZ 文件路径
    reactants: Optional[Complex] = None,    # 反应物 Complex 对象
    products: Optional[Complex] = None,     # 产物 Complex 对象
    name: str = "reaction",                 # 反应名称 (也用做工作目录)
    charge: Optional[int] = None,           # 体系电荷
    multiplicity: Optional[int] = None,     # 自旋多重度
    fixed_atoms: Optional[List[int]] = None,# 固定原子索引 (1-indexed)
    cluster_atoms: Optional[List[int]] = None,
    rcs_method: Literal['rcs', 'rcs_v2'] = 'rcs_v2',
    work_folder: Optional[str] = None,
)
```

**公开方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `locate_ts(do_sampling: bool = True) → Dict` | GSM → TSOPT → IRC 全流程，xTB 级别，~10-30 min | 返回含 `TSs[]` 的结果字典，每个 TS: `DE_F`, `DE_B` (kcal/mol), `TS_SPE` (Hartree), `TSGeo`, `IRC_DE_F`, `IRC_DE_B` |
| `run_gsm() → ...` | 运行 Growing String Method 寻找初始 TS 猜测 |
| `get_ts_guess() → ...` | 获取 TS 初始猜测几何构型 |

**内部属性** (Cython):
- `reac_complex`: 反应物 Complex 对象 (含 geometry, elements)
- `prod_complex`: 产物 Complex 对象
- `smiles`: 反应 SMILES (无原子映射)
- `atom_mapped_smiles`: 原子映射 SMILES

#### 3.2.2 `Complex` 类

**源文件**: `core/species.cpython-311.so` [Cython]

**公开方法**:

| 方法 | 说明 |
|------|------|
| `conf_sample() → ...` | 构象采样 (CREST/Confab/Auto3D) |
| `optimize() → ...` | 几何优化 |
| `single_point() → float` | 单点能计算 |
| `save_mol() → ...` | 保存为 .mol 文件 |
| `save_xyz() → ...` | 保存为 XYZ 文件 |
| `get_fixed_atoms() → ...` | 获取固定原子列表 |

**属性**:

| 属性 | 类型 | 说明 |
|------|------|------|
| `length` | int (property) | 分子数 |
| `cluster_atom_idx` | list (property) | 团簇原子索引 |
| `mol_atom_idx` | list (property) | 分子原子索引 |
| `mol_elements` | list (property) | 各分子元素符号 |
| `undetermined_charge_idxs` | list (property) | 未确定电荷的原子索引 |

#### 3.2.3 `Species` / `Molecule` 类

`Species`: 原子物种的基类表示。
`Molecule`: 单分子，继承自 Species。

---

### 3.3 reactnet.config — 全局配置

**源文件**: `config.py` (570+ 行)

核心是 `_ConfigClass` 单例 (`Config`)，使用 `_ConfigBase` 提供类型安全的属性访问和拼写错误提示。

#### 顶层配置项

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `nprocs` | int | 8 | 总 CPU 核数 |
| `mem` | int | 1 | 每核内存 (GB) |
| `scratch` | str | `'output'` | 输出工作目录 |
| `inp_path` | str | None | 输入 XYZ 文件夹 |
| `cons_path` | str | None | 约束文件夹 |
| `fixed_path` | str | None | 固定原子文件夹 |
| `charge` | int | 0 | 体系电荷 |
| `multiplicity` | int | 1 | 自旋多重度 |
| `lf_engine` | str | `'xtb'` | 低精度计算引擎: `gxtb`, `xtb`, `pyscf`, `mace`, `uma`, `orb` |
| `hf_engine` | str | `'pyscf'` | 高精度引擎: `pyscf`, `orca` |
| `conf_engine` | str | `'crest'` | 构象采样引擎: `crest`, `confab` |
| `python_exe` | str | `'python'` | Python 可执行文件路径 |
| `dft_restart` | bool | True | DFT 任务重启 |
| `dft_wt` | int | 14400 | DFT walltime (秒) |
| `irc_wt` | int | 14400 | IRC walltime (秒) |
| `tsopt_wt` | int | 14400 | TSOPT walltime (秒) |

#### 子配置块

| 配置块 | 说明 | 关键属性 |
|--------|------|----------|
| `Config.XTB` | xTB 计算器设置 | `lot='gxtb'`, `nprocs=4`, `solvent`, `solvation_model`, `accuracy`, `electronic_temp` |
| `Config.PYGSM` | GSM 算法设置 | `num_nodes=11`, `max_gsm_iters=50`, `conv_tol=0.005`, `dmax=0.1`, `method='xtb'` |
| `Config.PYSIS` | Pysisyphus 设置 | `.TSOPT`: `thresh='gau'`, `hessian_recalc=3`, `max_cycles=30`; `.IRC`: `step_length=0.1` (Bohr), `max_cycles=500` |
| `Config.CREST` | CREST 构象采样 | `nprocs=2`, `maxconf=1000`, `ecutoff=15.0` (kcal/mol), `rcutoff=0.1` (Å) |
| `Config.Confab` | Confab 构象采样 | 同 CREST 参数结构 |
| `Config.AUTO3D` | Auto3D 构象采样 | 3D 自动构象生成 |
| `Config.PYSCF` | PySCF DFT 设置 | `functional='wb97x'`, `basis='6-31g'`, `use_gpu=False`, `grid_level=5` |
| `Config.RCS` | RCS 设置 | 反应构象采样参数 |
| `Config.SSM` | SSM 设置 | 单端搜索方法参数 |
| `Config.MLIP` | MLIP 设置 | 机器学习势函数参数 |
| `Config.TSSWF` | 过渡态搜索工作流设置 | |
| `Config.ORCA` | ORCA 设置 | ORCA 量子化学软件参数 |
| `Config.PROTON_SHUTTLE` | 质子穿梭设置 | |
| `Config.MESSAGE` | 消息通知设置 | 邮件/飞书配置 |

**辅助函数**:
- `capture_config_state()` / `restore_config_state(config_state)`: 配置状态序列化/恢复
- `resolve_xtb_calctype(engine)`: xTB 计算类型解析
- `parallel_wrapper(func, args, config_state)`: 并行包装器

---

### 3.4 reactnet.netgen — 网络生成引擎

#### 3.4.1 `producer` 子包 — 反应枚举

**文件**: `netgen/producer/__init__.py`

**导出**:
| 符号 | 说明 |
|------|------|
| `EnumerateReactions` | 反应枚举器类 |
| `RunReactions` | 反应运行器类 |
| `get_reactants` | 获取反应物 |

##### `EnumerateReactions` 类

**源文件**: `netgen/producer/gen_prods.cpython-311.so`

**构造函数**:
```python
EnumerateReactions(
    max_break_bonds: int = 1,          # 最大断键数
    max_form_bonds: int = 1,           # 最大成键数
    lewis_score_paticence: float = 0.1,# Lewis 评分容忍度
    threshold: float = 20,             # 成键评分截断
    logger: Logger = None,
    n_workers: int = 1,               # 并行工作线程
)
```

**公开方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `run(reactant: str) → Tuple[str, Optional[List[Tuple[str, float]]]]` | 输入反应物 SMILES (≤2 分子)，返回 `(映射反应物, [(产物SMILES, rxn_hash)])` |

**内部模块**:
- `enumeration.cpython-311.so`: 核心图论枚举算法
- `atom_mapping.cpython-311.so`: 原子映射处理
- `check_rxns.cpython-311.so`: 反应合法性检查
- `post_processing.cpython-311.so`: 枚举后处理
- `simple_metal.cpython-311.so`: 碱金属/碱土金属的配位键重附着

#### 3.4.2 `calculator` 子包 — 能垒计算

- `dft_cal.cpython-311.so`: 能垒计算器（含 `DE_source` 逻辑）
- `get_params.cpython-311.so`: 计算参数获取

#### 3.4.3 `CoreEdgeReactionModel` 类

**源文件**: `netgen/crn.cpython-311.so`

核心-边缘反应网络模型，用于组织网络拓扑结构为 `in_core`（推进的活性物种）和边缘物种。

#### 3.4.4 其他子模块

| 模块 | 功能 |
|------|------|
| `data.cpython-311.so` | 网络数据结构 |
| `dijkstra.cpython-311.so` | 图最短路径算法 |
| `growth_rules.cpython-311.so` | 网络增长规则 |

---

### 3.5 reactnet.reaction_tools — 反应分析工具

| 模块 | 功能 |
|------|------|
| `rcs.cpython-311.so` | RCS v1: 反应构象采样 |
| `rcs_v2.cpython-311.so` | RCS v2 (推荐): 改进的构象采样，支持力场驱动 |
| `D2.cpython-311.so` | 双端对接/反应路径搜索 |
| `gen_graph.cpython-311.so` | 图谱生成工具 |
| `reaction_analysis.cpython-311.so` | IRC 路径分析、反应类型分类 |
| `volcqc.cpython-311.so` | Volcengine QC 客户端封装 |
| `shuttle/proton_shuttle.cpython-311.so` | 质子穿梭机制 |

---

### 3.6 reactnet.workflows — 计算工作流引擎

这是 ReactNet 最核心的计算编排层。

#### 3.6.1 CLI 入口 (纯 Python wrapper)

| 文件 | 对应命令行 | 功能 |
|------|-----------|------|
| `yarp_ts_search.py` | `python -m reactnet.workflows.yarp_ts_search <config.yaml>` | xTB 批量 TS 搜索 |
| `yarp_qc.py` | `python -m reactnet.workflows.yarp_qc <config.yaml>` | DFT 精修 |
| `yarp_xtb.py` | `python -m reactnet.workflows.yarp_xtb <config.yaml>` | xTB 搜索 |
| `yarp_xtb_ray.py` | `python -m reactnet.workflows.yarp_xtb_ray <config.yaml>` | Ray 并行 xTB |

所有 CLI wrapper 都遵循相同模式:
```python
from reactnet.workflows._yarp_xxx import main
if __name__ == "__main__":
    parameters = yaml.load(open(sys.argv[1]))
    main(parameters)
```

#### 3.6.2 核心工作流函数 (全部 Cython 编译)

| 函数 | 所属模块 | 说明 |
|------|----------|------|
| **`main_functions` 模块** | | |
| `analyze_outputs()` | main_functions | 分析 TS 搜索输出，生成总结 |
| `postprocess_reactions()` | main_functions | 后处理反应结果 |
| `compute_ref_barriers()` | main_functions | 计算参考能垒 (最低能量构象) |
| `analyze_DFT_IRC()` | main_functions | 分析 DFT IRC 结果 |
| `check_dup_ts_irc()` | main_functions | IRC 层面重复 TS 检查 |
| `check_dup_ts_pysis()` | main_functions | Pysisyphus 层面重复 TS 检查 |
| **`mol_opt` 模块** | | |
| `RP_optimize()` | mol_opt | 反应物/产物几何优化 |
| `TS_prediction()` | mol_opt | TS 结构预测 |
| `run_gsm()` | mol_opt | GSM 字符串方法执行 |
| `run_pygsm()` | mol_opt | pyGSM 引擎 |
| `run_pysis()` | mol_opt | Pysisyphus 引擎 |
| `run_xtb()` | mol_opt | xTB 单点/优化 |
| `run_gauxtb()` | mol_opt | g-xTB 单点/优化 |
| `run_dft()` | mol_opt | DFT 单点/优化 |
| **构象采样** | | |
| `run_crest()` | mol_opt | CREST 构象搜索 |
| `run_confab()` | mol_opt | Confab 构象搜索 |
| `run_auto3d()` | mol_opt | Auto3D 构象搜索 |
| `run_ssm()` | mol_opt | SSM 单端搜索 |
| **`sieve` 模块** | | 分子过滤/筛分 |
| `sieve_bmat_scores()` | sieve | 键矩阵评分过滤 |
| `sieve_fc()` | sieve | 形式电荷过滤 |
| `sieve_fused_rings()` | sieve | 稠环过滤 |
| `sieve_rings()` | sieve | 环状结构过滤 |
| `sieve_valency_violations()` | sieve | 化合价违规过滤 |
| **`qc_jobs` 模块** | | DFT 批量作业管理 |
| `QcBatchJob` (class) | qc_jobs | Volcengine QC 批量作业客户端 |
| **工具函数** | | |
| `xyz_write()` | utils | XYZ 文件写入 |
| `xyz_parse()` | utils | XYZ 文件解析 |
| `mol_hash()` | utils | 分子 hash |
| `return_e()` | utils | 能量提取 |
| `return_smi()` | utils | SMILES 提取 |
| `return_atommaped_smi()` | utils | 原子映射 SMILES |
| `seperate_mols()` | utils | 分子分离 |
| `drop_map_num()` | utils | 去除映射编号 |

#### 3.6.3 常数与元数据

| 符号 | 说明 |
|------|------|
| `el_mass` (dict) | 元素质量表 |
| `el_metals` (set) | 金属元素集合 |
| `el_expand_octet` (dict) | 扩展八隅体元素 |
| `el_n_deficient` (dict) | 缺氮元素 |
| `valid_smiles_tokens` (set) | 合法 SMILES token |
| `topo_smiles_tokens` (set) | 拓扑 SMILES token |

#### 3.6.4 SMARTS 模式匹配

| 函数 | 说明 |
|------|------|
| `smarts_match()` | SMARTS 模式匹配 |
| `smarts_to_paths()` | SMARTS → 路径 |
| `smarts_to_tokens()` | SMARTS → token |
| `tokens_to_adjlist()` | token → 邻接表 |

#### 3.6.5 路径比较

| 函数 | 说明 |
|------|------|
| `compare_paths_bos()` | 键序比较 |
| `compare_paths_els()` | 元素比较 |
| `compare_paths_inds()` | 索引比较 |
| `compare_paths_via_bools()` | 布尔比较 |
| `graph_seps()` | 图分离 |
| `pattern_to_path()` | 模式 → 路径 |

#### 3.6.6 特殊官能团检测

| 函数 | 说明 |
|------|------|
| `is_cyano()` | 氰基检测 |
| `is_isocyano()` | 异氰基检测 |
| `is_nitro()` | 硝基检测 |
| `is_sulfonyl()` | 磺酰基检测 |
| `is_sulfoxide()` | 亚砜检测 |
| `is_phosphate()` | 磷酸酯检测 |
| `is_frag_ethenone()` | 乙烯酮片段检测 |
| `is_frag_sulfonyl()` | 磺酰片段检测 |
| `is_frag_sulfoxide()` | 亚砜片段检测 |
| `is_valency_violation()` | 化合价违规检测 |
| `has_any_metal()` | 金属原子检测 |

---

### 3.7 reactnet.tools — 命令行工具入口

| 子模块 | 说明 |
|--------|------|
| `reactot.cpython-311.so` | **`predict_ts()`** 函数: React-OT API 客户端，发送反应 SMILES 获取 TS 几何构型 |
| `run_network.cpython-311.so` | **`python -m reactnet.tools.run_network`**: 反应网络生成 CLI |
| `cleanup_layer_scratch.cpython-311.so` | 层工作目录清理 |

#### `predict_ts()` 函数 (reactot 子模块)
```python
predict_ts(rxn_smiles: str, work_folder: str) → Dict[str, Any]
```
- 调用 React-OT 远程 API (`/react-ot-str` 端点)
- 约束: ≤30 atoms/side, C/H/O/N only
- 返回: `{success, task_id, output_files, output_file_contents, error}`

---

### 3.8 reactnet.auth / io / log — 支撑模块

#### 3.8.1 `auth` 模块

| 函数 | 说明 |
|------|------|
| `set_api_key(api_key, save=False, verbose=True)` | 设置 API key |
| `check_api_key()` | 验证 API key 是否有效 |
| `get_license_info()` | 获取许可证信息 |
| `require_api_key()` | 强制要求 API key |
| `save_api_key(api_key)` | 持久化保存 API key |
| `load_saved_key()` | 加载已保存的 API key |
| `validate_key_format(api_key)` | 验证 key 格式 |

#### 3.8.2 `io` 模块

| 函数 | 说明 |
|------|------|
| `hash_to_name(hash_id: float, power: int) → str` | Hash → 文件名 |
| `name_to_hash(name: str, power: int) → float` | 文件名 → Hash |

#### 3.8.3 `log` 模块

| 类/函数 | 说明 |
|----------|------|
| `Messenger(mode='email'|'feishu')` | 消息通知: `.send(message, head)` |
| `get_logger(logging_path, slevel, flevel)` | 创建文件+控制台双通道 logger |
| `log_list_dynamic(logger, lst, line_width)` | 动态列宽列表日志 |

---

## 4. Skill 层架构 (SKILL.md + references)

### 4.1 入口路由 (SKILL.md)

用户意图 → 路由映射:

| 用户意图 | 路由 | 典型时间 |
|----------|------|----------|
| 单个已知反应 | **Step 1** → `predict_ts()` 或 `Reaction.locate_ts()` | 1-30 min |
| 发现可能的反应 | **Step 0** → 枚举 或 LLM 提议 → **Step B** | 0.5-several hrs |
| 多个已知反应 | **Step B** → Mira `run_ts_search` | 0.5-several hrs |
| 反应网络 | **Step N** → Mira `run_network` (≤3 layers) | hrs per layer |
| 已有网络的图谱 | **Step V** → 下载 `/graph` + `reaction_data.csv` | seconds |
| xTB → DFT 精修 | **Step R** → 本地 `yarp_qc` | 10 min-1 hr per rxn |

### 4.2 参考文档职责

| 文件 | 职责 |
|------|------|
| `SKILL.md` | 主路由、预飞问题、快速决策表、单位规范、DFT 精修路径 |
| `API.md` | `predict_ts()`, `Reaction`, `EnumerateReactions`, `Complex`, `Config` 的完整 API |
| `MIRA_API.md` | Mira REST 端点、作业生命周期、轮询策略、工具映射、错误处理 |
| `NETWORK.md` | 反应网络规则、参数选择、输出解读、屏障语义、图谱规则、检查清单 |
| `WORKFLOWS.md` | 批量 TS 搜索、XYZ 构建、DFT 精修步骤、检查清单 |
| `ts_search_config.yaml` | 完整 YAML 配置模板 (263 行) |

### 4.3 脚本

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `scripts/summarize_graph_reactions.py` | 验证并渲染图谱反应清单 | `reaction_data.csv` | Markdown 表格 + 统计摘要 |

**验证规则** (7 个必需列):
1. `reaction_hash_id` (非空、唯一)
2. `reactant_smiles` (非空)
3. `product_smiles` (非空)
4. `barrier` (数值)
5. `barrier_original` (数值)
6. `selection_round` (整数或空)
7. `is_closure_reaction` (true/false)

---

## 5. 完整调用关系图

### 5.1 本地 TS 搜索管线

```
用户提供 SMILES
    │
    ▼
Reaction(reaction="R>>P")
    │
    ▼
Reaction.locate_ts(do_sampling=True)
    │
    ├─→ [可选] Complex.conf_sample()        # CREST/Confab/Auto3D 构象采样
    │       └─ run_crest() / run_confab() / run_auto3d()
    │
    ├─→ [1] rcs_v2()                          # Reaction Conformer Sampling v2
    │       └─ reaction_tools.rcs_v2
    │
    ├─→ [2] Reaction.run_gsm()               # Growing String Method
    │       ├─ pyGSM 引擎 (Config.PYGSM.gsm_engine='pygsm')
    │       │   └─ run_pygsm() → Config.PYGSM 参数
    │       └─ pysis_gsm 引擎
    │           └─ run_pysis() → Config.PYSIS 参数
    │       └─ 计算器: run_xtb() / run_gauxtb() (xTB/g-xTB)
    │
    ├─→ [3] TSOPT (pysisyphus)               # TS 优化
    │       └─ run_pysis() → Config.PYSIS.TSOPT 参数
    │       └─ 计算器: run_xtb()
    │
    ├─→ [4] IRC (pysisyphus)                 # IRC 验证
    │       └─ run_pysis() → Config.PYSIS.IRC 参数
    │       └─ 计算器: run_xtb()
    │
    └─→ [5] 后处理分析
            └─ reaction_analysis → reaction_tools.reaction_analysis
            └─ classify reaction type (Intended/R_Unintended/P_Unintended/Unintended)

返回: {TSs: [{DE_F, DE_B, TS_SPE, TSGeo, IRC_DE_F, IRC_DE_B, ...}]}
```

### 5.2 反应枚举管线

```
EnumerateReactions(max_break_bonds=N, max_form_bonds=M, n_workers=W)
    │
    ▼
EnumerateReactions.run(reactant="SMILES")
    │
    ├─→ 分子图构建 (RDKit/yamol)
    │
    ├─→ 键断裂组合生成
    │       └─ enumeration.cpython-311.so (核心图论算法)
    │
    ├─→ 键形成组合生成
    │       └─ enumeration.cpython-311.so
    │
    ├─→ Lewis 结构评分
    │       └─ post_processing.cpython-311.so
    │
    ├─→ [金属体系] 配位键重附着
    │       └─ simple_metal.cpython-311.so
    │
    ├─→ 产物验证
    │       ├─ check_rxns.cpython-311.so
    │       ├─ sieve (化合价/环/稠环过滤)
    │       └─ atom_mapping.cpython-311.so
    │
    └─→ 返回: (mapped_reactant, [(product_smiles, rxn_hash), ...])
```

### 5.3 批量 TS 搜索管线 (Mira 云端)

```
mira_inference_upload_file(path="/api/v1/jobs/run_ts_search")
    │
    ▼
服务端: python -m reactnet.tools.run_ts_search
    │
    ├─→ 输入解析
    │   ├─ Mode 1: reactions=["R>>P"]  → Reaction class → XYZ 构建
    │   └─ Mode 2: xyz_zip            → 直接使用用户几何
    │
    └─→ 对每个反应并行执行:
        │
        ├─→ RCS (rcs_v2)
        ├─→ GSM (pyGSM/pysis_gsm)
        ├─→ TSOPT (pysisyphus)
        ├─→ IRC (pysisyphus)
        │   └─ 全部以 xTB/g-xTB 作为计算器
        │
        └─→ 后处理
            ├─ analyze_outputs()
            ├─ postprocess_reactions()
            ├─ compute_ref_barriers()
            └─ check_dup_ts_irc() / check_dup_ts_pysis()

输出:
    ├── cli.log                        # BATCH TS SEARCH SUMMARY
    └── runs/<name>/
        ├── IRC-record-processed.txt   # barrier, TS_SPE, type, ref_barrier
        ├── IRC-record.txt             # 原始 IRC
        ├── IRC-RPOPT-record.txt       # (如有 R_opt)
        ├── final_TSs.p                # 收敛 TS pickle
        └── ts_search.resolved.yaml
```

### 5.4 反应网络生成管线 (Mira 云端)

```
POST /api/v1/jobs/run_network
{reactants: ["SMILES"], layers: L, max_break_bonds: B, max_form_bonds: F, ...}
    │
    ▼
服务端: python -m reactnet.tools.run_network
    │
    └─→ for layer in 1..L:
        │
        ├─→ [枚举] EnumerateReactions (max_break_bonds, max_form_bonds)
        │       └─ producer.gen_prods
        │
        ├─→ [筛选] sieve (valence/ring/fused_ring 过滤)
        │       └─ sieve.cpython-311.so
        │
        ├─→ [TS搜索] 对每个候选反应:
        │       └─ RCS → GSM → TSOPT → IRC (xTB/g-xTB)
        │           └─ _yarp_ts_search 引擎
        │
        ├─→ [能垒计算] calculator.dft_cal
        │       ├─ IRC_DE_F (IRC endpoint reference)
        │       ├─ DE_F (R_OPT reference)
        │       └─ DE_source 决策: R_OPT if DE_F > IRC_DE_F else IRC
        │
        ├─→ [排序] barrier < barrier_threshold → 推进 top max_species_per_layer
        │       └─ CoreEdgeReactionModel
        │
        └─→ 保存 checkpoint:
                ├── layer_<N>/NetGen_record.txt
                ├── layer_<N>_checkpoint/species_pool.json
                ├── layer_<N>_checkpoint/reaction_pool.json
                └── layer_<N>_checkpoint/model_state.json

    └─→ [图谱] ReactomeForge (自动触发):
        │
        ├─→ 读取 checkpoint pools + per-reaction trajectories
        ├─→ 方向归一化完整 IRC
        │       └─ barrier = [max(E_full_irc) - E_reactant_endpoint] × 627.509
        ├─→ 应用 max_barrier 截断 (default 120.0 kcal/mol)
        ├─→ 生成 reaction_network.html (Cytoscape.js)
        └─→ 生成 reaction_data.csv
```

### 5.5 DFT 精修管线 (本地)

```
Step R: 从 xTB 完成作业下载 final_TSs.p
    │
    ▼
python -m reactnet.workflows.yarp_qc <config.yaml>
    │
    └─→ _yarp_qc.main(params)
        │
        ├─→ 读取 scratch/final_TSs.p
        ├─→ 选择反应子集 (keep_for_refine: Intended*/P_Unintended*/_CoordChange)
        ├─→ 对每个选定反应:
        │       ├─→ QcBatchJob (volcqc 客户端)
        │       │       └─ 提交到 Volcengine QC 云平台
        │       ├─→ DFT TSOPT
        │       └─→ DFT IRC
        │
        └─→ 输出: <scratch>/DFT/yarp_results-processed.txt
                ├── IRC_DE_F (kcal/mol)
                ├── IRC_DE_B (kcal/mol)
                ├── type
                └── ref_barrier
```

---

## 6. Mira 云端 API 架构

### 6.1 服务信息

| 属性 | 值 |
|------|-----|
| Slug | `reactnet-19d712` (可能变更，用 `mira_inference_list_services` 确认) |
| 计算资源 | CPU-only |
| 并发数 | 1 (任务排队) |
| 结果保留 | ~7 天 |
| 认证 | 自动 JWT (平台签名) |

### 6.2 端点映射

| 方法 | 路径 | 用途 | Skill 工具 |
|------|------|------|------------|
| GET | `/health` | 健康检查 + 空闲槽位 | `mira_inference_call` GET |
| POST | `/api/v1/jobs/run_network` | 提交反应网络 (JSON) | `mira_inference_call` POST |
| POST | `/api/v1/jobs/run_ts_search` | 批量 TS 搜索 (multipart) | `mira_inference_upload_file` |
| GET | `/api/v1/jobs/{id}` | 作业状态 | `mira_inference_call` GET |
| GET | `/api/v1/jobs/{id}/log` | 最后 64 KiB stdout | `mira_inference_call` GET |
| GET | `/api/v1/jobs/{id}/files` | 递归文件列表 | `mira_inference_call` GET |
| GET | `/api/v1/jobs/{id}/files/{relpath}` | 下载单个文件 | `mira_inference_download_file` |
| GET | `/api/v1/jobs/{id}/graph` | 下载交互式图谱 HTML | `mira_inference_download_file` |
| GET | `/api/v1/jobs/{id}/result` | 下载完整结果 zip | `mira_inference_download_file` |
| DELETE | `/api/v1/jobs/{id}` | 取消作业 | `mira_inference_call` DELETE |

### 6.3 作业生命周期

```
QUEUED → RUNNING → ┬→ SUCCEEDED (exit_code=0)
                   ├→ FAILED    (exit_code≠0)
                   ├→ TIMEOUT   (exceeds timeout_sec)
                   └→ CANCELED  (DELETE)
                        ↓ (仅 run_network, 自动)
              graph_state: PENDING → RUNNING → READY / FAILED
```

### 6.4 `run_network` 请求参数

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `reactants` | list[str] | required | 起始物 SMILES 列表 |
| `resume_from` | str/null | null | 恢复 checkpoints 的绝对路径 |
| `layers` | int | 1 | 增长层数 (≤3) |
| `bimolecular` | bool | false | 允许双分子反应 |
| `barrier_threshold` | float | 70.0 | 能垒截断 (kcal/mol) |
| `max_species_per_layer` | int | 2 | 每层推进物种数 |
| `max_heavy_atoms` | int | 50 | 最大重原子数 |
| `max_break_bonds` | int | 1 | 每反应最大断键数 |
| `max_form_bonds` | int | 1 | 每反应最大成键数 |
| `lot` | str | `gfn2` | `gfn2` 或 `gxtb` |
| `solvent` | str/null | null | 隐式溶剂 |
| `solvation_model` | str | `alpb` | `alpb` 或 `gbsa` |
| `cat_smiles` | str/null | null | 催化剂 SMILES |
| `run_name` | str/null | 自动生成 | 结果子目录名 |
| `timeout_sec` | int | 21600 | 超时 (≤48h) |

### 6.5 `run_ts_search` 请求参数

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `reactions` | list[str] | — | `"R>>P"` SMILES 列表 (或上传 xyz_zip) |
| `n_cores` | int | all | 总并行 worker |
| `crest_nprocs` | int | n_cores//2 | CREST 并发数 |
| `calc` | str | `xtb` | `gxtb` 或 `xtb` |
| `nconf` | int/null | null | 最大构象数 |
| `charge` | int/null | null | 全局电荷 |
| `multiplicity` | int/null | null | 全局多重度 |
| `solvent` | str/null | null | 隐式溶剂 |
| `solvation_model` | str | `alpb` | 溶剂化模型 |
| `barrier_threshold` | float/null | null | 能垒截断 |
| `cat_smiles` | str/null | null | 催化剂 |
| `run_name` | str/null | null | 结果子目录名 |
| `timeout_sec` | int | 21600 | 超时 (≤48h) |

---

## 7. 数据流

### 7.1 分子表示流

```
SMILES (文本)
    │
    ├─→ yamol() → 3D 几何构型 (元素 + 坐标)
    │
    ├─→ Complex/Reaction → 原子映射 SMILES
    │
    ├─→ XYZ 文件 (帧: reactant→product)
    │
    └─→ pickle (final_TSs.p)
```

### 7.2 计算结果流

```
TS 搜索
    │
    ├── xTB: IRC-record-processed.txt
    │   └── barrier (kcal/mol), TS_SPE (Hartree), type
    │
    ├── 网络: NetGen_record.txt
    │   └── IRC_DE_F, DE_F, DE_source, IRC_type
    │
    ├── Checkpoint JSON
    │   └── species_pool, reaction_pool, model_state
    │
    └── DFT: DFT/yarp_results-processed.txt
        └── IRC_DE_F, IRC_DE_B, ref_barrier
```

### 7.3 屏障语义数据流

```
ReactNet xTB TS 搜索
    │
    ├─→ IRC_DE_F = TS_SPE - E_reactant,IRC-endpoint
    │               计算: workflows/main_functions
    │
    ├─→ DE_F = TS_SPE - E_reactant,R_OPT
    │          计算: netgen/calculator/dft_cal
    │
    ├─→ DE_source = R_OPT if DE_F > IRC_DE_F else IRC
    │               决策: netgen/calculator/dft_cal
    │
    └─→ ReactomeForge:
        │
        ├─→ 方向归一化完整 IRC 路径
        ├─→ barrier = [max(E_full_irc) - E_first_reactant_frame] × 627.509
        ├─→ → reaction_data.csv "barrier"
        └─→ → reaction_data.csv "barrier_original" = ReactNet pool 值
```

---

## 8. 关键算法管线

### 8.1 Growing String Method (GSM)

```
输入: 反应物几何 R, 产物几何 P
    │
    ├─→ 1. 线性插值生成初始弦 (N=Config.PYGSM.num_nodes 个节点)
    │
    ├─→ 2. 迭代:
    │   ├─ 对每个节点做约束优化 (沿切线方向)
    │   ├─ 重新参数化弦 (等弧长)
    │   ├─ 在最高能量节点两侧添加新节点
    │   └─ 重复直到收敛 (conv_tol) 或 max_gsm_iters
    │
    └─→ 3. 最高能量节点 → TS 初始猜测

引擎: pyGSM (默认) 或 pysis_gsm
计算器: run_xtb() / run_gauxtb()
```

### 8.2 TS Optimization (Pysisyphus)

```
输入: TS 初始猜测几何
    │
    ├─→ 1. 计算初始 Hessian
    │
    ├─→ 2. 迭代:
    │   ├─ 用 Hessian 特征向量跟随 (eigenvector following)
    │   ├─ 步长控制: trust_radius
    │   ├─ 每 hessian_recalc 步重新计算 Hessian
    │   └─ 收敛检查: 梯度 < thresh
    │
    └─→ 3. 输出: 优化后 TS 几何 + 能量

计算器: run_xtb() (xTB) 或 run_dft() (DFT)
```

### 8.3 IRC (Intrinsic Reaction Coordinate)

```
输入: TS 几何 + Hessian
    │
    ├─→ 1. 从 TS 沿虚频方向向前/后积分
    │      步长: Config.PYSIS.IRC.step_length (Bohr)
    │
    ├─→ 2. 每一步:
    │   ├─ 沿质量加权梯度方向移动
    │   └─ 投影 Hessian 以保持路径
    │
    ├─→ 3. 终止条件:
    │   ├─ max_cycles 达到
    │   ├─ 梯度 < rms_grad_thresh (收敛到极小点)
    │   └─ 能量变化 < energy_thresh
    │
    └─→ 4. reaction_analysis:
        ├─ match_irc_nodes(): 匹配 IRC 端点与输入 R/P
        ├─ 分类: Intended/R_Unintended/P_Unintended/Unintended
        └─ _CoordChange 后缀 (金属体系)

引擎: pysisyphus
```

### 8.4 反应枚举算法

```
输入: 反应物分子图 (键列表 + 原子属性)
    │
    ├─→ 1. 枚举所有可能的断键组合
    │   └─ max_break_bonds 控制复杂度
    │
    ├─→ 2. 对每种断键组合:
    │   ├─ 生成开放的价电子
    │   └─ 枚举所有合法成键组合 (max_form_bonds 控制)
    │
    ├─→ 3. Lewis 结构评分
    │   ├─ 形式电荷
    │   ├─ 八隅体规则
    │   └─ lewis_score_paticence 过滤
    │
    ├─→ 4. 分子筛分 (sieve)
    │   ├─ 化合价违规
    │   └─ 不合理环/稠环
    │
    ├─→ 5. [金属] 配位键重附着
    │
    └─→ 6. 原子映射保留

复杂度: O(C(N_break) × C(N_form))，N 为键数
```

---

## 附录

### A. 单位约定

| 物理量 | 单位 | 出现位置 |
|--------|------|----------|
| 反应能垒 (DE_F, DE_B, IRC_DE_F, IRC_DE_B, barrier, ref_barrier, barrier_threshold) | **kcal/mol** | TS 搜索结果、网络输出、配置 |
| 单点能 (R_SPE, P_SPE, TS_SPE, SPE) | **Hartree** | TS 搜索、网络 |
| 几何坐标 | **Å (Angstrom)** | XYZ 文件 |
| RMSD | **Å** | 重复 TS 检查 |
| Walltime (*_wt, timeout_sec) | **seconds** | 配置/请求 |
| 内存 (mem) | **GB/CPU** | 配置 |
| IRC step_length | **Bohr** | pysisyphus 约定 |
| 温度 | **K** | 动力学 |
| 压力 | **Pa** | 动力学 |

### B. 原子映射规则

- `EnumerateReactions.run()` 和 `Reaction()` 保证一致的原子排序
- 禁止使用 `yamol(unmapped_smiles)` 直接构建 R/P 对
- XYZ 文件必须保留原子映射: reactant frame → product frame 原子一一对应

### C. 技能安全性约束

- Mira 认证: 平台自动签名 JWT，无需手动设置密钥
- 用户确认门控: Step N (QN1-QN4) 必须在提交 `run_network` 前通过
- 层数上限: `run_network` layers ≤ 3
- 云端 xTB only: Mira 无 DFT 参数，精修必须在本地
- 图谱只读: 不本地重建 ReactomeForge 图谱
