<template>
  <div class="eval-center">
    <!-- Start New Eval -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <span class="card-title-text">发起新评估</span>
      </template>
      <a-form layout="inline" size="small">
        <a-form-item label="目标类型">
          <a-select v-model:value="form.target_type" style="width: 140px" placeholder="选择类型" :options="targetTypeOptions" />
        </a-form-item>
        <a-form-item label="目标 ID">
          <a-select
            v-model:value="form.target_id"
            style="width: 200px"
            placeholder="请选择目标"
            show-search
            :options="targetIdOptions"
            :loading="targetIdLoading"
            :disabled="!form.target_type"
            :filter-option="(input, option) => option.label?.toLowerCase().includes(input.toLowerCase())"
          />
        </a-form-item>
        <a-form-item label="版本">
          <a-input v-model:value="form.version" style="width: 120px" placeholder="版本" />
        </a-form-item>
        <a-form-item label="数据集">
          <a-select
            v-model:value="form.datasets"
            mode="multiple"
            style="min-width: 200px"
            placeholder="选择数据集"
            :options="datasetOptions"
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" @click="startEval" :loading="starting">
            <PlayCircleOutlined /> 开始评估
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- Eval Runs Table -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">评估运行列表</span>
          <a-button size="small" type="link" @click="refreshSelected" :loading="detailLoading">
            <ReloadOutlined /> 刷新当前
          </a-button>
        </div>
      </template>
      <a-table
        :columns="runColumns"
        :data-source="evalRuns"
        :pagination="{ pageSize: 8, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.eval_run_id"
        :loading="false"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'started_at'">
            <span class="tabular-nums">{{ formatTime(record.started_at) }}</span>
          </template>
          <template v-if="column.key === 'metrics'">
            <span class="text-muted">{{ formatMetricsSummary(record.metrics) }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-button size="small" type="link" @click="viewDetail(record)" :loading="detailLoading && selectedId === record.eval_run_id">
              <EyeOutlined /> 查看详情
            </a-button>
          </template>
        </template>
        <template #emptyText>
          <EmptyState
            type="create"
            description="暂无评估运行，请先发起一个评估"
            action-text="发起评估"
            :action-icon="markRaw(PlayCircleOutlined)"
            @action="scrollToTop"
          />
        </template>
      </a-table>
    </a-card>

    <!-- Eval Detail -->
    <a-card v-if="detail" size="small" :body-style="{ padding: '12px' }" class="section-card">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">评估详情</span>
          <a-button
            v-if="isAdmin && detail.gate?.passed"
            size="small"
            type="primary"
            @click="promote(detail)"
            :loading="promoting"
          >
            <ArrowUpOutlined /> 发布
          </a-button>
        </div>
      </template>
      <a-spin :spinning="detailLoading">
        <!-- 基本信息 -->
        <div class="section-title">基本信息</div>
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="目标类型">{{ formatValue(detail.target_type) }}</a-descriptions-item>
          <a-descriptions-item label="目标 ID">{{ formatValue(detail.target_id) }}</a-descriptions-item>
          <a-descriptions-item label="目标">{{ formatValue(detail.target) }}</a-descriptions-item>
          <a-descriptions-item label="版本">{{ formatValue(detail.version) }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detail.status)">{{ statusLabel(detail.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="开始时间">{{ formatTime(detail.started_at) }}</a-descriptions-item>
          <a-descriptions-item label="完成时间">{{ formatTime(detail.completed_at || detail.finished_at || detail.ended_at) }}</a-descriptions-item>
          <a-descriptions-item label="数据集">{{ formatList(detail.datasets) }}</a-descriptions-item>
        </a-descriptions>

        <!-- 指标分解 -->
        <div class="section-title">指标分解</div>
        <a-table
          v-if="metricsTableData.length"
          :columns="metricsColumns"
          :data-source="metricsTableData"
          :pagination="false"
          size="small"
          :row-key="(r) => r.name"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'value'">
              <pre v-if="isObject(record.value)" class="metric-json">{{ formatJson(record.value) }}</pre>
              <span v-else>{{ formatMetric(record.value) }}</span>
            </template>
          </template>
        </a-table>
        <EmptyState v-else type="data" description="暂无指标数据，评估完成后将展示" />

        <!-- 基线对比 -->
        <div class="section-title">基线对比</div>
        <div v-if="detail.baseline_comparison">
          <a-table
            :columns="comparisonColumns"
            :data-source="comparisonData"
            :pagination="false"
            size="small"
            :row-key="(r) => r.metric"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'current'">
                <span v-if="isObject(record.current)" class="metric-json-inline">{{ formatJson(record.current) }}</span>
                <span v-else>{{ formatMetric(record.current) }}</span>
              </template>
              <template v-if="column.key === 'baseline'">
                <span v-if="isObject(record.baseline)" class="metric-json-inline">{{ formatJson(record.baseline) }}</span>
                <span v-else>{{ formatMetric(record.baseline) }}</span>
              </template>
              <template v-if="column.key === 'delta'">
                <a-tag v-if="record.delta != null" :color="record.delta >= 0 ? 'success' : 'error'">
                  {{ record.delta >= 0 ? '+' : '' }}{{ formatMetric(record.delta) }}
                </a-tag>
                <span v-else>-</span>
              </template>
            </template>
          </a-table>
        </div>
        <EmptyState v-else type="data" description="暂无基线对比数据" />

        <!-- 门禁结果 -->
        <div class="section-title">门禁结果</div>
        <div v-if="detail.gate">
          <a-descriptions :column="1" size="small" bordered>
            <a-descriptions-item label="是否通过">
              <a-tag :color="detail.gate.passed ? 'success' : 'error'">
                {{ detail.gate.passed ? '通过' : '未通过' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item v-if="detail.gate.reasons?.length" label="判定原因">
              <ul class="evidence-list">
                <li v-for="(r, idx) in detail.gate.reasons" :key="idx">{{ formatValue(r) }}</li>
              </ul>
            </a-descriptions-item>
            <a-descriptions-item v-if="detail.gate.score != null" label="门禁分数">
              {{ formatMetric(detail.gate.score) }}
            </a-descriptions-item>
            <a-descriptions-item v-if="detail.gate.threshold != null" label="门禁阈值">
              {{ formatMetric(detail.gate.threshold) }}
            </a-descriptions-item>
          </a-descriptions>
        </div>
        <EmptyState v-else type="data" description="暂无门禁数据" />

        <!-- 失败用例 -->
        <div class="section-title">失败用例</div>
        <div v-if="detail.failure_cases?.length">
          <a-table
            :columns="failureColumns"
            :data-source="detail.failure_cases"
            :pagination="{ pageSize: 5, size: 'small' }"
            size="small"
            :row-key="(r, idx) => idx"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'error'">
                <span v-if="isObject(record.error)" class="metric-json-inline">{{ formatJson(record.error) }}</span>
                <span v-else>{{ formatValue(record.error) }}</span>
              </template>
            </template>
          </a-table>
        </div>
        <EmptyState v-else type="data" description="无失败用例" />
      </a-spin>
    </a-card>

    <!-- Lookup by ID -->
    <a-card size="small" :body-style="{ padding: '12px' }" class="section-card">
      <a-input-search
        v-model:value="lookupId"
        placeholder="输入评估运行 ID 查看详情"
        enter-button="查看"
        size="small"
        style="max-width: 400px"
        @search="lookupEval"
        :loading="detailLoading"
      />
    </a-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, markRaw } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  ReloadOutlined,
  EyeOutlined,
  ArrowUpOutlined,
} from '@ant-design/icons-vue'
import EmptyState from '@/components/EmptyState.vue'
import { useSystemStore } from '@/stores/system'
import { createEvalRun, listEvalRuns, getEvalRun, promoteEval, getProviders, getPolicies } from '@/api/controlPlane'
import { listAgents } from '@/api/agents'
import { getCommitteeCases } from '@/api/committees'
import { getTools } from '@/api/system'
import { useMdmDict } from '@/utils/mdmDict'
import { useAuth } from '@/composables/useAuth'

const systemStore = useSystemStore()
const { isAdmin } = useAuth()

// --- State ---
const evalRuns = ref([])
const starting = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const selectedId = ref('')
const promoting = ref(false)
const lookupId = ref('')
const listLoading = ref(false)
let isMounted = true
onUnmounted(() => { isMounted = false })

const form = reactive({
  target_type: undefined,
  target_id: '',
  version: '',
  datasets: [],
})

const TARGET_TYPE_OPTIONS_FALLBACK = [
  { value: 'model', label: '模型' },
  { value: 'agent', label: '智能体' },
  { value: 'committee', label: '委员会' },
  { value: 'tool', label: '工具' },
  { value: 'policy', label: '策略' },
]
const targetTypeOptions = ref([...TARGET_TYPE_OPTIONS_FALLBACK])

const datasetOptions = [
  { label: '合成路径基准', value: 'synthesis_bench' },
  { label: '材料发现基准', value: 'discovery_bench' },
  { label: '委员会裁决基准', value: 'committee_bench' },
  { label: '工具调用基准', value: 'tool_bench' },
]

// 目标 ID 下拉选项：根据目标类型动态加载
const targetIdOptions = ref([])
const targetIdLoading = ref(false)

async function loadTargetIdOptions(targetType) {
  targetIdOptions.value = []
  if (!targetType) return
  targetIdLoading.value = true
  try {
    let options = []
    if (targetType === 'agent') {
      const resp = await listAgents()
      const agents = resp?.data || resp || []
      options = (Array.isArray(agents) ? agents : []).map(a => ({
        label: a.agent_name || a.name || a.agent_id,
        value: a.agent_id,
      }))
    } else if (targetType === 'committee') {
      const resp = await getCommitteeCases({})
      const cases = resp?.data?.items || resp?.data || resp?.items || []
      options = (Array.isArray(cases) ? cases : []).map(c => ({
        label: c.case_id,
        value: c.case_id,
      }))
    } else if (targetType === 'tool') {
      const resp = await getTools()
      const tools = resp?.data || resp || []
      options = (Array.isArray(tools) ? tools : []).map(t => ({
        label: t.display_name || t.name || t.tool_name,
        value: t.name || t.tool_name,
      }))
    } else if (targetType === 'model') {
      const resp = await getProviders()
      const providers = resp?.providers || resp?.data || []
      options = (Array.isArray(providers) ? providers : []).map(p => ({
        label: `${p.provider_id || p.name || 'provider'} (${p.model_id || p.model || '-'})`,
        value: p.provider_id || p.name || '',
      })).filter(o => o.value)
    } else if (targetType === 'policy') {
      const resp = await getPolicies()
      const policies = resp?.policies || resp?.data || []
      options = (Array.isArray(policies) ? policies : []).map(p => ({
        label: `${p.version || p.policy_id || 'policy'}${p.is_active ? ' · 激活' : ''}`,
        value: p.version || p.policy_id || '',
      })).filter(o => o.value)
    }
    targetIdOptions.value = options
  } catch (e) {
    console.warn('加载目标 ID 失败:', e)
    targetIdOptions.value = []
  } finally {
    targetIdLoading.value = false
  }
}

watch(() => form.target_type, (newType) => {
  form.target_id = ''
  loadTargetIdOptions(newType)
})

// --- Table columns ---
const runColumns = [
  { title: '目标', dataIndex: 'target', key: 'target', width: 140, ellipsis: true },
  { title: '版本', dataIndex: 'version', key: 'version', width: 90 },
  { title: '状态', key: 'status', width: 100 },
  { title: '开始时间', key: 'started_at', width: 160 },
  { title: '指标', key: 'metrics', ellipsis: true },
  { title: '操作', key: 'actions', width: 100, fixed: 'right' },
]

const comparisonColumns = [
  { title: '指标', dataIndex: 'metric', key: 'metric', width: 140 },
  { title: '当前', dataIndex: 'current', key: 'current', width: 120 },
  { title: '基线', dataIndex: 'baseline', key: 'baseline', width: 120 },
  { title: '变化', key: 'delta', width: 100 },
]

const metricsColumns = [
  { title: '指标名', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
  { title: '指标值', dataIndex: 'value', key: 'value' },
]

const failureColumns = [
  { title: '用例 ID', dataIndex: 'case_id', key: 'case_id', width: 140, ellipsis: true },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  { title: '错误', dataIndex: 'error', key: 'error', width: 200, ellipsis: true },
]

// --- Computed ---
const metricsTableData = computed(() => {
  if (!detail.value?.metrics) return []
  const metrics = detail.value.metrics
  if (typeof metrics !== 'object') return []
  return Object.keys(metrics).map((k) => ({
    name: k,
    value: metrics[k],
  }))
})

const comparisonData = computed(() => {
  if (!detail.value?.baseline_comparison) return []
  const bc = detail.value.baseline_comparison
  const metrics = detail.value.metrics || {}
  const baseline = bc.baseline || bc
  const result = []
  for (const key of Object.keys(metrics)) {
    result.push({
      metric: key,
      current: metrics[key],
      baseline: baseline[key] ?? '-',
      delta: (typeof metrics[key] === 'number' && typeof baseline[key] === 'number')
        ? metrics[key] - baseline[key]
        : null,
    })
  }
  return result
})

// --- Label helpers ---
const STATUS_LABELS_FALLBACK = {
  pending: '待处理',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}
const statusLabels = ref({ ...STATUS_LABELS_FALLBACK })
function statusLabel(s) {
  return statusLabels.value[s] || s || '-'
}

// 空状态「发起评估」按钮：滚动到页面顶部的发起新评估卡片
function scrollToTop() {
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

const statusColors = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
}
function statusColor(s) {
  return statusColors[s] || 'default'
}

// --- Formatting ---
const formatTime = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

function formatMetric(val) {
  if (val == null || val === '') return '-'
  if (typeof val === 'number') {
    return Number.isInteger(val) ? String(val) : val.toFixed(4)
  }
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'object') {
    try { return JSON.stringify(val) } catch { return String(val) }
  }
  return String(val)
}

function formatValue(val) {
  if (val == null || val === '') return '-'
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'object') {
    try { return JSON.stringify(val) } catch { return String(val) }
  }
  return String(val)
}

function formatList(val) {
  if (!val) return '-'
  if (!Array.isArray(val)) return formatValue(val)
  if (!val.length) return '-'
  return val.map((v) => (typeof v === 'object' && v !== null) ? JSON.stringify(v) : String(v)).join(', ')
}

function isObject(val) {
  return val !== null && typeof val === 'object' && !Array.isArray(val)
}

function formatJson(val) {
  try {
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

function formatMetricsSummary(metrics) {
  if (!metrics) return '-'
  const keys = Object.keys(metrics)
  if (!keys.length) return '-'
  return keys.slice(0, 3).map((k) => `${k}: ${formatMetric(metrics[k])}`).join(', ') + (keys.length > 3 ? '…' : '')
}

// --- API calls ---
async function startEval() {
  if (!form.target_type || !form.target_id) {
    message.warning('请填写目标类型和目标 ID')
    return
  }
  starting.value = true
  try {
    const res = await createEvalRun({
      target_type: form.target_type,
      target_id: form.target_id,
      version: form.version || undefined,
      datasets: form.datasets,
    })
    if (!isMounted) return
    const run = res.eval_run || res
    if (run?.eval_run_id) {
      evalRuns.value = [run, ...evalRuns.value]
      message.success('评估已启动')
      viewDetail(run)
    }
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) starting.value = false
  }
}

async function viewDetail(record) {
  selectedId.value = record.eval_run_id
  detailLoading.value = true
  detail.value = null
  try {
    const res = await getEvalRun(record.eval_run_id)
    if (!isMounted) return
    detail.value = res.eval_run || res
  } catch {
    if (isMounted) detail.value = null
  } finally {
    if (isMounted) detailLoading.value = false
  }
}

async function refreshSelected() {
  if (!selectedId.value) {
    message.info('未选择评估运行')
    return
  }
  detailLoading.value = true
  try {
    const res = await getEvalRun(selectedId.value)
    if (!isMounted) return
    detail.value = res.eval_run || res
    // 同步更新列表中的记录
    const idx = evalRuns.value.findIndex((r) => r.eval_run_id === selectedId.value)
    if (idx >= 0) {
      evalRuns.value[idx] = { ...evalRuns.value[idx], ...detail.value }
    }
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) detailLoading.value = false
  }
}

async function lookupEval() {
  if (!lookupId.value?.trim()) {
    message.warning('请输入评估运行 ID')
    return
  }
  detailLoading.value = true
  selectedId.value = lookupId.value.trim()
  detail.value = null
  try {
    const res = await getEvalRun(selectedId.value)
    if (!isMounted) return
    detail.value = res.eval_run || res
    // 加入列表
    if (detail.value && !evalRuns.value.find((r) => r.eval_run_id === detail.value.eval_run_id)) {
      evalRuns.value = [detail.value, ...evalRuns.value]
    }
  } catch {
    if (isMounted) detail.value = null
  } finally {
    if (isMounted) detailLoading.value = false
  }
}

async function promote(record) {
  promoting.value = true
  try {
    await promoteEval({
      target_type: record.target_type,
      target_id: record.target_id,
      version: record.version,
      eval_run_id: record.eval_run_id,
    })
    message.success('已发布')
    await refreshSelected()
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) promoting.value = false
  }
}

async function fetchEvalRuns() {
  listLoading.value = true
  try {
    const res = await listEvalRuns()
    if (!isMounted) return
    evalRuns.value = res.eval_runs || []
  } catch {
    // 后端可能无列表端点，静默处理
  } finally {
    if (isMounted) listLoading.value = false
  }
}

onMounted(async () => {
  fetchEvalRuns()

  const { dimensionOptions, statusOptions } = useMdmDict()
  let hasFallback = false
  try {
    const typeOpts = await dimensionOptions('version_type')
    if (typeOpts && typeOpts.length > 0) {
      targetTypeOptions.value = typeOpts
    } else {
      throw new Error('empty')
    }
  } catch {
    hasFallback = true
  }
  try {
    const statusOpts = await statusOptions('run')
    if (statusOpts && statusOpts.length > 0) {
      statusLabels.value = Object.fromEntries(statusOpts.map((o) => [o.value, o.label]))
    } else {
      throw new Error('empty')
    }
  } catch {
    hasFallback = true
  }
  if (hasFallback) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})
</script>

<style scoped>
.eval-center {
  width: 100%;
  max-width: 100%;
  margin: 0;
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

/* Section Title */
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 16px 0 8px;
}

.section-title:first-child {
  margin-top: 0;
}

/* Metrics JSON Display */
.metric-json {
  margin: 0;
  padding: 8px;
  background: var(--light-bg-hover);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow: auto;
}

.metric-json-inline {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

/* Evidence List */
.evidence-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

/* Misc */
.tabular-nums {
  font-variant-numeric: tabular-nums;
}

.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}
</style>
