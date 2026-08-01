<template>
  <div class="candidate-workbench">
    <!-- 来自 ECML 推荐候选的引导提示 -->
    <a-alert
      v-if="recommendedTarget"
      type="info"
      show-icon
      closable
      message="来自实验闭环迭代的推荐候选材料"
      :description="`推荐目标材料：${recommendedTarget}。请选择项目任务后，基于此目标生成或优化候选材料。`"
      style="margin-bottom: 12px"
      @close="recommendedTarget = ''"
    />
    <!-- 顶部输入区（紧凑单行） -->
    <div class="workbench-header">
      <div class="header-row">
        <span class="header-label">当前项目，</span>
        <a-select
          v-model:value="selectedProjectId"
          :options="projectOptions"
          placeholder="请选择项目"
          size="small"
          class="project-select"
          show-search
          option-filter-prop="label"
          allow-clear
          :get-popup-container="getPopupContainer"
          @change="onProjectChange"
        />
        <span class="header-label">任务，</span>
        <a-select
          v-model:value="selectedTaskId"
          :options="taskOptions"
          :placeholder="selectedProjectId ? '请选择任务' : '请先选择项目'"
          :disabled="!selectedProjectId"
          size="small"
          class="task-select"
          show-search
          option-filter-prop="label"
          allow-clear
          :get-popup-container="getPopupContainer"
          @change="onTaskChange"
        />
        <a-input-number
          v-model:value="numCandidates"
          :min="5"
          :max="50"
          size="small"
          class="num-input"
          addon-before="数量"
        />
        <a-tooltip title="清空项目、任务与候选结果，并恢复默认数量">
          <a-button size="small" @click="onReset">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </a-tooltip>
      </div>

      <!-- Agent 行：智能体信息卡 + 模式切换 + 生成按钮（已抽取为子组件） -->
      <CandidateAgentBar
        v-model:generate-mode="generateMode"
        :loading="loading"
        :disabled="!selectedTaskId"
        @run="onRun"
        @agent-loaded="onAgentLoaded"
      />

      <!-- 选中任务后：自动带出交付物与目标属性 -->
      <div v-if="selectedTask" class="task-info-bar">
        <div class="task-info-item">
          <span class="info-label">交付物：</span>
          <span class="info-value">{{ selectedTask.deliverable || '—' }}</span>
        </div>
        <div class="task-info-item">
          <span class="info-label">交付物具体要求：</span>
          <span class="info-value">
            <a-tag
              v-for="p in selectedTask.target_properties"
              :key="p.name"
              size="small"
              class="prop-tag"
            >
              {{ p.name }}
              <template v-if="p.direction === 'maximize'">↑</template>
              <template v-else>↓</template>
              <template v-if="p.min != null">≥{{ p.min }}</template>
              <template v-if="p.max != null">≤{{ p.max }}</template>
            </a-tag>
            <span v-if="!selectedTask.target_properties?.length" class="text-muted">无</span>
          </span>
        </div>
      </div>
      <!-- 选中项目但无任务时：提示用户 -->
      <div v-else-if="selectedProjectId && !taskOptions.length" class="task-info-bar empty-task">
        <EmptyState
          type="data"
          description="该项目暂无任务，请先在「项目中心」新建项目并生成任务"
        />
      </div>

      <!-- Agent 生成进度（异步模式实时反馈） -->
      <div v-if="loading && agentProgress > 0" class="agent-progress-bar">
        <div class="progress-header">
          <LoadingOutlined spin />
          <span class="progress-label">{{ agentStepLabel || 'Agent 正在生成…' }}</span>
          <span class="progress-percent">{{ agentProgress }}%</span>
        </div>
        <a-progress :percent="agentProgress" :show-info="false" size="small" />
      </div>
      <!-- 需求7：批量预测进度（生成完成后自动预测） -->
      <div v-if="batchPredicting" class="agent-progress-bar">
        <div class="progress-header">
          <LoadingOutlined spin />
          <span class="progress-label">{{ agentStepLabel || '正在批量预测…' }}</span>
        </div>
        <a-progress :percent="100" :show-info="false" status="active" size="small" />
      </div>

      <!-- Agent 思考过程（可折叠） -->
      <div v-if="agentReasoning" class="reasoning-bar" :class="{ 'is-collapsed': reasoningCollapsed }">
        <div class="reasoning-header" @click="reasoningCollapsed = !reasoningCollapsed">
          <div class="reasoning-title">
            <BulbOutlined />
            <span>Agent 思考过程</span>
            <a-tag v-if="agentInfo" size="small" color="orange">{{ agentInfo.name }}</a-tag>
            <a-tag size="small">{{ generateMode === 'pure_llm' ? 'AI 创造' : 'AI+检索增强' }}</a-tag>
          </div>
          <a-button type="text" size="small" class="reasoning-toggle">
            <template #icon>
              <DownOutlined v-if="reasoningCollapsed" />
              <UpOutlined v-else />
            </template>
            {{ reasoningCollapsed ? '展开' : '收起' }}
          </a-button>
        </div>
        <div v-show="!reasoningCollapsed" class="reasoning-content">
          {{ agentReasoning }}
        </div>
      </div>
    </div>

    <!-- 主体：未选项目时显示引导卡片，否则显示左右分栏 -->
    <div class="workbench-body">
      <!-- 未选项目：居中引导卡片 -->
      <div v-if="!selectedProjectId" class="project-guide-card">
        <a-card class="guide-card" :bordered="false">
          <div class="guide-icon">
            <FolderOpenOutlined />
          </div>
          <h2 class="guide-title">请选择项目</h2>
          <p class="guide-desc">选择一个研发项目后，系统将展示该项目下的候选材料</p>
          <a-select
            v-model:value="selectedProjectId"
            placeholder="选择项目..."
            style="width: 300px"
            :options="projectOptions"
            show-search
            option-filter-prop="label"
            @change="onProjectChange"
          />
        </a-card>
      </div>
      <!-- 已选项目：左右分栏 -->
      <template v-else>
      <!-- 左侧候选列表 -->
      <div class="left-panel" :style="{ width: leftPanelWidth + 'px' }">
        <CandidateList
          :candidates="displayCandidates"
          :loading="loading || taskCandidatesLoading"
          :selected="selectedCandidate"
          type="crystal"
          :status-map="candidateStatusMap"
          :empty-text="selectedTaskId ? '该任务暂无候选材料，点击「调用智能体生成候选材料」' : '请选择项目任务后查看候选材料'"
          @select="onSelectCandidate"
        />
        <!-- 列表宽度调节 -->
        <div class="resize-handle" @mousedown="startResize"></div>
      </div>

      <!-- 右侧详情 + 操作 -->
      <div class="right-panel">
        <div v-if="!selectedCandidate" class="placeholder">
          <EmptyState type="data" description="从左侧列表选择一个候选材料查看详情" />
        </div>
        <template v-else>
          <div class="detail-wrap">
            <CandidateDetail
              :candidate="selectedCandidate"
              type="crystal"
              @route-selected="onRouteSelected"
            />
          </div>

          <!-- 底部操作按钮区（始终固定在最下面） -->
          <div class="action-bar">
            <span class="action-hint">下一步操作：</span>
            <a-button
              type="primary"
              :icon="h(ExperimentOutlined)"
              @click="adoptToWetLab"
            >采纳进入湿实验</a-button>
            <a-button :icon="h(AuditOutlined)" :loading="approvalLoading" @click="submitApproval">发起审批</a-button>
            <a-button :icon="h(SwapOutlined)" @click="addToCompare">加入对比</a-button>
            <a-button type="primary" :icon="h(FormOutlined)" @click="goFormulaDesign">
              进入配方设计
              <span v-if="selectedRouteInfo" class="route-hint">·已选路线{{ selectedRouteInfo.route_index + 1 }}</span>
            </a-button>
            <a-button :icon="h(SyncOutlined)" @click="goEcmlIteration">送入闭环迭代</a-button>
            <a-button :icon="h(SaveOutlined)" ghost :loading="saveLoading" @click="saveToLibrary">收藏到物料库</a-button>
          </div>
        </template>
      </div>
      </template>
    </div>

    <!-- 对比抽屉 -->
    <a-drawer
      :open="compareOpen"
      title="候选对比（最多 4 个）"
      width="900"
      placement="right"
      @update:open="(v) => (compareOpen = v)"
    >
      <a-table
        v-if="compareList.length"
        :row-key="(r) => r._compareKey"
        :columns="compareColumns"
        :data-source="compareTableData"
        :pagination="false"
        size="small"
        bordered
      >
        <template #bodyCell="{ column, record }">
          <template v-if="record.metric === '化学式' && column.key !== 'metric' && record[column.key]">
            <ChemicalFormula :formula="record[column.key]" size="small" />
          </template>
          <template v-else-if="record.metric === '化学式' && column.key !== 'metric'">
            <span>—</span>
          </template>
        </template>
      </a-table>
      <EmptyState v-else type="data" description="尚未加入对比" />
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, h, onBeforeUnmount, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ECML_RECOMMENDED_TARGET_KEY } from '@/utils/researchContext'
import {
  ReloadOutlined,
  BlockOutlined,
  ExperimentOutlined,
  AuditOutlined,
  SwapOutlined,
  FormOutlined,
  SaveOutlined,
  BulbOutlined,
  DownOutlined,
  UpOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import CandidateList from '@/components/CandidateList.vue'
import CandidateDetail from '@/components/CandidateDetail.vue'
import CandidateAgentBar from '@/components/candidate/CandidateAgentBar.vue'
import { useUnitSymbols } from '@/utils/mdmDict'
import { useDiscoveryStore } from '@/stores/discovery'
import client from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const route = useRoute()
const discoveryStore = useDiscoveryStore()
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const energyUnit = computed(() => unitSymbols.value.energy || 'eV')
const energyPerAtomUnit = computed(() => unitSymbols.value.energy_per_atom || 'eV/atom')
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')

// 项目与任务选择
const projects = ref([])
const selectedProjectId = ref(undefined)
const selectedTaskId = ref(undefined)

// a-select 下拉挂载到 body，避免被父容器 overflow:hidden 裁剪
const getPopupContainer = () => document.body

const projectOptions = computed(() =>
  projects.value.map((p) => ({ label: p.name || '未命名项目', value: p.project_id }))
)

const selectedProject = computed(() =>
  projects.value.find((p) => p.project_id === selectedProjectId.value) || null
)

// 项目下任务列表：从后端 GET /projects/{project_id}/tasks 加载，避免依赖
// projects 列表中可能过期的 tasks JSONB 字段（D1 修复）
const projectTasks = ref([])
const taskOptions = computed(() =>
  projectTasks.value.map((t) => ({
    label: t.title || '未命名任务',
    value: t.task_id,
  }))
)

const selectedTask = computed(() =>
  projectTasks.value.find((t) => t.task_id === selectedTaskId.value) || null
)

// 候选数量（保留可调）
const numCandidates = ref(15)

// 加载与结果
const loading = computed(() => discoveryStore.loading)
const candidates = computed(() => discoveryStore.crystalCandidates)

// 生成模式：pure_llm（AI 创造）/ llm_plus_retrieval（AI+检索增强）
const generateMode = computed({
  get: () => discoveryStore.generateMode,
  set: (v) => { discoveryStore.generateMode = v },
})
// Agent 思考过程（可折叠，默认折叠避免占用空间）
const agentReasoning = computed(() => discoveryStore.agentReasoning)
const agentInfo = computed(() => discoveryStore.agentInfo)
const reasoningCollapsed = ref(true)
// 异步生成进度
const agentProgress = computed(() => discoveryStore.agentProgress)
const agentStepLabel = computed(() => discoveryStore.agentStepLabel)
// 需求7：批量预测状态（三点状态指示）
const candidateStatusMap = computed(() => discoveryStore.candidateStatusMap)
const batchPredicting = computed(() => discoveryStore.batchPredicting)

// 当前首席材料学家 Agent（由子组件加载后回传，供 onRun 构造 payload 使用）
const materialScientistAgentId = ref('')
function onAgentLoaded(agent) {
  materialScientistAgentId.value = agent?.id || ''
}

// 材料类型：根据任务交付物推断（含"聚合物"/"polymer"→polymer，否则 crystal）
const materialKind = computed(() => {
  const deliverable = (selectedTask.value?.deliverable || '').toLowerCase()
  if (deliverable.includes('聚合物') || deliverable.includes('polymer') || deliverable.includes('peo')) {
    return 'polymer'
  }
  return 'crystal'
})

// 选中候选
const selectedCandidate = ref(null)

// 左面板宽度
const leftPanelWidth = ref(360)

// 对比功能
const compareOpen = ref(false)
const compareList = ref([])

// 操作按钮 loading
const approvalLoading = ref(false)
const saveLoading = ref(false)

// 来自 ECML 闭环迭代的推荐候选（通过 sessionStorage 传递）
const recommendedTarget = ref('')

// 研发场景 ID（从研发工作台派生时透传，跳转下游模块时继续传递）
const currentScenarioId = ref('')

const compareColumns = computed(() => {
  const cols = [
    { title: '属性', dataIndex: 'metric', key: 'metric', width: 140, fixed: 'left' },
  ]
  compareList.value.forEach((c, idx) => {
    cols.push({
      title: c.name || c.formula || `候选材料 ${idx + 1}`,
      dataIndex: `col_${idx}`,
      key: `col_${idx}`,
      ellipsis: true,
    })
  })
  return cols
})

const compareTableData = computed(() => {
  const metrics = [
    { metric: '化学式', key: 'formula' },
    { metric: 'SMILES', key: 'smiles' },
    { metric: '空间群', key: 'space_group' },
    { metric: `带隙 (${energyUnit.value})`, key: 'band_gap' },
    { metric: `形成能 (${energyPerAtomUnit.value})`, key: 'formation_energy' },
    { metric: `电导率 (${condUnit.value})`, key: 'ionic_conductivity_estimate' },
    { metric: '稳定性', key: 'stability_score' },
    { metric: '综合评分', key: 'multi_objective_score' },
    { metric: '来源', key: 'source' },
  ]
  return metrics.map((m) => {
    const row = { metric: m.metric }
    compareList.value.forEach((c, idx) => {
      let v = c[m.key]
      if (m.key === 'multi_objective_score' && v != null) {
        v = (v * 100).toFixed(1) + '%'
      }
      row[`col_${idx}`] = v ?? '—'
    })
    return row
  })
})

async function loadProjects() {
  try {
    const data = await client.get('/projects')
    projects.value = Array.isArray(data) ? data : []
  } catch {
    projects.value = []
  }
}

// 加载项目下任务列表（D1 修复：从后端获取，不依赖 projects 列表中的 tasks 字段）
async function loadProjectTasks() {
  const pid = selectedProjectId.value
  if (!pid) {
    projectTasks.value = []
    return
  }
  try {
    const data = await client.get(`/projects/${pid}/tasks`)
    projectTasks.value = Array.isArray(data) ? data : (data?.tasks || [])
  } catch {
    projectTasks.value = []
  }
}

function onProjectChange() {
  // 切换项目时清空任务选择与候选结果
  selectedTaskId.value = undefined
  selectedCandidate.value = null
  discoveryStore.clearCandidates()
  taskCandidates.value = []
  loadProjectTasks()
}

function onTaskChange() {
  // 切换任务时清空候选结果，并加载该任务下已有的候选列表
  selectedCandidate.value = null
  discoveryStore.clearCandidates()
  loadTaskCandidates()
}

// 任务下已有候选列表（来自 GET /tasks/{task_id}/candidates）
const taskCandidates = ref([])
const taskCandidatesLoading = ref(false)

async function loadTaskCandidates() {
  const tid = selectedTaskId.value
  if (!tid) {
    taskCandidates.value = []
    return
  }
  taskCandidatesLoading.value = true
  try {
    const resp = await client.get(`/tasks/${tid}/candidates`)
    taskCandidates.value = (resp?.candidates || []).map((c) => ({
      // P1-2：合并持久化 data 中的生成字段（confidence/key_assumptions/evidence_sources 等）
      ...(c.data || {}),
      ...c,
      // 兼容 CandidateList/CandidateDetail 期望的字段
      id: c.candidate_id,
      formula: c.name, // 晶体候选 name 即化学式
      _fromStore: true,
    }))
    // 需求7：加载已有候选后，触发批量预测以更新三点状态标志
    if (taskCandidates.value.length > 0) {
      const task = selectedTask.value
      // 限制批量预测数量，避免84个候选导致超时
      const candidatesToPredict = taskCandidates.value.slice(0, 10)
      discoveryStore.batchPredict({
        candidates: candidatesToPredict,
        material_kind: materialKind.value || 'crystal',
        target_properties: task?.target_properties || [],
        run_synthesis_check: true,
      }).catch(() => { /* 非阻塞，失败不影响列表展示 */ })
    }
  } catch {
    taskCandidates.value = []
  } finally {
    taskCandidatesLoading.value = false
  }
}

// 候选列表数据源：优先展示任务下已有候选，无则展示 discoveryStore 即时生成的结果
const displayCandidates = computed(() => {
  if (discoveryStore.crystalCandidates.length > 0) {
    return discoveryStore.crystalCandidates
  }
  return taskCandidates.value
})

async function onRun() {
  const task = selectedTask.value
  if (!task) {
    message.warning('请先选择项目任务')
    return
  }
  selectedCandidate.value = null

  // 构造目标属性（后端 AgentGenerateRequest.target_properties 接受 [{name, direction, min, max}]）
  const targetProperties = (task.target_properties || [])
    .filter((p) => p.name)
    .map((p) => ({
      name: p.name,
      direction: p.direction === 'minimize' ? 'minimize' : 'maximize',
      min: p.min ?? null,
      max: p.max ?? null,
    }))

  const payload = {
    agent_id: materialScientistAgentId.value || '',
    task_title: task.title || '',
    deliverable: task.deliverable || '',
    target_properties: targetProperties,
    mode: generateMode.value,
    num_candidates: numCandidates.value,
    project_id: selectedProjectId.value || '',
    task_id: selectedTaskId.value || '',
    scenario_id: currentScenarioId.value || '',
    material_kind: materialKind.value || 'crystal',
  }

  // 切换到新生成结果时清空旧候选与已选中项，生成期间折叠思考过程
  taskCandidates.value = []
  reasoningCollapsed.value = true

  try {
    const res = await discoveryStore.agentGenerate(payload)
    message.success(`Agent 已生成 ${res.candidates?.length || 0} 个候选材料`)
    // 生成完成后展开思考过程，让用户了解 Agent 推理逻辑
    reasoningCollapsed.value = false
    const list = candidates.value
    if (list.length > 0) {
      selectedCandidate.value = { ...list[0] }
    }
    // 刷新任务候选列表，确保刷新页面后仍可看到最新候选（D8 修复）
    await loadTaskCandidates()
  } catch (err) {
    // 超时或失败时回退查 DB——后端可能已持久化候选但前端轮询窗口已过
    message.warning('Agent 生成耗时较长，正在为您加载已有候选…')
    await loadTaskCandidates()
    if (taskCandidates.value.length > 0) {
      message.success(`已加载 ${taskCandidates.value.length} 个候选材料`)
    }
  }
}

// 默认候选数量，重置时恢复（D6 修复）
const DEFAULT_NUM_CANDIDATES = 15

function onReset() {
  selectedProjectId.value = undefined
  selectedTaskId.value = undefined
  selectedCandidate.value = null
  compareList.value = []
  projectTasks.value = []
  taskCandidates.value = []
  numCandidates.value = DEFAULT_NUM_CANDIDATES
  discoveryStore.clearCandidates()
}

function onSelectCandidate(item) {
  selectedCandidate.value = item
}

// 操作按钮
// P1-1：采纳进入湿实验 → 跳转实验工作台，新建任务抽屉自动带出项目与候选，
// 用户在表单中确认执行模式/优先级/条件后再提交，避免直接生成信息不全的草稿单
function adoptToWetLab() {
  if (!selectedCandidate.value) return
  const c = selectedCandidate.value
  const candidateId = c.candidate_id || c.id || ''
  router.push({
    path: '/experiment-workbench',
    query: {
      create: '1',
      project_id: selectedProjectId.value || '',
      candidate_id: candidateId,
    },
  })
}

async function submitApproval() {
  if (!selectedCandidate.value) return
  approvalLoading.value = true
  try {
    const task = selectedTask.value
    await client.post('/approvals', {
      title: `候选材料审批：${selectedCandidate.value.name || selectedCandidate.value.formula}`,
      type: 'material_adoption',
      payload: {
        candidate: selectedCandidate.value,
        project_id: selectedProjectId.value || '',
        task_id: selectedTaskId.value || '',
        deliverable: task?.deliverable || '',
        target_properties: task?.target_properties || [],
      },
    })
    message.success('已发起审批，可在「审批中心」跟踪进度')
  } catch {
    /* handled */
  } finally {
    approvalLoading.value = false
  }
}

function addToCompare() {
  if (!selectedCandidate.value) return
  if (compareList.value.length >= 4) {
    message.warning('对比列表已满（最多 4 个）')
    return
  }
  const c = selectedCandidate.value
  const key =
    c.id || c.material_id || c.formula || c.smiles || c.name
  if (compareList.value.some((x) => (x.id || x.formula) === (c.id || c.formula))) {
    message.info('该候选材料已在对比列表中')
    return
  }
  compareList.value.push({ ...c, _compareKey: key + '-' + Date.now() })
  message.success('已加入对比')
  compareOpen.value = true
}

// 用户在 CandidateDetail 中选中的合成路径（供 goFormulaDesign 携带）
const selectedRouteInfo = ref(null)

// 切换候选时清空已选路径，避免上一个候选的 route_id 残留
watch(selectedCandidate, () => {
  selectedRouteInfo.value = null
})

function onRouteSelected(info) {
  selectedRouteInfo.value = info
}

function goFormulaDesign() {
  if (!selectedCandidate.value) return
  // 通过 query 携带候选信息与研发场景 ID
  const c = selectedCandidate.value
  const query = {
    formula: c.formula || '',
    smiles: c.smiles || '',
    name: c.name || '',
    candidate_id: c.candidate_id || c.id || '',
  }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  // 若用户在合成路径 Tab 选中了路线，携带 route_id 与 synthesis_task_id
  // FormulaDesign 接收后会自动生成或打开对应的 BOM 草案
  if (selectedRouteInfo.value) {
    query.route_id = selectedRouteInfo.value.route_id
    query.synthesis_task_id = selectedRouteInfo.value.synthesis_task_id
  }
  router.push({ name: 'FormulaDesign', query })
}

function goEcmlIteration() {
  if (!selectedCandidate.value) return
  // 携带目标材料与目标属性跳转闭环迭代，ECML 读取 query 自动预填表单
  const c = selectedCandidate.value
  const props = (selectedTask.value?.target_properties || []).filter((p) => p.name).map((p) => p.name)
  const query = {
    target: c.formula || c.name || '',
  }
  if (props.length > 1) {
    query.multi_props = props.join(',')
  } else if (props.length === 1) {
    query.target_property = props[0]
  }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/ecml', query })
}

async function saveToLibrary() {
  if (!selectedCandidate.value) return
  saveLoading.value = true
  try {
    // D4 修复：改用 POST /raw-materials（后端物料规格库接口）
    await client.post('/raw-materials', {
      name: selectedCandidate.value.name || selectedCandidate.value.formula,
      smiles: selectedCandidate.value.smiles || '',
      properties: {
        formula: selectedCandidate.value.formula,
        band_gap: selectedCandidate.value.band_gap,
        ionic_conductivity: selectedCandidate.value.ionic_conductivity_estimate,
      },
      data_source: 'predicted',
      update_reason: '候选材料收藏入库',
    })
    message.success('已收藏到物料规格库')
  } catch {
    /* handled */
  } finally {
    saveLoading.value = false
  }
}

// 左面板宽度调节
let resizeStartX = 0
let resizeStartWidth = 0
function startResize(e) {
  resizeStartX = e.clientX
  resizeStartWidth = leftPanelWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
function onResizeMove(e) {
  const dx = e.clientX - resizeStartX
  const newWidth = Math.max(280, Math.min(560, resizeStartWidth + dx))
  leftPanelWidth.value = newWidth
}
function stopResize() {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
onBeforeUnmount(stopResize)

onMounted(async () => {
  await loadProjects()
  loadUnitSymbols()

  // 读取来自 ECML 闭环迭代推荐候选的上下文
  const ecmlTarget = sessionStorage.getItem(ECML_RECOMMENDED_TARGET_KEY)
  if (ecmlTarget) {
    recommendedTarget.value = ecmlTarget
    sessionStorage.removeItem(ECML_RECOMMENDED_TARGET_KEY)
  }

  // 透传研发场景 ID（从研发工作台派生时携带，跳转下游模块时继续传递）
  if (route.query.scenario_id) {
    currentScenarioId.value = String(route.query.scenario_id)
  }

  // 支持通过 URL query 预选项目/任务，便于测试与外部跳转（D3 修复）
  if (route.query.project_id) {
    const pid = String(route.query.project_id)
    const foundProject = projects.value.find((p) => p.project_id === pid)
    if (foundProject) {
      selectedProjectId.value = pid
      // 从后端加载该项目下的任务列表（D1 修复：不依赖 projects 列表中的 tasks 字段）
      await loadProjectTasks()
      if (route.query.task_id) {
        const tid = String(route.query.task_id)
        const foundTask = projectTasks.value.find((t) => t.task_id === tid)
        if (foundTask) {
          selectedTaskId.value = tid
          // 直接赋值不会触发 a-select 的 change 事件，需手动加载候选
          await loadTaskCandidates()
        }
      }
    }
  }
})
</script>

<style scoped>
.candidate-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--light-bg, #f5f7fa);
  overflow: hidden;
}

.workbench-header {
  background: var(--light-bg-card, #fff);
  border-bottom: 1px solid var(--border, #e8e8e8);
  padding: 8px 16px;
  flex-shrink: 0;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.header-label {
  font-size: 13px;
  color: var(--text-primary, #333);
  white-space: nowrap;
  flex-shrink: 0;
}

.project-select {
  min-width: 200px;
  flex: 1;
  max-width: 280px;
}

.task-select {
  min-width: 220px;
  flex: 1;
  max-width: 320px;
}

.num-input {
  width: 140px;
  flex-shrink: 0;
}

/* 选中任务后的交付物信息条 */
.task-info-bar {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  margin-top: 6px;
  padding: 6px 12px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: 6px;
  flex-wrap: wrap;
}

.task-info-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}

.task-info-item .info-label {
  color: var(--text-secondary, #666);
  flex-shrink: 0;
}

.task-info-item .info-value {
  color: var(--text-primary, #333);
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.prop-tag {
  font-family: var(--font-family-mono, "JetBrains Mono", Consolas, monospace);
  font-size: 11px;
}

.text-muted {
  color: var(--text-muted, #999);
}

.task-info-bar.empty-task {
  padding: 12px;
}

.task-info-bar.empty-task :deep(.ant-empty) {
  margin: 0;
}

.task-info-bar.empty-task :deep(.ant-empty-description) {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.workbench-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.left-panel {
  position: relative;
  flex-shrink: 0;
  height: 100%;
  display: flex;
}

.left-panel > :first-child {
  flex: 1;
  min-width: 0;
}

.resize-handle {
  width: 6px;
  height: 100%;
  background: var(--border, #e8e8e8);
  cursor: col-resize;
  position: relative;
  z-index: 5;
  flex-shrink: 0;
  transition: background 0.15s;
}

.resize-handle::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 24px;
  border-radius: 1px;
  background: rgba(0, 0, 0, 0.15);
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--primary);
}

.resize-handle:hover::after,
.resize-handle:active::after {
  background: rgba(255, 255, 255, 0.6);
}

.right-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.detail-wrap {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* 让 CandidateDetail 自然撑开高度，由 .detail-wrap 统一管理滚动，
   而不是 CandidateDetail 内部各 tab 自己滚动（避免内容被截断） */
.detail-wrap :deep(.candidate-detail) {
  height: auto;
  min-height: 100%;
  overflow: visible;
}

.detail-wrap :deep(.detail-tabs) {
  overflow: visible;
}

.detail-wrap :deep(.detail-tabs .ant-tabs-content) {
  overflow: visible;
}

.detail-wrap :deep(.detail-tabs .ant-tabs-tabpane) {
  height: auto;
  overflow: visible;
}

.action-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--light-bg-card, #fff);
  border-top: 1px solid var(--border, #e8e8e8);
  flex-wrap: wrap;
}

.action-hint {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin-right: 4px;
}

/* 「进入配方设计」按钮中已选路线的轻量提示 */
.route-hint {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-on-dark);
  font-weight: 400;
}

/* ── Agent 生成进度条 ── */
.agent-progress-bar {
  margin-top: 6px;
  padding: 10px 12px;
  background: var(--light-bg-active);
  border: 1px solid var(--primary-border);
  border-radius: 6px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.progress-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
}

.progress-percent {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}

/* ── Agent 思考过程（可折叠） ── */
.reasoning-bar {
  margin-top: 6px;
  background: var(--light-bg-active);
  border: 1px solid var(--primary-border);
  border-radius: 6px;
  overflow: hidden;
}

.reasoning-bar.is-collapsed {
  background: var(--light-bg-active);
}

.reasoning-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  cursor: pointer;
  user-select: none;
}

.reasoning-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.reasoning-toggle {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.reasoning-content {
  padding: 8px 12px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary, #333);
  white-space: pre-wrap;
  border-top: 1px solid var(--primary-border);
  max-height: 200px;
  overflow-y: auto;
}

/* ── 未选项目时的引导卡片 ── */
.project-guide-card {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  padding: 24px;
}

.guide-card {
  text-align: center;
  padding: 40px;
  max-width: 480px;
  background: var(--light-bg-card, #fff);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--shadow-card, 0 2px 8px rgba(0, 0, 0, 0.06));
}

.guide-card :deep(.ant-card-body) {
  padding: 0;
}

.guide-icon {
  font-size: 48px;
  color: var(--primary);
  margin-bottom: 16px;
  line-height: 1;
}

.guide-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 8px;
}

.guide-desc {
  font-size: 13px;
  color: var(--text-secondary, #475569);
  margin-bottom: 24px;
  line-height: 1.6;
}
</style>
