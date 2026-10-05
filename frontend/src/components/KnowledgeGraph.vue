<template>
  <div class="knowledge-graph">
    <div v-if="!nodes.length" class="kg-empty">
      <InboxOutlined aria-hidden="true" />
      <span>暂无知识图谱数据</span>
    </div>
    <div
      v-else
      ref="chartRef"
      class="kg-chart"
      aria-label="知识图谱可视化"
      role="img"
    ></div>

    <!-- 节点详情抽屉 -->
    <a-modal
      v-model:open="detailVisible"
      :title="selectedNode?.label || '节点详情'"
      width="520px"
      :footer="null"
      :mask-closable="true"
    >
      <div v-if="selectedNode" class="node-detail">
        <!-- 顶部类型与核心指标 -->
        <div class="detail-summary">
          <span class="detail-type" :style="{ color: typeColor[selectedNode.type] || '#6b7280' }">
            {{ typeLabel[selectedNode.type] || selectedNode.type }}
          </span>
          <div class="detail-metrics">
            <div class="metric">
              <span class="metric-value">{{ selectedNode.properties?.papers || 0 }}</span>
              <span class="metric-label">关联文献</span>
            </div>
            <div class="metric">
              <span class="metric-value">{{ connectedEdges.length }}</span>
              <span class="metric-label">关联关系</span>
            </div>
            <div class="metric">
              <span class="metric-value">{{ confidenceLabel }}</span>
              <span class="metric-label">置信度</span>
            </div>
          </div>
        </div>

        <!-- 节点定义/描述 -->
        <div v-if="selectedNode.properties?.description || selectedNode.properties?.definition" class="detail-block">
          <div class="block-title">定义</div>
          <div class="block-text">
            {{ selectedNode.properties?.description || selectedNode.properties?.definition }}
          </div>
        </div>

        <!-- 关键属性 -->
        <div v-if="extraProperties.length" class="detail-block">
          <div class="block-title">属性</div>
          <div class="property-grid">
            <div v-for="prop in extraProperties" :key="prop.key" class="property-item">
              <span class="property-key">{{ prop.label }}</span>
              <span class="property-value" :title="prop.value">{{ prop.value }}</span>
            </div>
          </div>
        </div>

        <!-- 关联关系：以当前节点为起点 -->
        <div v-if="outgoingEdges.length" class="detail-block">
          <div class="block-title">出向关联</div>
          <div class="relation-list">
            <div
              v-for="(e, idx) in outgoingEdges"
              :key="`out-${e.target}-${idx}`"
              class="relation-row"
            >
              <span class="relation-dot" :style="{ background: targetColor(e.target) }"></span>
              <span class="relation-peer" :title="e.target">{{ peerLabel(e.target) }}</span>
              <span class="relation-label">{{ e.label }}</span>
              <span v-if="e.weight" class="relation-weight">{{ e.weight }}</span>
            </div>
          </div>
        </div>

        <!-- 关联关系：以当前节点为终点 -->
        <div v-if="incomingEdges.length" class="detail-block">
          <div class="block-title">入向关联</div>
          <div class="relation-list">
            <div
              v-for="(e, idx) in incomingEdges"
              :key="`in-${e.source}-${idx}`"
              class="relation-row"
            >
              <span class="relation-dot" :style="{ background: targetColor(e.source) }"></span>
              <span class="relation-peer" :title="e.source">{{ peerLabel(e.source) }}</span>
              <span class="relation-label">{{ e.label }}</span>
              <span v-if="e.weight" class="relation-weight">{{ e.weight }}</span>
            </div>
          </div>
        </div>

        <!-- 关键文献 -->
        <div v-if="paperList.length" class="detail-block">
          <div class="block-title">关键文献</div>
          <div class="paper-list">
            <div v-for="(paper, idx) in paperList" :key="idx" class="paper-row" :title="paper">
              <span class="paper-index">{{ idx + 1 }}</span>
              <span class="paper-title-sm">{{ paper }}</span>
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { InboxOutlined } from '@ant-design/icons-vue'
import * as echarts from 'echarts'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

const chartRef = ref(null)
let chart = null
let retryTimer = null
let resizeObserver = null
let motionMediaQuery = null

const prefersReducedMotion = ref(false)
function updateMotionPreference() {
  prefersReducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

// 节点类型 → 颜色
const typeColor = {
  material: '#2050d0',
  property: '#10b981',
  method: '#1d4ed8',
  application: '#8b5cf6',
  institution: '#ef4444',
}

const typeLabel = {
  material: '材料',
  property: '性能指标',
  method: '合成方法',
  application: '应用场景',
  institution: '研究机构',
}

const categoryIndex = {
  material: 0,
  property: 1,
  method: 2,
  application: 3,
  institution: 4,
}

const detailVisible = ref(false)
const selectedNode = ref(null)

const connectedEdges = computed(() => {
  if (!selectedNode.value) return []
  const id = selectedNode.value.id
  return props.edges.filter((e) => e.source === id || e.target === id).slice(0, 20)
})

const outgoingEdges = computed(() => {
  if (!selectedNode.value) return []
  return props.edges.filter((e) => e.source === selectedNode.value.id).slice(0, 10)
})

const incomingEdges = computed(() => {
  if (!selectedNode.value) return []
  return props.edges.filter((e) => e.target === selectedNode.value.id).slice(0, 10)
})

const confidenceLabel = computed(() => {
  const v = selectedNode.value?.properties?.confidence
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return v
  return `${Math.round(n * 100)}%`
})

const extraProperties = computed(() => {
  if (!selectedNode.value?.properties) return []
  const skip = new Set(['papers', 'confidence', 'description', 'definition', 'paper_titles', 'paper_list'])
  const result = []
  for (const [key, value] of Object.entries(selectedNode.value.properties)) {
    if (skip.has(key) || value == null || value === '') continue
    result.push({ key, label: propertyLabel(key), value: formatPropertyValue(value) })
  }
  return result.slice(0, 6)
})

const paperList = computed(() => {
  const p = selectedNode.value?.properties
  if (!p) return []
  const raw = p.paper_titles || p.paper_list || p.papers_list || []
  if (typeof raw === 'string') {
    return raw.split(/[,;，；]/).map((s) => s.trim()).filter(Boolean).slice(0, 5)
  }
  if (Array.isArray(raw)) return raw.slice(0, 5)
  return []
})

function propertyLabel(key) {
  const map = {
    formula: '化学式',
    cas: 'CAS 号',
    molecular_weight: '分子量',
    melting_point: '熔点',
    source: '数据来源',
    doi: 'DOI',
    year: '年份',
    country: '国家/地区',
    application_area: '应用领域',
    test_method: '测试方法',
    unit: '单位',
  }
  return map[key] || key
}

function formatPropertyValue(value) {
  if (Array.isArray(value)) return value.join('，')
  return String(value)
}

function peerLabel(id) {
  const node = props.nodes.find((n) => n.id === id)
  return node?.label || id
}

function targetColor(id) {
  const node = props.nodes.find((n) => n.id === id)
  return typeColor[node?.type] || '#6b7280'
}

function escapeHtml(str) {
  if (str == null) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function buildNodes() {
  const nodeIds = new Set()
  return props.nodes
    .filter((n) => n.id != null && n.id !== '')
    .map((n) => {
      const color = typeColor[n.type] || '#6b7280'
      const papers = n.properties?.papers || 1
      const size = Math.min(70, 30 + papers * 6)
      if (nodeIds.has(n.id)) return null
      nodeIds.add(n.id)
      return {
        id: n.id,
        name: n.label || String(n.id),
        symbolSize: size,
        category: categoryIndex[n.type] ?? -1,
        itemStyle: {
          color,
          borderColor: color,
          borderWidth: 2,
          shadowBlur: 6,
          shadowColor: color,
        },
        label: {
          show: true,
          position: 'bottom',
          color: '#1a1a2e',
          fontSize: 11,
          fontWeight: 500,
        },
        _raw: n,
      }
    })
    .filter(Boolean)
}

function buildLinks() {
  const nodeIds = new Set(props.nodes.map((n) => n.id))
  return props.edges
    .filter((e) => e.source != null && e.target != null && e.source !== '' && e.target !== '')
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e, idx) => ({
      source: e.source,
      target: e.target,
      value: e.weight,
      _index: idx,
      label: {
        show: true,
        formatter: e.label,
        fontSize: 10,
        color: '#6b7280',
        backgroundColor: 'rgba(255,255,255,0.85)',
        padding: [2, 4],
        borderRadius: 3,
      },
      lineStyle: {
        color: '#c5c8cf',
        width: Math.min(4, 1 + (e.weight || 0) * 0.5),
        curveness: 0.15,
        opacity: 0.8,
      },
    }))
}

function buildCategories() {
  return [
    { name: '材料', itemStyle: { color: typeColor.material } },
    { name: '性能指标', itemStyle: { color: typeColor.property } },
    { name: '合成方法', itemStyle: { color: typeColor.method } },
    { name: '应用场景', itemStyle: { color: typeColor.application } },
    { name: '研究机构', itemStyle: { color: typeColor.institution } },
  ]
}

function buildOption() {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const d = p.data._raw
          return `<b>${escapeHtml(d.label)}</b><br/>类型：${escapeHtml(typeLabel[d.type] || d.type)}<br/>关联文献：${d.properties?.papers || 0} 篇`
        }
        if (p.dataType === 'edge') {
          return `${escapeHtml(p.data.source)} <b>${escapeHtml(p.data.label?.formatter || '')}</b> ${escapeHtml(p.data.target)}`
        }
        return ''
      },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#dde0e6',
      textStyle: { color: '#1a1a2e', fontSize: 12 },
    },
    legend: {
      show: true,
      bottom: 4,
      textStyle: { color: '#4a5060', fontSize: 11 },
      data: ['材料', '性能指标', '合成方法', '应用场景', '研究机构'],
    },
    animation: !prefersReducedMotion.value,
    animationDuration: prefersReducedMotion.value ? 0 : 800,
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        categories: buildCategories(),
        force: {
          repulsion: 280,
          edgeLength: [90, 180],
          gravity: 0.08,
          layoutAnimation: true,
        },
        label: { show: true },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3, color: '#2050d0' },
          itemStyle: { shadowBlur: 16 },
        },
        data: buildNodes(),
        links: buildLinks(),
      },
    ],
  }
}

function ensureChart() {
  if (chart) return chart
  if (!chartRef.value) return null
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    chartRef.value.style.height = '500px'
    const rect2 = chartRef.value.getBoundingClientRect()
    if (rect2.width === 0 || rect2.height === 0) return null
  }
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chart.on('click', handleClick)
  return chart
}

function render() {
  if (!props.nodes.length) return
  const c = ensureChart()
  if (!c) {
    nextTick(() => {
      setTimeout(() => {
        if (!props.nodes.length) return
        const c2 = ensureChart()
        if (!c2) {
          scheduleRetry()
          return
        }
        c2.setOption(buildOption(), { notMerge: true })
        c2.resize()
        clearRetry()
      }, 100)
    })
    return
  }
  c.setOption(buildOption(), { notMerge: true })
  c.resize()
}

function clearRetry() {
  if (retryTimer) {
    clearInterval(retryTimer)
    retryTimer = null
  }
}

function scheduleRetry() {
  if (retryTimer) return
  let tries = 0
  retryTimer = setInterval(() => {
    if (tries >= 20) {
      clearRetry()
      return
    }
    render()
    if (chart) clearRetry()
    tries++
  }, 100)
}

function handleClick(params) {
  if (params.dataType === 'node' && params.data?._raw) {
    selectedNode.value = params.data._raw
    detailVisible.value = true
    emit('select', params.data._raw)
  }
}

function resize() {
  if (chart) {
    chart.resize()
  } else {
    render()
  }
}

onMounted(() => {
  updateMotionPreference()
  motionMediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionMediaQuery.addEventListener('change', updateMotionPreference)
  render()
  if (!chart && props.nodes.length) scheduleRetry()
  window.addEventListener('resize', resize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  clearRetry()
  motionMediaQuery?.removeEventListener('change', updateMotionPreference)
  window.removeEventListener('resize', resize)
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(
  () => [props.nodes, props.edges],
  () => nextTick(() => { setTimeout(render, 100) }),
  { deep: true },
)
</script>

<style scoped>
.knowledge-graph {
  width: 100%;
  height: 100%;
}

.kg-chart {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.kg-empty {
  width: 100%;
  height: 100%;
  min-height: 400px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted);
  font-size: 14px;
}

.kg-empty :deep(.anticon) {
  font-size: 36px;
  opacity: 0.5;
}

/* ── 节点详情弹窗 ── */
.node-detail {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.node-detail::-webkit-scrollbar {
  width: 4px;
}

.node-detail::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 2px;
}

.detail-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-type {
  font-size: 13px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  background: #f5f6f8;
  flex-shrink: 0;
}

.detail-metrics {
  display: flex;
  gap: 18px;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
  line-height: 1.1;
}

.metric-label {
  font-size: 11px;
  color: var(--text-muted);
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.block-title {
  font-size: 12px;
  font-weight: 600;
  color: #4a5060;
}

.block-text {
  font-size: 13px;
  color: #1a1a2e;
  line-height: 1.6;
}

.property-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;
}

.property-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.property-key {
  font-size: 11px;
  color: var(--text-muted);
}

.property-value {
  font-size: 13px;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.relation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.relation-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  background: #f7f8fa;
  font-size: 13px;
}

.relation-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.relation-peer {
  color: var(--primary);
  font-weight: 500;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.relation-label {
  color: #4a5060;
  padding: 0 2px;
}

.relation-weight {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  background: #fff;
  padding: 0 6px;
  border-radius: 8px;
  line-height: 1.4;
}

.paper-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.paper-row {
  display: flex;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #f7f8fa;
  font-size: 12px;
  color: #4a5060;
  line-height: 1.5;
}

.paper-index {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #e6e9f0;
  color: #5a6070;
  font-size: 10px;
  font-weight: 600;
}

.paper-title-sm {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

:deep(.ant-modal-header) {
  padding: 14px 20px;
}

:deep(.ant-modal-title) {
  font-weight: 600;
  font-size: 16px;
}

:deep(.ant-modal-body) {
  padding: 16px 20px 18px;
}
</style>
