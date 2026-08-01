# 电池材料研发AI Agent项目开发说明书
## 基于OpenScience底座 + 开源组件整合 —— 一整套开源版"Deep Principle"（全能力覆盖版）

版本: v4.0（补全 ReactNet 合成路径导航 + ReactHTE 实验闭环第一阶段 + 湿数据中间件）
日期: 2026-07-21

项目定位:
以 OpenScience (https://github.com/synthetic-sciences/openscience) 为 Agent 底座，直接封装整合各领域最成熟的开源模型/工具，构建一整套面向锂电池材料（固态聚合物电解质 + 无机晶体正负极材料）的 AI 驱动研发闭环系统，完整对标 Deep Principle (https://www.deepprinciple.com/) 的 Agent Mira 六大模块能力，包括合成路径导航、实验闭环第一阶段以及从第三方软件系统获取湿实验数据的数据中间件层。

说明：本版不区分“自研模块”与“开源替代”，每一项能力直接采用对应的最佳开源方案作为该能力的最终实现，通过 Skill + MCP 封装统一挂载到 OpenScience Agent 架构下。系统核心自研部分仅剩 ECML 七步调度编排逻辑及湿数据中间件的业务规则设计。

---

## 1. 项目背景

参考资料：
- Deep Principle 官网: https://www.deepprinciple.com/
- Deep Principle 报道 (Startup of the Week): https://theinnovator.news/startup-of-the-week-deep-principle/
- Deep Principle MPA 材料基础模型报道: https://pandaily.com/deep-principle-mpa-materials-ai-2026
- Deep Principle 关于页面: https://www.deepprinciple.com/about.html
- Deep Principle World Economic Forum 介绍: https://www.weforum.org/organizations/deep-principle/
- OpenScience 项目主页: https://github.com/synthetic-sciences/openscience
- OpenScience 规划文档目录: https://github.com/synthetic-sciences/openscience/tree/main/docs/plans

---

## 2. 材料体系分类

| 电池组件 | 材料类型 | 表示方法 | 建模引擎（最终方案） |
|----------|----------|----------|----------------------|
| 正极材料 | 无机晶体 | CIF/POSCAR | CGCNN / M3GNet |
| 负极材料 | 无机晶体 / 碳基 | CIF/POSCAR | CGCNN / M3GNet |
| 固态聚合物电解质 (SPE) | 高分子 | PSMILES | PolymerGNN + polyBERT 指纹 |
| 无机固态电解质 | 无机晶体 | CIF/POSCAR | CGCNN / M3GNet |
| 液态电解质 | 有机小分子 | SMILES | RDKit 描述符 |

参考资料：
- 固态聚合物电解质机器学习综述: https://pubs.acs.org/doi/10.1021/acscentsci.2c01123
- AI 加速储能材料发现综述 (NAE): https://www.nae.edu/340918/Accelerated-Materials-Discovery-Through-the-Power-of-Artificial-Intelligence-for-Energy-Storage
- 电解质创新机器学习综述: https://www.sciencedirect.com/science/article/abs/pii/S2542529325001555

---

## 3. 系统总体架构（全能力整合版）

```text
battery-materials-agent (OpenScience Agent 架构直接扩展)
│
├── Router 层：判断材料类型，路由到高分子分支或晶体分支
│
├── 高分子分支 = PSMILES 工具链 + PolymerGNN + LLM 生成
│   ├── 表示: PSMILES + canonicalize_psmiles + RDKit
│   ├── 生成: 多 LLM API 规则重组 + 分子扩散模型
│   └── 预测: PolymerGNN(微调) + MatterSim-MT
│
├── 晶体分支 = pymatgen + CGCNN/M3GNet + Materials Project
│   ├── 表示: pymatgen 结构解析 + CIF/POSCAR
│   ├── 生成: Materials Project 候选库 + GNoME 晶体数据
│   └── 预测: CGCNN/MT-CGCNN(多任务) + M3GNet(结构优化)
│
├── 合成路径导航层 = ASKCOS （新增，对标 ReactNet）
│   └── 逆合成规划 + 反应条件推荐 + 产物预测 + 路径评分排序
│
├── 共享 DFT 验证层 = RDKit + PySCF + ASE
│
├── 实验闭环层（第一阶段） = FINDUS / RoboChem-Flex （新增，对标 ReactHTE）
│   └── 低成本自驱动实验硬件对接 + 高通量实验数据采集
│
├── 数据集成中间件层（新增）：第三方 LIMS/ELN/仪器软件湿实验数据接入
│   └── 从实验室管理系统、电子实验记录本、仪器厂商软件中读取/订阅数据，统一清洗与标准化
│
├── 共享数据层 = Materials Project API + PolymerGenome + GNoME 数据集 + 实验数据仓库
│
└── 共享 ECML 调度 Agent = OpenScience Agent runtime + 自定义七步循环编排逻辑
    (核心自研：ECML 调度 + 湿数据集成规则)
```

架构参考：
- MCP/A2A/Skill/Agent 三层架构: https://shuji-bonji.github.io/ai-agent-architecture/concepts/03-architecture
- MCP 构建 AI Agent 实践: https://developers.redhat.com/articles/2026/01/08/building-effective-ai-agents-mcp

---

## 4. 各能力模块的整合实现方案

### 4.1 高分子结构表示 —— 整合方案：PSMILES 工具链

- PSMILES 官方工具库: https://psmiles.readthedocs.io/
- PSMILES 规范化工具 (Ramprasad Group): https://github.com/Ramprasad-Group/canonicalize_psmiles
- RDKit 官方文档: https://www.rdkit.org/docs/GettingStartedInPython.html
- DeepChem 高分子表示教程: https://deepchem.io/tutorials/an-introduction-to-the-polymers-and-their-representation/
- RDKit 高分子 SMILES 处理讨论: https://stackoverflow.com/questions/76947745/smile-to-feature-vector-problem-for-polymers-in-rdkit

落地动作：
pip 安装 psmiles 库 + canonicalize_psmiles 仓库代码，封装成 MCP 工具，3–5 天完成。

---

### 4.2 晶体结构表示 —— 整合方案：pymatgen

- CGCNN 项目（内含结构解析参考代码）: https://github.com/txie-93/cgcnn

落地动作：
pip 安装 pymatgen，封装 CIF 解析与 Materials Project API 查询接口，3–5 天完成。

---

### 4.3 高分子性质预测 —— 整合方案：PolymerGNN + MatterSim-MT

- MatterSim 官方介绍 (微软): https://www.microsoft.com/en-us/research/blog/mattersim-a-deep-learning-model-for-materials-under-real-world-conditions/
- MatterSim-MT 多任务基础模型: https://arxiv.org/html/2605.07927v1
- PolymerGNN 开源仓库 (含训练代码): https://github.com/owencqueen/PolymerGNN
- PolymerGenome 参考数据平台: https://www.polymergenome.org/reference
- Polymer Genome 预测方法论文: https://pubs.aip.org/aip/jap/article/128/17/171104/1062836/Machine-learning-predictions-of-polymer-properties
- 化学信息神经网络预测固态电解质离子电导率: https://pubs.acs.org/doi/10.1021/acscentsci.2c01123

落地动作：
clone PolymerGNN 仓库，用自有小样本数据微调；MatterSim-MT 走 API 调用做兜底，1 周内跑通。

---

### 4.4 晶体性质预测 —— 整合方案：CGCNN + MT-CGCNN + M3GNet

- CGCNN 官方实现: https://github.com/txie-93/cgcnn
- MT-CGCNN 多任务版本: https://github.com/soumyasanyal/mt-cgcnn
- MT-CGCNN 论文: https://arxiv.org/abs/1811.05660
- M3GNet: https://github.com/materialyzeai/m3gnet
- crystal-gnn 基准测试框架 (集成 CGCNN/SCHNET/ALIGNN): https://github.com/hspark1212/crystal-gnn
- CGNN 原始实现: https://github.com/Tony-Y/cgnn
- CGCNN 教程笔记本: https://github.com/Diego-2504/CGCNN_tutorial
- AI 晶体材料资源合集: https://github.com/WanyuGroup/AI-for-Crystal-Materials
- 开源锂离子正极 ML 筛选 pipeline 案例:
  https://www.reddit.com/r/ScientificComputing/comments/1taa7xo/i_built_an_opensource_ml_pipeline_for_lithiumion/

落地动作：
用 crystal-gnn 跑通 CGCNN 基准，MT-CGCNN 做多任务预测，M3GNet 做结构 relaxation，1–1.5 周完成。

---

### 4.5 高分子候选生成 —— 整合方案：多 LLM API + 开源分子扩散模型

- Awesome Molecular Diffusion Models 资源合集: https://github.com/azureleon1/awesome-molecular-diffusion-models
- GPT 与扩散模型对比设计聚合物电解质论文: https://www.nature.com/articles/s41524-024-01470-9
- 机器学习辅助设计聚合物电解质案例:
  https://www.advancedsciencenews.com/machine-learning-helps-create-polymer-electrolyte-for-batteries/
- 相关讲解视频: https://www.youtube.com/watch?v=BKYQWzXOB20
- 分子扩散模型综述: https://arxiv.org/html/2502.09511v1

落地动作：
用现有 LLM API 写生成 prompt 模板，1 周内产出第一版生成器；扩散模型作为后续增强项。

---

### 4.6 晶体候选生成 —— 整合方案：Materials Project API + GNoME 数据

- Materials Project Battery Explorer: https://next-gen.materialsproject.org/batteries
- GNoME 晶体发现项目 (DeepMind): https://deepmind.google/blog/millions-of-new-materials-discovered-with-deep-learning/
- 开源电池数据集合集: https://github.com/lappemic/open-source-battery-data
- 电池材料自动生成数据库论文: https://www.nature.com/articles/s41597-020-00602-2

落地动作：
调用 Materials Project API 检索候选结构，叠加 GNoME 数据做二次筛选，1 周内完成。

---

### 4.7 合成路径导航 —— 整合方案：ASKCOS（新增，对标 ReactNet）

- ASKCOS 开源代码仓库: https://github.com/ASKCOS/ASKCOS
- ASKCOS 论文 (Acc. Chem. Res. 2025): https://pubs.acs.org/doi/10.1021/acs.accounts.5c00155
- ASKCOS 技术综述 (arXiv): https://arxiv.org/html/2501.01835v1
- ASKCOS 文献解读: https://www.themoonlight.io/en/review/askcos-an-open-source-software-suite-for-synthesis-planning
- MIT ASKCOS 项目主页:
  https://jclinic.mit.edu/research-project/askcos-open-source-data-driven-synthesis-planning/
- 路径感知逆合成模板方法: https://pubs.acs.org/doi/10.1021/acs.jcim.6c01458
- LLM 驱动多分支路径搜索算法 MBRPS: https://arxiv.org/html/2501.08897v1

落地动作：
部署 ASKCOS（Docker 镜像），将 Tree Builder 接口封装为 MCP 工具：
- 输入：生成层候选分子 / 高分子单体 SMILES
- 输出：可行合成路线 + 推荐反应条件 + 路径评分
在 ECML 循环中插入“合成可行性打分”环节，预计 1 周对接完成。
（注：ASKCOS 面向小分子/有机合成设计，高分子单体合成路径可直接复用；聚合反应路径规划为二期优化项。）

---

### 4.8 实验闭环第一阶段 + 湿数据中间件 —— 整合方案：FINDUS / RoboChem-Flex + 数据集成中间件（新增，对标 ReactHTE）

目标：同时打通“软件决策 → 硬件执行 → 数据回传”和“第三方软件系统湿实验数据接入 → 数据清洗标准化 → Agent 可用”的双重闭环。

#### 4.8.1 自驱动实验硬件层（FINDUS / RoboChem-Flex）

- FINDUS 低成本 3D 打印自驱动实验室: 相关论文可见 RSC 的自驱动实验室系列[web:19]
- RoboChem-Flex 低成本模块化自驱动化学实验室: https://www.nature.com/articles/s44160-026-01053-0
- 自驱动实验室资源合集 (Acceleration Consortium): https://github.com/AccelerationConsortium/awesome-self-driving-labs
- 开源实验室机器人工具 (OpenTrons 等): https://amchagas.github.io/open-source-toolkit/

硬件落地动作（第一阶段范围）：
1. 按 FINDUS 方案搭建最小实验台，采用 3D 打印+开源组件方案，控制硬件成本与复杂度。
2. 打通数据流：ECML Agent 输出候选配方 → 硬件执行简单合成/表征 → 实验结果写入本地或云端数据源。
3. 初期只覆盖 1–2 类易自动化表征实验（如离子电导率、电化学测试），逐步扩展品类。
4. 优先选用 awesome-self-driving-labs 合集中已有 Python 驱动设备，减轻驱动开发负担。

预计工期：2–3 周（软件对接），硬件采购/组装另计。

#### 4.8.2 湿数据中间件层（第三方软件数据接入）

需求：实验数据往往分散在 LIMS、ELN（电子实验记录本）、仪器厂商软件（如电化学工作站、光谱仪自带软件）以及已有自驱动实验平台中，需要一个专门的中间件来统一接入、清洗和标准化为 Agent 可用的结构化数据。

参考实践：
- awesome-self-driving-labs 合集中列出多种“软件-硬件-数据”整合方案，强调通过 Python 中间件将不同数据源接入统一实验数据仓库[web:78]
- OpenTrons 等开源实验室机器人平台提供了用于数据记录和 API 集成的开源工具，可作为设计中间件的接口参考[web:88]

中间件功能设计：
1. **数据源适配器层**：
   - LIMS/ELN 适配器：通过 REST/GraphQL API 或数据库读写，将样品信息、实验条件、测量结果拉取到统一中间件。
   - 仪器软件适配器：
     - 文件监听模式：监控指定目录下的 CSV/Excel/文本报表文件，自动解析结构化数据。
     - 厂商 API 模式：利用厂商提供的 SDK/HTTP API 获取原始测量数据与元数据。
   - 自驱动平台适配器：针对 FINDUS/RoboChem-Flex 以及未来其他平台，封装其 Python/HTTP API，将实验结果推送到中间件。

2. **数据清洗与标准化层**：
   - 统一定义实验结果数据模型（如样品 ID、配方、工艺参数、测试方法、测试结果、误差范围、时间戳等）。
   - 对不同来源的数据进行列名映射、单位换算、异常值检测、空值处理。
   - 生成统一的 JSON/Parquet/表格式数据，写入“实验数据仓库”。

3. **Agent 接入层 (MCP 工具)**：
   - 提供按条件查询接口：如“查询某类固态聚合物电解质在特定温度下的离子电导率测试结果”。
   - 提供订阅/推送接口：在新实验结果落库时，触发对性质预测模型的增量更新或对生成策略的调参。
   - 为 ECML Agent 提供“get_experiment_results”、“subscribe_experiment_updates”等工具调用。

技术选型建议：
- 使用 Python+FastAPI 构建中间件服务，方便与你现有栈集成。
- 数据存储建议使用 PostgreSQL + Parquet 文件（方便后续用 pandas/Polars 分析）。
- 接口描述遵循 MCP 规范，便于在 OpenScience Agent 中注册为工具。[web:40]

预计工期：1–2 周（不含与具体第三方系统的业务对接时间）。

---

### 4.9 计算验证 —— 整合方案：RDKit + PySCF + ASE

- RDKit: https://www.rdkit.org/docs/GettingStartedInPython.html
- PySCF、ASE：标准量子化学/材料模拟开源工具

落地动作：
封装统一接口：结构优化 + 单点能 + HOMO-LUMO + 形成能，3–5 天完成，供晶体/分子两分支共用。

---

### 4.10 ECML 调度编排 —— 整合方案：OpenScience Agent runtime + 自定义循环

七步完整版循环（加入合成可行性与实验/湿数据反馈后的 ECML）：

1. Agent 根据目标判断走高分子/晶体分支。
2. 调用对应生成层产出 N 个候选结构。
3. 调用 ASKCOS 判断候选合成可行性，过滤不可合成候选。
4. 调用对应性质预测层打分，筛出 Top-K。
5. 对 Top-K 调用 DFT 验证层做精确计算。
6. （可选）将验证通过的候选送入 FINDUS/RoboChem-Flex 实验闭环执行真实合成与表征，结果通过中间件写入实验数据仓库。
7. ECML Agent 通过中间件查询最新实验数据，与计算/预测结果对比，分析成功/失败模式，调整下一轮生成与筛选策略，循环迭代。

参考：
- OpenScience Agent 架构: https://github.com/synthetic-sciences/openscience
- AI Agent 架构 (Skills/MCP/Tools/Subagents) 讲解:
  https://www.linkedin.com/posts/reshmawithai_aiagents-agenticai-artificialintelligence-activity-7467807615322988544-62iO

落地动作：
在 OpenScience 中新增 battery-materials 专家角色，用 system prompt + 工具调用顺序定义七步循环，1.5–2 周完成。

---

## 5. 完整开发路线时间表（补全版）

| 阶段 | 任务                         | 整合的开源方案                                       | 预计工期     |
|------|------------------------------|------------------------------------------------------|--------------|
| 1    | Router 层 + 晶体表示         | pymatgen                                             | 3–5 天       |
| 2    | 高分子表示                   | PSMILES + canonicalize_psmiles                       | 3–5 天       |
| 3    | 晶体性质预测                 | CGCNN + MT-CGCNN + M3GNet + crystal-gnn              | 1–1.5 周     |
| 4    | 高分子性质预测               | PolymerGNN + MatterSim-MT                            | 1 周         |
| 5    | 高分子候选生成               | 多 LLM API + 分子扩散模型                            | 1 周         |
| 6    | 晶体候选生成                 | Materials Project API + GNoME 数据                   | 1 周         |
| 7    | 合成路径导航（ReactNet）     | ASKCOS                                               | 1 周         |
| 8    | 计算验证层                   | RDKit + PySCF + ASE                                  | 3–5 天       |
| 9    | 实验闭环第一阶段（ReactHTE） | FINDUS / RoboChem-Flex                               | 2–3 周       |
| 10   | 湿数据中间件（新增）         | Python+FastAPI 中间件 + 第三方系统适配器            | 1–2 周       |
| 11   | ECML 七步调度整合            | OpenScience Agent runtime（自定义编排）             | 1.5–2 周     |
| 12   | 端到端测试（含实验闭环&湿数据） | 全部整合                                           | 1–2 周       |

总预计工期：约 15–18 周。软件部分可并行压缩至 10–12 周，实验闭环硬件搭建与湿数据中间件对接可与软件开发并行推进。

---

## 6. 数据资源汇总

| 数据集/平台                     | 用途                          | 链接                                                                 |
|---------------------------------|-------------------------------|----------------------------------------------------------------------|
| Materials Project Battery Explorer | 晶体候选材料 + 电压曲线   | https://next-gen.materialsproject.org/batteries                      |
| Materials Project 电池数据发布  | 历史批量数据集               | https://newscenter.lbl.gov/2016/06/08/massive-trove-battery-molecule-data-released-public/ |
| 电池材料自动生成数据库          | 结构化属性数据               | https://www.nature.com/articles/s41597-020-00602-2                  |
| 开源电池数据集合集              | 多源数据索引                 | https://github.com/lappemic/open-source-battery-data                 |
| PolymerGenome                   | 高分子性质数据               | https://www.polymergenome.org/reference                              |
| GNoME 发现晶体数据              | 220 万新晶体结构             | https://deepmind.google/blog/millions-of-new-materials-discovered-with-deep-learning/ |
| ASKCOS 反应数据库               | 逆合成模板/反应条件数据      | https://github.com/ASKCOS/ASKCOS                                     |

---

## 7. 关键风险与注意事项

1. 高分子与晶体两分支的表示方法完全独立，不要共用同一 Embedding 空间，分别微调各自开源模型。
2. ECML 调度逻辑（4.10 节）和湿数据中间件业务规则是系统唯一真正需要自研的部分，建议先跑通简化版再迭代复杂版。
3. Materials Project API 有调用频率限制，建议本地缓存数据，避免重复请求。
4. PySCF 计算成本较高，仅用于初筛后 Top 候选的精确验证，不要对全候选池跑 DFT。
5. ASKCOS 主要面向有机小分子合成设计，高分子聚合反应路径规划学界仍在发展中；第一阶段将其用于单体/前驱体合成路径判断即可。
6. 实验闭环第一阶段务必控制范围，只打通 1–2 类简单表征实验的数据流，避免一次性追求全流程自动化导致周期失控。
7. FINDUS/RoboChem-Flex 目前更多验证于小分子化学合成场景，用于电池材料（尤其固态合成、高温烧结工艺）时可能需要额外硬件改造，建议先验证液相/电化学表征，再扩展到复杂工艺。
8. 湿数据中间件对接第三方系统时，需特别注意：
   - 数据 schema 不一致（字段命名、单位、缺失值）需要明确的映射与清洗规则。
   - 时间戳与批次信息必须精确对齐，否则很难将实验结果与具体生成/预测迭代对应起来。
   - LIMS/ELN/仪器软件可能存在权限与合规限制，需与企业 IT/法务协同确认数据访问边界。

---

## 8. 能力对标一览（全覆盖整合版）

| Deep Principle 能力            | 本系统整合实现（最终方案）                                                                                                 |
|--------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| ReactGen (生成)                | 多 LLM API 生成 + 分子扩散模型 + Materials Project/GNoME 候选库检索                                                        |
| MPA (性质预测基础模型)        | PolymerGNN + MatterSim-MT（高分子） / CGCNN + MT-CGCNN + M3GNet（晶体）                                                     |
| Reactify (精密计算)           | RDKit + PySCF + ASE                                                                                                         |
| ReactControl / ReactBO (筛选优化) | ECML 调度 Agent 内置 Top-K 评分与筛选逻辑                                                                              |
| ReactNet (合成路径导航)       | ASKCOS 开源逆合成规划套件（逆合成模型 + MCTS 路径搜索 + 条件推荐 + 路径评分）                                               |
| ReactHTE (实验闭环)           | FINDUS / RoboChem-Flex 开源自驱动实验平台（第一阶段：软硬件最小闭环打通） + 湿数据中间件层，从第三方软件系统接入实验数据 |
| ECML 统一范式                 | OpenScience Agent runtime + 自定义七步循环编排（系统核心自研部分，仅此一处）                                                |

本版本已实现对 Deep Principle Agent Mira 六大核心模块的全能力覆盖，并额外增强了湿数据中间件层，全部采用开源方案整合落地，系统核心自研部分收敛于 ECML 七步调度与数据集成规则设计。
