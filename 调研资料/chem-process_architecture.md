# Chem-Process 系统架构文档

> 技能名: `chem-process` | 依赖: thermo, chemicals, chempy, scipy
> 生成日期: 2026-08-01

---

## 1. 系统总览

Chem-Process 是**化工过程与反应工程计算**技能，覆盖反应热、动力学、反应器建模、萃取、蒸馏和扩散系数估计。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 1 reference | 6 大计算模板 + 技能路由 |
| **Python 包** | `thermo`, `chemicals`, `chempy`, `scipy` | 热力学模型 + 数值求解 |

**与 chem-properties 分工**: chem-process 做**过程工程计算**，chem-properties 做**纯物质性质查询**。

---

## 2. 文件架构

```
chem-process/
├── SKILL.md                          # 主入口: 6 大计算模块
└── references/
    └── refs.md                        # 引用来源
```

---

## 3. 六大计算模块

### 模块 1: 反应热与生成焓

| 方法 | 精度 | 适用 |
|------|------|------|
| Hess 定律: `chemicals.Hfg(cas)` / `chemicals.Hfl(cas)` | ±1-3 kJ/mol | 常见化合物 |
| Joback: `thermo.Joback(SMILES).Hf(counts)/1000` | ±15-20 kJ/mol | 新化合物 |
| `/DP-YAMO` DFT | ±2-5 kJ/mol | 高精度 |

⚠️ `thermo.Chemical.Hf` ≠ ΔHf° (是 EOS 参考焓)

### 模块 2: 扩散系数

| 类型 | 方法 |
|------|------|
| 液中小分子 | Wilke-Chang: D=7.4e-12·(φM)^0.5·T/(μ·Vb^0.6), ±20% |
| 胶体/大分子 | Stokes-Einstein: D=kBT/(6πηr) |
| 气体 | Chapman-Enskog: `chemicals.lennard_jones` |

### 模块 3: 反应动力学与反应器

| 项 | 方法 |
|----|------|
| 表面动力学 | Langmuir-Hinshelwood: r=k·KA·CA/(1+KA·CA+...)² |
| TS→速率 | Eyring: k=(kBT/h)·exp(-ΔG‡/RT) ← `/reactnet` 提供 ΔG‡ |
| 批量反应器 | dCᵢ/dt=νᵢ·r → `scipy.solve_ivp` |
| 吸附动力学 | PFO/PSO 拟合, RMSE/R² 报告 |

### 模块 4: 液液萃取 (Kremser)

```
Step 1: E = K·V_org/V_aq
  E≥1 → 可行 → Step 2
  E<1 → 上限 = E×100%, 检查是否可达到要求后停止

Step 2: r = (x_in - y_in/K)/(x_out - y_in/K)
        N = ln[r·(1-1/E)+1/E]/ln(E)
```

### 模块 5: 蒸馏 (FUG 捷径)

```
Fenske → N_min → Underwood → R_min → Gilliland → N_actual → HETP→柱高
```

- R=1.3×Rmin 给出 N>>Nmin (物理正确); 实际用 R=1.5-2×Rmin
- Gilliland 在 xD>0.99 或近共沸时不可靠

### 模块 6: 技能路由

| 上游技能 | 提供 |
|----------|------|
| `/chem-properties` | Pᵢˢᵃᵗ, μ, ρ, ΔHf°, logP, VLE, 溶解度 |
| `/dp-yamo` | ΔHf° (XTB/DFT) |
| `/lammps` | 液体扩散 D (MSD 法) |
| `/reactnet` | ΔG‡ → Eyring 速率常数 |

---

## 4. 调用关系图

```
用户需求
    │
    ├── 反应热 → Hess(已知)/Joback(新)/dp-yamo(高精度)
    ├── 扩散系数 → Wilke-Chang/Stokes-Einstein/Chapman-Enskog
    ├── 反应器 → scipy.solve_ivp/chempy.ReactionSystem
    ├── 萃取 → Kremser (先检查 E 可行性)
    └── 蒸馏 → Fenske→Underwood→Gilliland
```
