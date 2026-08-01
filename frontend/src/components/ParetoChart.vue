<template>
  <div class="pareto-chart">
    <div class="chart-header">
      <span class="chart-title">帕累托前沿分析</span>
      <a-select
        v-if="objectiveNames.length > 2"
        v-model:value="selectedPair"
        size="small"
        style="width: 240px"
        @change="onPairChange"
      >
        <a-select-option v-for="pair in objectivePairs" :key="pair.value" :value="pair.value">
          {{ pair.label }}
        </a-select-option>
      </a-select>
      <a-button size="small" @click="exportData">
        <DownloadOutlined /> 导出
      </a-button>
    </div>
    <div v-if="!hasEnoughData" class="chart-empty">
      <EmptyState type="data" description="多目标数据不足，无法绘制帕累托前沿" />
    </div>
    <div v-else ref="chartRef" class="chart-body" aria-label="帕累托前沿散点图" role="img"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { DownloadOutlined } from '@ant-design/icons-vue'
import * as XLSX from 'xlsx'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  candidates: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null
let motionMediaQuery = null
let retryTimer = null

const prefersReducedMotion = ref(false)
function updateMotionPreference() {
  prefersReducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const objectiveNames = computed(() => {
  if (!props.candidates.length || !props.candidates[0].objectives) return []
  return props.candidates[0].objectives.map((o) => o.name)
})

const hasEnoughData = computed(() => objectiveNames.value.length >= 2)

const objectivePairs = computed(() => {
  const names = objectiveNames.value
  const pairs = []
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      pairs.push({
        label: `${names[i]} × ${names[j]}`,
        value: `${i}-${j}`,
      })
    }
  }
  return pairs
})

const selectedPair = computed({
  get() {
    if (!hasEnoughData.value) return ''
    return _selectedPair.value || '0-1'
  },
  set(val) {
    _selectedPair.value = val
  },
})
const _selectedPair = ref('0-1')

function computeParetoFrontier(candidates) {
  const n = candidates.length
  if (n === 0) return []
  const m = candidates[0].objectives.length
  if (m === 0) return candidates.map(() => false)

  const values = candidates.map((c) =>
    c.objectives.map((o) => (o.direction === 'maximize' ? o.value : -o.value))
  )

  const isPareto = new Array(n).fill(true)
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) continue
      let allGE = true
      let anyGT = false
      for (let k = 0; k < m; k++) {
        if (values[j][k] < values[i][k]) {
          allGE = false
          break
        }
        if (values[j][k] > values[i][k]) {
          anyGT = true
        }
      }
      if (allGE && anyGT) {
        isPareto[i] = false
        break
      }
    }
  }
  return isPareto
}

const paretoFlags = computed(() => computeParetoFrontier(props.candidates))

const chartData = computed(() => {
  if (!hasEnoughData.value) return { paretoData: [], dominatedData: [], obj0Name: '', obj1Name: '' }
  const [i0, i1] = selectedPair.value.split('-').map(Number)
  const first = props.candidates[0]
  const obj0Name = first.objectives[i0]?.name || '目标1'
  const obj1Name = first.objectives[i1]?.name || '目标2'

  const paretoData = []
  const dominatedData = []

  props.candidates.forEach((c, idx) => {
    if (!c.objectives || c.objectives.length < 2) return
    const x = c.objectives[i0]?.value
    const y = c.objectives[i1]?.value
    if (x == null || y == null) return
    const point = {
      value: [x, y],
      name: c.name || c.formula || c.smiles || `候选材料${idx + 1}`,
      candidateIndex: idx,
    }
    if (paretoFlags.value[idx]) {
      paretoData.push(point)
    } else {
      dominatedData.push(point)
    }
  })

  return { paretoData, dominatedData, obj0Name, obj1Name }
})

function buildOption() {
  const { paretoData, dominatedData, obj0Name, obj1Name } = chartData.value

  const series = []
  if (dominatedData.length) {
    series.push({
      name: '被支配解',
      type: 'scatter',
      data: dominatedData,
      symbolSize: 8,
      itemStyle: { color: '#b0b0b0', opacity: 0.6 },
      emphasis: { itemStyle: { color: '#909090' } },
    })
  }
  if (paretoData.length) {
    series.push({
      name: '帕累托最优',
      type: 'scatter',
      data: paretoData,
      symbolSize: 14,
      itemStyle: { color: '#e74c3c', borderColor: '#c0392b', borderWidth: 1 },
      emphasis: { itemStyle: { color: '#ff6b6b' } },
    })
  }

  return {
    title: { show: false },
    animation: !prefersReducedMotion.value,
    animationDuration: prefersReducedMotion.value ? 0 : 300,
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const d = params.data
        return `${d.name}<br/>${obj0Name}: ${d.value[0]}<br/>${obj1Name}: ${d.value[1]}`
      },
    },
    toolbox: {
      right: 10,
      feature: {
        saveAsImage: { title: '保存图片', pixelRatio: 2 },
      },
    },
    grid: { left: 60, right: 30, top: 20, bottom: 50 },
    xAxis: {
      name: obj0Name,
      nameLocation: 'center',
      nameGap: 35,
      nameTextStyle: { fontSize: 12, color: '#666' },
      type: 'value',
    },
    yAxis: {
      name: obj1Name,
      nameLocation: 'center',
      nameGap: 45,
      nameTextStyle: { fontSize: 12, color: '#666' },
      type: 'value',
    },
    series,
  }
}

function initChart() {
  if (chartInstance || !chartRef.value) return false
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    chartRef.value.style.height = chartRef.value.style.height || '350px'
    const rect2 = chartRef.value.getBoundingClientRect()
    if (rect2.width === 0 || rect2.height === 0) return false
  }
  chartInstance = echarts.init(chartRef.value)
  chartInstance.on('click', (params) => {
    if (params.data && params.data.candidateIndex !== undefined) {
      emit('select', props.candidates[params.data.candidateIndex])
    }
  })
  return true
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
    renderChart()
    if (chartInstance) clearRetry()
    tries++
  }, 100)
}

function handleResize() {
  if (!chartRef.value) return
  if (chartInstance) {
    chartInstance.resize()
  } else {
    renderChart()
  }
}

function renderChart() {
  if (!chartRef.value || !hasEnoughData.value) {
    clearRetry()
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    return
  }
  if (!chartInstance && !initChart()) {
    scheduleRetry()
    return
  }
  const option = buildOption()
  chartInstance.setOption(option, true)
}

function onPairChange() {
  nextTick(renderChart)
}

function exportData() {
  const headers = ['候选名称', 'SMILES/Formula']
  const first = props.candidates[0]
  if (first?.objectives) {
    first.objectives.forEach((o) => headers.push(o.name))
  }
  headers.push('综合评分', '是否帕累托最优')

  const rows = props.candidates.map((c, idx) => {
    const row = [
      c.name || c.formula || c.smiles || '',
      c.smiles || c.formula || '',
    ]
    if (c.objectives) {
      c.objectives.forEach((o) => row.push(o.value ?? ''))
    }
    row.push(
      c.multi_objective_score != null ? (c.multi_objective_score * 100).toFixed(1) + '%' : '',
      paretoFlags.value[idx] ? '是' : '否'
    )
    return row
  })

  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '帕累托前沿')
  XLSX.writeFile(wb, 'pareto_frontier.xlsx')
}

onMounted(() => {
  updateMotionPreference()
  motionMediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionMediaQuery.addEventListener('change', updateMotionPreference)
  nextTick(() => {
    renderChart()
    if (chartRef.value) {
      resizeObserver = new ResizeObserver(handleResize)
      resizeObserver.observe(chartRef.value)
    }
  })
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  clearRetry()
  motionMediaQuery?.removeEventListener('change', updateMotionPreference)
  resizeObserver?.disconnect()
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})

watch(
  () => [props.candidates, selectedPair.value],
  () => nextTick(renderChart),
  { deep: true }
)
</script>

<style scoped>
.pareto-chart {
  width: 100%;
}

.chart-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-body {
  width: 100%;
  height: 350px;
}

.chart-empty {
  width: 100%;
  height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>