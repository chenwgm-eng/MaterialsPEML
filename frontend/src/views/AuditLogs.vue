<template>
  <div class="audit-logs">
    <div class="page-header">
      <h1 class="page-title">审计日志</h1>
      <p class="page-subtitle">全链路操作记录 — 认证、权限拒绝、关键数据变更，追加防篡改、多条件检索</p>
    </div>

    <!-- 汇总卡片 -->
    <div class="stat-row" v-if="total > 0">
      <div class="stat-item">
        <span class="stat-value">{{ total }}</span>
        <span class="stat-label">记录总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ counts.auth }}</span>
        <span class="stat-label">认证事件</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ counts.permission }}</span>
        <span class="stat-label">权限拒绝</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ counts.data }}</span>
        <span class="stat-label">数据变更</span>
      </div>
    </div>

    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">审计记录</span>
          <a-tag color="green" class="count-tag">DB 层级追加防篡改</a-tag>
        </div>
      </template>
      <template #extra>
        <a-space wrap>
          <a-select
            v-model:value="filters.event_type"
            placeholder="事件类型"
            allow-clear
            size="small"
            style="width: 130px"
            :options="eventTypeOptions"
          />
          <a-select
            v-model:value="filters.module"
            placeholder="模块"
            allow-clear
            size="small"
            style="width: 120px"
            :options="moduleOptions"
          />
          <a-input
            v-model:value="filters.operator"
            placeholder="操作者"
            allow-clear
            size="small"
            style="width: 120px"
          />
          <a-select
            v-model:value="filters.resource_type"
            placeholder="资源类型"
            allow-clear
            size="small"
            style="width: 130px"
            :options="resourceTypeOptions"
          />
          <a-input
            v-model:value="filters.resource_id"
            placeholder="资源 ID"
            allow-clear
            size="small"
            style="width: 140px"
          />
          <a-tooltip title="归档早于该时间的记录（仅当前租户，归档后主表删除）">
            <a-date-picker
              v-model:value="archiveDate"
              placeholder="归档截止"
              size="small"
              style="width: 150px"
            />
          </a-tooltip>
          <a-button type="primary" size="small" @click="onSearch">
            <SearchOutlined /> 查询
          </a-button>
          <a-button size="small" @click="onReset">
            <ReloadOutlined /> 重置
          </a-button>
          <a-popconfirm
            title="确认归档该日期之前的全部审计记录？归档后主表记录将被清除且不可恢复。"
            ok-text="归档"
            cancel-text="取消"
            :disabled="!archiveDate"
            @confirm="onArchive"
          >
            <a-button size="small" type="danger" ghost :disabled="!archiveDate">
              <ClockCircleOutlined /> 归档
            </a-button>
          </a-popconfirm>
        </a-space>
      </template>

      <a-table
        :data-source="items"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        size="middle"
        :row-key="(r) => r.entry_id"
        :scroll="{ x: 1100 }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'event_type'">
            <a-tag :color="eventTypeColor(record.event_type)">{{ eventTypeLabel(record.event_type) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <span class="mono">{{ record.action }}</span>
          </template>
          <template v-else-if="column.key === 'operator'">
            <span>{{ record.operator || 'system' }}</span>
          </template>
          <template v-else-if="column.key === 'detail'">
            <a-tooltip :title="formatJson(record.detail)">
              <span class="detail-preview">{{ formatJson(record.detail) }}</span>
            </a-tooltip>
          </template>
          <template v-else-if="column.key === 'created_at'">
            <span class="mono">{{ formatTime(record.created_at) }}</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SearchOutlined, ReloadOutlined, ClockCircleOutlined } from '@ant-design/icons-vue'
import client from '@/api/client'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const counts = reactive({ auth: 0, permission: 0, data: 0 })

const filters = reactive({
  event_type: undefined,
  module: undefined,
  operator: '',
  resource_type: undefined,
  resource_id: '',
})
const archiveDate = ref(null)

const pagination = reactive({ current: 1, pageSize: 20, showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'] })

const eventTypeOptions = [
  { value: 'auth', label: '认证' },
  { value: 'permission_denied', label: '权限拒绝' },
  { value: 'ai_suggestion', label: 'AI 建议' },
  { value: 'human_edit', label: '人工修改' },
  { value: 'decision', label: '决策' },
  { value: 'agent_action', label: 'Agent 动作' },
  { value: 'data_change', label: '数据变更' },
]
const moduleOptions = [
  { value: 'auth', label: '认证' },
  { value: 'candidate', label: '候选材料' },
  { value: 'experiment', label: '实验' },
  { value: 'prediction', label: '预测' },
  { value: 'synthesis', label: '合成' },
  { value: 'ecml', label: '闭环迭代' },
  { value: 'orchestration', label: '编排' },
  { value: 'report', label: '报表' },
]
const resourceTypeOptions = [
  { value: 'candidate', label: '候选材料' },
  { value: 'project', label: '项目' },
  { value: 'experiment', label: '实验' },
  { value: 'report', label: '报表' },
  { value: 'user', label: '用户' },
  { value: 'permission', label: '权限' },
]

const columns = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '事件类型', dataIndex: 'event_type', key: 'event_type', width: 120 },
  { title: '模块', dataIndex: 'module', key: 'module', width: 100 },
  { title: '动作', dataIndex: 'action', key: 'action', width: 140 },
  { title: '操作者', dataIndex: 'operator', key: 'operator', width: 130 },
  { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true },
  { title: '资源', key: 'resource', width: 200 },
]

function eventTypeColor(t) {
  return { auth: 'blue', permission_denied: 'red', ai_suggestion: 'purple', human_edit: 'orange', decision: 'cyan', agent_action: 'magenta', data_change: 'green' }[t] || 'default'
}
function eventTypeLabel(t) {
  const m = eventTypeOptions.find((o) => o.value === t)
  return m ? m.label : (t || '-')
}
function formatJson(d) {
  if (!d || typeof d !== 'object') return String(d || '')
  try {
    return JSON.stringify(d)
  } catch {
    return String(d)
  }
}
function formatTime(t) {
  if (!t) return '-'
  return String(t).replace('T', ' ').slice(0, 19)
}

async function fetchAudit() {
  loading.value = true
  try {
    const params = {
      page: pagination.current,
      page_size: pagination.pageSize,
    }
    if (filters.event_type) params.event_type = filters.event_type
    if (filters.module) params.module = filters.module
    if (filters.operator) params.operator = filters.operator
    if (filters.resource_type) params.resource_type = filters.resource_type
    if (filters.resource_id) params.resource_id = filters.resource_id
    const data = await client.get('/audit/logs', { params })
    items.value = data.items || []
    total.value = data.total || 0
    pagination.current = data.page || 1
    pagination.pageSize = data.page_size || 20
    computeCounts()
  } finally {
    loading.value = false
  }
}

function computeCounts() {
  counts.auth = items.value.filter((i) => i.event_type === 'auth').length
  counts.permission = items.value.filter((i) => i.event_type === 'permission_denied').length
  counts.data = items.value.filter((i) => ['data_change', 'human_edit', 'decision'].includes(i.event_type)).length
}

function onSearch() {
  pagination.current = 1
  fetchAudit()
}
function onReset() {
  Object.assign(filters, { event_type: undefined, module: undefined, operator: '', resource_type: undefined, resource_id: '' })
  pagination.current = 1
  fetchAudit()
}
function onTableChange(pg) {
  pagination.current = pg.current || 1
  pagination.pageSize = pg.pageSize || 20
  fetchAudit()
}

async function onArchive() {
  if (!archiveDate.value) {
    message.warning('请先选择归档截止日期')
    return
  }
  const beforeAt = archiveDate.value.format('YYYY-MM-DDTHH:mm:ss')
  try {
    const data = await client.post('/audit/archive', null, { params: { before_at: beforeAt } })
    message.success(`已归档 ${data.archived} 条记录`)
    archiveDate.value = null
    fetchAudit()
  } catch (e) {
    message.error('归档失败，请稍后重试')
  }
}

onMounted(fetchAudit)
</script>

<style scoped>
.audit-logs {
  padding: 20px 24px;
}
.page-header {
  margin-bottom: 16px;
}
.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0;
}
.page-subtitle {
  color: var(--text-secondary, #888);
  margin: 4px 0 0;
  font-size: 13px;
}
.stat-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.stat-item {
  background: var(--card-bg, #fff);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 10px;
  padding: 14px 20px;
  min-width: 130px;
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin-top: 2px;
}
.card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-title-text {
  font-weight: 600;
}
.count-tag {
  font-size: 12px;
}
.mono {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}
.detail-preview {
  color: var(--text-secondary, #888);
  font-size: 12px;
}
</style>