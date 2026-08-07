# Packmol 系统架构文档

> 技能名: `packmol` | 版本: 1.0.0
> 生成日期: 2026-08-01

---

## 1. 系统总览

Packmol 是**分子堆积与 MD 初始构型构建**工具，将分子按空间约束打包成 MD 仿真的起始结构。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 4 reference + 6 scripts + 4 templates + 4 examples | 输入生成、约束语法、验证脚本 |
| **引擎** | `packmol` 二进制 | GENCAN 优化算法，无重叠堆积 |

**核心约束类型**: box, sphere, cylinder, plane (above/below), ellipsoid

---

## 2. 文件架构

```
packmol/
├── SKILL.md                          # 主入口: 4 种工作流 + 约束速查
├── scripts/
│   ├── generate_input.py             # 程序化生成输入
│   ├── validate_input.py             # 输入语法验证
│   ├── check_overlaps.py             # 输出重叠检测
│   ├── analyze_density.py            # 密度分析
│   ├── solvate_helper.py             # 自动蛋白溶剂化
│   └── verify_success.py             # Packmol 成功验证
├── references/
│   ├── constraints.md                # 完整约束语法
│   ├── parameters.md                 # 所有输入参数
│   ├── file_formats.md               # 文件格式规范
│   └── troubleshooting.md            # 问题解决
├── templates/                        # 3 个模板 (basic/solvation/interface)
└── examples/                         # 4 个示例 (basic/solvation/interface/advanced)
```

---

## 3. 四种工作流

### 工作流 1: 基本分子堆积

```text
tolerance 2.0
output mixture.pdb
filetype pdb

structure water.pdb
  number 800
  inside box 0. 0. 0. 40. 40. 40.
end structure

structure ethanol.pdb
  number 200
  inside box 0. 0. 0. 40. 40. 40.
end structure
```

### 工作流 2: 蛋白溶剂化

```text
structure protein.pdb
  number 1
  fixed 0. 0. 0. 0. 0. 0.
  center
end structure

structure water.pdb
  number 5000
  inside box -10. -10. -10. 50. 50. 50.
end structure
```

辅助脚本: `python scripts/solvate_helper.py protein.pdb --shell 15.0 --charge +4`

### 工作流 3: 液-液界面

```text
tolerance 2.0
discale 1.5      # 平面约束必须!
maxit 50
pbc -20. -20. -30. 20. 20. 30.

structure water.pdb
  number 1000
  below plane 0. 0. 1. 0.
end structure

structure hexane.pdb
  number 200
  above plane 0. 0. 1. 0.
end structure
```

### 工作流 4: 高级约束

球形/圆柱/椭球 + atom 级别约束 (双层囊泡等)。

---

## 4. 核心 API

### 输入文件结构

```
tolerance <距离>      # 最小原子间距 (Å)
output <文件名>       # 输出文件
filetype <格式>       # pdb, xyz, tinker
[pbc <尺寸>]          # 周期边界
[seed <整数>]         # 随机种子
[discale <因子>]      # 距离缩放优化
[maxit <N>]          # 最大迭代 (默认 20)

structure <分子文件>
  number <N>
  {inside|outside} <约束>
  [fixed x y z a b c]
  [center]
  [constrain_rotation {x|y|z} <角度> <容忍>]
  [atoms <i j k> ... end atoms]
end structure
```

### 运行

```bash
packmol < input.inp
```

```python
with open("packmol.inp", "w") as f: f.write(inp_content)
subprocess.run(["packmol"], stdin=open("packmol.inp"), capture_output=True, text=True)
```

### 验证

```bash
python scripts/check_overlaps.py output.pdb --tolerance 2.0
python scripts/verify_success.py input.inp output.pdb
python scripts/analyze_density.py output.pdb
```

---

## 5. 调用关系图

```
用户需求
    │
    ├─→ 生成输入: generate_input.py / 模板
    │
    ├─→ 验证输入: validate_input.py
    │
    ├─→ 运行: packmol < input.inp
    │
    ├─→ 验证输出: check_overlaps / verify_success / analyze_density
    │
    └─→ 输出: .pdb 文件 → LAMMPS/GROMACS/AMBER 等 MD 软件
```

## 附录: 关键约束

- 平面约束系统必须加 `discale 1.5` 和 `maxit 50`
- `"ENDED WITHOUT PERFECT PACKING"` 仍可用作起始构型 (需能量最小化)
- 蛋白溶剂化: 溶剂壳 ~10-15 Å 围绕溶质
- 离子中和: N_ions = charge / e
- 大系统: 用 restart 文件增量构建
