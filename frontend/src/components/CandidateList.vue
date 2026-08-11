<template>
  <div class="candidate-list">
    <!-- 工具栏 -->
    <div class="list-toolbar">
      <a-input-search
        v-model:value="searchKeyword"
        placeholder="搜索化学式 / 名称 / SMILES"
        size="small"
        allow-clear
        class="search-input"
      />
      <a-select
        v-model:value="sortBy"
        size="small"
        class="sort-select"
        :options="sortOptions"
      />
    </div>

    <!-- 列表头部 -->
    <div class="list-header">
      <span class="header-count">共 {{ sortedCandidates.length }} 个候选材料</span>
      <a-tooltip title="按综合评分排序">
        <InfoCircleOutlined class="header-info" />
      </a-tooltip>
    </div>

    <!-- 列表内容 -->
    <div class="list-body">
      <SmartLoading
        v-if="loading && sortedCandidates.length === 0"
        :loading="true"
        skeleton-type="list"
        tip="正在加载候选材料..."
        show-cancel
      />
      <div v-else-if="sortedCandidates.length === 0" class="empty-state">
        <EmptyState
          :description="emptyText"
          type="data"
        />
      </div>
      <div v-else class="list-scroll">
        <div
          v-for="(item, idx) in sortedCandidates"
          :key="getRowKey(item, idx)"
          class="candidate-card"
          :class="{
            'is-selected': isSelected(item),
            'is-hovered': hoveredId === getRowKey(item, idx),
          }"
          @click="$emit('select', item)"
          @mouseenter="hoveredId = getRowKey(item, idx)"
          @mouseleave="hoveredId = ''"
        >
        <!-- 排名徽章 -->
        <div class="card-rank" :class="rankClass(idx)">
          {{ idx + 1 }}
        </div>

        <!-- 结构缩略图 -->
        <div class="card-thumb">
          <StructureView
            :smiles="getSmiles(item)"
            :formula="item.formula || ''"
            :space-group="item.space_group || ''"
            :structure-type="item.structure_type || ''"
            :kind="thumbKind"
            :size="64"
          />
        </div>

        <!-- 主信息 -->
        <div class="card-main">
          <div class="card-title-row">
            <span class="card-title">{{ getTitle(item) }}</span>
            <a-tag
              v-if="getSourceBadge(item).label !== '未知'"
              :color="getSourceBadge(item).color"
              class="card-source"
            >
              {{ getSourceBadge(item).label }}
            </a-tag>
          </div>
          <div class="card-subtitle">{{ getSubtitle(item) }}</div>
          <!-- 关键属性 -->
          <div class="card-metrics">
            <span v-if="item.tensile_strength != null" class="metric">
              <span class="metric-label">拉伸强度</span>
              <span class="metric-value">{{ Number(item.tensile_strength).toFixed(1) }} MPa</span>
            </span>
            <span v-if="item.flexural_modulus != null" class="metric">
              <span class="metric-label">弯曲模量</span>
              <span class="metric-value">{{ Number(item.flexural_modulus).toFixed(0) }} MPa</span>
            </span>
            <span v-if="item.impact_strength != null" class="metric">
              <span class="metric-label">冲击强度</span>
              <span class="metric-value">{{ Number(item.impact_strength).toFixed(1) }} kJ/m²</span>
            </span>
            <span v-if="item.heat_deflection_temp != null" class="metric">
              <span class="metric-label">热变形温度</span>
              <span class="metric-value">{{ Number(item.heat_deflection_temp).toFixed(0) }} °C</span>
            </span>
          </div>
          <!-- 需求7：三点状态指示（预测/合成/验证） -->
          <div v-if="statusDotsMap[getRowKey(item, idx)]?.length" class="card-status-dots">
            <a-tooltip
              v-for="dot in statusDotsMap[getRowKey(item, idx)]"
              :key="dot.key"
              :title="dot.label + '：' + dot.text"
            >
              <span
                class="status-dot"
                :class="'dot-' + dot.status"
              >{{ dot.icon }}</span>
            </a-tooltip>
          </div>
        </div>

        <!-- 综合评分 -->
        <div v-if="item.multi_objective_score != null" class="card-score">
          <a-progress
            type="circle"
            :percent="Math.round(item.multi_objective_score * 100)"
            :size="44"
            :stroke-color="scoreColor(item.multi_objective_score)"
          />
        </div>
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import EmptyState from '@/components/EmptyState.vue'
import SmartLoading from '@/components/SmartLoading.vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import StructureView from './StructureView.vue'
import { getSourceBadge } from '@/utils/candidateSource'
import { useUnitSymbols } from '@/utils/mdmDict'

// MDM 单位符号
const { load: loadUnitSymbols, get: getUnitSymbol } = useUnitSymbols()
const energyUnit = computed(() => getUnitSymbol('energy'))
const energyPerAtomUnit = computed(() => getUnitSymbol('energy_per_atom'))
const condUnit = computed(() => getUnitSymbol('conductivity'))
onMounted(() => { loadUnitSymbols() })

const props = defineProps({
  candidates: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selected: { type: Object, default: null },
  type: { type: String, default: 'crystal' }, // crystal | polymer
  emptyText: { type: String, default: '请先输入项目目标并执行发现' },
  // 需求7：三点状态映射表 { candidateKey: { prediction, synthesis, verification, ... } }
  statusMap: { type: Object, default: () => ({}) },
})

defineEmits(['select'])

const searchKeyword = ref('')
const sortBy = ref('score')
const hoveredId = ref('')

const sortOptions = [
  { value: 'score', label: '综合评分' },
  { value: 'tensile_strength', label: '拉伸强度' },
  { value: 'flexural_modulus', label: '弯曲模量' },
  { value: 'impact_strength', label: '冲击强度' },
  { value: 'heat_deflection_temp', label: '热变形温度' },
]

const thumbKind = computed(() => (props.type === 'polymer' ? 'molecule' : 'crystal'))

const sortedCandidates = computed(() => {
  let list = [...props.candidates]

  // 搜索过滤
  if (searchKeyword.value.trim()) {
    const kw = searchKeyword.value.trim().toLowerCase()
    list = list.filter((c) => {
      const fields = [c.formula, c.name, c.smiles, c.psmiles, c.material_id]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return fields.includes(kw)
    })
  }

  // 排序
  const getScore = (c) => c.multi_objective_score ?? 0
  const getNum = (c, k) => (c[k] != null ? Number(c[k]) : -Infinity)

  switch (sortBy.value) {
    case 'score':
      list.sort((a, b) => getScore(b) - getScore(a))
      break
    case 'tensile_strength':
      list.sort((a, b) => getNum(b, 'tensile_strength') - getNum(a, 'tensile_strength'))
      break
    case 'flexural_modulus':
      list.sort((a, b) => getNum(b, 'flexural_modulus') - getNum(a, 'flexural_modulus'))
      break
    case 'impact_strength':
      list.sort((a, b) => getNum(b, 'impact_strength') - getNum(a, 'impact_strength'))
      break
    case 'heat_deflection_temp':
      list.sort((a, b) => getNum(b, 'heat_deflection_temp') - getNum(a, 'heat_deflection_temp'))
      break
  }

  return list
})

function getRowKey(item, idx) {
  return (
    item.id ||
    item.material_id ||
    item.candidate_id ||
    item.formula ||
    item.smiles ||
    item.name ||
    `row-${idx}`
  )
}

function isSelected(item) {
  if (!props.selected) return false
  return (
    (props.selected.id && props.selected.id === item.id) ||
    (props.selected.material_id && props.selected.material_id === item.material_id) ||
    (props.selected.formula && props.selected.formula === item.formula &&
     props.selected.smiles === item.smiles)
  )
}

function getSmiles(item) {
  return item.smiles || item.monomer_smiles?.[0] || item.psmiles || ''
}

function getTitle(item) {
  return item.name || item.formula || item.smiles || item.material_id || '未命名'
}

function getSubtitle(item) {
  if (props.type === 'polymer') {
    return item.smiles || item.psmiles || '—'
  }
  return item.structure_type || item.space_group || '—'
}

function scoreColor(score) {
  if (score >= 0.8) return '#52c41a'
  if (score >= 0.6) return '#faad14'
  return '#ff4d4f'
}

function rankClass(idx) {
  if (idx === 0) return 'rank-gold'
  if (idx === 1) return 'rank-silver'
  if (idx === 2) return 'rank-bronze'
  return ''
}

// 需求7：三点状态指示——返回候选的预测/合成/可制造性三点状态
const STATUS_META = {
  pending: { icon: '○', text: '未执行' },
  done: { icon: '●', text: '已完成' },
  failed: { icon: '✕', text: '失败' },
  error: { icon: '!', text: '检查出错' },
  review: { icon: '?', text: '待复核' },
  skipped: { icon: '—', text: '跳过' },
}

function lookupStatus(item) {
  const map = props.statusMap || {}
  // 按后端 candidate_key 优先级匹配：candidate_id → id → material_id → formula → smiles → psmiles
  const keys = [
    item.candidate_id,
    item.id,
    item.material_id,
    item.formula,
    item.smiles,
    item.psmiles,
  ].filter(Boolean)
  for (const k of keys) {
    if (map[k]) return map[k]
  }
  return null
}

function buildStatusDots(item) {
  const status = lookupStatus(item)
  if (!status) {
    return []
  }
  const predText = status.prediction === 'done'
    ? `达标 ${status.targetsMet}/${status.totalTargets}`
    : (STATUS_META[status.prediction]?.text || '未执行')
  const synthText = status.synthesis === 'done' && status.synthesisScore != null
    ? `评分 ${(status.synthesisScore * 100).toFixed(0)}%`
    : (STATUS_META[status.synthesis]?.text || '未执行')
  const mfgText = status.manufacturability === 'done' && status.manufacturabilityScore != null
    ? `评分 ${(status.manufacturabilityScore * 100).toFixed(0)}%`
    : (STATUS_META[status.manufacturability]?.text || '未执行')
  return [
    { key: 'prediction', label: '属性预测', status: status.prediction || 'pending', ...STATUS_META[status.prediction || 'pending'], text: predText },
    { key: 'synthesis', label: '合成可行性', status: status.synthesis || 'pending', ...STATUS_META[status.synthesis || 'pending'], text: synthText },
    { key: 'manufacturability', label: '可制造性', status: status.manufacturability || 'pending', ...STATUS_META[status.manufacturability || 'pending'], text: mfgText },
  ]
}

// 缓存每个候选的三点状态，避免 v-if 和 v-for 中重复调用
const statusDotsMap = computed(() => {
  const map = {}
  sortedCandidates.value.forEach((item, idx) => {
    const key = getRowKey(item, idx)
    map[key] = buildStatusDots(item)
  })
  return map
})
</script>

<style scoped>
.candidate-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--light-bg-card, #fff);
  border-right: 1px solid var(--border, #e8e8e8);
}

.list-toolbar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border, #f0f0f0);
  background: var(--light-bg-hover, #fafafa);
}

.search-input {
  flex: 1;
}

.sort-select {
  width: 110px;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-secondary, #666);
  border-bottom: 1px solid var(--border, #f0f0f0);
}

.header-count {
  font-weight: 500;
}

.header-info {
  color: var(--text-muted, #999);
  cursor: help;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 12px;
}

/* 列表主体：flex: 1 占满剩余高度，骨架屏需穿透样式继承高度 */
.list-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.list-body :deep(.smart-loading) {
  flex: 1;
  overflow-y: auto;
}

.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.candidate-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 8px 32px;
  margin-bottom: 4px;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.candidate-card:hover {
  background: var(--light-bg-hover, #f5f7fa);
  border-color: var(--primary-bg, #d6e4ff);
}

.candidate-card.is-selected {
  background: var(--primary-bg, #e6f4ff);
  border-color: var(--primary);
}

.card-rank {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, #999);
  background: var(--light-bg-hover, #f0f0f0);
}

.rank-gold {
  background: linear-gradient(135deg, #ffd700, #ffa500) !important;
  color: #fff !important;
}

.rank-silver {
  background: linear-gradient(135deg, #c0c0c0, #a8a8a8) !important;
  color: #fff !important;
}

.rank-bronze {
  background: linear-gradient(135deg, #cd7f32, #a0522d) !important;
  color: #fff !important;
}

.card-thumb {
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--light-bg-hover, #fafafa);
  border-radius: 4px;
  overflow: hidden;
}

.card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.card-source {
  margin-left: auto;
  font-size: 10px;
  line-height: 14px;
  padding: 0 4px;
}

.card-subtitle {
  font-size: 11px;
  color: var(--text-secondary, #666);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 2px;
}

.metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  line-height: 14px;
}

.metric-label {
  color: var(--text-muted, #999);
}

.metric-value {
  color: var(--text-primary, #333);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

/* 需求7：三点状态指示 */
.card-status-dots {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}

.status-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 10px;
  line-height: 1;
  cursor: help;
  transition: all 0.15s;
}

.dot-pending {
  color: var(--text-muted, #bfbfbf);
  background: var(--light-bg-hover, #f0f0f0);
}

.dot-done {
  color: #fff;
  background: #52c41a;
}

.dot-failed {
  color: #fff;
  background: #ff4d4f;
}

.dot-skipped {
  color: var(--text-muted, #bfbfbf);
  background: transparent;
  border: 1px dashed var(--border, #d9d9d9);
}

.dot-error {
  color: #fff;
  background: #faad14;
}

.dot-review {
  color: #fff;
  background: #faad14;
}

.card-score {
  flex-shrink: 0;
}

.list-scroll::-webkit-scrollbar {
  width: 6px;
}

.list-scroll::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.list-scroll::-webkit-scrollbar-track {
  background: transparent;
}
</style>
