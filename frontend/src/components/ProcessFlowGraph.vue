<template>
  <div class="process-flow">
    <div v-if="!steps.length" class="flow-empty">
      <span>暂无分步反应数据</span>
    </div>
    <div
      ref="chartRef"
      class="flow-chart"
      :class="{ 'is-hidden': !steps.length }"
      aria-label="工艺步骤流程图"
      role="img"
    ></div>

    <!-- 步骤详情浮层 -->
    <a-modal v-model:open="detailVisible" :title="detailTitle" width="480px" :footer="null">
      <div v-if="selectedStep" class="step-detail">
        <div class="detail-row">
          <span class="detail-label">步骤</span>
          <span class="detail-value">步骤 {{ selectedStep.index }}</span>
        </div>
        <div v-if="selectedStep.reaction_type" class="detail-row">
          <span class="detail-label">类型</span>
          <a-tag color="blue">{{ selectedStep.reaction_type }}</a-tag>
        </div>
        <div v-if="selectedStep.reaction_smiles" class="detail-row">
          <span class="detail-label">反应</span>
          <code class="detail-value mono">{{ selectedStep.reaction_smiles }}</code>
        </div>
        <div v-if="selectedStep.conditions" class="detail-row">
          <span class="detail-label">条件</span>
          <span class="detail-value">{{ selectedStep.conditions }}</span>
        </div>
        <div v-if="selectedStep.score != null" class="detail-row">
          <span class="detail-label">评分</span>
          <span class="detail-value num">{{ (selectedStep.score * 100).toFixed(0) }}%</span>
        </div>
        <div v-if="selectedStep.reactants?.length" class="detail-row">
          <span class="detail-label">反应物</span>
          <div class="detail-value">
            <div v-for="r in selectedStep.reactants" :key="r" class="reactant-item">
              <MoleculeView :smiles="r" :size="72" />
              <code class="reactant-smiles">{{ r.length > 22 ? r.slice(0, 18) + '…' : r }}</code>
            </div>
          </div>
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
  steps: { type: Array, default: () => [] },
  target: { type: String, default: '' },
})

const chartRef = ref(null)
let chart = null
let retryTimer = null
let resizeObserver = null

const detailVisible = ref(false)
const selectedStep = ref(null)
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

// 线性工艺步骤链：S1 → S2 → … → 目标产物
function buildOption() {
  const steps = props.steps.filter((s) => s && s.reaction_smiles)
  const nodes = steps.map((s, idx) => ({
    id: `step-${idx}`,
    name: `步骤 ${idx + 1}`,
    symbolSize: 44,
    category: idx % 2 === 0 ? 0 : 1,
    x: idx * 150,
    y: 0,
    label: {
      show: true,
      position: 'inside',
      color: '#fff',
      fontSize: 11,
      fontWeight: 600,
    },
    itemStyle: {
      color: idx % 2 === 0 ? '#2050d0' : '#3b82f6',
      borderColor: '#fff',
      borderWidth: 2,
      shadowBlur: 6,
      shadowColor: 'rgba(32,80,208,0.35)',
    },
    _raw: { ...s, index: idx + 1 },
  }))
  const links = steps.slice(1).map((_, idx) => ({
    source: `step-${idx}`,
    target: `step-${idx + 1}`,
    label: {
      show: true,
      formatter: props.steps[idx]?.reaction_type || '',
      fontSize: 10,
      color: '#6b7280',
      backgroundColor: 'rgba(255,255,255,0.85)',
      padding: [1, 4],
      borderRadius: 3,
    },
    lineStyle: { color: '#c5c8cf', width: 2, type: 'solid', curveness: 0 },
  }))
  // 目标产物节点（若有）
  if (props.target && steps.length) {
    nodes.push({
      id: 'target',
      name: '目标产物',
      symbolSize: 52,
      category: 2,
      x: steps.length * 150,
      y: 0,
      label: { show: true, position: 'inside', color: '#fff', fontSize: 11, fontWeight: 700 },
      itemStyle: {
        color: '#10b981',
        borderColor: '#fff',
        borderWidth: 2,
        shadowBlur: 8,
        shadowColor: 'rgba(16,185,129,0.4)',
      },
      _raw: null,
    })
    links.push({
      source: `step-${steps.length - 1}`,
      target: 'target',
      label: { show: false },
      lineStyle: { color: '#10b981', width: 2 },
    })
  }
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node' && p.data._raw) {
          const s = p.data._raw
          return `<b>步骤 ${s.index}</b><br/>${escapeHtml(s.reaction_type || '')}<br/><code style="word-break:break-all">${escapeHtml(s.reaction_smiles || '')}</code>`
        }
        return ''
      },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#dde0e6',
      textStyle: { color: '#1a1a2e', fontSize: 12 },
    },
    animationDuration: 500,
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true,
        draggable: false,
        categories: [
          { name: '奇步', itemStyle: { color: '#2050d0' } },
          { name: '偶步', itemStyle: { color: '#3b82f6' } },
          { name: '目标', itemStyle: { color: '#10b981' } },
        ],
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 10],
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
          itemStyle: { shadowBlur: 12 },
        },
        data: nodes,
        links,
      },
    ],
  }
}

function ensureChart() {
  if (chart) return chart
  if (!chartRef.value) return null
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    chartRef.value.style.height = '240px'
    const rect2 = chartRef.value.getBoundingClientRect()
    if (rect2.width === 0 || rect2.height === 0) return null
  }
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chart.on('click', handleClick)
  return chart
}

function render() {
  if (!props.steps.length) return
  const c = ensureChart()
  if (!c) {
    nextTick(() => {
      setTimeout(() => {
        if (!props.steps.length) return
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
    selectedStep.value = params.data._raw
    detailTitle.value = `步骤详情 — 步骤 ${params.data._raw.index}`
    detailVisible.value = true
  }
}

function resize() {
  if (chart) chart.resize()
  else render()
}

onMounted(() => {
  render()
  if (!chart && props.steps.length) scheduleRetry()
  window.addEventListener('resize', resize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  clearRetry()
  window.removeEventListener('resize', resize)
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(
  () => props.steps,
  () => nextTick(render),
  { deep: true },
)
</script>

<style scoped>
.process-flow {
  width: 100%;
}

.flow-chart {
  width: 100%;
  height: 240px;
}

.flow-chart.is-hidden {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
}

.flow-empty {
  width: 100%;
  height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

.step-detail {
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
  word-break: break-all;
}

.detail-value.mono {
  font-family: 'JetBrains Mono', monospace;
}

.reactant-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin-bottom: 8px;
}

.reactant-smiles {
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  word-break: break-all;
}

.num {
  font-variant-numeric: tabular-nums;
}
</style>
