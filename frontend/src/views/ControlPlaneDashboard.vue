<template>
  <div class="control-plane-dashboard">
    <div class="page-header">
      <div>
        <h1 class="page-title">控制平面</h1>
        <p class="page-subtitle">运行调度与资源治理中心：集中监控 AI/ECML 运行队列、模型服务健康度和资源预算用量</p>
      </div>
      <a-tooltip title="控制平面帮助运维人员统一查看运行状态、模型服务健康、预算消耗，并可在失败时恢复或取消运行。">
        <InfoCircleOutlined class="header-tip" />
      </a-tooltip>
    </div>

    <!-- 页面导览：用业务语言解释三个核心板块 -->
    <a-alert
      type="info"
      show-icon
      message="本页能做什么？"
      :description="pageGuide"
      class="page-guide"
    />

    <!-- Summary Metrics -->
    <div class="metrics-row">
      <a-tooltip title="历史累计的运行任务总数">
        <div class="metric-card">
          <div class="metric-icon" style="background: var(--primary-bg); color: var(--primary)">
            <ControlOutlined />
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ metrics.total }}</div>
            <div class="metric-label">总运行数</div>
          </div>
        </div>
      </a-tooltip>
      <a-tooltip title="当前正在执行的运行任务数">
        <div class="metric-card">
          <div class="metric-icon" style="background: var(--info-bg); color: var(--info)">
            <SyncOutlined :spin="true" v-if="metrics.running > 0" />
            <SyncOutlined v-else />
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ metrics.running }}</div>
            <div class="metric-label">运行中</div>
          </div>
        </div>
      </a-tooltip>
      <a-tooltip title="排队等待资源或依赖条件的运行任务数">
        <div class="metric-card">
          <div class="metric-icon" style="background: var(--warning-bg); color: var(--warning)">
            <ClockCircleOutlined />
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ metrics.waiting }}</div>
            <div class="metric-label">等待中</div>
          </div>
        </div>
      </a-tooltip>
      <a-tooltip title="执行失败、需要关注或恢复的运行任务数">
        <div class="metric-card">
          <div class="metric-icon" style="background: var(--error-bg); color: var(--error)">
            <CloseCircleOutlined />
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ metrics.failed }}</div>
            <div class="metric-label">失败</div>
          </div>
        </div>
      </a-tooltip>
      <a-tooltip title="处于暂停、失败或恢复中的运行，可点击恢复按钮继续">
        <div class="metric-card">
          <div class="metric-icon metric-icon-warning">
            <WarningOutlined />
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ metrics.recovery_needed }}</div>
            <div class="metric-label">需恢复</div>
          </div>
        </div>
      </a-tooltip>
    </div>

    <!-- Run Queue -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">运行队列</span>
          <a-button size="small" type="link" @click="fetchRuns" :loading="loading">
            <ReloadOutlined /> 刷新
          </a-button>
        </div>
      </template>
      <a-table
        :columns="runColumns"
        :data-source="runs"
        :pagination="{ pageSize: 8, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.run_id"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            <span class="tabular-nums">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-button size="small" type="link" aria-label="查看详情" @click="viewTrace(record)">
                <EyeOutlined /> 查看详情
              </a-button>
              <a-tooltip :title="canResume(record.status) ? '恢复' : '仅已暂停/已阻断的运行可恢复'">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    type="primary"
                    aria-label="恢复运行"
                    @click="resumeRun(record)"
                    :loading="resumingId === record.run_id"
                    :disabled="!canResume(record.status)"
                  >
                    <PlayCircleOutlined />
                  </a-button>
                </span>
              </a-tooltip>
              <a-tooltip :title="canCancel(record.status) ? '取消' : '仅进行中的运行可取消'">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    danger
                    aria-label="取消运行"
                    @click="cancelRun(record)"
                    :loading="cancellingId === record.run_id"
                    :disabled="!canCancel(record.status)"
                  >
                    <StopOutlined />
                  </a-button>
                </span>
              </a-tooltip>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <EmptyState type="data" description="暂无运行记录" />
        </template>
      </a-table>
    </a-card>

    <!-- Provider Health -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <div class="card-title-row">
          <a-space size="small">
            <span class="card-title-text">模型连接健康</span>
            <a-tooltip title="展示 LLM/DFT/外部服务等模型 Provider 的健康状态，便于快速发现服务异常">
              <InfoCircleOutlined style="color: var(--text-muted)" />
            </a-tooltip>
          </a-space>
          <a-button size="small" type="link" @click="fetchProviders" :loading="providerLoading">
            <ReloadOutlined /> 刷新
          </a-button>
        </div>
      </template>
      <a-spin :spinning="providerLoading">
        <EmptyState v-if="!providers.length" type="data" description="暂无 Provider 数据" />
        <a-table
          v-else
          :columns="providerColumns"
          :data-source="providers"
          :pagination="false"
          size="small"
          :row-key="(r) => r.name"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'health'">
              <a-tag v-if="record.configured === false" color="default">未配置</a-tag>
              <a-tag v-else-if="!record.health && !record.health_status" color="default">
                <a-tooltip title="尚未执行健康探测。在「系统设置」配置对应服务后，点击上方「刷新」触发探测">
                  未探测
                </a-tooltip>
              </a-tag>
              <a-tag v-else :color="healthColor(record.health || record.health_status)">{{ healthLabel(record.health || record.health_status) }}</a-tag>
            </template>
            <template v-if="column.key === 'last_check'">
              <span class="tabular-nums">{{ formatTime(record.last_check || record.last_health_check) }}</span>
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-card>

    <!-- Budget Overview -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <div class="card-title-row">
          <a-space size="small">
            <span class="card-title-text">资源用量预算</span>
            <a-tooltip title="按组织/项目/运行等维度展示 Token、外部调用、DFT 时长、成本、并发等资源的预算限额与已用量">
              <InfoCircleOutlined style="color: var(--text-muted)" />
            </a-tooltip>
          </a-space>
          <a-button size="small" type="link" @click="fetchBudgets" :loading="budgetLoading">
            <ReloadOutlined /> 刷新
          </a-button>
        </div>
      </template>
      <a-spin :spinning="budgetLoading">
        <div v-if="budgets.length" class="budget-hint">
          用量 = 已消耗 / 限额；类别含义：令牌（Token 数）、外部调用（SCP 服务调用次数）、DFT CPU 时长（小时）、成本（¥）、并发（同时运行任务数）
        </div>
        <EmptyState v-if="!budgets.length" type="data" description="暂无预算数据" />
        <a-table
          v-else
          :columns="budgetColumns"
          :data-source="budgets"
          :pagination="{ pageSize: 5, size: 'small' }"
          size="small"
          :row-key="(r) => (r.scope + '-' + r.scope_id + '-' + r.category)"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'scope'">
              <a-tag>{{ scopeLabels[record.scope] || record.scope || '-' }}</a-tag>
            </template>
            <template v-if="column.key === 'category'">
              <a-tag>{{ categoryLabel(record.category) }}</a-tag>
            </template>
            <template v-if="column.key === 'usage'">
              <div class="usage-cell">
                <a-progress
                  :percent="usagePercent(record)"
                  :stroke-color="usageColor(usagePercent(record))"
                  size="small"
                  :show-info="false"
                />
                <span class="usage-text">{{ usageText(record) }}</span>
              </div>
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-card>

    <!-- Run Detail Drawer -->
    <RunDetailDrawer v-model:open="drawerVisible" :run-id="selectedRunId" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  ControlOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  ReloadOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  StopOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons-vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  getRuns,
  resumeRun as resumeRunApi,
  cancelRun as cancelRunApi,
  getProviders,
  getBudgets,
} from '@/api/controlPlane'
import { useProjectContextStore } from '@/stores/projectContext'
import RunDetailDrawer from '@/components/RunDetailDrawer.vue'

const projectContext = useProjectContextStore()

// --- State ---
const runs = ref([])
const loading = ref(false)
const providers = ref([])
const providerLoading = ref(false)
const budgets = ref([])
const budgetLoading = ref(false)
const resumingId = ref('')
const cancellingId = ref('')
const drawerVisible = ref(false)
const selectedRunId = ref('')
let isMounted = true
onUnmounted(() => { isMounted = false })

const pageGuide = '1）运行队列：查看所有 AI/ECML 任务的执行状态，对失败或暂停的任务可「恢复」或「取消」；2）模型连接健康：检查 LLM、DFT 等外部服务是否可用，及时发现连接异常；3）资源用量预算：监控 Token、调用次数、成本等资源消耗，避免预算超支。'

const metrics = reactive({
  total: 0,
  running: 0,
  waiting: 0,
  failed: 0,
  recovery_needed: 0,
})

// --- Table columns ---
const runColumns = [
  { title: '运行 ID', dataIndex: 'run_id', key: 'run_id', width: 140, ellipsis: true },
  { title: '类型', dataIndex: 'type', key: 'type', width: 100, customRender: ({ text }) => text || '-' },
  { title: '状态', key: 'status', width: 100 },
  { title: '项目', dataIndex: 'project_id', key: 'project_id', width: 100, ellipsis: true, customRender: ({ text }) => text || '—' },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 130, fixed: 'right' },
]

const providerColumns = [
  { title: '模型/服务', dataIndex: 'name', key: 'name', width: 140 },
  { title: '服务类型', dataIndex: 'type', key: 'type', width: 120 },
  { title: '健康状态', key: 'health', width: 110 },
  { title: '版本', dataIndex: 'version', key: 'version', width: 100, customRender: ({ text }) => text || '—' },
  { title: '最后检查', key: 'last_check', width: 160 },
]

const budgetColumns = [
  { title: '范围', dataIndex: 'scope', key: 'scope', width: 110 },
  { title: '范围 ID', dataIndex: 'scope_id', key: 'scope_id', width: 140, ellipsis: true },
  { title: '类别', key: 'category', width: 110 },
  { title: '用量', key: 'usage' },
]

// --- Label helpers ---
const statusLabels = {
  running: '运行中',
  waiting: '等待中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  paused: '已暂停',
  recovery: '恢复中',
}
function statusLabel(s) {
  return statusLabels[s] || s || '-'
}

const statusColors = {
  running: 'processing',
  waiting: 'gold',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
  paused: 'orange',
  recovery: 'volcano',
}
function statusColor(s) {
  return statusColors[s] || 'default'
}

const healthLabels = {
  healthy: '健康',
  degraded: '降级',
  unhealthy: '异常',
  unknown: '未知',
}
function healthLabel(h) {
  return healthLabels[h] || h || '-'
}

const healthColors = {
  healthy: 'success',
  degraded: 'warning',
  unhealthy: 'error',
  unknown: 'default',
}
function healthColor(h) {
  return healthColors[h] || 'default'
}

const categoryLabels = {
  token: '令牌',
  external_call: '外部调用',
  dft_cpu_hour: 'DFT CPU 时长',
  cost: '成本',
  concurrency: '并发',
}
function categoryLabel(c) {
  return categoryLabels[c] || c || '-'
}

const scopeLabels = {
  organization: '组织',
  project: '项目',
  ecml_run: 'ECML 运行',
  committee_case: '委员会案件',
  user: '用户',
}

// --- Action helpers ---
const resumableStatuses = ['paused', 'failed', 'recovery']
const cancellableStatuses = ['running', 'waiting', 'paused']

function canResume(status) {
  return resumableStatuses.includes(status)
}
function canCancel(status) {
  return cancellableStatuses.includes(status)
}

// --- Formatting ---
const formatTime = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

function usagePercent(b) {
  const used = (b.reserved || 0) + (b.settled || 0)
  const limit = b.limit
  if (!limit || limit <= 0) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

function usageColor(pct) {
  if (pct >= 90) return '#1d4ed8'
  if (pct >= 70) return '#3b82f6'
  return '#93c5fd'
}

function usageText(b) {
  const used = (b.reserved || 0) + (b.settled || 0)
  const limit = b.limit || 0
  return `${used} / ${limit}`
}

// --- API calls ---
async function fetchRuns() {
  loading.value = true
  try {
    const res = await getRuns()
    if (!isMounted) return
    runs.value = res.runs || res.items || []
    computeMetrics()
  } catch {
    if (isMounted) runs.value = []
  } finally {
    if (isMounted) loading.value = false
  }
}

function computeMetrics() {
  metrics.total = runs.value.length
  metrics.running = runs.value.filter((r) => r.status === 'running').length
  metrics.waiting = runs.value.filter((r) => r.status === 'waiting').length
  metrics.failed = runs.value.filter((r) => r.status === 'failed').length
  metrics.recovery_needed = runs.value.filter((r) => ['paused', 'recovery', 'failed'].includes(r.status)).length
}

async function fetchProviders() {
  providerLoading.value = true
  try {
    const res = await getProviders()
    if (!isMounted) return
    providers.value = res.providers || res.items || []
  } catch {
    if (isMounted) providers.value = []
  } finally {
    if (isMounted) providerLoading.value = false
  }
}

async function fetchBudgets() {
  budgetLoading.value = true
  try {
    // 优先按当前项目上下文过滤预算，无上下文时展示全部
    const pid = projectContext.currentProjectId
    const res = await getBudgets(pid ? { scope: 'project', scope_id: pid } : {})
    if (!isMounted) return
    budgets.value = res.budgets || res.items || []
  } catch {
    if (isMounted) budgets.value = []
  } finally {
    if (isMounted) budgetLoading.value = false
  }
}

function viewTrace(record) {
  selectedRunId.value = record.run_id
  drawerVisible.value = true
}

async function resumeRun(record) {
  resumingId.value = record.run_id
  try {
    await resumeRunApi(record.run_id)
    message.success('运行已恢复')
    await fetchRuns()
  } catch {
    // handled by interceptor
  } finally {
    resumingId.value = ''
  }
}

async function cancelRun(record) {
  cancellingId.value = record.run_id
  try {
    await cancelRunApi(record.run_id)
    message.success('运行已取消')
    await fetchRuns()
  } catch {
    // handled by interceptor
  } finally {
    cancellingId.value = ''
  }
}

// --- Lifecycle ---
let timer = null
onMounted(() => {
  fetchRuns()
  fetchProviders()
  fetchBudgets()
  timer = setInterval(() => {
    if (metrics.running > 0) fetchRuns()
  }, 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.control-plane-dashboard {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.page-guide {
  margin-bottom: 16px;
}

.header-tip {
  font-size: 18px;
  color: var(--text-muted);
  cursor: help;
}

/* Metrics Row */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: box-shadow var(--transition), border-color var(--transition);
}

.metric-card:hover {
  box-shadow: var(--shadow-hover);
  border-color: var(--primary-border);
}

.metric-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.metric-icon-warning {
  background: var(--primary-bg, #eef4ff);
  color: var(--primary, #1d4ed8);
}

.metric-body {
  flex: 1;
  min-width: 0;
}

.metric-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Section Card */
.section-card {
  margin-bottom: 16px;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title-text {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

/* Usage Cell */
.usage-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.budget-hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 0 0 8px;
}

.usage-cell :deep(.ant-progress) {
  flex: 1;
  min-width: 80px;
}

.usage-text {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* Misc */
.tabular-nums {
  font-variant-numeric: tabular-nums;
}

/* Responsive */
@media (max-width: 1024px) {
  .metrics-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }
}
</style>
