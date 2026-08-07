# 61项技能完整详解：Prompt协议与Python实现逻辑

> 生成日期：2026-07-31

---

## 阅读指南

- **Prompt/协议列**：描述 SKILL.md 中定义的 Agent 行为协议——Agent 如何按阶段编排任务、提问策略、确认门控
- **Python 实现逻辑列**：描述技能背后的 Python 脚本/库的具体实现——函数调用链、核心算法、API 交互模式
- "—"表示该技能不使用 Python 脚本

---

## 类别 A：AI Agent 纯编排型（闭源 · 无 Python）

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 1 | **brainstorming** | A | 5阶段协议：①框架决策（目标/资源/约束/成功标准）；②变量映射（可控变量/观测读数/固定约束/未知假设，含6个学科翻译模板）；③发散（2-4条不同路径，每条含核心机制/资源缺口/关键变量/失败模式/最快验证方法）；④共享标准收敛（默认6维度：资源匹配/信息增益/时间成本/技术风险/可重复性/下游价值）；⑤输出+可选HTML看板（`visual-companion.md`） | —（可选 `generate_image` 生成看板） |
| 2 | **scientific-writing** | A | 7阶段协议：①文档类型识别（研究论文/综述/基金/摘要/回复信）；②结构选择（IMRAD/主题组织/基金结构）；③逐节撰写（每节有子协议：Introduction漏斗→Methods可重复性→Results客观性→Discussion解释）；④图表创建（300+DPI/色盲友好）；⑤引用管理（验证一致性）；⑥语言清晰度（主动语态/精确/简洁）；⑦投稿前检查清单 | `citation_checker.py`（验证引用一致性）<br>`readability_analyzer.py`（分析文本复杂度/改进建议）<br>`word_counter.py`（按节统计字数）<br>`figure_generator.py`（从数据生成图表）<br>`table_formatter.py`（格式化表格） |
| 3 | **peer-review** | A | 7阶段协议：①初步评估（核心问题/主要发现/科学性/适用性）；②逐节详细审阅（摘要/引言→方法→结果→讨论→参考文献，每节有检查清单）；③方法学与统计严谨性（统计评估+实验设计+计算生物信息）；④可重复性与透明性（数据/代码/报告标准CONSORT/STROBE）；⑤图表评估（质量+完整性）；⑥伦理考量（人体/动物/科研诚信）；⑦写作质量 | —（PDF审阅时用 `pdf_to_images.py` 转换PPT为图像逐页检查） |
| 4 | **patent-disclosure** | A | 4功能模块：①起草交底书（8节固定结构：技术领域/背景/目的/技术方案/关键条件表/副作用控制/优势效果/实施例+对比例+附录）；②合规检查（3子模块：完整性缺口/模糊语言/技术因果链，含CNIPA特有规则）；③技术扩展（核心特征分层→上位概括建议→替代实施方案→合规警报）；④发明亮点摘要（为IP律师会议准备）<br>安全规则：SMILES用`<SMILES>`标签包裹（不入最终文档），禁止编造数据和法规引用 | — |
| 5 | **humanizer / humanizer-zh** | A | 基于Wikipedia "Signs of AI writing"指南的检测→修复协议：检测模式含膨胀象征/宣传语言/肤浅-ing分析/模糊归因/破折号滥用/三连规则/AI词汇/否定排比/过度连接短语，逐项修复 | — |
| 6 | **ai-writing-detection** | A | 提供AI写作检测词汇表、结构模式、模型特定指纹、假阳性预防指南 | — |
| 7 | **help / help-en** | A | SciClaw产品知识库检索协议（中文/英文分别触发）：功能说明/设置/积分计费/套餐/集成/退款/发票 | — |

---

## 类别 B：深度研究/文献工具链（闭源 · Research CLI + 平台工具）

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 8 | **deep-research** | B | **7阶段v3.2协议**（最复杂技能之一）：<br>Phase 1: Contract & Plan — 写 `workflow.json` + `research-contract.json` + `search/plan.json`，证据需求标 `core/material/contextual`，停止等待用户显式批准<br>Phase 2: Retrieval (2-6轮) — English用 `research` CLI，中文用 `search_scholar`，专利用 `search_patents`，每轮后更新 `coverage-matrix.json`，写 `gap-exhaustion.jsonl`<br>Phase 3: Evidence Structure — 构建 `corpus/manifest.json` + `evidence/cards.json` + `contradictions.jsonl`<br>Phase 4: Report Plan — `answer-matrix.json` → `outline.md` → `section-readiness.json`，feasibility计算<br>Phase 5: Write Section-by-Section — 每H2独立生成，`section-receipts.jsonl`<br>Phase 6: Audit & Review — `claim-inventory.jsonl` + Red Team<br>Phase 7: Deliver — `verify-ref` → `final/report.md` | `scripts/dr_check.py`（9637B）：v3.2核心校验器<br>• `validate-contract` — JSON Schema验证<br>• `validate-search-plan` — 搜索计划验证<br>• `validate-stop-decision` — 停止决策验证<br>• `validate-coverage` — 覆盖率矩阵验证<br>• `freeze-candidates` — 冻结候选文献<br>• `validate-corpus/evidence/outline/section-readiness/report-feasibility` — 各阶段门控<br>• `build-section-context` — 组装节上下文<br>• `prepare-report-plan/precommitment` — 准备报告计划<br>• `validate-delivery/release` — 交付前最终检查<br>• `audit-completion` — 完整性审计<br>`shared_quality.py`（87KB）：共享质量逻辑<br>`v32_quality.py`（92KB）：v3.2特定质量逻辑<br>`evidence_quality.py`（8KB）：证据质量评估 |
| 9 | **literature-review** | B | **7阶段v4协议**：<br>Phase 1: Confirm Protocol — 写 `00_protocol.md` + `protocol.json`（schema v4）+ `01_search-plan.md`，支持7种综述类型（narrative/scoping/systematic/rapid/integrative-critical/state-of-art/umbrella）<br>Phase 2: Search & Citation Tracing — English用 `research` CLI，中文用 `search_scholar`+`web_search`，引文追踪用 `openalex_citation_network.py`<br>Phase 3: Screen Records — 双独立流程（系统综述），`02_screening.jsonl` → `03_included.jsonl`<br>Phase 4: Full Text & Evidence — `research fetch` + `web_fetch`，写 `evidence/cards/*.md`<br>Phase 5: Synthesis Plan — `claim-map.jsonl` + `section-plan.jsonl` + `budget-baseline.json`<br>Phase 6: Draft & Verify — 逐节生成，每节独立验证声明<br>Phase 7: Citations & Export — `research cite` → `FINAL_文献综述.md` | `phase_gate.py`（44KB）：阶段门控系统<br>• `--enter search/screening/evidence/synthesis/writing/final/complete/limited` — 各阶段前置条件检查<br>`status_scan.py`（4KB）：扫描运行目录状态，报告缺失/无效工件<br>`section_gate.py`（1.2KB）：单节门控验证<br>`assemble_draft.py`（1.5KB）：确定性拼接章节为完整手稿<br>`openalex_citation_network.py`（1.9KB）：OpenAlex引文网络API<br>`freeze_budget_baseline.py`（4.4KB）：冻结写作预算基线<br>`migrate_protocol_v2_to_v3.py` / `v3_to_v4.py`：协议版本迁移<br>`litreview/manuscript.py`（40KB）：手稿组装<br>`litreview/budget.py`（4KB）：预算分配<br>`litreview/length_control.py`（3.5KB）：长度控制<br>`litreview/openalex_citations.py`（25KB）：引文检索 |
| 10 | **research-literature-search** | B | 搜索计划确认→`research` CLI执行（search→import→dedupe→resolve→enrich→filter→rerank）→导出HTML/JSON/CSV/BibTeX | 通过 `bash` 调用 `research` CLI 管道 |
| 11 | **research-fetch** | B | DOI/arXiv/PMID/PMCID→检查内置OA源→下载PDF→记录来源/许可/哈希/大小→输出JSON/CSV报告 | 通过 `bash` 调用 `research fetch` 命令 |
| 12 | **citation-check-format** | B | DOI/PMID/BibTeX→`research verify-ref`验证→格式转换（BibTeX/RIS/NBIB/ENW） | 通过 `bash` 调用 `research verify-ref` + `research cite` |
| 13 | **freshness-verification** | B | 提取时效声明→`web_search`+`web_fetch`对比一手来源→判断是否过时 | —（使用平台 `web_search`/`web_fetch`） |
| 14 | **patent-search** | B | 用户需求→Google Patents检索式（支持TI=/AB=/CPC=/NEAR/N语法）→`search_patents`执行→结果分析/过滤/PDF下载 | —（使用平台 `search_patents` 工具，底层调用 Google Patents API via SerpAPI） |

---

## 类别 C：Mira Compute 云端异步计算

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 15 | **dp-yamo** | C | **分子量子化学计算**<br>前置检查：Step 0分子确认（fast path: 标准分子直通, 否则渲染2D结构确认）→ Step 1内置工作流路由（CREST构象/BP-Hvap/redox→使用内置workflow）→ Step 2/3参数确认（DFT级别/泛函/基组/溶剂/超时）<br>**Mira Compute提交流程**：写1个CSV→`compute_submit`一次→轮询`compute_get_status`→终端后`compute_sync_results`<br>**本地执行规则（非Mira任务）**：写.py脚本→`nohup python -u`→主动轮询PID/log/结果文件<br>**强制规则**：yamol推导电荷/多重度（禁止手动），DFT仅via VOLCQC（GPU4PYSCF） | **云端路径**：输入CSV + `compute_submit(compute_type="crest_sampling"/"bp_hvap")` → 等待终端状态 → `compute_sync_results` 下载结果<br>**本地路径 (非Mira任务)**：<br>`yamol(smiles)` → 解析SMILES/文件为分子对象（含adj_mat/bond_mats/q/fc/geo等属性）<br>`mol.opt(calculator="xtb")` → XTB几何优化（封装GFN-xTB shell调用）<br>`mol.conf_sample(method="crest")` → MTD构象采样（shell-out到crest二进制）<br>`mol.evaluate("energy", method="dft")` → DFT单点能(VOLCQC)<br>`mol.evaluate("redox", method="xtb")` → XTB氧化还原电位<br>**VOLCQC包装器**（底层GPU4PYSCF）：<br>`load_molecules(from_list=[xyz_strings])` → `execute(task_type="opt"/"sp"/"pysisyphus")` → `get_energy(name)` / `get_final_structure(name)` |
| 16 | **dp-yamo-pbc** | C | 周期性DFT协议：晶体/表面/能带/DOS/声子/Bader电荷/NEB/功函数等。路由：CIF构→ABACUS | `compute_submit(compute_type="abacus"/"mace_bfgs"/"crest_sampling")` → 轮询 → 下载结果 |
| 17 | **esmfold2** | C | **蛋白质结构预测**<br>输入分类→`recommend-model`→预测门控（用户确认模型+候选数）→`POST /v1/fold`→轮询→下载PDB/mmCIF/PAE/distogram<br>多采样：`--num-diffusion-samples 3`→`candidate_ranking.csv`+Board<br>MSA：`build-msa-request`→`model=esmfold2` | `scripts/esmfold2_client.py` → 导入 `esmfold2_skill/` 包：<br>`cli.py`（17KB）：CLI入口，`fold`/`recommend-model`/`validate-request`/`summarize-run`等子命令<br>`api.py`（4KB）：异步POST `/v1/fold`，轮询 `GET /v1/jobs/{id}`，下载artifacts<br>`request_builder.py`（7.6KB）：构建请求JSON（蛋白质/DNA/RNA/配体/修饰/共价键/MSA模板）<br>`recommendation.py`（15KB）：模型推荐逻辑（fast vs full，候选数建议）<br>`validation.py`（8.2KB）：请求验证<br>`ranking.py`（4.5KB）：多候选排名<br>`candidate_csv.py`（3KB）：生成ranking CSV<br>`board_artifact.py`（15.6KB）：生成Board JSON<br>`manifest_builder.py`（18.9KB）：构建 `agent_manifest.json`<br>`report_writer.py`（9.5KB）：生成 `report.md`<br>`plot_orchestrator.py`（15.5KB）：QC图表生成<br>`visualization.py`（21.7KB）：可视化<br>`structure_delivery.py`（7.7KB）：结构文件输出 |
| 18 | **material-property-prediction** | C | SMILES/名称→42种性质预测（沸点/熔点/临界常数/粘度/导热率等）via MPA模型HTTP服务 | HTTP API调用：输入SMILES→服务端MPA模型推理→返回JSON性质值 |
| 19 | **protein-ligand-binding-mode-analysis** | C | PDB码+配体ID→ProteinsPlus/PoseEdit/Protoss REST API→InteractionDrawer JSON→Board可视化 | 调用ProteinsPlus外部REST API（学术公开）：<br>POST PoseEdit → 获取结合模式分析JSON<br>POST Protoss → 加氢/质子化处理<br>生成CSV+2D相互作用图+3D结构Board |

---

## 类别 D：Mira Inference 云端推理服务

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 20 | **reactnet** | D | **过渡态搜索与反应网络**<br>入口路由：Step 0（发现反应/枚举）→ Step 1（单反应`predict_ts`/`locate_ts`）→ Step B（批量`run_ts_search`）→ Step N（多层网络`run_network`≤3层）→ Step V（查看已有网络图）→ Step R（DFT精修）<br>每步前强制渲染2D结构确认 | **本地工具**：<br>`predict_ts(rxn_smiles)` → React-OT API调用，输出reactot_ts.xyz<br>`Reaction.locate_ts(do_sampling=True)` → GSM→TSOPT→IRC全流程（xTB/g-xTB），返回TS列表含DE_F/DE_B（kcal/mol）<br>`EnumerateReactions(max_break_bonds, max_form_bonds)` → 图枚举算法生成所有候选反应（`gen_prods`）<br>**Mira Inference路径**：<br>`mira_inference_upload_file` → 提交`run_ts_search`（批量TS，xTB/g-xTB）<br>`mira_inference_call` POST `/api/v1/jobs/run_network` → 多层反应网络<br>轮询 `GET /api/v1/jobs/{id}` + `/log`<br>`mira_inference_download_file` → 下载 `cli.log`/`IRC-record-processed.txt`/`final_TSs.p`<br>**DFT精修**：本地 `python -m reactnet.workflows.yarp_qc config.yaml` → VOLCQC DFT tsopt+IRC<br>`scripts/summarize_graph_reactions.py`（8.3KB）：从CSV生成完整反应清单 |
| 21 | **multiwfn-analysis** | D | ESP分析/分子表面/HOMO-LUMO/轨道立方体/Batch分析/Board注册 | Mira Inference云端VMD Runner + 本地Multiwfn脚本自动化：<br>`mira_inference_upload_file` → 提交渲染任务 → `mira_inference_download_file` → 获取PNG渲染结果 |

---

## 类别 E：本地 Python 科学计算

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 22 | **rdkit** | E | 12个功能模块协议：①分子IO；②清洗与验证（13步Sanitize）；③分子分析与属性（原子/键/环/手性/片段）；④描述符（MW/LogP/TPSA/氢键给受体/可旋转键/芳香环数，`CalcMolDescriptors`批量）；⑤指纹与相似性（Morgan/MACCS/原子对/拓扑扭转/Avalon, Tanimoto/Dice/Cosine）；⑥子结构搜索与SMARTS；⑦化学反应（SMARTS反应式, `RunReactants`）；⑧2D/3D坐标生成（ETKDG嵌入, UFF/MMFF优化）；⑨可视化（`MolDraw2DCairo`, `MolsToGridImage`）；⑩分子修改（加氢/去氢/Kekulize/替换子结构）；⑪分子哈希（Murcko/CanoSMILES/Regioisomer）；⑫药效团特征 | `Chem.MolFromSmiles(smiles)` → 解析+Sanitize 13步<br>`Descriptors.CalcMolDescriptors(mol)` → 完整描述符字典<br>`rdFingerprintGenerator.GetMorganGenerator(radius=2)` → ECFP类圆形指纹<br>`AllChem.EmbedMultipleConfs(mol, numConfs=10)` → ETKDG 3D嵌入<br>`AllChem.MMFFOptimizeMolecule(mol)` → MMFF94力场优化<br>`Draw.MolDraw2DCairo(300,300)` → Cairo渲染PNG<br>`FilterCatalog` → 官方PAINS过滤（480+警报，非硬编码SMARTS）<br>`scripts/molecular_properties.py`（7KB）<br>`scripts/similarity_search.py`（9.5KB）<br>`scripts/substructure_filter.py`（13KB） |
| 23 | **datamol** | E | RDKit的Pythonic封装，简化API。使用`dm.to_mol()`/`dm.standardize_mol()`/`dm.descriptors`等简化接口 | `dm.to_mol(smiles)` → 内部调用 `Chem.MolFromSmiles`<br>`dm.standardize_mol(mol)` → 标准化管道（断开金属/标准化互变/中和电荷等）<br>`dm.descriptors.mw(mol)` → 封装RDKit描述符<br>`dm.parallelized(fn, inputs)` → 并行处理 |
| 24 | **chem-properties** | E | **5模块路由**：<br>M1（标准常数）→ sources优先级：`query_chemicals.py`→`query_stenutz.py`→`/pubchem-database`→`/yape-molecular`→`/dp-yamo`<br>M2（T/P依赖性质）→ `query_chemicals.py <T> [P]` + `query_nist_fluid.py` + `query_nist_antoine.py`<br>M3（VLE）→ IPDB Wilson/NRTL查询 → UNIFAC回退<br>M4（多组分闪蒸）→ `thermo.FlashVL` (PR EOS)<br>M5（溶解度）→ Henry定律/van't Hoff/Hansen/Hildebrand | `scripts/query_chemicals.py`（6.5KB）：DIPPR/Perry's数据库 ~340化合物 → 查询Tm/Tb/Tc/Pc/Vc/ω/ΔHf°/Tflash/LFL/UFL等<br>`scripts/query_stenutz.py`（2.4KB）：Stenutz溶剂数据库 ~200溶剂 → Hansen/Hildebrand溶解度参数<br>`scripts/query_nist_fluid.py`（8.9KB）：NIST REFPROP 76流体 → H/S/声速<br>`scripts/query_nist_antoine.py`（5.8KB）：NIST Antoine蒸气压参数<br>M3: `thermo.interaction_parameters.IPDB` → `get_ip_asymmetric_matrix('ChemSep Wilson', CASs, 'aij')`<br>M4: `thermo.eos_mix.PRMIX` + `thermo.phases.CEOSGas/CEOSLiquid` + `FlashVL.flash(T,P,zs)` → 返回VF/y/x<br>M5: `chemicals.Hfus(cas)` / `chemicals.solubility_parameter(T, Hvapm, Vml)` |
| 25 | **chem-process** | E | 反应工程协议：反应热估算/Arrhenius拟合/反应器ODE求解/液-液萃取Kremser/精馏FUG/扩散系数/吸附动力学PFO/PSO | `chemicals` 库反应热力学 + `thermo` 库传递性质<br>`scipy.integrate.solve_ivp` → 反应器ODE<br>`scipy.optimize.curve_fit` → 动力学参数拟合 |
| 26 | **battery-simulation** | E | **三轨道路由**：<br>Track 0：确认参数集（Chen2020/OKane2022/Prada2013等14个预设，每个对应真实电池实测参数）<br>P2D轨道：模型选择SPM/SPMe/DFN(P2D)→基本仿真→实验协议(CC/CV/Cycling)→参数修改→模型比较→变量提取→热仿真→C-rate扫描<br>ECM轨道：Thevenin等效电路→`references/ecm.md`<br>PyBOP轨道：参数辨识→`references/pybop.md`<br>**强制规则**：Parameter sweep三强制联调（厚度/孔隙率/温度） | `pybamm.lithium_ion.DFN()` → Doyle-Fuller-Newman电化学模型<br>`pybamm.ParameterValues("Chen2020")` → 加载LG M50实测参数集<br>`pybamm.Simulation(model, param)` → `sol.solve([0,3600])` → 求解PDE系统<br>`pybamm.Experiment([...])` → CC/CV/Cycling实验协议解析<br>`sol["Terminal voltage [V]"].entries` → 提取时域结果<br>`pybamm.lithium_ion.DFN(options={"thermal":"lumped"})` → 集总热模型<br>`matplotlib.use('Agg')` + `plt.savefig` → 非交互渲染PNG<br>ECM: `pybamm.equivalent_circuit.Thevenin()`<br>PyBOP: `pybop.optimisation` → 拟合实测数据 |
| 27 | **fluidsim** | E | CFD仿真协议：Navier-Stokes 2D/3D/浅水方程/分层流/湍流/涡动力学，FFT伪谱法 | `numpy.fft` 伪谱法求解PDE → 时间推进RK4/ETDRK4 → 湍流模型LES/DNS → `matplotlib` 可视化 |
| 28 | **lammps** | E | **三路径分类**：Path A（晶体/无机）→ pymatgen+LammpsData；Path B（有机分子/聚合物）→ mbuild+foyer+OPLS-AA；Path C（生物分子）→ CHARMM/AMBER预构拓扑<br>**5步协议**：Step 0系统分类→Step 1数据文件→Step 2输入脚本→Step 3验证（语法/物理/协议）→Step 4模拟阶段（Minimization→NPT/NVT→Production）→Step 5轨迹分析（OVITO/MDAnalysis）<br>**力场决策规则**：金属→EAM；离子氧化物→Buckingham+Coulomb；共价晶体→Tersoff/SW/ReaxFF；有机→OPLS-AA | `scripts/generate_input.py`（26KB）：程序化生成LAMMPS输入脚本<br>`scripts/validate_syntax.py`（25KB）：语法验证<br>`scripts/validate_physics.py`（33KB）：物理验证（时间步/单位/力场匹配）<br>`scripts/universal_validator.py`（20KB）：通用验证<br>`scripts/parse_input.py`（20KB）：输入解析<br>`scripts/commands_index.json`（266KB）：516条LAMMPS命令索引<br>`scripts/commands_syntax.json`（51KB）：命令语法<br>**数据准备**：<br>Path A: `pymatgen.io.lammps.data.LammpsData.from_structure(struct, atom_style="atomic")`<br>Path B: `mb.load(smiles)` → `foyer.Forcefield(name="oplsaa").apply(mol)` → `write_lammps_data()`<br>**执行**：`subprocess.Popen(["lmp","-sf","omp","-in","script.in"], stdout=PIPE)` → 实时解析thermo输出 |
| 29 | **packmol** | E | MD初始结构搭建协议：分子填充/溶剂化/双层膜/多组分起始构型。触发：LAMMPS/GROMACS/AMBER仿真设置但无初始结构 | `packmol` 命令行生成初始坐标 → 输出PDB/XYZ |
| 30 | **pymatgen** | E | 材料科学协议：晶体结构(CIF/POSCAR)/相图/能带/DOS/Materials Project本地数据库/格式转换 | `pymatgen.core.Structure.from_file("file.cif")` → `LammpsData.from_structure()`<br>`MPRester` → Materials Project API查询<br>`PhaseDiagram` → 相图计算<br>`BandStructure`/`Dos` → 电子结构分析 |
| 31 | **pyopenms** | E | 蛋白质组学质谱协议：特征检测→肽段鉴定→蛋白定量→LC-MS/MS管道。支持mzML/mzXML/mzData等格式 | `pyopenms.MSExperiment()` → 加载质谱数据<br>`FeatureFinderMetabo` → 特征检测<br>`PeptideIdentification` → 肽段鉴定<br>`ProteinQuantifier` → 蛋白定量 |
| 32 | **biopython** | E | 分子生物学协议：序列操作/FASTA-GenBank-PDB解析/系统发育/Bio.Entrez（NCBI E-utilities）/BLAST自动化 | `SeqIO.parse("file.fasta", "fasta")` → 序列读取<br>`Bio.Entrez.efetch(db="pubmed", id=pmid)` → NCBI查询<br>`Bio.PDB.PDBParser()` → PDB结构解析<br>`Phylo.read("tree.nwk", "newick")` → 系统发育树 |
| 33 | **esm** | E | 蛋白质语言模型协议：ESM3生成式设计（序列/结构/功能多模态）+ ESM C嵌入/逆折叠 | `esm.pretrained.esmfold_v1()` → 本地蛋白折叠<br>Forge API → 云端推理<br>`esm.inverse_folding` → 序列设计 |
| 34 | **diffdock** | E | 扩散模型分子对接协议：PDB/SMILES→结合姿势预测→置信度评分→虚拟筛选 | `diffdock.DiffDock` → 扩散采样结合姿势<br>`confidence_score` → 排序<br>适用于基于结构的药物设计 |

---

## 类别 F：外部公开 API 调用

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 35 | **pubchem-database** | F | 9功能模块：①名称消歧搜索（Autocomplete API→候选列表）；②精确检索（名称/CAS/SMILES/CID/InChI/分子式）；③性质检索（`get_properties`批量）；④相似性搜索（Tanimoto≥85%）；⑤子结构搜索（SMARTS）；⑥格式转换（SDF/JSON/PNG）；⑦结构可视化；⑧同义词；⑨生物活性；⑩PUG-View注释<br>速率限制：5 req/s, 400 req/min | `pubchempy.get_compounds(name, 'name')` → PUG-REST API<br>`pubchempy.get_properties(property_list, identifier, namespace)` → 批量性质<br>`pubchempy.get_compounds(smiles, 'smiles', searchtype='similarity', Threshold=85)` → 异步相似性搜索（30-120s）<br>`pcp.download('PNG', name, 'name', 'file.png')` → 下载结构图<br>`scripts/compound_search.py`（8KB）：封装搜索/检索函数<br>`scripts/bioactivity_query.py`（9.8KB）：生物活性查询<br>`scripts/pugview_parser.py`（5KB）：PUG-View解析（自动跳过空节，去重）→ `fetch_pugview_section(cid, headings)` |
| 36 | **chembl-database** | F | ChEMBL协议：化合物结构/性质搜索→生物活性(IC50/Ki)→抑制剂→SAR研究 | `chembl_webresource_client` → ChEMBL REST API<br>`new_client.molecule.search(q)` → 化合物搜索<br>`new_client.activity.filter(molecule_chembl_id=id)` → 活性数据 |
| 37 | **alphafold-database** | F | AlphaFold DB协议：UniProt ID→PDB/mmCIF下载→置信度指标(pLDDT/PAE)分析 | `requests.get(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}")` → EBI API<br>解析JSON→`pLDDT`/`PAE`→下载`cifUrl`/`pdbUrl` |
| 38 | **pdb-database** | F | RCSB PDB协议：文本/序列/结构搜索→下载PDB/mmCIF→元数据检索 | `rcsbsearchapi` → RCSB Search API<br>`rcsbapi.fetch("4HHB")` → 下载结构 |
| 39 | **pubmed-database** | F | PubMed REST API协议：高级Boolean/MeSH查询→E-utilities→批量处理→引用管理 | `Bio.Entrez.esearch(db="pubmed", term=query)` → NCBI E-utilities<br>`Bio.Entrez.efetch(db="pubmed", id=ids, rettype="xml")` → 批量获取<br>或直接 `requests.get` NCBI REST端点 |
| 40 | **chemprice** | F | ChemSpace协议：化合物名称/SMILES→价格查询→供应商比较 | `requests` → ChemSpace API<br>返回 100+ 供应商的价格/库存数据 |

---

## 类别 G：可视化与文件生成

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 41 | **chem-visualization** | G | 双功能协议：<br>①SMILES/名称→2D结构图（RDKit `MolDraw2DCairo`渲染确认）<br>②文件→静态2D图像（.xyz/.mol/.sdf/.mol2/.pdb/.cif/.cube） | `Chem.MolFromSmiles(smiles)` → `Draw.MolDraw2DCairo` → 渲染PNG<br>文件读取 → `Chem.MolFromMolFile`/`MolFromPDBFile` → 渲染结构或性质图 |
| 42 | **scientific-visualization** | G | 出版物级图表元技能：多面板布局/显著性标注/误差条/色盲友好配色/Nature-Science-Cell格式 | 编排 `matplotlib` + `seaborn` + `plotly`：<br>`plt.style.use('seaborn-v0_8-paper')` → 出版物风格<br>`statannotations` → 显著性标注<br>`colorblind-friendly` 调色板 → `plt.cm.tab10`/`seaborn.color_palette("colorblind")` |
| 43 | **scientific-schematics** | G | 科学示意图协议：描述→`generate_image`→迭代优化。类型：神经网络架构/系统图/流程图/生物通路 | —（调用 `generate_image` 工具，底层 Gemini 3 Pro Image） |
| 44 | **drawio-skill** | G | 图表协议：生成.drawio XML→`drawio-render`→导出PNG/SVG/PDF/JPG | 生成 draw.io XML → `drawio-render` 渲染 |
| 45 | **code-to-diagram** | G | 代码→图表协议：解析代码结构→生成Mermaid.js语法→渲染架构图/ER图/序列图/类图/流程图 | 代码解析 → Mermaid.js DSL → 渲染 |
| 46 | **website-design** | G | 创意网站协议：动画/交互/视觉体验 | HTML/CSS/JS 生成 |
| 47 | **md-to-latex** | G | Markdown→LaTeX协议：pandoc转换→XeLaTeX编译→PDF（支持中英文/图表/引用/IEEEtran） | `pandoc input.md -o output.tex` → `xelatex output.tex` → `latexmk -pdf` |

---

## 类别 H：Office 文档生成

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 48 | **pptx** | H | PowerPoint协议：创建/读取/编辑/模板/合并/演讲者备注/批注 | `python-pptx` 库：<br>`Presentation("template.pptx")` → `slide.shapes.add_picture()`/`add_table()`/`add_chart()` |
| 49 | **docx** | H | Word协议：创建/读取/编辑/目录/页眉页脚/批注/修订/查找替换 | `python-docx` 库：<br>`Document("template.docx")` → `add_paragraph()`/`add_table()`/`add_picture()`/`add_heading()` |
| 50 | **xlsx** | H | Excel协议：创建/读取/编辑/公式/图表/数据清洗/格式转换 | `openpyxl` 库：<br>`Workbook()` → `ws['A1'] = value` → `ws.add_chart()` → `DataBar`条件格式 |
| 51 | **pdf** | H | PDF协议：读取/合并/拆分/旋转/水印/表单/OCR | `PyPDF2` → 合并/拆分/旋转<br>`pdfplumber` → 提取文本/表格<br>`pytesseract` → OCR扫描PDF |

---

## 类别 I：元技能 / 基础设施

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 52 | **skill-finder** | I | skills.sh生态系统搜索→安装协议 | `search_skills(query)` → `install_skill(source)` |
| 53 | **skill-creator** | I | 技能创建指南：模板填充+规范检查 | — |
| 54 | **planning-with-files** | I | Manus风格文件化规划：`task_plan.md`（阶段追踪）+ `findings.md`（研究发现）+ `progress.md`（会话日志）。规则：2-Action规则/5-Question重启测试/3-Strike错误协议/Read-vs-Write决策矩阵 | `scripts/session-catchup.py` — 从上次会话恢复上下文<br>`scripts/init-session.sh` — 初始化规划文件<br>`scripts/check-complete.sh` — 验证所有阶段完成 |
| 55 | **rag-task-investigator** | I | RAG检索与证据合成协议：<br>Step 1: 解释请求→4-8个紧凑检索查询（按交付物类型扩展：pptx/png/html/csv/docx各有5个扩展维度）<br>Step 2: `rag_search`并发查询→≤50 chunks<br>Step 3: 富化task_conclusion（读取完整文件→查找引用文件→提取文本/图像/表格证据）<br>Step 4: 返回去重参考列表 | 并发 `rag_search(query, top_k=50, merge=True)` → 合并chunks<br>读取 `task_conclusion.md` → 解析引用路径 → 对文本文件(`.md/.py/.yaml`)直接读取 → 对图像(`.png/.jpg`)生成摘要 → 对表格(`.csv/.xlsx`)用 `pandas` 分析 → 附加到结果 |
| 56 | **project-db** | I | SQLite持久化协议：结构化状态/任务队列/查找表/去重集/进度追踪/知识库 | `sqlite3.connect(project_db_path)` → `CREATE TABLE IF NOT EXISTS` → `INSERT/UPDATE/SELECT` 持久化结构化数据 |
| 57 | **lab-notebook** | I | 湿实验记录协议：9节结构化intake（实验目的/试剂/方案步骤/原始数据/偏差/后分析）→SQLite持久化 | 交互式问答 → 填充结构化记录 → `sqlite3` 持久化 |
| 58 | **sci-personality-test** | I | 科研人格测试：生成个性化HTML页面→用户在画板作答→结果写入USER.md | `get_activity_token(purpose="scibti")` → 生成认证token → 注入HTML页面 |
| 59 | **reactnavi** | - | **逆合成路线设计**<br>5步协议：Step 1准备目标（SMILES→标准化为中性前体→保留立体化学）；Step 2提出计划（ReactNavi-led全面 / Reported routes only简化）；Step 3调用工具（`call_retrosynthesis`默认参数）；Step 4无结果诊断（0模板→前体回退/扩大搜索）；Step 5读取判断路线 | `reactnavi.tools.retrosynthesis_toolkit.call_retrosynthesis(target_smiles, output_dir, max_paths=10, max_depth=6, template_max_count=20, expansion_time=900)` → POST到逆合成服务 → 下载 `api_response.json`/`summary.json`/`multi_step_pathway_N.png`<br>从 `summary.json` 解析路线树（含 `reaction_smiles`/`ff_score`/`conditions`/`reactants`） |

---

## 未分类/补充

| # | 技能名 | 类别 | Prompt/协议 | Python 实现逻辑 |
|---|--------|------|------------|----------------|
| 60 | **lab-notebook** | I | 湿实验记录（已列） | — |
| 61 | **md-to-latex** | G | Markdown→PDF（已列） | — |

---

## 调用机理总图

```
                      ┌──────────────────────────┐
                      │    用户输入               │
                      └──────────┬───────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
    │  类型A (8)  │    │   类型 B-E    │    │   类型 C/D   │
    │ Agent纯编排 │    │   Python执行  │    │  Mira云端    │
    │             │    │   本地/API    │    │  Compute/Inf │
    └──────┬──────┘    └──────┬───────┘    └──────┬───────┘
           │                  │                    │
           ▼                  ▼                    ▼
    Agent直接推理     execute_code()         compute_submit()
    按SKILL.md协      或 bash 调用           或 mira_inference_call()
    议驱动对话         Python库/脚本           → 轮询 → 下载结果
```

---

## 开源/闭源总结

| 层级 | 开源/闭源状况 |
|------|-------------|
| **技能SKILL.md协议** | 全部闭源（Deep Principle 专有） |
| **Research CLI** | 闭源（Deep Principle 私有命令行工具） |
| **Mira Compute/Inference** | 闭源（Deep Principle 计算网关），底层模型部分开源（ESMFold2 Meta开源，ABACUS开源，PySCF开源） |
| **yamol分子对象** | 闭源（DP-YAMO专有封装），底层调用开源引擎（XTB/GFN-xTB/PySCF/CREST） |
| **Python科学计算库** | 开源（RDKit BSD/PyBaMM BSD/LAMMPS GPL/Pymatgen MIT等） |
| **外部API** | 公开API（PubChem/ChEMBL/AlphaFold DB/PDB/PubMed） |
| **Python文档库** | 开源（python-pptx MIT/python-docx MIT/openpyxl MIT/PyPDF2 BSD） |
| **AI模型调用** | `generate_image` 底层调用 Gemini 3 Pro Image（闭源） |
