# Multiwfn Analysis 系统架构文档

> 技能名: `multiwfn-analysis` | 引擎: Multiwfn + 远程 VMD Runner
> 生成日期: 2026-08-01

---

## 1. 系统总览

Multiwfn Analysis 是**计算化学波函数分析与可视化**技能，集成 ESP 分析、HOMO/LUMO 轨道分析、远程 VMD 渲染、平台板导出。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 6 reference + 15 scripts + 3 VMD assets | 4 种内置工作流 + 自定义脚本 |
| **Multiwfn** | `Multiwfn` 二进制 (`MULTIWFN_BIN` 或 PATH) | 波函数分析引擎 |
| **VMD Runner** | Mira 推理服务 (`vmd-runner-5f2a38`) | 远程 GPU 渲染 (A30) |

---

## 2. 文件架构

```
multiwfn-analysis/
├── SKILL.md                          # 主入口: 4 种内置工作流
├── scripts/
│   ├── multiwfn_skill/               # Python 工具库
│   │   ├── atoms.py                  # 原子数据处理
│   │   ├── common.py                 # 通用工具
│   │   ├── cube.py                   # Cube 文件处理
│   │   ├── esp_parser.py             # ESP 结果解析
│   │   ├── multiwfn_pipe.py          # Multiwfn 管道驱动 (subprocess stdin)
│   │   ├── orbital_summary.py        # 轨道摘要
│   │   ├── vmd_package.py            # VMD 渲染包生成
│   │   └── vmd_runner_client.py      # VMD Runner 客户端
│   ├── run_esp_local.py              # ESP 分析 (4 阶段)
│   ├── run_homo_lumo_local.sh        # HOMO/LUMO 轨道分析
│   ├── run_vmd_render.py             # VMD 渲染 (esp/orbital/custom)
│   ├── run_board_export.py           # 平台板导出
│   ├── run_batch_analysis.py         # 批量工作流 (esp/orbital/vmd-*)
│   └── run_custom_multiwfn.py        # 自定义 Multiwfn 脚本
├── references/
│   ├── esp-workflow.md               # ESP 工作流详解
│   ├── orbital-workflow.md           # 轨道工作流详解
│   ├── vmd-render-workflow.md        # VMD 渲染工作流
│   ├── batch-workflow.md             # 批量工作流
│   ├── board-workflow.md             # 平台板工作流
│   └── custom-scripting.md           # 自定义脚本
└── assets/vmd/                       # VMD Tcl 渲染脚本
    ├── esp/ESP_layout_core.vmd + ESP_render_core.vmd
    └── orbital/ORB_render_core.vmd
```

---

## 3. 四种内置工作流

### 工作流 1: ESP 分析 (4 阶段)

```bash
python3 scripts/run_esp_local.py molecule.molden [output_dir]
```

| 阶段 | 内容 | Multiwfn 菜单路径 | 输出 |
|------|------|-------------------|------|
| 1 | 整体分子表面 ESP 统计 | `12→0` | step_1_surface_analysis.log |
| 2 | ESP 区间面积分布 | `9→all→<range>→15→3` | step_2_esp_area_bins.csv + .svg |
| 3 | 原子局部 ESP 统计 | `11→n→2` | step_3_atom_surface_stats.csv + surfanalysis.pdb |
| 4 | Cube 生成 (可选) | `5→1`(密度) + `5→12`(ESP) | density.cub + totesp.cub |

### 工作流 2: HOMO/LUMO 轨道分析

```bash
scripts/run_homo_lumo_local.sh molecule.fchk [above_lumo] [below_homo] [output_dir]
```

默认: HOMO-3 ~ LUMO+3, high 网格 → `results/Orb_Val_Sum.csv` + `orb*.cub`

下一步选项:
- A) 平台多文件画布 (交互查看)
- B) 远程 VMD 渲染 (发表级图片)
- C) 先渲染再生成画布

### 工作流 3: 远程 VMD 渲染

```
run_vmd_render.py --params-only → 预览参数 → --confirmed --dry-run → 生成 zip
    → mira_inference_upload_file("vmd-runner-5f2a38") → 轮询 → 下载 BMP + log
```

支持: esp, orbital, custom (用户自定义 .vmd 脚本)

### 工作流 4: 批量工作流

```bash
python3 scripts/run_batch_analysis.py esp mol1.molden mol2.fchk
python3 scripts/run_batch_analysis.py orbital mol1.fchk mol2.fchk
python3 scripts/run_batch_analysis.py vmd-esp esp_mol1 esp_mol2 --confirmed
python3 scripts/run_batch_analysis.py vmd-custom --job-csv jobs.csv
```

输出: `batch_<mode>_<ts>/tasks/` (独立任务目录) + `results/batch_tasks.csv` + `results/batch_*_summary.csv`

---

## 4. Multiwfn 驱动模式

**管道模式** (沙箱兼容):
```python
# multiwfn_pipe.py: subprocess PIPE, stdin 菜单命令
process = subprocess.Popen([multiwfn_bin, input_file],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
process.communicate(input=menu_commands.encode())
```

---

## 5. 输出目录布局

```
<output_dir>/
├── logs/          # 完整终端日志
├── commands/      # Multiwfn 菜单输入文件 (*.mf) + VMD 渲染包
└── results/       # 用户输出: CSV, SVG, PDB, CUB, BMP, JSON
```

---

## 6. 调用关系图

```
用户输入 (.molden/.fchk/.wfn/.wfx)
    │
    ├─→ ESP 分析
    │   ├── run_esp_local.py → Multiwfn (3 阶段连续执行)
    │   ├── (询问) → run_esp_local.py --only-cubes
    │   └── (询问) → run_vmd_render.py esp → VMD Runner (GPU)
    │
    ├─→ 轨道分析
    │   ├── run_homo_lumo_local.sh → Multiwfn 生成 cub
    │   ├── (选项A) → run_board_export.py orbital → 平台画布
    │   ├── (选项B) → run_vmd_render.py orbital → VMD Runner
    │   └── (选项C) → 先B后A
    │
    ├─→ 批量 → run_batch_analysis.py → 独立任务目录 + CSV
    │
    └─→ 自定义 → run_custom_multiwfn.py → 用户 .mf 菜单文件
```

## 附录: 关键约束

- 沙箱环境禁止 PTY (`pexpect.spawn`); 必须用 subprocess PIPE
- `g16` 环境变量指向 Gaussian 16 可执行文件
- 引用: 必须引用 Lu & Chen (2012) + Lu (2024)
