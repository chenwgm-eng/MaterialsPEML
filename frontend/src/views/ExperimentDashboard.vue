<template>
  <div class="experiment-dashboard">
    <div class="page-header">
      <h1 class="page-title">实验数据看板</h1>
      <p class="page-subtitle">整合样品、设备与实验结果三类数据，快速掌握实验数据全貌</p>
    </div>

    <!-- 汇总卡片 -->
    <div class="stat-row">
      <div class="stat-item">
        <span class="stat-value">{{ samples.length }}</span>
        <span class="stat-label">样品总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ equipment.length }}</span>
        <span class="stat-label">设备总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ results.length }}</span>
        <span class="stat-label">实验结果数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ qcPending.length }}</span>
        <span class="stat-label">QC 待审数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ orders.length }}</span>
        <span class="stat-label">实验任务数</span>
      </div>
    </div>

    <!-- 状态分布 -->
    <div class="dist-row">
      <!-- 设备状态分布 -->
      <a-card class="table-card" :bordered="false">
        <template #title>
          <div class="card-title-row">
            <span class="card-title-text">设备状态分布</span>
            <a-tag color="blue" class="count-tag">{{ equipment.length }} 台</a-tag>
          </div>
        </template>
        <div class="dist-list">
          <div v-for="item in equipmentDist" :key="item.status" class="dist-item">
            <a-tag :color="item.color" class="dist-tag">{{ item.label }}</a-tag>
            <div class="dist-bar-wrap">
              <div class="dist-bar" :style="{ width: item.pct + '%', background: item.colorVar }"></div>
            </div>
            <span class="dist-count">{{ item.count }}</span>
          </div>
          <div v-if="equipmentDist.length === 0" class="empty-hint">暂无设备数据</div>
        </div>
      </a-card>

      <!-- 样品状态分布 -->
      <a-card class="table-card" :bordered="false">
        <template #title>
          <div class="card-title-row">
            <span class="card-title-text">样品状态分布</span>
            <a-tag color="blue" class="count-tag">{{ samples.length }} 个</a-tag>
          </div>
        </template>
        <div class="dist-list">
          <div v-for="item in sampleDist" :key="item.status" class="dist-item">
            <a-tag :color="item.color" class="dist-tag">{{ item.label }}</a-tag>
            <div class="dist-bar-wrap">
              <div class="dist-bar" :style="{ width: item.pct + '%', background: item.colorVar }"></div>
            </div>
            <span class="dist-count">{{ item.count }}</span>
          </div>
          <div v-if="sampleDist.length === 0" class="empty-hint">暂无样品数据</div>
        </div>
      </a-card>
    </div>

    <!-- 近期实验结果 -->
    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">近期实验结果</span>
          <a-tag color="blue" class="count-tag">最多 8 条</a-tag>
        </div>
      </template>
      <a-table
        :data-source="recentResults"
        :loading="loading"
        :pagination="false"
        :columns="resultColumns"
        size="small"
        :row-key="(r) => r.result_id || r.id || `${r.sample_id}-${r.timestamp}`"
        :scroll="{ x: 800 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'qc_status'">
            <a-tag :color="qcStatusColor(record.qc_status)">{{ qcStatusLabel(record.qc_status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'timestamp'">
            <span class="tabular-nums">{{ formatDateTime(record.timestamp) }}</span>
          </template>
        </template>
      </a-table>
      <div v-if="!loading && recentResults.length === 0" class="empty-state">暂无可展示的实验结果</div>
    </a-card>

    <!-- 实验任务概览 -->
    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">实验任务概览</span>
          <a-tag color="blue" class="count-tag">{{ orders.length }} 条</a-tag>
        </div>
      </template>
      <a-table
        :data-source="orders"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t) => `共 ${t} 条`, showSizeChanger: false }"
        :columns="orderColumns"
        size="small"
        :row-key="(r) => r.order_id || r.id"
        :scroll="{ x: 800 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="orderStatusColor(record.status)">{{ orderStatusLabel(record.status) }}</a-tag>
          </template>
        </template>
      </a-table>
      <div v-if="!loading && orders.length === 0" class="empty-state">暂无实验任务</div>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listSamples } from '@/api/samples'
import { listEquipment } from '@/api/equipment'
import {
  listExperimentResults,
  listExperimentOrders,
  listQCPending,
} from '@/api/experiments'
import {
  qcStatusLabel,
  qcStatusColor,
  orderStatusLabel,
  orderStatusColor,
  sampleStatusColor,
  equipmentStatusColor,
} from '@/utils/enumLabels'

// 样品状态中文标签（含 proposed=待提案，扩展 enumLabels 缺失项）
const SAMPLE_STATUS_LABEL = {
  created: '已创建',
  in_storage: '在库',
  in_use: '使用中',
  consumed: '已消耗',
  discarded: '已废弃',
  proposed: '待提案',
}
const sampleStatusLabel = (v) => SAMPLE_STATUS_LABEL[v] || v || '-'

// 设备 / 样品状态顺序（用于有序展示分布）
const EQUIPMENT_STATUS_ORDER = ['idle', 'in_use', 'maintenance', 'calibration', 'retired']
const SAMPLE_STATUS_ORDER = ['created', 'in_storage', 'in_use', 'consumed', 'discarded', 'proposed']

const samples = ref([])
const equipment = ref([])
const results = ref([])
const qcPending = ref([])
const orders = ref([])
const loading = ref(false)

const resultColumns = [
  { title: '样品编号', dataIndex: 'sample_id', key: 'sample_id', width: 130, ellipsis: true },
  { title: '批次号', dataIndex: 'batch_id', key: 'batch_id', width: 110, ellipsis: true },
  { title: '实验类型', dataIndex: 'experiment_type', key: 'experiment_type', width: 120, ellipsis: true },
  { title: 'QC 状态', key: 'qc_status', width: 100 },
  { title: '关联任务', dataIndex: 'order_id', key: 'order_id', width: 130, ellipsis: true },
  { title: '时间', key: 'timestamp', width: 160, className: 'tabular-nums' },
]

const orderColumns = [
  { title: '任务编号', dataIndex: 'order_id', key: 'order_id', width: 150, ellipsis: true },
  { title: '任务名称', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '关联样品', dataIndex: 'sample_id', key: 'sample_id', width: 130, ellipsis: true },
  { title: '状态', key: 'status', width: 110 },
]

// 设备状态分布
const equipmentDist = computed(() => {
  const total = equipment.value.length || 1
  return EQUIPMENT_STATUS_ORDER.map((status) => {
    const count = equipment.value.filter((e) => e.status === status).length
    return {
      status,
      count,
      label: equipmentStatusLabel(status),
      color: equipmentStatusColor(status),
      colorVar: equipmentColorVar(status),
      pct: Math.round((count / total) * 100),
    }
  }).filter((item) => item.count > 0)
})

// 样品状态分布
const sampleDist = computed(() => {
  const total = samples.value.length || 1
  return SAMPLE_STATUS_ORDER.map((status) => {
    const count = samples.value.filter((s) => s.status === status).length
    return {
      status,
      count,
      label: sampleStatusLabel(status),
      color: sampleStatusColor(status),
      colorVar: sampleColorVar(status),
      pct: Math.round((count / total) * 100),
    }
  }).filter((item) => item.count > 0)
})

// 近期实验结果（按时间倒序，最多 8 条）
const recentResults = computed(() =>
  [...results.value]
    .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))
    .slice(0, 8),
)

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return dateFormatter.format(d)
}

// 状态条颜色（与 a-tag 语义色对应，映射为 CSS 色值）
function equipmentColorVar(status) {
  const map = { idle: 'var(--success)', in_use: 'var(--primary)', maintenance: 'var(--warning)', calibration: 'var(--info)', retired: 'var(--text-muted)' }
  return map[status] || 'var(--text-muted)'
}
function sampleColorVar(status) {
  const map = { created: 'var(--primary)', in_storage: 'var(--success)', in_use: 'var(--info)', consumed: 'var(--text-muted)', discarded: 'var(--danger)', proposed: 'var(--warning)' }
  return map[status] || 'var(--text-muted)'
}

async function fetchAll() {
  loading.value = true
  // 五类数据并行拉取，各自 try/catch 隔离，任一失败不影响其余渲染
  const [samplesRes, equipmentRes, resultsRes, ordersRes, qcRes] = await Promise.all([
    listSamples().then((d) => ({ ok: true, data: d })).catch(() => ({ ok: false, data: [] })),
    listEquipment().then((d) => ({ ok: true, data: d })).catch(() => ({ ok: false, data: [] })),
    listExperimentResults().then((d) => ({ ok: true, data: d })).catch(() => ({ ok: false, data: [] })),
    listExperimentOrders().then((d) => ({ ok: true, data: d })).catch(() => ({ ok: false, data: [] })),
    listQCPending().then((d) => ({ ok: true, data: d })).catch(() => ({ ok: false, data: [] })),
  ])
  samples.value = Array.isArray(samplesRes.data) ? samplesRes.data : []
  equipment.value = Array.isArray(equipmentRes.data) ? equipmentRes.data : []
  results.value = Array.isArray(resultsRes.data) ? resultsRes.data : []
  orders.value = Array.isArray(ordersRes.data) ? ordersRes.data : []
  qcPending.value = Array.isArray(qcRes.data) ? qcRes.data : []
  loading.value = false
}

onMounted(fetchAll)
</script>

<style scoped>
.experiment-dashboard {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.stat-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-item {
  flex: 1;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.dist-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.dist-row .table-card {
  flex: 1;
  min-width: 0;
}

.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title-text {
  font-size: 14px;
  font-weight: 600;
}

.count-tag {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

/* 状态分布列表 */
.dist-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}

.dist-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dist-tag {
  min-width: 64px;
  text-align: center;
  margin: 0;
}

.dist-bar-wrap {
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.dist-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.dist-count {
  min-width: 32px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.empty-hint {
  padding: 16px 0;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}

/* 小屏堆叠 */
@media (max-width: 900px) {
  .stat-row,
  .dist-row {
    flex-direction: column;
  }
}
</style>