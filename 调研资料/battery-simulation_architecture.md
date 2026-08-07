# Battery Simulation 系统架构文档

> 技能名: `battery-simulation` | 依赖: PyBaMM, PyBOP
> 生成日期: 2026-08-01

---

## 1. 系统总览

锂离子电池仿真技能，提供三条独立轨道：

| 轨道 | 引擎 | 用途 |
|------|------|------|
| **P2D/DFN** | PyBaMM (SPM/SPMe/DFN) | 机理仿真: 充放电曲线, CCCV, C-rate, 热分析, 降解 |
| **ECM** | 等效电路模型 (Thevenin) | BMS 原型, HPPC 分析, 快速仿真 |
| **PyBOP** | PyBOP 参数辨识 | 从实测数据拟合扩散系数/交换电流密度/电极几何 |

---

## 2. 文件架构

```
battery-simulation/
├── SKILL.md                          # 主入口: 轨道识别 + P2D 6步工作流
└── references/
    ├── p2d.md                         # P2D 详解: 降解, 热分析, 故障排除
    ├── ecm.md                         # ECM/Thevenin 等效电路
    └── pybop.md                       # PyBOP 参数辨识
```

---

## 3. P2D 轨道 (6 步工作流)

### Step 0: 轨道识别

| 用户需求 | 轨道 |
|----------|------|
| 快速仿真/BMS/HPPC 数据 | ECM → `references/ecm.md` |
| 机理理解/高倍率/降解/发表 | P2D/DFN → 继续 |
| 温度分析 | P2D + thermal |
| C-rate 扫描/参数敏感性 | P2D |
| 实测数据拟合参数 | PyBOP → `references/pybop.md` |

### Step 0b: 参数集确认 (P2D 独有)

| 参数集 | 正极 | 负极 | 电池 | 最佳用途 |
|--------|------|------|------|----------|
| `Chen2020` | NMC811 | 石墨 | LG M50 21700 (5Ah) | **默认通用基线** |
| `Chen2020_composite` | NMC811 | 石墨+Si | LG M50 | Si-C 复合负极 |
| `OKane2022` | NMC811 | 石墨 | LG M50 | **降解研究** (SEI/镀锂/裂纹) |
| `Prada2013` | LFP | 石墨 | A123 26650 (2.3Ah) | LFP 化学 |
| `OKane2022_graphite_SiOx_halfcell` | — | 石墨+SiOx | 半电池 | SiOx 负极降解 |

### Step 1: 模型选择

| 模型 | 类 | 适用场景 |
|------|-----|----------|
| SPM | `pybamm.lithium_ion.SPM()` | ≤1C 快速筛选 |
| SPMe | `pybamm.lithium_ion.SPMe()` | 1–3C |
| DFN(P2D) | `pybamm.lithium_ion.DFN()` | 高倍率/降解/发表 |

### Step 2-6: 仿真→实验→参数→对比→变量

```python
import pybamm, numpy as np
model = pybamm.lithium_ion.DFN()
param = pybamm.ParameterValues("Chen2020")
sim = pybamm.Simulation(model, parameter_values=param)
sol = sim.solve([0, 3600])

t = sol["Time [s]"].entries
V = sol["Terminal voltage [V]"].entries
cap = sol["Discharge capacity [A.h]"].entries

# SOC 计算 (DFN/SPMe 无 "State of charge")
nominal_cap = param["Nominal cell capacity [A.h]"]
soc = 1 - cap / nominal_cap
```

### CCCV 循环 (pybamm.Experiment)

```python
experiment = pybamm.Experiment([
    ("Discharge at C/5 until 2.5 V",
     "Rest for 10 minutes",
     "Charge at C/5 until 4.2 V",
     "Hold at 4.2 V until 50 mA",
     "Rest for 10 minutes")
] * 3)
```

### 热仿真

```python
model = pybamm.lithium_ion.DFN(options={"thermal": "lumped"})
# 关键参数: Cell cooling surface area, Cell volume, Heat transfer coefficient
```

热选项: `"isothermal"`(默认) | `"lumped"`(均匀温度) | `"x-full"`(厚度梯度)

### 关键变量

| 变量 | 说明 |
|------|------|
| `"Terminal voltage [V]"` | 端电压 |
| `"Current [A]"` | 电流 |
| `"Discharge capacity [A.h]"` | 累积容量 |
| `"Cell temperature [K]"` | 需热模型 |

---

## 4. 调用关系图

```
用户需求
    │
    ├─→ 轨道识别 (Step 0)
    │   ├── ECM → references/ecm.md
    │   ├── PyBOP → references/pybop.md
    │   └── P2D → Step 0b
    │
    ├─→ 参数集确认 (Step 0b)
    │   └── 16 种预设参数集
    │
    └─→ PyBaMM 仿真
        ├── pybamm.lithium_ion.{SPM,SPMe,DFN}()
        ├── pybamm.ParameterValues("Chen2020")
        ├── pybamm.Simulation(model, param, experiment?)
        └── sol.solve() → 曲线 + CSV + PNG
```

## 附录: 关键约束

- 参数集必须在仿真前确认
- 容量参数只缩放 C-rate 电流，不调整电极几何
- 厚度扫描: 同步缩放 Nominal cell capacity
- 孔隙率扫描: 同步更新 active material volume fraction
- 热时间序列: 用 `"X-averaged cell temperature [K]"` 非 `"Cell temperature [K]"`
