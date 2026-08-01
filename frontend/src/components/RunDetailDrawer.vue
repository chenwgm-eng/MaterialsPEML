<template>
  <a-drawer
    :open="open"
    :width="640"
    title="运行详情"
    placement="right"
    @update:open="(v) => $emit('update:open', v)"
  >
    <a-spin :spinning="loading">
      <div v-if="run">
        <!-- Run Info -->
        <a-descriptions size="small" :column="1" bordered>
          <a-descriptions-item label="运行 ID">{{ run.run_id }}</a-descriptions-item>
          <a-descriptions-item label="类型">{{ runTypeLabel(run.type) }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(run.status)">{{ statusLabel(run.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="项目">{{ run.project_id || '-' }}</a-descriptions-item>
          <a-descriptions-item label="策略版本">{{ run.policy_version || '-' }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ formatTime(run.created_at) }}</a-descriptions-item>
        </a-descriptions>

        <!-- Timeline -->
        <div class="section-title">事件时间线</div>
        <EmptyState v-if="!events.length" type="data" description="暂无事件数据" />
        <div v-else class="event-timeline">
          <div v-for="(evt, idx) in events" :key="idx" class="event-item">
            <div class="event-dot" :class="'dot-' + (eventColors[evt.event_type] || 'default')"></div>
            <div class="event-body">
              <div class="event-header">
                <span class="event-type">{{ eventTypeLabel(evt.event_type) }}</span>
                <span class="event-time">{{ formatTime(evt.timestamp) }}</span>
              </div>
              <div class="event-summary" v-if="evt.summary">{{ evt.summary }}</div>
              <a-collapse
                v-if="evt.details && Object.keys(evt.details).length"
                :bordered="false"
                ghost
                size="small"
              >
                <a-collapse-panel key="detail" header="详情">
                  <pre class="event-detail">{{ formatDetail(evt.details) }}</pre>
                </a-collapse-panel>
              </a-collapse>
            </div>
          </div>
        </div>
      </div>
      <EmptyState v-else-if="!loading" type="data" description="暂无运行数据" />
    </a-spin>
  </a-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { getRun, getTrace } from '@/api/controlPlane'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  runId: { type: String, default: '' },
})
defineEmits(['update:open'])

const loading = ref(false)
const run = ref(null)
const events = ref([])

const runTypeLabels = {
  ecml: '实验闭环迭代',
  discovery: '材料发现',
  prediction: '性质预测',
  synthesis: '合成路径',
  orchestration: 'Agent 编排',
}
function runTypeLabel(type) {
  return runTypeLabels[type] || type || '-'
}

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

const eventTypeLabels = {
  checkpoint: '检查点',
  tool_invocation: '工具调用',
  committee_case: '委员会案件',
  policy_decision: '策略决策',
}
function eventTypeLabel(t) {
  return eventTypeLabels[t] || t || '-'
}

const eventColors = {
  checkpoint: 'blue',
  tool_invocation: 'cyan',
  committee_case: 'purple',
  policy_decision: 'orange',
  default: 'default',
}

const formatTime = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

const SENSITIVE_KEYS = ['thinking', 'reasoning', 'api_key', 'secret', 'token', 'password', 'authorization', 'internal_reasoning', 'secret_ref']
function sanitizeDetail(obj) {
  if (Array.isArray(obj)) return obj.map(sanitizeDetail)
  if (obj && typeof obj === 'object') {
    return Object.fromEntries(Object.entries(obj).map(([k, v]) =>
      SENSITIVE_KEYS.some((s) => k.toLowerCase().includes(s)) ? [k, '***'] : [k, sanitizeDetail(v)],
    ))
  }
  return obj
}

const formatDetail = (details) => {
  if (!details) return ''
  if (typeof details === 'string') return details
  return JSON.stringify(sanitizeDetail(details), null, 2)
}

async function fetchRun(runId) {
  loading.value = true
  run.value = null
  events.value = []
  try {
    const res = await getRun(runId)
    run.value = res.run || res
    const correlationId = run.value?.correlation_id
    if (correlationId) {
      try {
        const trace = await getTrace(correlationId)
        events.value = trace.events || trace.spans || []
      } catch {
        events.value = []
      }
    }
  } catch {
    run.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.runId],
  ([isOpen, id]) => {
    if (isOpen && id) {
      fetchRun(id)
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.section-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 20px 0 12px;
}

.event-timeline {
  padding-left: 4px;
}

.event-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
}

.event-item:last-child {
  border-bottom: none;
}

.event-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

.dot-blue { background: var(--primary); box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15); }
.dot-purple { background: #8b5cf6; box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15); }
.dot-cyan { background: #06b6d4; box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.15); }
.dot-green { background: var(--success); box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); }
.dot-orange { background: var(--warning); box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15); }
.dot-red { background: var(--error); box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15); }
.dot-default { background: #6b7280; box-shadow: 0 0 0 3px rgba(107, 114, 128, 0.15); }

.event-body {
  flex: 1;
  min-width: 0;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.event-type {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.event-time {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.event-summary {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
  line-height: 1.5;
}

.event-detail {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin: 4px 0 0;
  font-family: var(--font-family-mono);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow-y: auto;
}
</style>
