<template>
  <div class="candidate-workbench">
    <!-- 页面头 + 主视图切换：候选材料工作台（主场景） / 临时材料性能预测（高级能力） -->
    <div class="page-header">
      <h1 class="page-title">候选材料工作台</h1>
      <p class="page-subtitle">第一层配方设计：针对项目任务生成候选材料，进行性质预测与多目标评分，为工艺深化提供候选配方</p>
    </div>
    <div class="mode-switch">
      <a-radio-group v-model:value="mode" class="mode-radio">
        <a-radio-button value="workbench"><ExperimentOutlined /> 候选材料工作台</a-radio-button>
        <a-radio-button value="temp"><LineChartOutlined /> 临时材料性能预测</a-radio-button>
      </a-radio-group>
    </div>

    <!-- ═══════════════ 工作台视图：候选材料流水线 ═══════════════ -->
    <template v-if="mode === 'workbench'">
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
    <!-- 顶部输入区（紧凑单行）：
         项目/任务选择已上移至左侧「项目定位」面板（三栏方案 #1），此处仅展示当前上下文 -->
    <div class="workbench-header">
      <div class="header-row">
        <span class="header-label">当前项目，</span>
        <span class="context-value" :class="{ 'context-empty': !projectCtx.currentProject }">
          {{ projectCtx.currentProject?.name || '全部项目' }}
        </span>
        <span class="header-label">任务，</span>
        <span class="context-value" :class="{ 'context-empty': !projectCtx.currentTask }">
          {{ projectCtx.currentTask?.title || '全部任务' }}
        </span>
        <a-tooltip title="在左侧「项目定位」中选择项目与任务">
          <a-tag class="context-tip" color="blue">切换请在左栏</a-tag>
        </a-tooltip>
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
          <span class="progress-elapsed">{{ generateMode === 'pure_llm' ? 'AI 创造' : 'AI+检索' }} · 已耗时 {{ agentElapsedText }}</span>
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
          :type="materialKind"
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
              :type="materialKind"
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
            <a-button :icon="h(FormOutlined)" @click="goFormulaDesign">
              进入配方设计
              <span v-if="selectedRouteInfo" class="route-hint">·已选路线{{ selectedRouteInfo.route_index + 1 }}</span>
            </a-button>
            <a-button type="primary" :icon="h(ToolOutlined)" @click="goProcessDeepening">
              送去工艺深化
            </a-button>
            <a-button :icon="h(SyncOutlined)" @click="goEcmlIteration">送入闭环迭代</a-button>
            <a-button :icon="h(SaveOutlined)" ghost :loading="saveLoading" @click="saveToLibrary">收藏到物料库</a-button>
            <a-button danger :icon="h(DeleteOutlined)" :loading="deletingCandidate" @click="onDeleteCandidate">
              删除候选
            </a-button>
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
      <template v-if="compareList.length">
        <!-- B2：综合达成度概览 -->
        <div class="compare-achievement" v-if="compareAchievement.length">
          <div
            v-for="a in compareAchievement"
            :key="a._compareKey"
            class="achievement-item"
            :style="{ '--accent': a.color }"
          >
            <span class="achievement-name">{{ a.name }}</span>
            <a-progress
              type="circle"
              :percent="a.percent"
              :size="64"
              :stroke-color="a.color"
              :format="(p) => `${p}%`"
            />
            <span class="achievement-score">{{ a.scoreText }}</span>
          </div>
        </div>

        <!-- B2：多维目标雷达图 -->
        <div class="compare-radar" v-if="compareList.length >= 2">
          <RadarChart :candidates="compareObjectives" />
        </div>

        <a-table
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
      </template>
      <EmptyState v-else type="data" description="尚未加入对比" />
    </a-drawer>
    </template>

    <!-- ═══════════════ 临时材料性能预测（高级能力）：不绑定候选流水线 ═══════════════ -->
    <template v-else>
      <div class="temp-mode-wrap">
        <TemporaryPrediction @promoted="onTempPromoted" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, h, onBeforeUnmount, onMounted, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ECML_RECOMMENDED_TARGET_KEY } from '@/utils/researchContext'
import {
  ReloadOutlined,
  BlockOutlined,
  ExperimentOutlined,
  AuditOutlined,
  SwapOutlined,
  FormOutlined,
  ToolOutlined,
  SaveOutlined,
  SyncOutlined,
  BulbOutlined,
  DownOutlined,
  UpOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  LineChartOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import CandidateList from '@/components/CandidateList.vue'
import CandidateDetail from '@/components/CandidateDetail.vue'
import CandidateAgentBar from '@/components/candidate/CandidateAgentBar.vue'
import TemporaryPrediction from '@/views/TemporaryPrediction.vue'
import RadarChart from '@/components/RadarChart.vue'
import { useUnitSymbols } from '@/utils/mdmDict'
import { useDiscoveryStore } from '@/stores/discovery'
import { useTaskStore } from '@/stores/tasks'
import { useProjectContextStore } from '@/stores/projectContext'
import client from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const route = useRoute()
const discoveryStore = useDiscoveryStore()
const taskStore = useTaskStore()
const projectCtx = useProjectContextStore()
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()

// ── 主视图模式：workbench（候选材料工作台）/ temp（临时材料性能预测）──
// 支持 URL query ?mode=temp 直接进入临时预测（研发工作台派生入口）
const mode = ref(route.query.mode === 'temp' ? 'temp' : 'workbench')

// 临时材料性能预测转正成功 → 切回工作台并定位到新候选
function onTempPromoted(payload) {
  mode.value = 'workbench'
  const c = payload?.candidate
  if (c && c.candidate_id) {
    router.replace({ query: { ...route.query, promote: c.candidate_id } })
  }
}
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
// D1(P2-001)：已耗时计时（Agent 长任务进度反馈）
const agentElapsed = ref(0) // 秒
let _elapsedTimer = null
function _startElapsedTimer() {
  agentElapsed.value = 0
  clearInterval(_elapsedTimer)
  _elapsedTimer = setInterval(() => { agentElapsed.value += 1 }, 1000)
}
function _stopElapsedTimer() {
  clearInterval(_elapsedTimer)
  _elapsedTimer = null
}
const agentElapsedText = computed(() => {
  const s = agentElapsed.value
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}分${s % 60}秒` : `${s}秒`
})
onBeforeUnmount(_stopElapsedTimer)
// 需求7：批量预测状态（三点状态指示）
const candidateStatusMap = computed(() => discoveryStore.candidateStatusMap)
const batchPredicting = computed(() => discoveryStore.batchPredicting)

// 当前首席材料学家 Agent（由子组件加载后回传，供 onRun 构造 payload 使用）
const materialScientistAgentId = ref('')
function onAgentLoaded(agent) {
  materialScientistAgentId.value = agent?.id || ''
}

// 材料类型：完全由领域注册表（/domain-packs）驱动，不再对交付物文本做
// 硬编码关键词猜测。优先取活跃领域包声明的 material_kind，其次取首个
// 声明 material_kind 的领域包；均无时回退默认 crystal。
const domainPacks = ref([])
const materialKind = computed(() => {
  const active = domainPacks.value.find((p) => p.is_active)
  const primary = active || domainPacks.value.find((p) => p.material_kind) || domainPacks.value[0]
  return primary?.material_kind || 'crystal'
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
    { metric: '拉伸强度 (MPa)', key: 'tensile_strength' },
    { metric: '弯曲模量 (MPa)', key: 'flexural_modulus' },
    { metric: '冲击强度 (kJ/m²)', key: 'impact_strength' },
    { metric: '热变形温度 (°C)', key: 'heat_deflection_temp' },
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

// 对比雷达图所需的预测目标（对齐 ECML / 临时预测的 objectives 结构）
const COMPARE_OBJECTIVES = [
  { key: 'tensile_strength', name: '拉伸强度', direction: 'maximize' },
  { key: 'flexural_modulus', name: '弯曲模量', direction: 'maximize' },
  { key: 'impact_strength', name: '冲击强度', direction: 'maximize' },
  { key: 'heat_deflection_temp', name: '热变形温度', direction: 'maximize' },
  { key: 'multi_objective_score', name: '综合评分', direction: 'maximize' },
]

const compareObjectives = computed(() => {
  return compareList.value.map((c) => ({
    ...c,
    objectives: COMPARE_OBJECTIVES.map((o) => ({
      name: o.name,
      key: o.key,
      value: c[o.key] ?? null,
      direction: o.direction,
    })),
  }))
})

// 综合达成度：以 multi_objective_score 为主，缺失时按已有目标取平均
const COMPARE_COLORS = ['#5470c6', '#91cc75', '#fac858', '#ee6666']
const compareAchievement = computed(() => {
  return compareList.value.map((c, idx) => {
    const score = Number.parseFloat(c.multi_objective_score ?? '')
    const percent = Number.isFinite(score)
      ? Math.max(0, Math.min(100, Math.round(score * 100)))
      : 0
    return {
      _compareKey: c._compareKey,
      name: c.name || c.formula || `候选材料 ${idx + 1}`,
      percent,
      scoreText: Number.isFinite(score) ? (score * 100).toFixed(1) + '%' : '暂无评分',
      color: COMPARE_COLORS[idx % COMPARE_COLORS.length],
    }
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

// 加载领域注册表：识别候选材料所属领域 / 材料类型（替代硬编码关键词猜测）
async function loadDomainPacks() {
  try {
    const res = await client.get('/domain-packs')
    domainPacks.value = res?.packs || []
  } catch {
    domainPacks.value = []
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
  // 双向联动：本页选择也更新全局上下文（顶部选择器）
  const pid = selectedProjectId.value
  if (pid && pid !== projectCtx.currentProjectId) {
    const p = projects.value.find((x) => x.project_id === pid)
    if (p) projectCtx.setCurrentProject(p)
  }
}

function onTaskChange() {
  // 切换任务时清空候选结果，并加载该任务下已有的候选列表
  selectedCandidate.value = null
  discoveryStore.clearCandidates()
  loadTaskCandidates()
  // 双向联动：本页任务选择更新全局任务上下文
  const tid = selectedTaskId.value
  if (tid && tid !== projectCtx.currentTaskId) {
    const t = projectTasks.value.find((x) => x.task_id === tid)
    if (t) projectCtx.setCurrentTask(t)
  }
}

// 任务下已有候选列表（来自 GET /tasks/{task_id}/candidates）
const taskCandidates = ref([])
const taskCandidatesLoading = ref(false)

// 全局上下文 → 本页选择（顶部选择器变化时联动，防循环）
// 注意：必须放在 taskCandidates/loadTaskCandidates 声明之后（immediate 首次执行会访问它们）
let syncingFromGlobal = false
watch(
  () => [projectCtx.currentProjectId, projectCtx.currentTaskId],
  ([pid, tid]) => {
    if (syncingFromGlobal) return
    syncingFromGlobal = true
    try {
      if (pid && pid !== selectedProjectId.value) {
        selectedProjectId.value = pid
        onProjectChange()
      }
      if (tid && tid !== selectedTaskId.value) {
        selectedTaskId.value = tid
        onTaskChange()
      }
    } finally {
      syncingFromGlobal = false
    }
  },
  { immediate: true },
)

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

  _startElapsedTimer()
  try {
    // 非阻塞后台任务：提交后立即返回，进度经右下角任务组件/页内步骤条展示
    const res = await discoveryStore.agentGenerateBackground(payload)
    taskStore.addTask({
      id: res.task_id,
      name: `Agent 生成候选材料（${task.title || '未命名任务'}）`,
      type: 'agent',
      link: '/workbench',
      detail: '正在后台生成候选材料…',
    })
    message.success('Agent 生成任务已提交后台执行，可在右下角查看进度')
    // 生成期间先加载已有候选占位，避免列表空白
    await loadTaskCandidates()
  } catch (err) {
    message.error(err?.response?.data?.detail || err?.message || '任务提交失败，请稍后重试', 6)
  } finally {
    _stopElapsedTimer()
  }
}

// 后台任务完成（agentProgress===100）时刷新任务候选列表并选中首个
watch(
  () => discoveryStore.agentProgress,
  (progress) => {
    if (progress === 100) {
      loadTaskCandidates().then(() => {
        if (taskCandidates.value.length > 0) {
          selectedCandidate.value = { ...taskCandidates.value[0] }
        }
        message.success('Agent 生成完成')
      })
    }
  },
)

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
  // 同步清空全局上下文（否则左侧联动 watch 会立即回填）
  projectCtx.clearCurrentProject()
}

// 删除候选材料（#7：被实验/方案/配方引用的候选后端会拒绝，提示改用「淘汰」归档）
const deletingCandidate = ref(false)
async function onDeleteCandidate() {
  const c = selectedCandidate.value
  if (!c) return
  const cid = c.candidate_id || c.id || ''
  if (!cid) return
  Modal.confirm({
    title: '删除候选材料',
    content: `确定删除候选材料「${c.name || c.formula || cid}」吗？删除后不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      deletingCandidate.value = true
      try {
        await client.delete(`/candidates/${encodeURIComponent(cid)}`)
        message.success('候选材料已删除')
        selectedCandidate.value = null
        // 刷新任务候选列表
        if (selectedTaskId.value) await loadTaskCandidates()
      } catch {
        // 错误（含引用 409）由拦截器统一提示
      } finally {
        deletingCandidate.value = false
      }
    },
  })
}

// 选中候选材料
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
    const res = await client.post('/approvals', {
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
    // 展示本次审批进入的目标通道（后端返回；向后兼容用默认「实验审批」）
    const channelLabel = res?.channel_label || '实验审批'
    message.success(`已发起审批，本次将提交至「${channelLabel}」，可在「审批中心」跟踪进度`)
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

// 送去工艺深化：跳转工艺深化工作台，预选该候选（深化服务会自动推进 feasible → process_planning）
function goProcessDeepening() {
  if (!selectedCandidate.value) return
  const c = selectedCandidate.value
  const query = {
    candidate_id: c.candidate_id || c.id || '',
    smiles: c.smiles || '',
  }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ name: 'Synthesis', query })
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
        tensile_strength: selectedCandidate.value.tensile_strength,
        flexural_modulus: selectedCandidate.value.flexural_modulus,
        impact_strength: selectedCandidate.value.impact_strength,
        heat_deflection_temp: selectedCandidate.value.heat_deflection_temp,
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

  // 加载领域注册表，用于识别候选材料所属领域 / 材料类型（替代硬编码关键词猜测）
  loadDomainPacks()

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

/* ── 主视图切换（与合成路径/工艺深化工作台一致） ── */
.mode-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.mode-radio {
  flex: 1;
}
/* 临时材料性能预测：填满剩余空间以便内部滚动 */
.temp-mode-wrap {
  flex: 1;
  overflow: hidden;
  min-height: 0;
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

/* 当前上下文展示（#3：选择器已上移至左侧项目定位面板） */
.context-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-empty {
  color: var(--text-muted);
  font-weight: 400;
}

.context-tip {
  margin: 0;
  flex-shrink: 0;
}

.num-input {
  width: 140px;
  flex-shrink: 0;
}

.prediction-link {
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

/* B2：对比抽屉 —— 达成度 + 雷达图 */
.compare-achievement {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--light-bg-hover, #f8fafc);
  border-radius: 10px;
}
.achievement-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 96px;
}
.achievement-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #475569);
  max-width: 120px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.achievement-score {
  font-size: 12px;
  color: var(--text-secondary, #475569);
  font-variant-numeric: tabular-nums;
}
.compare-radar {
  margin-bottom: 16px;
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 10px;
  padding: 8px;
}
</style>
