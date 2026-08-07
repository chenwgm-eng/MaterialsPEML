# Pymatgen 系统架构文档

> 技能名: `pymatgen` | Python 包: `pymatgen`
> 生成日期: 2026-08-01

---

## 1. 系统总览

Pymatgen (Python Materials Genomics) 是**材料科学工具包**，覆盖晶体结构操作、相图构建、能带/DOS、表面与界面分析、本地材料数据库访问。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 5 reference + 3 scripts | 核心 API 速查、关键陷阱、每种任务必读 |
| **Python 包** | `pymatgen` (开源) | 结构操作、对称性分析、相图、I/O |
| **本地 API** | `http://124.174.7.177` | 自托管 Materials Project 数据库 (无 API key) |

---

## 2. 文件架构

```
pymatgen/
├── SKILL.md                          # 主入口: 7 大能力速查 + 关键陷阱
├── scripts/
│   ├── structure_converter.py        # 格式转换 (批处理)
│   ├── structure_analyzer.py         # 综合结构分析
│   └── phase_diagram_generator.py    # MP 相图生成
└── references/
    ├── core_classes.md               # Structure/Lattice/Molecule/Composition API
    ├── io_formats.md                 # 100+ 格式 I/O + VASP/Gaussian/LAMMPS 集成
    ├── analysis_modules.md           # 相图/配位/表面/磁性分析
    ├── transformations_workflows.md  # 10 种计算工作流
    └── materials_project_api.md      # 本地 MP API 端点详情
```

---

## 3. 七大核心能力

### 3.1 结构创建与操作

```python
from pymatgen.core import Structure, Lattice, Molecule

struct = Structure.from_file("structure.cif")
struct = Structure.from_spacegroup("Fm-3m", Lattice.cubic(4.05), ["Al"], [[0,0,0]])
supercell = struct * (2, 2, 2)
```

### 3.2 格式转换 (100+ 格式)

```python
struct.to(filename="output.cif")
CifWriter(struct, symprec=0.1).write_file("output.cif")  # 保留空间群
XYZ(struct).write_file("output.xyz")
Structure.from_file("POSCAR")
```

### 3.3 对称性分析

```python
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
sga = SpacegroupAnalyzer(struct)
primitive = sga.get_primitive_standard_structure()      # DFT 能带计算
conventional = sga.get_conventional_standard_structure() # 表面/界面
```

### 3.4 相图与热力学

```python
import requests
BASE = "http://124.174.7.177"
resp = requests.get(f"{BASE}/materials/entries", params={"chemsys": "Li-Fe-O"})
entries = [ComputedEntry(Composition(e["formula_pretty"]),
           e["formation_energy_per_atom"] * Composition(e["formula_pretty"]).num_atoms,
           entry_id=e["material_id"]) for e in resp.json()["entries"]]
pd = PhaseDiagram(entries)
```

### 3.5 表面与界面

```python
from pymatgen.core.surface import SlabGenerator
slabgen = SlabGenerator(conventional, miller_index=(1,1,1), min_slab_size=10.0, min_vacuum_size=10.0)
slabs = slabgen.get_slabs()  # ⚠️ 可能返回 []
```

### 3.6 本地 MP 数据库

```python
BASE = "http://124.174.7.177"
# 搜索: /materials/search?chemsys=Li-Fe-P-O&is_stable=true&limit=500
# 结构: /materials/mp-149/structure?fmt=cif
# 声子: /phonon/search?chemsys=Fe-O&has_imaginary_modes=false
# 条目: /materials/entries?chemsys=Li-Fe-O
# 详情: /materials/mp-149 → formula_pretty, band_gap, energy_above_hull, ...
```

### 3.7 高级分析

```python
# XRD
from pymatgen.analysis.diffraction.xrd import XRDCalculator
pattern = XRDCalculator().get_pattern(struct)

# 弹性
from pymatgen.analysis.elasticity import ElasticTensor
tensor = ElasticTensor.from_voigt(matrix)
print(tensor.k_voigt, tensor.g_voigt, tensor.y_mod)

# 磁性
from pymatgen.transformations.advanced_transformations import MagOrderingTransformation
```

---

## 4. 关键陷阱速查

| 陷阱 | 修复 |
|------|------|
| 周期距离: `coords[j]-coords[i]` | 用 `struct.get_distance(i,j)` |
| `surface_area` 仅 Slab 有 | `np.linalg.norm(np.cross(lattice[0],lattice[1]))` |
| `to(filename="x.cif")` 丢失空间群 | `CifWriter(struct, symprec=0.1).write_file()` |
| `PeriodicSite` 无 `.index` | `for i, site in enumerate(struct):` |
| `get_slabs()` 返回 `[]` | 检查后才索引 `[0]` |
| `chemsys` vs `elements` | `chemsys`=精确 N 元素; `elements`=至少含这些元素 |
| GGA/PBE 对过渡金属氧化物给出 band_gap=0 | 交叉参照实验 |

---

## 5. 调用关系图

```
用户输入 (材料名称/结构文件)
    │
    ├─→ Structure.from_file() / from_spacegroup()  结构创建
    │
    ├─→ SpacegroupAnalyzer()                       对称性分析
    │
    ├─→ 本地 MP API (http://124.174.7.177)        数据库查询
    │   ├── /materials/search                      搜索
    │   ├── /materials/{id}/structure               获取结构
    │   ├── /materials/entries                      相图条目
    │   └── /phonon/search                          声子数据
    │
    ├─→ PhaseDiagram(entries)                      相图构建
    │
    ├─→ SlabGenerator + AdsorbateSiteFinder        表面/吸附
    │
    └─→ I/O (to/from_file)                        格式转换
```

## 附录: 计算工作流速查

| 任务 | 参考 |
|------|------|
| 批掺杂/替换 | Workflow 1 |
| 能带计算 | Workflow 4 |
| 表面能 | Workflow 3 |
| 吸附能 | Workflow 9 |
| 弹性常数 | Workflow 8 |
| 扩散 (NEB/MD) | Workflow 6 |
| 高通量筛选 | Workflow 10 |
