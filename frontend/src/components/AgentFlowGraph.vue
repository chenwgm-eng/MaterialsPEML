<template>
  <div class="agent-flow-graph-wrap">
    <div v-if="!steps.length" class="flow-empty" role="status" aria-live="polite">
      <span>暂无执行步骤</span>
    </div>
    <div
      ref="chartRef"
      class="agent-flow-graph"
      :class="{ 'is-hidden': !steps.length }"
      role="img"
      aria-label="Agent 执行流程图，节点可点击选择对应 Agent"
      tabindex="0"
      @keydown.enter.prevent="focusSelected"
    ></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  agents: { type: Array, default: () => [] },
  currentStepId: { type: String, default: '' },
  completedSteps: { type: Array, default: () => [] },
  failedSteps: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

const ROLE_COLOR = {
  project_manager: '#2050d0',
  material_discovery: '#10b981',
  synthesis_planning: '#f59e0b',
  dft_verification: '#8b5cf6',
  experiment_analysis: '#06b6d4',
  literature_research: '#ec4899',
  quality_review: '#ef4444',
  custom: '#6b7280',
}

const chartRef = ref(null)
let chart = null
let pulseTimer = null
let pulseOn = false
// 重试定时器引用，组件卸载时统一清理
let retryTimer = null
let resizeObserver = null

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
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

function focusSelected() {
  if (!props.steps.length) return
  const stepId = props.currentStepId || props.steps[0]?.step_id
  if (!stepId) return
  const step = props.steps.find((s) => s.step_id === stepId)
  if (step?.agent_id) emit('select', step.agent_id)
}

// 缓存 agent 映射，避免 pulse 期间每 700ms 重建
const agentMap = computed(() => {
  const m = {}
  props.agents.forEach((a) => { m[a.id] = a })
  return m
})

function getStepStatus(stepId) {
  if (props.completedSteps.includes(stepId)) return 'completed'
  if (props.failedSteps.includes(stepId)) return 'failed'
  if (props.currentStepId === stepId) return 'running'
  return 'pending'
}

function buildNodes(pulse = false) {
  const amap = agentMap.value
  const count = props.steps.length
  return props.steps.map((step, index) => {
    const agent = amap[step.agent_id]
    const role = agent?.role || 'custom'
    const roleColor = ROLE_COLOR[role] || ROLE_COLOR.custom
    const status = getStepStatus(step.step_id)
    const isRunning = status === 'running'
    const name = agent?.name || step.agent_id
    const baseSize = status === 'pending' ? 50 : 56
    const size = isRunning ? 66 : baseSize

    let color
    if (status === 'pending') color = 'rgba(107,114,128,0.25)'
    else if (status === 'failed') color = '#ef4444'
    else if (status === 'completed') color = '#10b981'
    else color = roleColor

    return {
      id: step.step_id,
      name,
      symbolSize: size,
      category: status,
      itemStyle: {
        color,
        borderColor: isRunning ? '#2050d0' : status === 'failed' ? '#ef4444' : roleColor,
        borderWidth: isRunning ? 4 : 2,
        shadowBlur: isRunning ? (pulse ? 32 : 12) : status === 'completed' ? 8 : 0,
        shadowColor: roleColor,
        opacity: status === 'pending' ? 0.6 : 1,
      },
      label: {
        show: true,
        position: 'bottom',
        color: '#1a1a2e',
        fontSize: 12,
        fontWeight: 600,
        formatter: () => `${name}`,
      },
      _agentId: step.agent_id,
      _status: status,
      _task: step.task,
      _roleColor: roleColor,
    }
  })
}

function buildLinks() {
  const stepIds = new Set(props.steps.map((s) => s.step_id))
  const links = []
  props.steps.forEach((step) => {
    ;(step.dependencies || []).forEach((dep) => {
      if (!stepIds.has(dep)) return
      links.push({
        source: dep,
        target: step.step_id,
      })
    })
  })
  return links
}

function buildOption(pulse = false) {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const d = p.data
          const statusText = {
            pending: '等待中',
            running: '执行中',
            completed: '已完成',
            failed: '失败',
          }[d._status]
          return `<b>${escapeHtml(d.name)}</b><br/>状态：${escapeHtml(statusText)}<br/>任务：${escapeHtml(d._task || '—')}`
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
      data: ['等待中', '执行中', '已完成', '失败'],
    },
    animationDuration: prefersReducedMotion() ? 0 : 800,
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        categories: [
          { name: '等待中', itemStyle: { color: '#6b7280' } },
          { name: '执行中', itemStyle: { color: '#2050d0' } },
          { name: '已完成', itemStyle: { color: '#10b981' } },
          { name: '失败', itemStyle: { color: '#ef4444' } },
        ],
        force: {
          repulsion: 260,
          edgeLength: [90, 170],
          gravity: 0.08,
          layoutAnimation: true,
        },
        label: { show: true },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 9],
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3, color: '#2050d0' },
          itemStyle: { shadowBlur: 16 },
        },
        lineStyle: {
          color: '#c5c8cf',
          width: 1.5,
          curveness: 0.15,
          opacity: 0.8,
        },
        data: buildNodes(pulse),
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
    // 容器不可见，设置最小尺寸
    chartRef.value.style.width = chartRef.value.style.width || '100%'
    chartRef.value.style.height = chartRef.value.style.height || '300px'
    // 尺寸仍为 0 则放弃本次初始化
    const rect2 = chartRef.value.getBoundingClientRect()
    if (rect2.width === 0 || rect2.height === 0) return null
  }
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chart.on('click', handleClick)
  return chart
}

function render() {
  if (!props.steps.length) {
    stopPulse()
    clearRetry()
    if (chart) {
      chart.dispose()
      chart = null
    }
    return
  }
  const c = ensureChart()
  if (!c) {
    // 容器尚未就绪，延迟重试一次
    nextTick(() => {
      setTimeout(() => {
        if (!props.steps.length) return
        const c2 = ensureChart()
        if (!c2) return
        const option = buildOption(false)
        c2.setOption(option, { notMerge: true })
        c2.resize()
        const hasRunning = props.steps.some((s) => getStepStatus(s.step_id) === 'running')
        if (hasRunning) startPulse()
        else stopPulse()
      }, 100)
    })
    return
  }
  const option = buildOption(false)
  c.setOption(option, { notMerge: true })
  c.resize()
  const hasRunning = props.steps.some((s) => getStepStatus(s.step_id) === 'running')
  if (hasRunning) startPulse()
  else stopPulse()
}

function clearRetry() {
  if (retryTimer) {
    clearInterval(retryTimer)
    retryTimer = null
  }
}

// 统一的重试机制：存储 timer ID 以便卸载时清理
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

function startPulse() {
  stopPulse()
  if (prefersReducedMotion()) return
  pulseTimer = setInterval(() => {
    if (!chart) return
    pulseOn = !pulseOn
    chart.setOption(
      { series: [{ data: buildNodes(pulseOn) }] },
      { notMerge: false },
    )
  }, 700)
}

function stopPulse() {
  if (pulseTimer) {
    clearInterval(pulseTimer)
    pulseTimer = null
  }
}

function handleClick(params) {
  if (params.dataType === 'node' && params.data?._agentId) {
    emit('select', params.data._agentId)
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
  render()
  if (!chart && props.steps.length) scheduleRetry()
  window.addEventListener('resize', resize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  stopPulse()
  clearRetry()
  window.removeEventListener('resize', resize)
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(
  () => [props.steps, props.agents, props.currentStepId, props.completedSteps, props.failedSteps],
  () => {
    nextTick(() => {
      setTimeout(() => {
        render()
        if (!chart && props.steps.length) scheduleRetry()
      }, 100)
    })
  },
  { deep: true },
)
</script>

<style scoped>
.agent-flow-graph-wrap {
  width: 100%;
  height: 100%;
  min-height: 400px;
  position: relative;
}

.agent-flow-graph {
  width: 100%;
  height: 100%;
  min-height: 400px;
  outline: none;
}

.agent-flow-graph:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.agent-flow-graph.is-hidden {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
}

.flow-empty {
  width: 100%;
  height: 100%;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
