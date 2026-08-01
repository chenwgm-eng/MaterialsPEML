<template>
  <div class="radar-chart">
    <div class="chart-title">多维目标雷达图</div>
    <div v-if="!hasEnoughData" class="chart-empty">
      <EmptyState type="data" description="多目标数据不足，无法绘制雷达图" />
    </div>
    <div v-else ref="chartRef" class="chart-body" aria-label="多维目标雷达图" role="img"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  candidates: { type: Array, default: () => [] },
})

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null
let motionMediaQuery = null
let retryTimer = null

const prefersReducedMotion = ref(false)
function updateMotionPreference() {
  prefersReducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
  '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#48b8d0',
]

const indicatorNames = computed(() => {
  if (!props.candidates.length || !props.candidates[0].objectives) return []
  return props.candidates[0].objectives.map((o) => o.name)
})

const hasEnoughData = computed(() => indicatorNames.value.length > 0)

const normalizedData = computed(() => {
  if (!props.candidates.length || !props.candidates[0].objectives) return []

  const m = props.candidates[0].objectives.length
  const mins = new Array(m).fill(Infinity)
  const maxs = new Array(m).fill(-Infinity)

  // Compute global min/max for each objective
  props.candidates.forEach((c) => {
    if (!c.objectives) return
    c.objectives.forEach((o, i) => {
      if (o.value != null) {
        mins[i] = Math.min(mins[i], o.value)
        maxs[i] = Math.max(maxs[i], o.value)
      }
    })
  })

  return props.candidates.map((c, idx) => {
    const values = (c.objectives || []).map((o, i) => {
      if (o.value == null) return null
      const range = maxs[i] - mins[i]
      if (range === 0) return 0.5
      const normalized = (o.value - mins[i]) / range
      return o.direction === 'maximize' ? normalized : 1 - normalized
    })

    return {
      name: c.name || c.formula || c.smiles || `候选材料${idx + 1}`,
      value: values,
    }
  })
})

function buildOption() {
  const names = indicatorNames.value
  const data = normalizedData.value

  const indicator = names.map((name) => ({ name, max: 1 }))

  const series = data.map((item, i) => ({
    name: item.name,
    type: 'radar',
    data: [{ value: item.value, name: item.name }],
    symbol: 'circle',
    symbolSize: 4,
    lineStyle: { color: COLORS[i % COLORS.length], width: 1.5 },
    areaStyle: { color: COLORS[i % COLORS.length], opacity: 0.06 },
    itemStyle: { color: COLORS[i % COLORS.length] },
    emphasis: {
      lineStyle: { width: 2.5 },
    },
  }))

  return {
    title: { show: false },
    animation: !prefersReducedMotion.value,
    animationDuration: prefersReducedMotion.value ? 0 : 300,
    tooltip: {
      trigger: 'item',
    },
    legend: {
      type: 'scroll',
      bottom: 0,
      textStyle: { fontSize: 11 },
      pageIconSize: 10,
    },
    radar: {
      indicator,
      center: ['50%', '48%'],
      radius: '65%',
      axisName: {
        fontSize: 11,
        color: '#666',
      },
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
  () => props.candidates,
  () => nextTick(renderChart),
  { deep: true }
)
</script>

<style scoped>
.radar-chart {
  width: 100%;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
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