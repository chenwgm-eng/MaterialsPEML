# BatteryEMCL Lab 前端优化修改方案

> 生成日期：2026-07-29
> 状态：待审核
> 涉及页面：13个需求点，覆盖8个视图文件、5个组件

---

## 需求1：首页布局 - 取消"快捷创建"block

### 现状分析
- **文件**：`Dashboard.vue` (L46-60)
- 当前实现：根据用户角色展示不同的新建按钮（管理员6个、研究员5个、审核员3个、实验员4个、访客3个）
- 问题：首页布局混乱，快捷创建区块占用过多空间

### 修改方案
1. **删除** `Dashboard.vue` 中 L46-60 的 `quick-create-section` 整个 section
2. **删除** 相关的 CSS 样式（L1429-1442 `.quick-create-grid`, `.quick-create-btn`）
3. **删除** `roleQuickCreate` 计算属性（L783-822）和相关逻辑
4. **保留** Hero区的"开始新材料研发"下拉菜单和"快速操作"section作为主要入口

### 影响范围
- `Dashboard.vue`：模板、样式

### 验证标准
- 首页不再显示"快捷创建"区块
- Hero区和快速操作区功能正常

---

## 需求2：我的待办 - 委员会Case配色 + tab数量自动刷新

### 现状分析
- **文件**：`MyTasks.vue`
- 委员会Case：badge颜色`#2050d0`，但指标卡片背景`rgba(249, 115, 22, 0.1)` + 文字颜色`#2050d0`（不一致）
- tab数量：依赖子组件 `@count-change` 事件回调，需点击tab后才加载数据

### 修改方案

#### 2.1 配色统一（蓝色系）
1. 修改 `MyTasks.vue` L142-143：
   - `bg: 'rgba(249, 115, 22, 0.1)'` → `bg: 'rgba(32, 80, 208, 0.1)'`
   - `color: '#2050d0'` 保持不变

#### 2.2 tab数量自动刷新
1. 在 `MyTasks.vue` 的 `onMounted` 中并行请求所有tab数量：
   ```js
   onMounted(async () => {
     loadMdmOptions()
     // 新增：页面加载时预取所有tab数量
     await Promise.all([
       loadReleaseCount(),
       loadCommitteeCount(),
       loadExpApprovalCount(),
       loadQcApprovalCount(),
       loadMaterialApprovalCount(),
     ])
   })
   ```
2. 新增独立的数量加载函数，复用各子组件的数据接口
3. 子组件仍保留 `@count-change` 机制作为兜底

### 影响范围
- `MyTasks.vue`：模板、脚本

### 验证标准
- 委员会Case指标卡片badge和背景色统一为蓝色系
- 页面加载后所有tab的badge数量立即显示，无需点击tab

---

## 需求3：我的待办 - TypeError JSON解析错误

### 现状分析
- **错误信息**：`TypeError: the JSON object must be str, bytes or bytearray, not dict`
- **工单编号**：ERR-MS5GU804-01
- **触发时机**：进入我的待办页面时
- **可能原因**：某个接口返回了dict对象，但代码尝试用 `json.loads()` 解析

### 修改方案
1. **排查** `MyTasks.vue` 及其子组件（`ReleaseCardCenter`, `CommitteeCenter`, `ApprovalCenter`）中的所有数据解析逻辑
2. 检查是否存在对已解析JSON对象重复调用 `JSON.parse()` 的情况
3. 添加防御性类型检查：
   ```js
   function safeParse(data) {
     if (typeof data === 'string') {
       try { return JSON.parse(data) } catch { return data }
     }
     return data  // 已经是对象则直接返回
   }
   ```
4. 排查后端接口响应，确认是否有字段返回了序列化后的JSON字符串

### 影响范围
- `MyTasks.vue` 及子组件
- 可能需要后端配合排查

### 验证标准
- 进入我的待办页面不再弹出TypeError错误
- 所有tab数据正常加载

---

## 需求4：项目管理 - 基本信息状态机 + 甘特图 + 实体图谱/数据血缘合并

### 现状分析
- **文件**：`Projects.vue`
- 基本信息：表单直接可编辑，无只读/编辑状态切换（L117-224）
- 甘特图：使用 `GanttChart` 组件（L286-289）
- 实体图谱：使用 `EntityGraph` 组件（L291-324）
- 数据血缘：树状结构展示（L325-360）

### 修改方案

#### 4.1 基本信息状态机控制
1. 新增 `isEditing` 状态（ref: false）
2. 默认所有表单字段 `disabled`
3. 点击"编辑"按钮后 `isEditing = true`，字段变为可编辑
4. 保存成功后 `isEditing = false`，回到只读状态
5. 新增"编辑"按钮在 `info-footer` 区域（L209-220）
6. "重置"和"保存"按钮仅在编辑状态显示

#### 4.2 甘特图修正
1. 检查 `GanttChart` 组件的数据映射逻辑
2. 确认甘特图展示项目任务时间线：
   - X轴：时间轴
   - Y轴：任务列表
   - 每个任务条：开始时间、结束时间、进度百分比
3. 如果组件内部逻辑错误，修复数据转换函数

#### 4.3 实体图谱与数据血缘合并
1. **删除** 独立的"实体图谱"tab（L291-324）
2. **重命名** "数据血缘"tab为"数据血缘与实体图谱"
3. 修改树状展示逻辑：
   - 保留树状结构展示方式
   - 节点数据从实体图谱API获取（包含更多实体类型）
   - 点击节点展开详情卡片（显示节点属性、关系数量）
4. 合并 `loadEntityGraph` 和 `loadLineage` 的数据加载逻辑

### 影响范围
- `Projects.vue`：模板、脚本、样式
- `GanttChart.vue`：可能需要修改
- `EntityGraph.vue`：可能需要修改

### 验证标准
- 基本信息默认只读，点击编辑后可修改
- 甘特图正确展示项目任务时间线
- 合并后的tab以树状展示血缘关系，点击节点可查看详情

---

## 需求5：项目新建 - 负责人改为下拉绑定系统用户

### 现状分析
- **文件**：`ProjectNew.vue` (L51-53)
- 当前实现：`a-input` 自由文本输入
- 需要改为：下拉选择，显示系统用户的显示名

### 修改方案
1. 将 L51-53 的 `a-input` 改为 `a-select`：
   ```html
   <a-form-item label="负责人" name="owner" required>
     <a-select
       v-model:value="form.owner"
       :options="userOptions"
       placeholder="请选择负责人"
       show-search
       option-filter-prop="label"
       :loading="usersLoading"
     />
   </a-form-item>
   ```
2. 新增 `userOptions` 和 `usersLoading` 状态
3. 在 `onMounted` 中调用用户列表接口：
   ```js
   async function loadUsers() {
     usersLoading.value = true
     try {
       const res = await client.get('/users')
       const list = Array.isArray(res) ? res : (res?.users || [])
       userOptions.value = list.map(u => ({
         label: u.display_name || u.name || u.username,
         value: u.id || u.user_id,
       }))
     } catch {
       userOptions.value = []
     } finally {
       usersLoading.value = false
     }
   }
   ```
4. 同步修改 `Projects.vue` 中基本信息表单的负责人字段（L145-148）

### 影响范围
- `ProjectNew.vue`：模板、脚本
- `Projects.vue`：基本信息表单

### 验证标准
- 负责人字段显示为下拉选择框
- 下拉列表显示系统用户的显示名
- 选择后保存正确

---

## 需求6：候选材料设计 - Agent生成无反馈 + 相关知识tab + 化学式/SMILES为空

### 现状分析
- **文件**：`CandidateWorkbench.vue`
- Agent生成：loading提示只有文案，无进度反馈（L311-316）
- 相关知识：`MaterialKnowledgeCard` 固定在详情下方（L173-178）
- 化学式/SMILES为空：后端Agent生成返回数据问题

### 修改方案

#### 6.1 Agent生成分阶段进度提示
1. 修改 `loadingHint` 为分阶段进度展示
2. 新增阶段状态：
   ```js
   const generateStages = [
     { key: 'analyze', label: '分析目标属性', status: 'waiting' },
     { key: 'retrieve', label: '检索文献知识', status: 'waiting' },
     { key: 'generate', label: '生成候选配方', status: 'waiting' },
     { key: 'validate', label: '验证结构合理性', status: 'waiting' },
     { key: 'complete', label: '完成', status: 'waiting' },
   ]
   ```
3. 通过WebSocket或轮询获取Agent执行进度，更新各阶段状态
4. 每个阶段显示状态图标：等待（灰）、进行中（蓝/动画）、完成（绿）、失败（红）

#### 6.2 相关知识改为tab
1. **删除** `CandidateWorkbench.vue` L173-178 的 `MaterialKnowledgeCard`
2. 在 `CandidateDetail.vue` 的tab栏末尾新增"相关知识"tab
3. tab内容包含 `MaterialKnowledgeCard` 组件
4. 调整tab顺序：结构可视化 → 性质预测 → 合成路径 → 可制造性/工业化验证 → 相关知识

#### 6.3 化学式/SMILES为空问题
1. **前端防御**：在 `CandidateDetail.vue` 中添加空值提示
2. **后端排查**：需要后端检查Agent生成逻辑，确认：
   - 是否正确调用了结构解析服务
   - SMILES生成逻辑是否正常
   - 空间群预测是否执行

### 影响范围
- `CandidateWorkbench.vue`：模板、脚本
- `CandidateDetail.vue`：模板、脚本
- 后端Agent生成服务

### 验证标准
- Agent生成时显示分阶段进度，每个阶段有状态指示
- 相关知识作为CandidateDetail的最后一个tab展示
- 化学式/SMILES为空时前端显示友好提示

---

## 需求7：候选材料 - 自动生成时后台执行预测 + 列表圆圈改三点

### 现状分析
- **文件**：`CandidateWorkbench.vue`、`CandidateList.vue`
- Agent生成后：只展示结果，无自动预测
- 列表指示器：圆形状态指示器

### 修改方案

#### 7.1 自动生成时后台执行预测
1. 在 `onRun()` 方法（L472-519）生成完成后，自动触发预测：
   ```js
   // 生成完成后自动触发预测
   await loadTaskCandidates()
   // 为每个候选材料并行发起预测
   const predictPromises = list.map(cand => 
     runPredictionForCandidate(cand).catch(() => null)
   )
   await Promise.all(predictPromises)
   ```
2. 新增 `runPredictionForCandidate` 函数：
   - 调用性质预测API
   - 调用合成预测API
   - 调用可制造性预测API
3. 预测结果存储在候选材料的 `predictionStatus` 字段中

#### 7.2 列表圆圈改三点
1. 修改 `CandidateList.vue` 中候选材料的状态指示器
2. 三个点分别表示：
   - 左点：性质预测结果与目标的满足情况（绿=达标，灰=未预测，红=不达标）
   - 中点：可合成性（绿=可合成，灰=未评估，红=不可合成）
   - 右点：可制造性（绿=可制造，灰=未评估，红=不可制造）
3. 鼠标悬停显示tooltip说明各点含义

### 影响范围
- `CandidateWorkbench.vue`：脚本
- `CandidateList.vue`：模板、样式
- 后端预测API

### 验证标准
- 候选材料生成后自动在后台执行三种预测
- 列表中每个候选材料显示三个状态点
- 预测完成后状态点颜色更新

---

## 需求8：跨尺度预测 - 模型选择与系统设置同步

### 现状分析
- **文件**：`CrossScaleDrawer.vue` (L110-130)
- 当前实现：硬编码模型列表，未同步系统设置中的可用状态
- `loadCrossScaleContext()` 只读取默认模型，不检查可用性

### 修改方案
1. 修改 `loadCrossScaleContext()` 方法：
   ```js
   async function loadCrossScaleContext() {
     const cfg = await client.get('/config')
     const modelStatus = cfg?.prediction_models || {}
     const availableModels = cfg?.available_models || []
     
     // 更新模型列表，标记可用状态
     allModels.value = modelList.map(m => ({
       ...m,
       disabled: !availableModels.includes(m.value) || modelStatus[m.value]?.disabled
     }))
   }
   ```
2. 修改模板，为禁用的模型添加灰色样式：
   ```html
   <a-radio-button
     v-for="m in allModels"
     :key="m.value"
     :value="m.value"
     :disabled="m.disabled"
   >
     {{ m.label }}
     <a-tag v-if="m.disabled" size="small" color="default">不可用</a-tag>
   </a-radio-button>
   ```
3. 如果所有模型都禁用，显示提示信息

### 影响范围
- `CrossScaleDrawer.vue`：模板、脚本

### 验证标准
- 系统设置中禁用的模型在跨尺度预测中显示为灰色
- 用户无法选择禁用的模型
- 可用的模型正常显示和选择

---

## 需求9：性质预测 - 右侧Agent信息面板 + 跨尺度建模崩溃

### 现状分析
- **文件**：`Prediction.vue`
- 当前布局：单列布局，无Agent面板
- 跨尺度建模崩溃：切换模式后页面卡死

### 修改方案

#### 9.1 右侧Agent信息面板
1. 将页面改为两列布局（参考 `ProjectNew.vue`）：
   - 左侧：表单 + 结果区（flex: 1）
   - 右侧：Agent信息面板（width: 300px）
2. Agent面板内容：
   - Agent头像 + 名称 + 角色标签
   - 职责描述
   - 能力列表
   - 模型信息
   - "开始预测"按钮在Agent信息下方
3. 新增 `loadPredictionAgent()` 函数加载Agent信息

#### 9.2 跨尺度建模崩溃修复
1. 排查 `predictMode` 切换时的响应式数据更新逻辑
2. 检查 `crossScaleForm` 的 `watch` 是否存在无限循环
3. 检查 `crossScaleResult` 的渲染逻辑是否有未处理的空值
4. 添加错误边界：
   ```js
   async function runCrossScale() {
     try {
       // ...
     } catch (err) {
       console.error('跨尺度建模失败:', err)
       message.error('跨尺度建模执行失败，请检查参数后重试')
     }
   }
   ```

### 影响范围
- `Prediction.vue`：模板、脚本、样式

### 验证标准
- 性质预测页面右侧显示Agent信息面板
- "开始预测"按钮在Agent信息下方
- 切换到跨尺度建模模式后页面正常，不再卡死

---

## 需求10：合成路径 - 页面布局改为右侧Agent信息

### 现状分析
- **文件**：`Synthesis.vue`
- 当前布局：单列布局（输入卡片 + 结果区）
- 无Agent信息展示

### 修改方案
1. 将页面改为两列布局：
   - 左侧：输入表单 + 结果区
   - 右侧：Agent信息 + ASKCOS服务状态
2. 右侧面板分为两个区块：
   - **合成规划Agent**：Agent详情卡片（头像、名称、能力、模型）
   - **ASKCOS服务状态**：连接状态、可用模板数、服务健康度、DFT校验队列
3. 当服务不可用时显示警告提示和重试按钮

### 影响范围
- `Synthesis.vue`：模板、脚本、样式

### 验证标准
- 合成路径页面右侧显示Agent信息和ASKCOS服务状态
- 服务异常时显示警告
- 布局在小屏幕下正常折叠

---

## 需求11：配方与工艺 - 状态机 + 相关知识改tab

### 现状分析
- **文件**：`FormulaDesign.vue`
- 配方详情：`isCandidateBom` 控制是否可编辑（来源决定，非状态切换）
- 相关知识：`MaterialKnowledgeCard` 固定在详情中（L188-194）

### 修改方案

#### 11.1 配方详情状态机控制
1. 新增 `isEditing` 状态（ref: false）
2. 所有配方（无论来源）默认只读
3. 点击"编辑"按钮后进入编辑状态
4. 编辑状态下显示"保存"和"取消"按钮
5. 保存成功后回到只读状态

#### 11.2 相关知识改为tab
1. **删除** L188-194 的 `MaterialKnowledgeCard`
2. 在配方详情抽屉中新增tab：
   - 物料清单 (BOM)
   - 工艺参数 (BOP)
   - 成本分析
   - 相关知识（新增）
3. 相关知识tab内容包含 `MaterialKnowledgeCard` 组件

### 影响范围
- `FormulaDesign.vue`：模板、脚本、样式

### 验证标准
- 所有配方详情默认只读，点击编辑后可修改
- 相关知识作为配方详情抽屉的一个tab展示
- 编辑状态有明确的视觉区分

---

## 需求12：实验迭代闭环 - TypeError + 执行状态节点 + 委员会门禁/结果概览/反馈优化

### 现状分析
- **文件**：`ECMLMonitor.vue`
- 执行状态：`ECMLStepFlow` 组件（L111）
- 委员会门禁：`ECMLCommitteePanel` 组件（L115-118）
- 结果概览：`ECMLResultOverview` 组件（L120-137）
- TypeError：`ERR-MS5HL0ZK-02`

### 修改方案

#### 12.1 TypeError修复
1. 排查 `ECMLMonitor.vue` 及子组件中的数据解析逻辑
2. 检查 `ecmlStore.state` 的使用是否存在对dict重复解析
3. 添加防御性类型检查（同需求3）

#### 12.2 执行状态节点多状态指示
1. 修改 `ECMLStepFlow` 组件，为每个节点增加4种状态：
   - 未开始（灰色）
   - 进行中（蓝色/动画）
   - 完成（绿色）
   - 失败/需干预（红色）
2. 当前节点高亮显示
3. 点击节点展示该步骤的详细活动情况（执行日志、耗时、输出）

#### 12.3 委员会门禁/结果概览/反馈卡片化
1. 将三个区块改为卡片样式
2. 每个卡片底部增加明确的下一步操作按钮：
   - 委员会门禁："审批通过"、"驳回"、"要求补充材料"
   - 结果概览："查看候选详情"、"采纳进入实验"、"采纳进入配方"
   - 反馈与建议："创建实验任务"、"调整参数重新运行"
3. 卡片标题清晰表达区块用途

### 影响范围
- `ECMLMonitor.vue`：模板、脚本
- `ECMLStepFlow.vue`：模板、脚本、样式
- `ECMLCommitteePanel.vue`：模板、样式
- `ECMLResultOverview.vue`：模板、样式

### 验证标准
- TypeError不再出现
- 执行状态节点显示4种状态，当前节点高亮
- 点击节点可查看该步骤的详细活动
- 三个区块底部有明确的下一步操作按钮

---

## 需求13：迭代历史 - 查询条件 + 新建按钮样式位置

### 现状分析
- **文件**：`ECMLRuns.vue`
- 当前筛选：只有环境筛选（正式/测试/全部）
- 新建按钮：页面头部右侧，使用 `router-link` 样式

### 修改方案

#### 13.1 新增项目+任务查询条件
1. 在表格上方新增筛选区域：
   ```html
   <div class="filter-bar">
     <a-select v-model:value="filterProjectId" placeholder="选择项目" />
     <a-select v-model:value="filterTaskId" placeholder="选择任务" :disabled="!filterProjectId" />
     <a-button @click="onResetFilter">重置</a-button>
   </div>
   ```
2. 项目选择后加载任务列表（联动）
3. 过滤逻辑：先按项目过滤，再按任务过滤

#### 13.2 新建按钮移到表格工具栏
1. 将"新建实验闭环迭代"按钮从页面头部移到表格标题栏
2. 样式改为标准的 `a-button ant-btn-primary`
3. 位置在表格标题栏左侧，与筛选器同行

### 影响范围
- `ECMLRuns.vue`：模板、脚本、样式

### 验证标准
- 支持按项目和任务筛选迭代记录
- 新建按钮在表格工具栏左侧
- 按钮样式与全站一致

---

## 任务优先级与实施顺序

### 第一阶段：Bug修复（高优先级）
| 序号 | 任务 | 预估工时 | 依赖 |
|------|------|----------|------|
| 1 | 需求3：TypeError修复 | 2h | 无 |
| 2 | 需求12.1：TypeError修复 | 2h | 无 |
| 3 | 需求9.2：跨尺度建模崩溃修复 | 3h | 无 |

### 第二阶段：布局优化（中优先级）
| 序号 | 任务 | 预估工时 | 依赖 |
|------|------|----------|------|
| 4 | 需求1：取消快捷创建block | 1h | 无 |
| 5 | 需求2：配色+数量刷新 | 2h | 无 |
| 6 | 需求11.2：相关知识改tab | 2h | 无 |
| 7 | 需求6.2：相关知识改tab | 2h | 无 |

### 第三阶段：状态机控制（中优先级）
| 序号 | 任务 | 预估工时 | 依赖 |
|------|------|----------|------|
| 8 | 需求4.1：基本信息状态机 | 3h | 无 |
| 9 | 需求11.1：配方状态机 | 3h | 无 |

### 第四阶段：功能增强（中优先级）
| 序号 | 任务 | 预估工时 | 依赖 |
|------|------|----------|------|
| 10 | 需求5：负责人下拉 | 2h | 无 |
| 11 | 需求8：模型同步 | 2h | 无 |
| 12 | 需求13：查询条件+按钮 | 2h | 无 |

### 第五阶段：复杂功能（低优先级）
| 序号 | 任务 | 预估工时 | 依赖 |
|------|------|----------|------|
| 13 | 需求6.1：分阶段进度 | 4h | 后端配合 |
| 14 | 需求7：自动预测+三点 | 6h | 后端配合 |
| 15 | 需求9.1：Agent面板 | 4h | 无 |
| 16 | 需求10：Agent面板 | 4h | 无 |
| 17 | 需求12.2：节点多状态 | 3h | 无 |
| 18 | 需求12.3：卡片化 | 3h | 无 |
| 19 | 需求4.2：甘特图修正 | 3h | 无 |
| 20 | 需求4.3：图谱血缘合并 | 4h | 无 |

---

## 风险与依赖

### 后端依赖
- 需求6.1：需要后端提供Agent执行进度接口（WebSocket或轮询）
- 需求7：需要后端提供批量预测接口
- 需求6.3：需要后端排查Agent生成逻辑

### 设计规范
- 所有Agent信息面板统一使用 `ProjectNew.vue` 的右侧面板样式
- 状态机交互统一：只读 → 编辑按钮 → 可编辑 → 保存/取消
- 状态指示器颜色规范：灰=未开始，蓝=进行中，绿=完成，红=失败/需干预

### 测试要求
- 每个需求完成后验证对应功能
- 跨浏览器测试（Chrome、Firefox、Edge）
- 响应式布局测试（1920px、1440px、768px）
