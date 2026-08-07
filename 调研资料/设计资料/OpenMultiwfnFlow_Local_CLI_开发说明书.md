# OpenMultiwfnFlow 本地 CLI 开发说明书

**版本**：V0.1  
**命令行入口**：`omwfn`  
**部署原则**：本地优先、显式依赖、可重跑、可审计

---

## 1. 目标与边界

构建以本地 Multiwfn 和本地 VMD 为核心的波函数后处理 CLI，提供 ESP、表面统计、HOMO/LUMO、轨道 Cube、批量分析和可复现渲染。远程渲染服务须完全移除。

只实现独立的本地工作流封装与公开工具集成，不复制附件涉及的私有服务、远程 GPU Runner、预装路径、二进制、模型权重或授权凭证。

---

## 2. V0.1 能力

- Molden/FCHK/WFN/WFX 等波函数文件识别和完整性检查
- Multiwfn 的 stdin 管道驱动、菜单脚本存档与日志解析
- ESP 表面统计、面积区间分布、原子局部表面统计、密度/ESP Cube
- HOMO/LUMO 及相邻轨道摘要、Cube 输出
- 本地 VMD Tcl 渲染或保留 VMD 场景包供人工运行
- 多文件批处理、每任务独立目录、CSV 汇总和失败隔离

每个任务目录必须保存原始输入、解析后配置、命令行、环境清单、stdout/stderr、结果索引和 SHA-256 哈希。

---

## 3. 模块结构

```text
openmultiwfnflow/
├── pyproject.toml
├── environment.yml
├── configs/
├── templates/
├── examples/
├── src/openmultiwfnflow/
│   ├── cli/
│   ├── core/
│   ├── adapters/
│   ├── workflows/
│   ├── validation/
│   ├── analysis/
│   ├── render/
│   └── io/
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

```text
runs/<run_id>/
├── inputs/       # 用户输入、resolved_config、manifest
├── work/         # 引擎中间文件
├── logs/         # commands、stdout、stderr、events
├── results/      # 面向用户的表格、图像、结构/轨迹
└── report.md
```

---

## 4. CLI

```bash
omwfn init ./projects/electrolyte_orbitals
omwfn doctor --strict
omwfn esp --input molecule.fchk --cubes --workdir runs/esp_001
omwfn orbitals --input molecule.fchk --below-homo 3 --above-lumo 3
omwfn render esp --input runs/esp_001 --renderer vmd-local
omwfn batch esp --inputs input/*.fchk --workdir runs/batch_001
omwfn custom --input molecule.wfx --menu-script analysis.mf
```

---

## 5. 配置

```yaml
multiwfn: {binary: Multiwfn, timeout_s: 1800, stdin_mode: pipe}
esp: {surface: molecular, bins: 100, generate_density_cube: true, generate_esp_cube: true}
orbitals: {below_homo: 3, above_lumo: 3, grid_quality: high}
render: {engine: vmd_local, image_format: png, width_px: 1800, height_px: 1200}
batch: {workers: 1, fail_fast: false}
```

配置使用 Pydantic 校验；任何未知字段默认报错。恢复执行时必须验证核心输入、配置、引擎版本和势函数/模型文件哈希。

---

## 6. 数据契约

`WavefunctionRecord`：输入格式、电子数、原子数、基组/方法（若可解析）、哈希。  
`ESPResult`：全局表面统计、区间面积 CSV、原子表面统计、Cube 路径、解析置信度。  
`OrbitalResult`：HOMO/LUMO index、能量、间隙、轨道摘要、Cube 路径。  
`RenderRecord`：场景脚本、渲染器版本、相机/颜色参数、图像路径。

---

## 7. 关键工作流

1. 校验波函数文件类型、原子坐标、轨道信息和文件截断；不完整输入停止任务。  
2. 为每个分析生成明确的 Multiwfn 菜单输入文件，而不是只保留 Python 调用。  
3. 用 `subprocess.Popen(..., stdin=PIPE)` 驱动 Multiwfn，保存命令、原始日志和退出状态。  
4. ESP 流程依次输出全局表面统计、区间分布、原子局部统计，Cube 为可选工件。  
5. 轨道流程记录 HOMO/LUMO 识别逻辑与网格质量；能隙仅是轨道能量差，不自动等于实验带隙或激发能。  
6. 本地 VMD 可渲染 PNG/TGA；若不可用则导出 `.vmd` 与资源包，标记 `RENDER_PENDING_LOCAL_VMD`。

---

## 8. 验证与安全阈值

- 禁止 PTY/交互式伪终端依赖；必须支持 PIPE 执行。  
- 每个解析数值均要关联原始 Multiwfn 文本行或文件路径。  
- Cube 网格体积与文件大小必须设上限，避免磁盘耗尽。  
- 渲染图仅为可视化，不得用颜色深浅代替定量结论。

---

## 9. 测试与里程碑

**测试**：FCHK/Molden/WFX 正常和截断文件、ESP CSV 解析、HOMO/LUMO 边界、超时、无 VMD fallback、批任务部分失败。  
**M1（3 天）**：环境检查、PIPE adapter、输入/日志工件。  
**M2（4 天）**：ESP 与 Cube 解析。  
**M3（3 天）**：轨道、VMD 本地渲染与批任务。  
**M4（2 天）**：Markdown 报告、引用/版本 manifest。


---

## 10. 冻结条件

- `doctor --strict` 能验证必需引擎、Python 包、模型/势函数和格式支持。
- 所有示例从原始输入到报告可离线重跑。
- 所有核心输出都附输入与配置哈希、引擎版本和单位。
- 批处理可隔离任务失败，并输出结构化错误表。
- 所有“预测”与“实验/物理计算”结论清楚区分，不夸大可信度。

---

## 11. 合规边界

仅接入用户有权使用的开源软件、公开模型、公开势函数和数据。第三方工具、力场、结构文件、训练权重和渲染资产必须在 `manifest` 中记录版本、来源和许可证；不得绕过访问控制或复制私有实现。
