# FluidSim 系统架构文档

> 技能名: `fluidsim` | Python 包: fluidsim + fluidfft
> 生成日期: 2026-08-01

---

## 1. 系统总览

FluidSim 是**面向对象的高性能 CFD 框架**，基于伪谱法 (FFT) 求解周期域偏微分方程。

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | SKILL.md + 6 reference | 5 步工作流 + 求解器选择 |
| **Python 包** | `fluidsim` (Pythran/Transonic 编译) | 求解器核心 + 输出分析 |
| **FFT 后端** | `fluidfft` (FFTW/mpi) | 高性能 FFT |

**关键优势**: 伪谱法 + Pythran 编译 = 接近 Fortran/C++ 的性能

---

## 2. 文件架构

```
fluidsim/
├── SKILL.md                          # 主入口: 5 步工作流 + 4 个例程
└── references/
    ├── installation.md               # 安装指南
    ├── solvers.md                    # 求解器列表与选择
    ├── simulation_workflow.md        # 详细工作流示例
    ├── parameters.md                 # 完整参数文档
    ├── output_analysis.md            # 输出类型与分析
    └── advanced_features.md          # 强制力/MPI/参数研究
```

---

## 3. 可用求解器

| 求解器 | 导入路径 | 物理场景 |
|--------|----------|----------|
| NS2D | `fluidsim.solvers.ns2d.solver` | 2D 湍流, 涡动力学 |
| NS3D | `fluidsim.solvers.ns3d.solver` | 3D 湍流 |
| NS2D.strat | `fluidsim.solvers.ns2d.strat.solver` | 分层流 (海洋/大气) |
| NS3D.strat | `fluidsim.solvers.ns3d.strat.solver` | 3D 分层流 |
| SW1L | `fluidsim.solvers.sw1l.solver` | 浅水方程 (旋转系统) |

---

## 4. 五步工作流

```python
# Step 0: HOME 设置 (沙箱环境必须)
import os; os.environ['HOME'] = '/tmp'

# Step 1: 导入
from fluidsim.solvers.ns2d.solver import Simul
from math import pi

# Step 2: 参数配置 (层次化, 点号访问, 拼写错误抛 AttributeError)
params = Simul.create_default_params()
params.oper.nx = params.oper.ny = 256         # 网格
params.oper.Lx = params.oper.Ly = 2 * pi       # 域大小
params.nu_2 = 1e-3                              # 粘度
params.time_stepping.t_end = 10.0               # 终止时间
params.time_stepping.USE_CFL = True             # 自适应时间步
params.init_fields.type = "noise"               # 初始条件类型
params.output.periods_save.phys_fields = 1.0    # 输出周期

# Step 3: 实例化
sim = Simul(params)

# Step 4: 执行
sim.time_stepping.start()

# Step 5: 分析
sim.output.phys_fields.plot("rot")       # 涡量 (key='rot' 非 'vorticity')
sim.output.phys_fields.plot("ux")        # x-速度 (key='ux' 非 'vx')
sim.output.spatial_means.plot()          # 空间平均时间序列
sim.output.spectra.plot1d()              # 能谱
```

---

## 5. 参数层次结构

```
params
├── oper          # 算子: nx/ny/nz, Lx/Ly/Lz, type_fft
├── nu_2, nu_4   # 物理: 粘度, 超粘度
├── time_stepping # 时间: t_end, USE_CFL, cfl_coef, deltat0
├── init_fields   # 初始: type ("noise"|"dipole"|"vortex"|"from_file"|"in_script")
├── output        # 输出: periods_save.{phys_fields,spectra,spatial_means}
├── forcing       # 强制力: enable, type ("tcrandom"), forcing_rate
└── N, f          # 分层流: Brunt-Väisälä; 浅水: Coriolis
```

---

## 6. 输出类型

| 输出 | 格式 | 访问方式 |
|------|------|----------|
| 物理场 (速度/涡量) | NetCDF | `sim.output.phys_fields.plot("rot")` |
| 空间平均 | 时间序列 | `sim.output.spatial_means.plot()` |
| 能谱 | 1D/2D | `sim.output.spectra.plot1d()` |
| 状态快照 | HDF5 | `h5py.File("state_phys_t=...hdf5","r")` |

⚠️ HDF5 读取用 `h5py` 非 `xarray` (流体嵌套组不兼容)

---

## 7. 高级特性

```python
# 强制力 (维持湍流)
params.forcing.enable = True
params.forcing.type = "tcrandom"

# 自定义初始条件 (谱空间)
params.init_fields.type = "in_script"
sim = Simul(params)
rot_fft = sim.oper.rotfft_from_vecfft(ux_fft, uy_fft)
sim.state.init_from_rotfft(rot_fft)

# MPI 并行
mpirun -np 64 python script.py

# 加载前次仿真
from fluidsim import load_sim_for_plot
sim = load_sim_for_plot("sim_dir")
```

---

## 8. 调用关系图

```
用户需求
    │
    ├─→ 求解器选择 (ns2d/ns3d/strat/sw1l)
    │
    ├─→ 参数配置 (网格/物理/时间/初始/输出/强制力)
    │
    ├─→ Simul(params) → sim.time_stepping.start()
    │   ├── 伪谱法 FFT (fluidfft 后端)
    │   ├── 自适应时间步 (CFL)
    │   └── 周期输出: NetCDF + HDF5
    │
    └─→ 输出分析
        ├── phys_fields.plot() (涡量/速度)
        ├── spatial_means.plot() (时间序列)
        ├── spectra.plot1d() (能谱)
        └── ParaView/VisIt (3D 可视化)
```

## 附录: 关键约束

- 沙箱: `HOME='/tmp'` 必须在 `import fluidsim` 前设置
- MPI: 需单独安装 `fluidfft-mpi-with-fftwmpi3d` 或 `fluidfft-mpi-with-p3dfft`
- NS2D: 涡量为原始状态变量 (`init_from_rotfft`)
- 速度场 key: `'ux'/'uy'` 非 `'vx'/'vy'`; 涡量 key: `'rot'` 非 `'vorticity'`
- HDF5: 用 `h5py`，不用 `xarray`
