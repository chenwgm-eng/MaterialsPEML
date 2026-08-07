<template>
  <a-card v-if="round && round.recommended?.length" class="round-card" :bordered="false">
    <template #title>
      <div class="round-title">
        <span>BO 推荐结果</span>
        <a-tag :color="statusColor">{{ statusLabel }}</a-tag>
        <a-tag v-if="modelTag" color="blue">模型 {{ modelTag }}</a-tag>
        <a-tag v-if="acqName" color="geekblue">策略 {{ acqName }}</a-tag>
      </div>
    </template>

    <!-- 推荐理由：可审计的决策依据 -->
    <a-alert v-if="round.reasoning" :message="round.reasoning" type="info" show-icon style="margin-bottom: 12px" />

    <!-- 训练池摘要 -->
    <div v-if="round.pool?.stats" class="round-pool-summary">
      训练依据：材料体系「{{ round.pool.family }}」+ 属性「{{ round.pool.property_name }}」，共 {{ round.pool.stats.total }} 条有效数据
      <span v-if="round.pool.stats.cross_project">（含 {{ round.pool.stats.cross_project }} 条跨项目复用）</span>
    </div>

    <!-- 推荐候选表 -->
    <a-table
      :columns="columns"
      :data-source="round.recommended"
      :pagination="false"
      size="small"
      :row-selection="{ selectedRowKeys, onChange: onSelect }"
      :expanded-row-keys="expandedKeys"
      @expand="onExpand"
      :row-key="(r) => rowKey(r)"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'id'">
          {{ record.name || record.formula || record.smiles || '-' }}
        </template>
        <template v-else-if="column.key === 'mean'">
          <div v-if="isMulti" class="pred-cell">
            <span class="pred-mean">{{ multiSummary(record) }}</span>
          </div>
          <template v-else>
            <div class="pred-cell">
              <span class="pred-mean">{{ fmt(record.expected_performance ?? record.acquisition_score) }}</span>
              <span class="pred-ci">± {{ fmt(record.uncertainty) }}</span>
            </div>
            <div class="ci-bar">
              <div class="ci-bar-track">
                <div class="ci-bar-fill" :style="ciStyle(record)"></div>
              </div>
            </div>
          </template>
        </template>
        <template v-else-if="column.key === 'ei'">
          <span :class="{ 'ei-zero': (record.expected_improvement ?? 0) <= 0 }">{{ fmt(record.expected_improvement) }}</span>
        </template>
        <template v-else-if="column.key === 'strategy'">
          <a-tag :color="record.strategy === 'exploitation' ? 'green' : 'orange'">
            {{ record.strategy === 'exploitation' ? '利用型' : '探索型' }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'reason'">
          <a-button type="link" size="small" @click="toggleReason(record)">查看依据</a-button>
        </template>
      </template>
      <template #expandedRowRender="{ record }">
        <div class="reason-panel">
          <div class="reason-title">推荐依据（可审计）</div>
          <p v-if="record.recommendation_reason" class="reason-text">{{ record.recommendation_reason }}</p>
          <a-descriptions v-if="record.predicted_objectives" :column="2" size="small" bordered class="reason-objs">
            <a-descriptions-item v-for="(v, k) in record.predicted_objectives" :key="k" :label="k">
              {{ fmt(v) }}
            </a-descriptions-item>
          </a-descriptions>
        </div>
      </template>
    </a-table>

    <!-- 决策确认区 -->
    <div class="confirm-actions">
      <a-button type="primary" :disabled="!selectedRowKeys.length" :loading="confirming" @click="onConfirm">
        确认下发（{{ selectedRowKeys.length }} 个采纳候选）
      </a-button>
      <a-button @click="onDiscard">仅做推荐，不下发</a-button>
      <span class="confirm-hint">采纳后自动生成实验任务，进入执行闭环</span>
    </div>
  </a-card>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { confirmECMLRound } from '@/api/ecml'
import { formatSci } from '@/utils/format'

const props = defineProps({
  round: { type: Object, default: null },
  currentScenarioId: { type: String, default: '' },
})
const emit = defineEmits(['confirmed'])

const selectedRowKeys = ref([])
const confirming = ref(false)

const statusLabel = computed(() => {
  const map = {
    pending_review: '待课题负责人复核',
    confirmed: '已确认下发',
    in_execution: '执行中',
    completed: '本轮完成',
  }
  return map[props.round?.status] || '待复核'
})

const statusColor = computed(() => {
  const map = { pending_review: 'orange', confirmed: 'green', in_execution: 'blue', completed: 'green' }
  return map[props.round?.status] || 'default'
})

const modelLabel = (k) => ({ gp: '高斯过程', gbt: '梯度提升树', mlp: '神经网络' }[k] || k || '-')
// EHVI 多目标：model 为 { models: [{property, family, n_samples}] }，not 单 family
const isMulti = computed(() => props.round?.acquisition?.name === 'ehvi')
const modelTag = computed(() => {
  const m = props.round?.model
  if (isMulti.value && Array.isArray(m?.models)) {
    return m.models.map((x) => modelLabel(x.family)).join(' + ')
  }
  return m?.family ? modelLabel(m.family) : ''
})
const multiSummary = (record) => {
  const po = record.predicted_objectives
  if (!po) return '-'
  return Object.entries(po).map(([k, v]) => `${k}=${fmt(v)}`).join('  ')
}
const acqName = computed(() => {
  const map = { ei: 'EI·期望改进', ucb: 'UCB·置信上界', pi: 'PI·改进概率', ehvi: 'EHVI·超体积改进' }
  return map[props.round?.acquisition?.name] || props.round?.acquisition?.name || ''
})

const columns = [
  { title: '候选材料', key: 'id', ellipsis: true },
  { title: '预测均值 ± 置信区间', key: 'mean', width: 180 },
  { title: '预期改进量', key: 'ei', width: 110, align: 'right' },
  { title: '探索/利用', key: 'strategy', width: 100, align: 'center' },
  { title: '推荐依据', key: 'reason', width: 100, align: 'center' },
]

const rowKey = (r) => r.name || r.formula || r.smiles || r.candidate_id || JSON.stringify(r)

function fmt(v) {
  if (v == null || v === '' || isNaN(Number(v))) return '-'
  return formatSci(v, 3)
}

function ciStyle(record) {
  const mean = Math.abs(Number(record.expected_performance ?? 0)) || 0
  const std = Math.abs(Number(record.uncertainty ?? 0))
  const span = mean + std
  if (!span) return { width: '4%' }
  const pct = Math.max(3, Math.min(100, (std / span) * 100))
  return { width: `${pct}%` }
}

function onSelect(keys) {
  selectedRowKeys.value = keys
}

function onExpand(expanded, record) {
  const k = rowKey(record)
  expandedKeys.value = expanded
    ? [...expandedKeys.value, k]
    : expandedKeys.value.filter((x) => x !== k)
}

function toggleReason(record) {
  // 展开"查看依据"行
  expandedKeys.value = expandedKeys.value.includes(rowKey(record))
    ? expandedKeys.value.filter((k) => k !== rowKey(record))
    : [...expandedKeys.value, rowKey(record)]
}

const expandedKeys = ref([])

async function onConfirm() {
  const items = props.round?.recommended || []
  const adopted = items
    .filter((r) => selectedRowKeys.value.includes(rowKey(r)))
    .map((r) => ({ formula: r.formula || r.smiles || r.name || '', candidate_id: r.candidate_id || '', name: r.name || '' }))
  confirming.value = true
  try {
    await confirmECMLRound(props.round.round_id, adopted)
    emit('confirmed', { round_id: props.round.round_id, adopted })
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '确认下发失败')
  } finally {
    confirming.value = false
  }
}

function onDiscard() {
  message.info('已保留推荐结果，如需下发可随时重新确认')
}

// round 变化时重置选中状态
watch(
  () => props.round?.round_id,
  () => {
    selectedRowKeys.value = []
    expandedKeys.value = []
  }
)
</script>

<style scoped>
.round-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.round-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.round-title :deep(.ant-tag) {
  margin: 0;
}

.round-pool-summary {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--light-bg-hover, #fafafa);
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 12px;
}

.pred-cell {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.pred-mean {
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.pred-ci {
  font-size: 11px;
  color: var(--text-muted);
}

.ci-bar {
  margin-top: 4px;
}

.ci-bar-track {
  height: 4px;
  background: var(--border, #e8e8e8);
  border-radius: 2px;
  overflow: hidden;
}

.ci-bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
}

.ei-zero {
  color: var(--text-muted);
}

.reason-panel {
  padding: 8px;
}

.reason-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.reason-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.reason-objs {
  margin-top: 8px;
}

.confirm-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0 4px;
}

.confirm-hint {
  font-size: 12px;
  color: var(--text-muted);
}
</style>