# LAMMPS Molecular Dynamics 系统架构文档

> 技能名: `lammps` | 版本: 1.0.0 | 200+ 示例文件 + 516 命令索引
> 生成日期: 2026-08-01

---

## 1. 系统总览

LAMMPS 分子动力学仿真技能，提供从数据文件准备到轨迹分析的完整工作流。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 6 reference + 17 scripts + 200+ examples | 系统分类、三条路径、验证三级、运行规则 |
| **Python 生态** | pymatgen, mbuild, foyer, OVITO, MDAnalysis | 结构准备、力场分配、轨迹分析 |
| **LAMMPS 引擎** | `lmp` 二进制 (OpenMP 4 线程) | 实际 MD 计算 |

---

## 2. 文件架构

```
lammps/
├── SKILL.md                          # 主入口: 5 步工作流 + 系统分类
├── scripts/
│   ├── generate_input.py             # 程序化生成 LAMMPS 输入
│   ├── validate_syntax.py            # 语法验证
│   ├── validate_physics.py           # 物理验证
│   ├── parse_input.py                # 输入解析
│   ├── profile_generator.py          # 性能分析配置
│   ├── commands_index.json           # (267KB) 516 命令索引
│   ├── commands_syntax.json          # (52KB) 命令语法
│   └── universal_validator.py        # 通用验证器
├── references/
│   ├── data_preparation.md           # .data 文件准备 (三条路径)
│   ├── trajectory_analysis.md        # OVITO/MDAnalysis 轨迹分析
│   ├── troubleshooting.md            # 错误诊断
│   ├── best-practices.md             # 仿真质量指南
│   ├── dof-validation.md             # DOF 冲突检测
│   └── hpc_optimization.md           # MPI/GPU 优化
└── examples/                         # 20 类目 200+ 示例脚本
```

---

## 3. 三条路径 (Step 0: 系统分类)

### Path A — 晶体/无机材料

```
物质: 纯金属/合金/离子氧化物/共价晶体
数据: pymatgen LammpsData.from_structure(struct, atom_style="atomic"|"charge")
力场:
  ├── 金属 (Fe,Cu,Al,Ni) → EAM (eam/alloy, eam/fs)
  ├── 离子氧化物 (Fe₂O₃,SiO₂,MgO) → Buckingham + Coulomb
  └── 共价晶体 (Si,C,SiC) → Tersoff, SW, ReaxFF
输入: units metal, atom_style atomic
```

### Path B — 有机分子/聚合物

```
物质: C,H,O,N,S,F,Cl,Br (不含 P,Si,Se,Te,过渡金属)
数据: mbuild + foyer (OPLS-AA) → write_lammps_data()
力场: OPLS-AA (via foyer)
输入: units real, atom_style full
OPLS-AA 必须:
  pair_style   lj/cut/coul/long 12.0
  pair_modify  mix geometric
  kspace_style pppm 1.0e-5
  special_bonds lj/coul 0.0 0.0 0.5
```

### Path C — 生物分子 (仅数据文件)

```
输入: CHARMM-GUI/AMBER/GROMACS 预建拓扑
数据: PSF+PRM, prmtop+inpcrd → LAMMPS data 转换
```

---

## 4. 五步工作流

### Step 1: 数据文件准备

```python
# Path A: 从 pymatgen
from pymatgen.io.lammps.data import LammpsData
lammps_data = LammpsData.from_structure(struct, atom_style="atomic")
lammps_data.write_file("data.lammps")

# 势文件: pip install lammps 捆绑 248+ 势文件
# 检查: lammps/share/lammps/potentials/
```

### Step 2: 输入脚本生成

```python
# 程序化 (推荐)
from scripts.generate_input import LAMMPSInputGenerator
gen = LAMMPSInputGenerator()
script = gen.generate(units="metal", atom_style="atomic", temperature=300)

# 命令行
python scripts/generate_input.py --type nvt -T 300 -o nvt.in
```

### Step 3: 三级验证

```bash
python scripts/validate_syntax.py input.in      # 语法
python scripts/validate_physics.py input.in      # 物理 (时间步/单位/力场)
# + 手动: 协议验证 (阶段顺序/平衡/收敛)
```

| 关键验证规则 | |
|------|------|
| 金属 → EAM, 禁止 LJ | |
| `atom_style full` → `lj/cut/coul/long`, 禁止裸 `lj/cut` | |
| OPLS-AA → 4 项全部设置 | |
| 每个 `run` 前必须有 active `fix` (nve/nvt/npt) | |
| 动力学前必须有 minimization | |

### Step 4: 仿真阶段

```
Minimization → NPT 平衡 (结构) 或 NVT 平衡 (动力学) → NVE/NPT 产出
```

### Step 5: 轨迹分析

- OVITO Python API: RDF, CNA, 可视化
- MDAnalysis: RMSD, RMSF, MSD, 扩散系数

---

## 5. 运行规则

```bash
# 短运行 (<5 min)
OMP_NUM_THREADS=4 timeout 300 lmp -sf omp -in script.in; exit 0

# 长运行 (需要实时进度)
subprocess.Popen(["lmp","-sf","omp","-in","script.in"],
    stdout=PIPE, stderr=STDOUT, text=True, bufsize=1,
    env={**os.environ, "OMP_NUM_THREADS":"4"})
```

---

## 6. 调用关系图

```
用户需求 → Step 0: 系统分类
    │
    ├── Path A (晶体) → pymatgen LammpsData → EAM/Tersoff/Buckingham
    ├── Path B (有机) → mbuild+foyer OPLS-AA → write_lammps_data()
    └── Path C (生物) → CHARMM/AMBER → data 转换
    │
    ├── Step 2: generate_input.py → LAMMPS 输入脚本
    ├── Step 3: validate_syntax + validate_physics → 验证
    ├── Step 4: lmp -sf omp -in script.in → 仿真
    └── Step 5: OVITO/MDAnalysis → 轨迹分析
```
