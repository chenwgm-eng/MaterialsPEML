<template>
  <div class="result-chart">
    <div
      v-if="!props.data.length"
      class="chart-empty"
      role="status"
      aria-live="polite"
    >
      {{ MESSAGES.empty }}
    </div>
    <div
      v-else
      ref="chartRef"
      role="img"
      :aria-label="title ? title : '数据图表'"
      :style="{ height: height + 'px', width: '100%' }"
      tabindex="0"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { MESSAGES } from '@/constants/glossary'

echarts.use([
  BarChart, LineChart, ScatterChart,
  TitleComponent, TooltipComponent, GridComponent, LegendComponent,
  CanvasRenderer,
])

const props = defineProps({
  type: { type: String, default: 'line' },
  data: { type: Array, default: () => [] },
  xKey: { type: String, default: 'x' },
  yKey: { type: String, default: 'y' },
  title: { type: String, default: '' },
  height: { type: Number, default: 280 },
  facet: { type: Boolean, default: false },
})

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null
let retryTimer = null

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

const chartOption = computed(() => {
  const xData = props.data.map((d) => d[props.xKey])
  const yData = props.data.map((d) => d[props.yKey])

  const tooltip = { trigger: 'axis', backgroundColor: '#ffffff', borderColor: '#e0e0e0', borderWidth: 1, textStyle: { color: '#1a1a2e', fontSize: 12 }, extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 6px;' }
  const grid = { left: 48, right: 20, top: props.title ? 36 : 16, bottom: 32 }
  const categoryAxis = { type: 'category', data: xData, axisLine: { lineStyle: { color: '#e0e0e0' } }, axisTick: { show: false }, axisLabel: { color: '#8a8f9c', fontSize: 11 } }
  const valueAxis = { type: 'value', splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { color: '#8a8f9c', fontSize: 11 } }

  if (props.type === 'line') {
    return {
      title: props.title ? { text: props.title, textStyle: { fontSize: 14, fontWeight: 600, color: '#1a1a2e' }, left: 0, top: 0 } : undefined,
      tooltip,
      grid,
      xAxis: categoryAxis,
      yAxis: valueAxis,
      series: [{
        type: 'line',
        data: yData,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: '#2050d0', width: 2 },
        itemStyle: { color: '#2050d0' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(32, 80, 208, 0.18)' }, { offset: 1, color: 'rgba(32, 80, 208, 0.01)' }] } },
      }],
    }
  }

  if (props.type === 'bar' && props.facet) {
    const groups = props.data // [{ name: string, values: number[] }]
    if (groups.length === 0) {
      return { title: undefined, grid: { left: 48, right: 20, top: 16, bottom: 32 }, xAxis: { show: false }, yAxis: { show: false }, series: [] }
    }
    const n = groups.length
    const gap = 4
    const each = (100 - gap * (n - 1)) / n
    const colors = ['#2050d0', '#d02050', '#20a050', '#d0a020', '#8020d0', '#20a0d0', '#d08020', '#5020d0']

    const grids = groups.map((_, i) => ({
      left: 65, right: 15,
      top: `${i * (each + gap) + 4}%`,
      height: `${each}%`,
    }))

    const xAxes = groups.map((g, i) => ({
      gridIndex: i,
      type: 'category',
      data: g.values.map((_, j) => `#${j + 1}`),
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { show: false },
    }))

    const yAxes = groups.map((g, i) => ({
      gridIndex: i,
      type: 'value',
      name: g.name,
      nameLocation: 'center',
      nameGap: 50,
      nameTextStyle: { fontSize: 11, color: '#8a8f9c' },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#8a8f9c', fontSize: 10 },
    }))

    const series = groups.map((g, i) => ({
      type: 'bar',
      xAxisIndex: i,
      yAxisIndex: i,
      data: g.values,
      name: g.name,
      itemStyle: { color: colors[i % colors.length], borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 24,
    }))

    const titleOption = props.title
      ? { text: props.title, textStyle: { fontSize: 14, fontWeight: 600, color: '#1a1a2e' }, left: 0, top: 0 }
      : undefined

    return {
      title: titleOption,
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#ffffff',
        borderColor: '#e0e0e0',
        borderWidth: 1,
        textStyle: { color: '#1a1a2e', fontSize: 12 },
        extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 6px;',
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      series,
    }
  }

  if (props.type === 'bar') {
    return {
      title: props.title ? { text: props.title, textStyle: { fontSize: 14, fontWeight: 600, color: '#1a1a2e' }, left: 0, top: 0 } : undefined,
      tooltip,
      grid,
      xAxis: categoryAxis,
      yAxis: valueAxis,
      series: [{
        type: 'bar',
        data: yData,
        itemStyle: { color: '#2050d0', borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 36,
      }],
    }
  }

  const scatterData = props.data
    .filter((d) => d[props.xKey] != null && d[props.yKey] != null)
    .map((d) => [d[props.xKey], d[props.yKey]])
  return {
    title: props.title ? { text: props.title, textStyle: { fontSize: 14, fontWeight: 600, color: '#1a1a2e' }, left: 0, top: 0 } : undefined,
    tooltip,
    grid,
    xAxis: valueAxis,
    yAxis: valueAxis,
    series: [{
      type: 'scatter',
      data: scatterData,
      itemStyle: { color: '#2050d0' },
      symbolSize: 10,
    }],
  }
})

function initChart() {
  if (chartInstance || !chartRef.value) return false
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    chartRef.value.style.height = `${props.height}px`
    const rect2 = chartRef.value.getBoundingClientRect()
    if (rect2.width === 0 || rect2.height === 0) return false
  }
  chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption(chartOption.value)
  chartInstance.setOption({ animation: !prefersReducedMotion() })
  return true
}

function updateChart() {
  if (!chartInstance) return
  chartInstance.setOption(chartOption.value, true)
  chartInstance.setOption({ animation: !prefersReducedMotion() })
}

function handleResize() {
  if (!chartRef.value) return
  if (chartInstance) {
    chartInstance.resize()
  } else {
    renderChart()
  }
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

function renderChart() {
  if (!props.data.length || !chartRef.value) {
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
  updateChart()
}

watch(chartOption, renderChart)

onMounted(() => {
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
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  clearRetry()
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.result-chart {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  padding: 12px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
  color: #8a92a6;
  font-size: 14px;
}

.result-chart > div[role="img"]:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}
</style>
