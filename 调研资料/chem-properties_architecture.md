# Chem-Properties 系统架构文档

> 技能名: `chem-properties` | 依赖: chemicals, thermo, requests
> 生成日期: 2026-08-01

---

## 1. 系统总览

Chem-Properties 是**化学性质查询工具**，覆盖从标准常数到 T/P 依赖性质、多组分 VLE/闪蒸、溶解度计算。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 4 scripts + 1 data file | 5 模块路由 + 数据源优先级 |
| **数据库** | DIPPR/Perry's (~340), Stenutz (~200), PubChem, NIST (76 fluids) | 实验数据 |
| **Python 包** | `chemicals`, `thermo` | 热力学模型 (Wilson/NRTL/UNIFAC, PR EOS, Henry, van't Hoff) |

---

## 2. 文件架构

```
chem-properties/
├── SKILL.md                          # 主入口: 5 模块路由
├── scripts/
│   ├── query_chemicals.py            # DIPPR/Perry's 查询 (~340 化合物)
│   ├── query_stenutz.py              # Stenutz 溶剂数据库 (~200)
│   ├── query_nist_fluid.py           # NIST REFPROP (76 流体, 高精度)
│   └── query_nist_antoine.py         # NIST Antoine 蒸气压
└── data/
    └── fluid_cgi_supported.json      # NIST 流体 CGI 支持列表
```

---

## 3. 五模块路由

| 模块 | 触发条件 | 方法 |
|------|----------|------|
| **M1** | 单组分, 标准条件 | query_chemicals → query_stenutz → /pubchem-database |
| **M2** | 单组分, 指定 T/P | query_chemicals T P; NIST 补充 H/S/声速 |
| **M3** | 多组分 VLE | IPDB Wilson/NRTL + UNIFAC 回退 |
| **M4** | 多组分闪蒸 (T,P,z) | thermo.FlashVL (PR EOS) |
| **M5** | 溶解度 | Henry (气), van't Hoff (固), Hansen/Hildebrand (溶剂选择) |

---

## 4. 数据源优先级

### M1 标准常数

```
1. query_chemicals.py → DIPPR/Perry's (~340 常见化合物)
   Tm, Tb, Tc, Pc, Vc, ω, Zc, ΔHf°(g/l), Tflash, LFL, UFL, Tauto,
   logP, dipole, GWP, εr, RI, σ, HHV, LHV

2. query_stenutz.py → Stenutz (~200 有机溶剂)
   含 Hansen δ, Hildebrand δ, Snyder P', ET, ε, RI, η, σ, logP
   命名注意: 希腊字母前缀被剥离 (γ-butyrolactone → butyrolactone)

3. /pubchem-database → 110M+ 化合物实验数据

4. ΔHf° 全 null → 建议 /dp-yamo DFT 计算
```

### M2 T/P 依赖性质

```bash
python scripts/query_chemicals.py ethanol 350 101325
```

输出含: `phase`, `Tb_K`, `Tc_K`, `density`, `Psat`, `Cp`, `η`, `λ`, `Hvap`, `σ`, `εr`, `RI`

- T > Tc → 超临界: Psat/Hvap/σ 物理无定义
- phase='s' → 固体: density/Cp/εr/σ 不适用

### M3 VLE (泡点/露点)

```python
from thermo.interaction_parameters import IPDB
# 优先查 IPDB 二元参数
if IPDB.has_ip_specific('ChemSep Wilson', CASs, 'aij'):
    aij = IPDB.get_ip_asymmetric_matrix('ChemSep Wilson', CASs, 'aij')
# 无数据 → UNIFAC 基团贡献法回退
```

### M4 多组分闪蒸

```python
from thermo import FlashVL
from thermo.eos_mix import PRMIX
from thermo.phases import CEOSGas, CEOSLiquid

flasher = FlashVL(constants, correlations, gas=gas, liquid=liq)
result = flasher.flash(T=T, P=P, zs=zs)
# result.VF (⚠️ 非 result.V)
# result.liquids[0].zs (液体组成)
# result.gas.zs (气体组成, 全液相时 result.gas=None)
```

### M5 溶解度

```python
# 气在液中: Henry 定律 + T-依赖 (kH 查文献或 C-T 数据拟合)
# 固在液中: van't Hoff → chemicals.Hfus(cas)
# 溶剂选择: Hansen/Hildebrand δ → query_stenutz
```

---

## 5. 调用关系图

```
用户查询
    │
    ├─→ 单组分标准 → M1
    │   ├── query_chemicals.py <name>
    │   ├── query_stenutz.py <溶剂名>
    │   └── /pubchem-database
    │
    ├─→ 单组分 T/P → M2
    │   ├── query_chemicals.py <name> <T_K> [P_Pa]
    │   └── query_nist_fluid.py (H/S/声速)
    │
    ├─→ VLE → M3
    │   ├── IPDB Wilson/NRTL/UNIQUAC
    │   └── UNIFAC 回退
    │
    ├─→ 闪蒸 → M4 → thermo.FlashVL (PR EOS)
    │
    └─→ 溶解度 → M5 → chemicals.Hfus/stenutz/Wilke
```

## 附录: 关键 API 陷阱

- `chemicals.viscosity.Wilke` 需显式导入子模块，非顶层
- Stenutz 命名: `γ-butyrolactone` → `butyrolactone`
- Stenutz `found: true` 仅指页面存在，仍需检查具体属性键
- M4 闪蒸: `result.VF` 非 `result.V`; `result.liquids` 是列表
- PR EOS 不预测 H-键共沸物 (醇/酸) → 用 M3 替代 M4
