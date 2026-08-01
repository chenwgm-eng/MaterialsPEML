<template>
  <div class="gantt-chart">
    <!-- Toolbar -->
    <div class="gantt-toolbar">
      <div class="gantt-toolbar-left">
        <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
          <a-radio-button value="day">天</a-radio-button>
          <a-radio-button value="week">周</a-radio-button>
          <a-radio-button value="month">月</a-radio-button>
        </a-radio-group>
      </div>
      <div class="gantt-toolbar-center">
        <a-button size="small" type="text" :disabled="timelineOffset <= 0" @click="shiftTimeline(-1)">
          <template #icon><LeftOutlined /></template>
        </a-button>
        <span class="gantt-timeline-label">{{ timelineLabel }}</span>
        <a-button size="small" type="text" @click="shiftTimeline(1)">
          <template #icon><RightOutlined /></template>
        </a-button>
      </div>
      <div class="gantt-toolbar-right">
        <a-button size="small" @click="goToToday">今天</a-button>
      </div>
    </div>

    <!-- Loading -->
    <a-spin v-if="loading" class="gantt-loading" />

    <!-- Empty state -->
    <EmptyState
      v-else-if="!loading && allTasks.length === 0"
      type="create"
      description="暂无研发计划，请先创建研发计划"
      action-text="创建研发计划"
      @action="router.push('/projects/new')"
    />

    <!-- Chart -->
    <div v-else class="gantt-grid-wrapper">
      <!-- Header -->
      <div class="gantt-header">
        <div class="gantt-sidebar-spacer"></div>
        <div class="gantt-timeline-header" :style="timelineGridStyle">
          <div
            v-for="(unit, i) in timeUnits"
            :key="i"
            class="time-unit-header"
            :class="{ 'time-unit-today': isTodayColumn(unit) }"
          >
            {{ unit.label }}
          </div>
        </div>
      </div>

      <!-- Body -->
      <div class="gantt-body">
        <template v-for="stage in groupedStages" :key="stage.label">
          <div class="stage-header" :style="{ borderLeftColor: stage.color }">
            <span class="stage-dot" :style="{ background: stage.color }"></span>
            <span class="stage-label">{{ stage.label }}</span>
            <span class="stage-count">{{ stage.tasks.length }} 项</span>
          </div>
          <div
            v-for="task in stage.tasks"
            :key="task.id"
            class="task-row"
          >
            <div class="task-info">
              <span class="task-name" :title="getActionLabel(task.action)">{{ getActionLabel(task.action) }}</span>
              <a-button
                size="small"
                type="link"
                class="task-go-btn"
                @click="goToTask(task)"
              >
                <template #icon><PlayCircleOutlined /></template>
                去执行
              </a-button>
            </div>
            <div class="task-timeline" :style="timelineGridStyle">
              <div
                v-for="(unit, i) in timeUnits"
                :key="i"
                class="grid-line-cell"
                :class="{ 'grid-line-today': isTodayColumn(unit) }"
              ></div>
              <div
                class="task-block"
                :style="getBlockStyle(task)"
                :title="getBlockTooltip(task)"
              >
                <span class="task-block-label">{{ getStatusLabel(task.status) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PlayCircleOutlined, PlusOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/EmptyState.vue'
import client from '@/api/client'

const props = defineProps({
  project: { type: Object, default: null },
})

const router = useRouter()

// ── State ──
const loading = ref(false)
const tasks = ref([])
const viewMode = ref('month')
const timelineOffset = ref(0)

// ── Constants ──
const stageConfig = [
  {
    key: 'exploration',
    label: '探索',
    color: '#1890ff',
    bg: '#e6f7ff',
    actions: ['route_material', 'generate_crystal_candidates', 'generate_polymer_candidates'],
    route: '/workbench',
  },
  {
    key: 'verification',
    label: '验证',
    color: '#52c41a',
    bg: '#f6ffed',
    actions: ['predict_crystal_properties', 'predict_polymer_properties', 'verify_dft'],
    route: '/prediction',
  },
  {
    key: 'experiment',
    label: '实验测试',
    color: '#fa8c16',
    bg: '#fff7e6',
    actions: ['design_formula', 'check_synthesis_feasibility'],
    route: '/synthesis',
  },
  {
    key: 'iteration',
    label: '迭代',
    color: '#eb2f96',
    bg: '#fff0f6',
    actions: ['compliance_check'],
    route: '/ecml',
  },
]

const actionLabels = {
  route_material: '材料路由',
  generate_crystal_candidates: '晶体候选生成',
  generate_polymer_candidates: '聚合物候选生成',
  predict_crystal_properties: '晶体性质预测',
  predict_polymer_properties: '聚合物性质预测',
  verify_dft: 'DFT验证',
  design_formula: '配方设计',
  check_synthesis_feasibility: '合成可行性',
  compliance_check: '合规审查',
}

const statusColorMap = {
  '待执行': '#d9d9d9',
  '进行中': '#1890ff',
  '已完成': '#52c41a',
  '已延期': '#ff4d4f',
  // 兼容后端 ProjectTask.status
  'draft': '#d9d9d9',
  'active': '#1890ff',
  'completed': '#52c41a',
  'cancelled': '#ff4d4f',
}

const statusLabelMap = {
  '待执行': '待执行',
  '进行中': '进行中',
  '已完成': '已完成',
  '已延期': '已延期',
  // 兼容后端 ProjectTask.status
  'draft': '待执行',
  'active': '进行中',
  'completed': '已完成',
  'cancelled': '已延期',
}

// ── Data fetching ──
async function fetchTasks() {
  if (!props.project?.project_id) {
    tasks.value = props.project?.tasks || []
    return
  }
  loading.value = true
  try {
    const data = await client.get(`/projects/${props.project.project_id}/tasks`)
    const raw = Array.isArray(data) ? data : (data.tasks || data.data || [])
    // 后端可能未返回 action 字段，根据 deliverable/title 推断甘特图阶段分组
    tasks.value = raw.map((t) => ({
      ...t,
      action: t.action || inferAction(t),
      start_date: t.start_date || '',
      end_date: t.end_date || '',
    }))
  } catch {
    tasks.value = props.project.tasks || []
  } finally {
    loading.value = false
  }
}

// 根据任务交付物/标题推断甘特图阶段动作
function inferAction(task) {
  const text = `${task.deliverable || ''} ${task.title || ''}`.toLowerCase()
  if (text.includes('路由') || text.includes('route')) return 'route_material'
  if (text.includes('聚合物') || text.includes('polymer')) return 'generate_polymer_candidates'
  if (text.includes('生成') || text.includes('候选') || text.includes('discover')) return 'generate_crystal_candidates'
  if (text.includes('dft') || text.includes('验证')) return 'verify_dft'
  if (text.includes('预测') || text.includes('predict')) return 'predict_crystal_properties'
  if (text.includes('配方') || text.includes('formula')) return 'design_formula'
  if (text.includes('合成') || text.includes('synthesis')) return 'check_synthesis_feasibility'
  if (text.includes('合规') || text.includes('compliance')) return 'compliance_check'
  // 默认归入探索阶段
  return 'route_material'
}

watch(() => props.project?.project_id, () => {
  timelineOffset.value = 0
  fetchTasks()
}, { immediate: false })

onMounted(() => {
  fetchTasks()
})

// ── All tasks (flattened) ──
const allTasks = computed(() => tasks.value)

// ── Stage grouping ──
const groupedStages = computed(() => {
  return stageConfig.map((stage) => {
    const stageTasks = tasks.value.filter((t) => stage.actions.includes(t.action))
    return { ...stage, tasks: stageTasks }
  })
})

// ── Timeline ──
function getBaseDate() {
  const now = new Date()
  if (viewMode.value === 'month') {
    return new Date(now.getFullYear(), now.getMonth(), 1)
  }
  if (viewMode.value === 'week') {
    const day = now.getDay()
    const monday = new Date(now)
    monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1))
    monday.setHours(0, 0, 0, 0)
    return monday
  }
  // day
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

function shiftBaseDate(base, offset) {
  const d = new Date(base)
  if (viewMode.value === 'month') {
    d.setMonth(d.getMonth() + offset)
  } else if (viewMode.value === 'week') {
    d.setDate(d.getDate() + offset * 7)
  } else {
    d.setDate(d.getDate() + offset)
  }
  return d
}

const timeUnits = computed(() => {
  const base = getBaseDate()
  const shifted = shiftBaseDate(base, timelineOffset.value)
  const units = []
  const count = viewMode.value === 'month' ? 3 : viewMode.value === 'week' ? 12 : 30

  for (let i = 0; i < count; i++) {
    let start, end, label
    if (viewMode.value === 'month') {
      start = new Date(shifted.getFullYear(), shifted.getMonth() + i, 1)
      end = new Date(shifted.getFullYear(), shifted.getMonth() + i + 1, 0)
      label = `${start.getMonth() + 1}月`
    } else if (viewMode.value === 'week') {
      start = new Date(shifted)
      start.setDate(shifted.getDate() + i * 7)
      end = new Date(start)
      end.setDate(start.getDate() + 6)
      label = `${start.getMonth() + 1}/${start.getDate()}`
    } else {
      start = new Date(shifted)
      start.setDate(shifted.getDate() + i)
      end = new Date(start)
      label = `${start.getMonth() + 1}/${start.getDate()}`
    }
    units.push({ start, end, label })
  }
  return units
})

const timelineGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${timeUnits.value.length}, 1fr)`,
}))

const timelineLabel = computed(() => {
  if (timeUnits.value.length === 0) return ''
  const first = timeUnits.value[0]
  const last = timeUnits.value[timeUnits.value.length - 1]
  const fmt = (d) => `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
  return `${fmt(first.start)} — ${fmt(last.end)}`
})

function shiftTimeline(delta) {
  timelineOffset.value += delta
}

function goToToday() {
  timelineOffset.value = 0
}

function isTodayColumn(unit) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const start = new Date(unit.start)
  start.setHours(0, 0, 0, 0)
  const end = new Date(unit.end)
  end.setHours(23, 59, 59, 999)
  return today >= start && today <= end
}

// ── Block positioning ──
function getBlockStyle(task) {
  const timelineStart = timeUnits.value[0]?.start
  const timelineEnd = timeUnits.value[timeUnits.value.length - 1]?.end
  if (!timelineStart || !timelineEnd) {
    return { left: '0%', width: '3%', backgroundColor: statusColorMap[task.status] || '#d9d9d9' }
  }

  const totalMs = timelineEnd.getTime() - timelineStart.getTime()

  if (!task.start_date || !task.end_date) {
    return {
      left: '0%',
      width: '3%',
      backgroundColor: statusColorMap[task.status] || '#d9d9d9',
    }
  }

  const taskStart = new Date(task.start_date).getTime()
  const taskEnd = new Date(task.end_date).getTime()

  const leftPercent = Math.max(0, ((taskStart - timelineStart.getTime()) / totalMs) * 100)
  const widthPercent = Math.max(2, Math.min(100 - leftPercent, ((taskEnd - taskStart) / totalMs) * 100))

  return {
    left: `${leftPercent}%`,
    width: `${widthPercent}%`,
    backgroundColor: statusColorMap[task.status] || '#d9d9d9',
  }
}

function getBlockTooltip(task) {
  const action = getActionLabel(task.action)
  const status = getStatusLabel(task.status)
  let dateStr = ''
  if (task.start_date && task.end_date) {
    dateStr = `${task.start_date} ~ ${task.end_date}`
  }
  return `${action} · ${status}${dateStr ? ' · ' + dateStr : ''}`
}

// ── Helpers ──
function getActionLabel(action) {
  return actionLabels[action] || action || '未知任务'
}

function getStatusLabel(status) {
  return statusLabelMap[status] || status || '未知'
}

function getStageForAction(action) {
  return stageConfig.find((s) => s.actions.includes(action))
}

// ── Navigation ──
function goToTask(task) {
  const stage = getStageForAction(task.action)
  const route = stage?.route || '/workbench'
  const query = {}
  if (task.material_scope) query.material_scope = task.material_scope
  if (task.target_properties) query.target_properties = task.target_properties
  router.push({ path: route, query })
}
</script>

<style scoped>
.gantt-chart {
  background: var(--realsee-surface, #fff);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

/* ── Toolbar ── */
.gantt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--border);
  gap: var(--space-md);
}

.gantt-toolbar-center {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.gantt-timeline-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  min-width: 200px;
  text-align: center;
  white-space: nowrap;
}

/* ── Loading / Empty ── */
.gantt-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* ── Grid wrapper ── */
.gantt-grid-wrapper {
  overflow-x: auto;
}

/* ── Header ── */
.gantt-header {
  display: flex;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--realsee-surface, #fff);
}

.gantt-sidebar-spacer {
  width: 240px;
  flex-shrink: 0;
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  border-right: 1px solid var(--border);
}

.gantt-timeline-header {
  flex: 1;
  display: grid;
  min-width: 0;
}

.time-unit-header {
  padding: var(--space-sm) 4px;
  text-align: center;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
  border-right: 1px solid var(--border-light);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.time-unit-header:last-child {
  border-right: none;
}

.time-unit-today {
  background: var(--primary-bg);
  color: var(--primary);
  font-weight: var(--font-weight-semibold);
}

/* ── Body ── */
.gantt-body {
  display: flex;
  flex-direction: column;
}

/* ── Stage header ── */
.stage-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-lg);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  background: var(--realsee-surface-soft);
  border-bottom: 1px solid var(--border);
  border-left: 3px solid;
}

.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.stage-count {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-normal);
  color: var(--text-muted);
  margin-left: auto;
}

/* ── Task row ── */
.task-row {
  display: flex;
  border-bottom: 1px solid var(--border-light);
  min-height: 44px;
  transition: background var(--transition-fast);
}

.task-row:hover {
  background: var(--light-bg-hover);
}

.task-row:last-child {
  border-bottom: none;
}

.task-info {
  width: 240px;
  flex-shrink: 0;
  padding: var(--space-xs) var(--space-md);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-xs);
  border-right: 1px solid var(--border);
}

.task-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.task-go-btn {
  font-size: var(--font-size-xs);
  padding: 0 4px;
  height: 24px;
  flex-shrink: 0;
}

/* ── Task timeline ── */
.task-timeline {
  flex: 1;
  display: grid;
  position: relative;
  min-width: 0;
}

.grid-line-cell {
  border-right: 1px solid var(--border-light);
  min-height: 44px;
}

.grid-line-cell:last-child {
  border-right: none;
}

.grid-line-today {
  background: rgba(37, 99, 235, 0.03);
}

/* ── Task block ── */
.task-block {
  position: absolute;
  top: 6px;
  bottom: 6px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  cursor: default;
  transition: filter var(--transition-fast);
}

.task-block:hover {
  filter: brightness(0.92);
}

.task-block-label {
  font-size: 10px;
  color: #fff;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}
</style>