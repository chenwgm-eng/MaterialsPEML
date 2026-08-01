<template>
  <div class="reaction-network">
    <div v-if="!nodes.length" class="network-empty">
      <span>暂无反应网络数据</span>
    </div>
    <div
      ref="chartRef"
      class="network-chart"
      :class="{ 'is-hidden': !nodes.length }"
      aria-label="反应网络可视化"
      role="img"
    ></div>

    <!-- 节点详情浮层 -->
    <a-modal
      v-model:open="detailVisible"
      :title="detailTitle"
      width="480px"
      :footer="null"
    >
      <div v-if="selectedNode" class="node-detail">
        <div class="detail-row">
          <span class="detail-label">SMILES</span>
          <code class="detail-value">{{ selectedNode.id }}</code>
        </div>
        <div class="detail-row">
          <span class="detail-label">类型</span>
          <a-tag :color="typeColor[selectedNode.type] || 'default'">
            {{ typeLabel[selectedNode.type] || selectedNode.type }}
          </a-tag>
        </div>
        <div class="detail-row">
          <span class="detail-label">机理</span>
          <a-tag :color="mechanismColor[selectedNode.mechanism] || 'default'">
            {{ mechanismLabel[selectedNode.mechanism] || selectedNode.mechanism }}
          </a-tag>
        </div>
        <div v-if="selectedNode.id" class="detail-row">
          <span class="detail-label">结构</span>
          <MoleculeView :smiles="selectedNode.id" :size="180" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import MoleculeView from '@/components/MoleculeView.vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  target: { type: String, default: '' },
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

const typeColor = {
  starting_material: '#10b981',
  intermediate: '#f59e0b',
  product: '#2050d0',
  byproduct: '#ef4444',
}

const typeLabel = {
  starting_material: '起始原料',
  intermediate: '中间体',
  product: '目标产物',
  byproduct: '副产物',
}

const mechanismColor = {
  substitution: '#3b82f6',
  elimination: '#8b5cf6',
  addition: '#06b6d4',
  oxidation: '#ef4444',
  reduction: '#10b981',
  other: '#6b7280',
}

const mechanismLabel = {
  substitution: '取代',
  elimination: '消除',
  addition: '加成',
  oxidation: '氧化',
  reduction: '还原',
  other: '其他',
}

const detailVisible = ref(false)
const selectedNode = ref(null)
const detailTitle = ref('')

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
      const isTarget = n.id === props.target
      // 去重：相同 id 只保留第一个
      if (nodeIds.has(n.id)) return null
      nodeIds.add(n.id)
      return {
        id: n.id,
        name: n.label || String(n.id),
        symbolSize: isTarget ? 60 : n.type === 'byproduct' ? 38 : 46,
        category: n.type,
        itemStyle: {
          color,
          borderColor: isTarget ? '#2050d0' : color,
          borderWidth: isTarget ? 4 : 2,
          shadowBlur: isTarget ? 12 : 0,
          shadowColor: color,
        },
        label: {
          show: true,
          position: 'bottom',
          color: '#1a1a2e',
          fontSize: 11,
          fontWeight: isTarget ? 700 : 500,
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
    .map((e) => {
      const isByproduct = e.is_byproduct
      return {
        source: e.source,
        target: e.target,
        label: {
          show: true,
          formatter: mechanismLabel[e.mechanism] || e.label,
          fontSize: 10,
          color: isByproduct ? '#ef4444' : '#6b7280',
          backgroundColor: 'rgba(255,255,255,0.8)',
          padding: [2, 4],
          borderRadius: 3,
        },
        lineStyle: {
          color: isByproduct ? '#ef4444' : mechanismColor[e.mechanism] || '#c5c8cf',
          width: isByproduct ? 2 : 1.5,
          type: isByproduct ? 'dashed' : 'solid',
          curveness: 0.15,
          opacity: 0.85,
        },
      }
    })
}

function buildOption() {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const d = p.data._raw
          return `<b>${escapeHtml(d.label)}</b><br/>类型：${escapeHtml(typeLabel[d.type] || d.type)}<br/>机理：${escapeHtml(mechanismLabel[d.mechanism] || d.mechanism)}`
        }
        if (p.dataType === 'edge') {
          return `反应：${escapeHtml(p.data.label?.formatter || '')}`
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
      data: ['起始原料', '中间体', '目标产物', '副产物'],
    },
    animation: !prefersReducedMotion.value,
    animationDuration: prefersReducedMotion.value ? 0 : 800,
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        categories: [
          { name: '起始原料', itemStyle: { color: typeColor.starting_material } },
          { name: '中间体', itemStyle: { color: typeColor.intermediate } },
          { name: '目标产物', itemStyle: { color: typeColor.product } },
          { name: '副产物', itemStyle: { color: typeColor.byproduct } },
        ],
        force: {
          repulsion: 240,
          edgeLength: [80, 160],
          gravity: 0.08,
          layoutAnimation: true,
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
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
    chartRef.value.style.height = '350px'
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
        if (!c2) return
        c2.setOption(buildOption(), { notMerge: true })
        c2.resize()
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
    detailTitle.value = `节点详情 — ${params.data._raw.label}`
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
  () => nextTick(render),
  { deep: true },
)
</script>

<style scoped>
.reaction-network {
  width: 100%;
}

.network-chart {
  width: 100%;
  height: 350px;
}

.network-chart.is-hidden {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
}

.network-empty {
  width: 100%;
  height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8a92a6;
  font-size: 14px;
}

.node-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.detail-label {
  font-size: 13px;
  color: var(--text-secondary, #6b7280);
  width: 56px;
  flex-shrink: 0;
  padding-top: 2px;
}

.detail-value {
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
  font-family: 'JetBrains Mono', monospace;
  word-break: break-all;
}
</style>
