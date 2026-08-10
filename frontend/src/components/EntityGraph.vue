<template>
  <div class="entity-graph-wrap">
    <div v-if="!nodes.length" class="entity-graph-empty">
      <EmptyState type="data" description="暂无实体数据" />
    </div>
    <div ref="chartRef" class="entity-chart" v-show="nodes.length"></div>

    <!-- 节点详情弹窗 -->
    <a-modal v-model:open="detailVisible" :title="detailTitle" :footer="null" width="520px">
      <a-descriptions v-if="detailNode" :column="1" size="small" bordered>
        <a-descriptions-item label="类型">{{ nodeTypeLabel(detailNode.type) }}</a-descriptions-item>
        <a-descriptions-item label="状态" v-if="detailNode.status">
          <a-tag :color="statusColor(detailNode.status)">{{ detailNode.status }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item v-for="(v, k) in detailMeta" :key="k" :label="metaLabel(k)">
          {{ v }}
        </a-descriptions-item>
      </a-descriptions>
      <div class="detail-actions" v-if="detailNode">
        <a-button type="primary" size="small" @click="onJumpToDetail">查看详情</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  // 显示层级：'core' 仅显示核心 5 类；'full' 显示全部
  level: { type: String, default: 'core' },
})
const emit = defineEmits(['select'])

const router = useRouter()
const chartRef = ref(null)
let chart = null
let resizeObserver = null

const detailVisible = ref(false)
const detailNode = ref(null)

// 核心 5 类（level==='core' 时仅展示这些节点 + 它们之间的边）
const CORE_TYPES = new Set(['project', 'task', 'candidate', 'experiment_order', 'ecml_run'])

// 节点类型 → 中文标签
const TYPE_LABELS = {
  project: '项目',
  task: '任务',
  candidate: '候选材料',
  bom: 'BOM 方案',
  process: '工艺方案',
  experiment_order: '实验任务',
  test_task: '测试任务',
  sample: '样品',
  result_record: '实验数据',
  ecml_run: 'ECML 迭代',
}

// 节点类型 → 颜色
const TYPE_COLORS = {
  project: '#2050d0',       // 蓝
  task: '#10b981',          // 绿
  candidate: '#8b5cf6',     // 紫
  ecml_run: '#06b6d4',     // 青
  experiment_order: '#1d4ed8', // 橙
  bom: '#ec4899',          // 粉
  process: '#f59e0b',      // 琥珀
  test_task: '#14b8a6',     // 蓝绿
  sample: '#a78bfa',        // 淡紫
  result_record: '#6366f1', // 靛蓝
}

// 状态 → 标签颜色
function statusColor(status) {
  if (!status) return 'default'
  const s = String(status).toLowerCase()
  if (['完成', 'completed', 'complete', 'valid', 'approved', 'success', '收敛', 'verified'].some(k => s.includes(k.toLowerCase()))) return 'success'
  if (['失败', 'failed', 'fail', 'invalid', 'rejected', 'cancel', 'timeout'].some(k => s.includes(k.toLowerCase()))) return 'error'
  if (['草稿', 'draft', 'pending', '等待', 'waiting', 'planned'].some(k => s.includes(k.toLowerCase()))) return 'default'
  if (['执行', '进行', 'running', 'in_execution', 'active', 'progress'].some(k => s.includes(k.toLowerCase()))) return 'processing'
  return 'blue'
}

const nodeTypeLabel = (t) => TYPE_LABELS[t] || t || '未知'

// 详情弹窗展示的元数据字段（排除 UI 字段）
const META_KEYS = ['task_id', 'candidate_id', 'bom_id', 'order_id', 'sample_id', 'run_id',
  'process_id', 'test_task_id', 'candidate_type', 'score', 'execution_mode', 'priority',
  'iteration_id', 'is_complete', 'parent_run_id', 'deliverable', 'test_type',
  'total', 'valid', 'step']
const META_LABELS = {
  task_id: '任务 ID',
  candidate_id: '候选 ID',
  bom_id: 'BOM ID',
  order_id: '任务单 ID',
  sample_id: '样品 ID',
  run_id: 'Run ID',
  process_id: '工艺 ID',
  test_task_id: '测试任务 ID',
  candidate_type: '候选类型',
  score: '评分',
  execution_mode: '执行模式',
  priority: '优先级',
  iteration_id: '迭代轮次',
  is_complete: '是否完成',
  parent_run_id: '父轮 Run ID',
  deliverable: '交付物',
  test_type: '测试类型',
  total: '数据总数',
  valid: '有效数据',
  step: 'ECML 步骤',
}
const metaLabel = (k) => META_LABELS[k] || k
const detailMeta = computed(() => {
  if (!detailNode.value) return {}
  const out = {}
  for (const k of META_KEYS) {
    if (detailNode.value[k] !== undefined && detailNode.value[k] !== '' && detailNode.value[k] !== null) {
      let v = detailNode.value[k]
      if (k === 'is_complete') v = v ? '是' : '否'
      out[k] = v
    }
  }
  return out
})

const detailTitle = computed(() => {
  if (!detailNode.value) return '节点详情'
  return `${nodeTypeLabel(detailNode.value.type)} · ${detailNode.value.label}`
})

// 过滤节点（按 level）
const filteredNodes = computed(() => {
  if (props.level === 'full') return props.nodes
  return props.nodes.filter(n => CORE_TYPES.has(n.type))
})

const filteredNodeIds = computed(() => new Set(filteredNodes.value.map(n => n.id)))

const filteredEdges = computed(() => {
  return props.edges.filter(e => filteredNodeIds.value.has(e.source) && filteredNodeIds.value.has(e.target))
})

// 计算布局：分层 + 孤立节点左侧纵列
function computeLayout(nodes, edges) {
  // 找出孤立节点（没有任何边连接）
  const connectedIds = new Set()
  edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target) })
  const isolatedNodes = nodes.filter(n => !connectedIds.has(n.id))
  const connectedNodes = nodes.filter(n => connectedIds.has(n.id))

  // 按 layer 分组（连通节点）
  const byLayer = new Map()
  connectedNodes.forEach(n => {
    const layer = n.layer ?? 0
    if (!byLayer.has(layer)) byLayer.set(layer, [])
    byLayer.get(layer).push(n)
  })

  // 排序 layer
  const sortedLayers = [...byLayer.keys()].sort((a, b) => a - b)

  // 画布参数（动态：同层节点越多，间距越小，避免溢出）
  const maxLayerSize = Math.max(1, ...sortedLayers.map(l => byLayer.get(l).length))
  // 节点多时压缩间距，但保留最小间距避免重叠
  const NODE_SPACING = Math.max(110, 160 - Math.max(0, maxLayerSize - 6) * 8)
  const LAYER_HEIGHT = 110
  const TOP_Y = 60
  // 中心 x 动态：最大层节点数决定画布宽度
  const CENTER_X = Math.max(600, (maxLayerSize - 1) * NODE_SPACING / 2 + 400)

  const positions = new Map()

  // 连通节点：分层布局，每层水平居中分布
  sortedLayers.forEach((layer, layerIdx) => {
    const ns = byLayer.get(layer)
    const totalWidth = (ns.length - 1) * NODE_SPACING
    const startX = CENTER_X - totalWidth / 2
    ns.forEach((n, idx) => {
      positions.set(n.id, {
        x: startX + idx * NODE_SPACING,
        y: TOP_Y + layerIdx * LAYER_HEIGHT,
      })
    })
  })

  // 孤立节点：左侧纵列（从 y=60 开始，x=80）
  const ISOLATED_X = 80
  const ISOLATED_SPACING = 90
  isolatedNodes.forEach((n, idx) => {
    positions.set(n.id, {
      x: ISOLATED_X,
      y: TOP_Y + idx * ISOLATED_SPACING,
    })
  })

  return positions
}

function buildOption() {
  const nodes = filteredNodes.value
  const edges = filteredEdges.value
  if (!nodes.length) return null

  const positions = computeLayout(nodes, edges)

  const chartNodes = nodes.map(n => {
    const pos = positions.get(n.id) || { x: 0, y: 0 }
    return {
      id: n.id,
      name: n.label || n.id,
      x: pos.x,
      y: pos.y,
      symbolSize: n.type === 'project' ? 56 : (n.type === 'task' ? 44 : 36),
      itemStyle: {
        color: TYPE_COLORS[n.type] || '#6b7280',
        borderColor: '#fff',
        borderWidth: 2,
      },
      label: {
        show: true,
        position: 'bottom',
        fontSize: 11,
        color: '#333',
        formatter: (p) => {
          const name = p.data.name || ''
          return name.length > 18 ? name.slice(0, 17) + '…' : name
        },
      },
      category: n.type,
      // 业务数据透传
      rawData: n,
    }
  })

  const chartEdges = edges.map(e => ({
    source: e.source,
    target: e.target,
    label: {
      show: false,
    },
    lineStyle: {
      width: 1.2,
      color: '#94a3b8',
      curveness: 0.15,
    },
  }))

  // 类别（用于 legend）
  const categories = [...new Set(nodes.map(n => n.type))].map(t => ({
    name: t,
  }))

  return {
    tooltip: {
      formatter: (p) => {
        if (p.dataType !== 'node') return ''
        const n = p.data.rawData || {}
        const esc = (s) => String(s || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
        const lines = [`<b>${esc(n.label || n.id)}</b>`, `类型: ${esc(nodeTypeLabel(n.type))}`]
        if (n.status) lines.push(`状态: ${esc(n.status)}`)
        return lines.join('<br/>')
      },
    },
    legend: {
      data: categories.map(c => c.name),
      formatter: (name) => nodeTypeLabel(name),
      top: 8,
      left: 'center',
      textStyle: { fontSize: 12 },
    },
    animation: false,
    series: [{
      type: 'graph',
      layout: 'none',  // 使用预计算的 x/y
      roam: true,
      draggable: true,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
      },
      data: chartNodes,
      links: chartEdges,
      categories,
      lineStyle: { color: '#94a3b8' },
    }],
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
    chart.on('click', handleClick)
  }
  const option = buildOption()
  if (option) {
    chart.setOption(option, true)
    // 自适应节点位置：用 dataZoom 适配视图
    nextTick(() => {
      if (chart) chart.resize()
    })
  } else {
    chart.clear()
  }
}

function handleClick(params) {
  if (params.dataType !== 'node') return
  const raw = params.data?.rawData
  if (!raw) return
  detailNode.value = raw
  detailVisible.value = true
  emit('select', raw)
}

// 节点详情跳转
function onJumpToDetail() {
  const n = detailNode.value
  if (!n) return
  detailVisible.value = false
  // 按类型跳转
  switch (n.type) {
    case 'project':
      router.push({ path: '/projects' })
      break
    case 'task':
      router.push({ path: '/projects', query: { task_id: n.task_id } })
      break
    case 'candidate':
      router.push({ path: '/workbench', query: { candidate_id: n.candidate_id } })
      break
    case 'experiment_order':
      router.push({ path: '/experiments', query: { order_id: n.order_id } })
      break
    case 'ecml_run':
      router.push({ path: '/ecml', query: { run_id: n.run_id } })
      break
    case 'sample':
      router.push({ path: '/samples', query: { sample_id: n.sample_id } })
      break
    case 'bom':
    case 'process':
      router.push({ path: '/formula-design', query: { bom_id: n.bom_id } })
      break
    case 'test_task':
      router.push({ path: '/experiments', query: { test_task_id: n.test_task_id } })
      break
    case 'result_record':
      router.push({ path: '/experiments', query: { order_id: n.order_id } })
      break
  }
}

watch([() => props.nodes, () => props.edges, () => props.level], () => {
  renderChart()
}, { deep: true })

onMounted(() => {
  nextTick(() => {
    renderChart()
    if (chartRef.value) {
      resizeObserver = new ResizeObserver(() => {
        if (chart) chart.resize()
      })
      resizeObserver.observe(chartRef.value)
    }
  })
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.entity-graph-wrap {
  width: 100%;
  height: 100%;
  position: relative;
  min-height: 480px;
}
.entity-chart {
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.entity-graph-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 480px;
}
.detail-actions {
  margin-top: 12px;
  text-align: right;
}
</style>
