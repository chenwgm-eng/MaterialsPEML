<template>
  <div class="mgmt-dashboard">
    <div class="page-header">
      <h1 class="page-title">管理看板</h1>
      <p class="page-subtitle">研发资源监控与成本分析 — 项目/任务/材料/计算资源总览</p>
      <p class="page-usage-hint">使用说明：管理员视角的平台健康看板；用于发现资源瓶颈、超支风险与异常任务</p>
      <a-button size="small" :loading="loading" @click="fetchAll" class="refresh-btn">
        <ReloadOutlined /> 刷新
      </a-button>
    </div>

    <!-- 时间范围筛选器：快捷选项 + 自定义日期范围 -->
    <div class="dashboard-toolbar">
      <a-space wrap>
        <a-button size="small" :type="activePreset === 'today' ? 'primary' : 'default'" @click="setRange('today')">今日</a-button>
        <a-button size="small" :type="activePreset === 'week' ? 'primary' : 'default'" @click="setRange('week')">本周</a-button>
        <a-button size="small" :type="activePreset === 'month' ? 'primary' : 'default'" @click="setRange('month')">本月</a-button>
        <a-button size="small" :type="activePreset === '30d' ? 'primary' : 'default'" @click="setRange('30d')">近30天</a-button>
        <a-button size="small" :type="activePreset === '90d' ? 'primary' : 'default'" @click="setRange('90d')">近90天</a-button>
        <a-range-picker
          v-model:value="dateRange"
          size="small"
          :placeholder="['开始日期', '结束日期']"
          @change="onDateRangeChange"
        />
      </a-space>
    </div>

    <!-- 顶部 4 个 StatCard -->
    <div class="stat-grid">
      <StatCard
        :value="overview.projects?.total || 0"
        label="项目总数"
        :icon="markRaw(ProjectOutlined)"
        icon-color="#1d4ed8"
      />
      <StatCard
        :value="overview.experiments?.total || 0"
        label="实验任务数"
        :icon="markRaw(FormOutlined)"
        icon-color="#20a050"
      />
      <StatCard
        :value="overview.candidates || 0"
        label="候选材料数"
        :icon="markRaw(ExperimentOutlined)"
        icon-color="#d0a020"
      />
      <StatCard
        :value="overview.ecml?.active || 0"
        label="活跃 ECML 运行"
        :icon="markRaw(SyncOutlined)"
        icon-color="#d02050"
      />
    </div>

    <!-- 中部：项目分布 + 任务状态 -->
    <div class="chart-grid">
      <a-card :bordered="false" class="chart-card">
        <template #title>
          <span class="card-title">项目阶段分布</span>
        </template>
        <div ref="projectPieRef" class="chart-box" />
      </a-card>
      <a-card :bordered="false" class="chart-card">
        <template #title>
          <span class="card-title">实验任务状态分布</span>
        </template>
        <div ref="taskBarRef" class="chart-box" />
      </a-card>
    </div>

    <!-- 团队分布 + 成本趋势 -->
    <div class="chart-grid">
      <a-card :bordered="false" class="chart-card">
        <template #title>
          <span class="card-title">团队角色分布</span>
        </template>
        <div ref="teamPieRef" class="chart-box" />
      </a-card>
      <a-card :bordered="false" class="chart-card">
        <template #title>
          <span class="card-title">成本分析趋势</span>
          <a-tag color="blue" class="title-tag tabular-nums">总成本 ¥{{ formatNum(cost.total_cost) }}</a-tag>
        </template>
        <div ref="costLineRef" class="chart-box" />
      </a-card>
    </div>

    <!-- 计算资源使用率趋势 + 资源使用率 -->
    <div class="chart-grid">
      <a-card :bordered="false" class="chart-card">
        <template #title>
          <span class="card-title">ECML 运行次数趋势</span>
          <a-tag color="blue" class="title-tag tabular-nums">单价 ¥{{ cost.compute?.unit_cost || 0 }}/次</a-tag>
        </template>
        <div ref="computeLineRef" class="chart-box" />
      </a-card>
      <a-card :bordered="false" class="chart-card resource-card">
        <template #title>
          <span class="card-title">资源使用率</span>
        </template>
        <div class="resource-body">
          <div class="resource-item">
            <div class="resource-label">
              <span>设备使用率</span>
              <span class="resource-value tabular-nums">{{ resources.equipment?.in_use || 0 }} / {{ resources.equipment?.total || 0 }}</span>
            </div>
            <a-progress
              :percent="toPercent(resources.equipment?.usage_rate)"
              :stroke-color="progressColor(toPercent(resources.equipment?.usage_rate))"
              size="small"
            />
          </div>
          <div class="resource-item">
            <div class="resource-label">
              <span>样品库存</span>
              <span class="resource-value tabular-nums">{{ resources.samples?.total || 0 }} 个</span>
            </div>
            <div class="resource-tags">
              <a-tag v-for="(v, k) in resources.samples?.by_status || {}" :key="k" class="sample-tag">
                {{ sampleStatusLabel(k) }}: {{ v }}
              </a-tag>
              <span v-if="Object.keys(resources.samples?.by_status || {}).length === 0" class="empty-inline">暂无</span>
            </div>
          </div>
          <div class="resource-item">
            <div class="resource-label">
              <span>计算队列</span>
              <span class="resource-value tabular-nums">{{ resources.compute_queue?.length || 0 }} 个</span>
            </div>
          </div>
          <div class="resource-item alert-item">
            <div class="resource-label">
              <span>
                <WarningOutlined /> 物料库存预警
              </span>
              <a-tag color="red">{{ resources.material_alerts?.count || 0 }} 条</a-tag>
            </div>
            <div v-if="(resources.material_alerts?.items || []).length === 0" class="empty-inline">
              所有物料库存充足（阈值 {{ resources.material_alerts?.threshold || 10 }}{{ massUnit }}）
            </div>
            <div v-else class="alert-list">
              <div
                v-for="item in (resources.material_alerts?.items || []).slice(0, 5)"
                :key="item.material_id"
                class="alert-row"
              >
                <div class="alert-main">
                  <span class="alert-name">{{ item.name || item.material_id }}</span>
                  <span class="alert-inventory tabular-nums">{{ item.inventory?.toFixed(1) }} {{ massUnit }}</span>
                </div>
                <div class="alert-context">{{ item.context || '库存低于阈值' }}</div>
                <div class="alert-action">建议：{{ item.action || '补充采购并登记到货' }}</div>
              </div>
              <div v-if="(resources.material_alerts?.items || []).length > 5" class="alert-more">
                还有 {{ (resources.material_alerts?.items || []).length - 5 }} 条…
              </div>
            </div>
          </div>
        </div>
      </a-card>
    </div>

    <!-- 系统监控 (T-056)：P0/P1 复发率 / 操作成功率 / AI 采纳率 -->
    <a-card :bordered="false" class="chart-card monitor-card">
      <template #title>
        <span class="card-title">系统监控 (T-056)</span>
        <a-tag color="blue" class="title-tag tabular-nums">近 {{ monitoring.days || 30 }} 天</a-tag>
      </template>
      <div class="monitor-grid">
        <div class="monitor-item">
          <a-statistic
            title="P0/P1 错误复发率"
            :value="toPercent(monitoring.p0_p1_recurrence?.recurrence_rate)"
            suffix="%"
            :value-style="{ color: recurrenceColor(monitoring.p0_p1_recurrence?.recurrence_rate) }"
          />
          <div class="monitor-meta tabular-nums">
            <span>近30天错误: {{ monitoring.p0_p1_recurrence?.errors_30d || 0 }}</span>
            <span>近7天错误: {{ monitoring.p0_p1_recurrence?.errors_7d || 0 }}</span>
          </div>
          <a-progress
            :percent="toPercent(monitoring.p0_p1_recurrence?.recurrence_rate)"
            :stroke-color="recurrenceColor(monitoring.p0_p1_recurrence?.recurrence_rate)"
            size="small"
          />
        </div>
        <div class="monitor-item">
          <a-statistic
            title="用户操作成功率"
            :value="toPercent(monitoring.operation_success_rate?.success_rate)"
            suffix="%"
            :value-style="{ color: rateColor(monitoring.operation_success_rate?.success_rate) }"
          />
          <div class="monitor-meta tabular-nums">
            <span>总操作: {{ monitoring.operation_success_rate?.total || 0 }}</span>
            <span>失败: {{ monitoring.operation_success_rate?.failed || 0 }}</span>
          </div>
          <a-progress
            :percent="toPercent(monitoring.operation_success_rate?.success_rate)"
            :stroke-color="rateColor(monitoring.operation_success_rate?.success_rate)"
            size="small"
          />
        </div>
        <div class="monitor-item">
          <a-statistic
            title="AI 输出采纳率"
            :value="toPercent(monitoring.ai_adoption_rate?.adoption_rate)"
            suffix="%"
            :value-style="{ color: rateColor(monitoring.ai_adoption_rate?.adoption_rate) }"
          />
          <div class="monitor-meta tabular-nums">
            <span>AI 输出: {{ monitoring.ai_adoption_rate?.total || 0 }}</span>
            <span>采纳: {{ monitoring.ai_adoption_rate?.adopted || 0 }}</span>
          </div>
          <a-progress
            :percent="toPercent(monitoring.ai_adoption_rate?.adoption_rate)"
            :stroke-color="rateColor(monitoring.ai_adoption_rate?.adoption_rate)"
            size="small"
          />
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, markRaw, computed } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import * as echarts from 'echarts/core'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, GridComponent, LegendComponent,
} from 'echarts/components'
import { useUnitSymbols } from '@/utils/mdmDict'
import { CanvasRenderer } from 'echarts/renderers'
import {
  ProjectOutlined, FormOutlined, ExperimentOutlined, SyncOutlined,
  ReloadOutlined, WarningOutlined,
} from '@ant-design/icons-vue'
import StatCard from '@/components/StatCard.vue'
import { getDashboardOverview, getDashboardCost, getDashboardResources, getDashboardMonitoring } from '@/api/dashboard'

echarts.use([
  PieChart, BarChart, LineChart,
  TitleComponent, TooltipComponent, GridComponent, LegendComponent,
  CanvasRenderer,
])

// MDM 单位符号（mass 维度）
const { load: loadUnitSymbols, get: getUnitSymbol } = useUnitSymbols()
const massUnit = computed(() => getUnitSymbol('mass'))

const CHART_HEIGHT = 300
const CHART_COLORS = ['#2050d0', '#20a050', '#d0a020', '#d02050', '#8020d0', '#20a0d0', '#d08020', '#5020d0']

const loading = ref(false)
const overview = ref({})
const cost = ref({})
const resources = ref({})
const monitoring = ref({})

// 时间范围筛选：dateRange 为 [dayjs, dayjs] 或空数组；activePreset 标记当前快捷选项
const dateRange = ref([])
const activePreset = ref('30d')

function setRange(preset) {
  const now = dayjs()
  let start
  if (preset === 'today') start = now.startOf('day')
  else if (preset === 'week') start = now.startOf('week')
  else if (preset === 'month') start = now.startOf('month')
  else if (preset === '30d') start = now.subtract(30, 'day')
  else if (preset === '90d') start = now.subtract(90, 'day')
  else return
  dateRange.value = [start, now]
  activePreset.value = preset
  fetchAll()
}

function onDateRangeChange() {
  // 用户手动选择日期范围后，取消快捷选项高亮
  activePreset.value = ''
  fetchAll()
}

function buildParams() {
  if (dateRange.value && dateRange.value.length === 2) {
    return {
      start_date: dateRange.value[0].format('YYYY-MM-DD'),
      end_date: dateRange.value[1].format('YYYY-MM-DD'),
    }
  }
  return null
}

// T-056 监控端点使用 days 参数（默认 30）；由当前日期范围推导
function buildMonitoringParams() {
  if (dateRange.value && dateRange.value.length === 2) {
    const diff = dateRange.value[1].diff(dateRange.value[0], 'day') + 1
    return { days: Math.max(1, Math.min(365, diff)) }
  }
  return { days: 30 }
}

async function fetchMonitoring() {
  try {
    const m = await getDashboardMonitoring(buildMonitoringParams())
    monitoring.value = m || {}
  } catch (e) {
    // 静默失败：监控数据不可用时不打扰主看板
    monitoring.value = {}
  }
}

// 图表 DOM 引用
const projectPieRef = ref(null)
const taskBarRef = ref(null)
const teamPieRef = ref(null)
const costLineRef = ref(null)
const computeLineRef = ref(null)

// 图表实例
let projectPieChart = null
let taskBarChart = null
let teamPieChart = null
let costLineChart = null
let computeLineChart = null

function formatNum(v) {
  if (v === undefined || v === null) return '0'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function toPercent(v) {
  if (!v) return 0
  return Math.round(v * 100)
}

function progressColor(p) {
  if (p >= 80) return '#d02050'
  if (p >= 50) return '#b45309'
  return '#20a050'
}

// T-056 监控指标颜色：越高越好（成功率/采纳率）≥95% 绿、80-95% 橙、<80% 红
function rateColor(rate) {
  const p = toPercent(rate)
  if (p >= 95) return '#20a050'
  if (p >= 80) return '#b45309'
  return '#d02050'
}

// 复发率：越低越好 <20% 绿、20-50% 橙、≥50% 红
function recurrenceColor(rate) {
  const p = toPercent(rate)
  if (p < 20) return '#20a050'
  if (p < 50) return '#b45309'
  return '#d02050'
}

function sampleStatusLabel(k) {
  const map = {
    created: '已创建', in_storage: '在库', in_use: '使用中',
    consumed: '已消耗', discarded: '已废弃',
  }
  return map[k] || k
}

// --- 图表初始化 ---

function makePieOption(data, titleText) {
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: '#8a8f9c' } },
    color: CHART_COLORS,
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data,
    }],
  }
}

function makeBarOption(categories, values, color = '#2050d0') {
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 50, right: 20, top: 16, bottom: 40 },
    xAxis: {
      type: 'category', data: categories,
      axisLabel: { color: '#8a8f9c', fontSize: 11, rotate: categories.length > 6 ? 25 : 0 },
      axisLine: { lineStyle: { color: '#e0e0e0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#8a8f9c', fontSize: 11 },
    },
    series: [{
      type: 'bar', data: values,
      itemStyle: { color, borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 36,
    }],
  }
}

function makeLineOption(categories, series, legend = true) {
  return {
    tooltip: { trigger: 'axis' },
    legend: legend ? { bottom: 0, textStyle: { fontSize: 11, color: '#8a8f9c' } } : undefined,
    grid: { left: 50, right: 20, top: 16, bottom: legend ? 36 : 24 },
    xAxis: {
      type: 'category', data: categories,
      axisLabel: { color: '#8a8f9c', fontSize: 11 },
      axisLine: { lineStyle: { color: '#e0e0e0' } },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#8a8f9c', fontSize: 11 },
    },
    series: series.map((s, i) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      smooth: true,
      showSymbol: true,
      symbolSize: 6,
      lineStyle: { width: 2, color: CHART_COLORS[i % CHART_COLORS.length] },
      itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
      areaStyle: s.area ? {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: CHART_COLORS[i % CHART_COLORS.length] + '33' },
            { offset: 1, color: CHART_COLORS[i % CHART_COLORS.length] + '01' },
          ],
        },
      } : undefined,
    })),
  }
}

function renderProjectPie() {
  if (!projectPieRef.value) return
  if (!projectPieChart) projectPieChart = echarts.init(projectPieRef.value)
  const byStage = overview.value.projects?.by_stage || {}
  const data = Object.entries(byStage).map(([name, value]) => ({ name, value }))
  projectPieChart.setOption(makePieOption(data, '项目阶段分布'), true)
  projectPieChart.resize()
}

function renderTaskBar() {
  if (!taskBarRef.value) return
  if (!taskBarChart) taskBarChart = echarts.init(taskBarRef.value)
  const byStatus = overview.value.experiments?.by_status || {}
  const statusLabels = {
    DRAFT: '草稿', PENDING_APPROVAL: '待审批', APPROVED: '已批准',
    SCHEDULED: '已排程', IN_EXECUTION: '执行中', WAITING_FOR_DATA: '待数据',
    COMPLETED: '已完成', CANCELLED: '已取消',
  }
  const categories = Object.keys(byStatus).map((k) => statusLabels[k] || k)
  const values = Object.values(byStatus)
  taskBarChart.setOption(makeBarOption(categories, values, '#2050d0'), true)
  taskBarChart.resize()
}

function renderTeamPie() {
  if (!teamPieRef.value) return
  if (!teamPieChart) teamPieChart = echarts.init(teamPieRef.value)
  const byRole = overview.value.users?.by_role || {}
  const roleLabels = {
    admin: '管理员', pm: '项目经理', researcher: '研究员',
    reviewer: '审核员', viewer: '只读访客',
  }
  const data = Object.entries(byRole).map(([k, v]) => ({ name: roleLabels[k] || k, value: v }))
  teamPieChart.setOption(makePieOption(data, '团队角色分布'), true)
  teamPieChart.resize()
}

function renderCostLine() {
  if (!costLineRef.value) return
  if (!costLineChart) costLineChart = echarts.init(costLineRef.value)
  const trend = cost.value.monthly_trend || []
  const months = trend.map((t) => t.month)
  costLineChart.setOption(
    makeLineOption(
      months,
      [
        { name: '物料成本', data: trend.map((t) => t.material_cost), area: true },
        { name: '计算成本', data: trend.map((t) => t.compute_cost), area: true },
        { name: '总成本', data: trend.map((t) => t.total) },
      ],
      true,
    ),
    true,
  )
  costLineChart.resize()
}

function renderComputeLine() {
  if (!computeLineRef.value) return
  if (!computeLineChart) computeLineChart = echarts.init(computeLineRef.value)
  const trend = cost.value.monthly_trend || []
  const months = trend.map((t) => t.month)
  const runCounts = trend.map((t) => Math.round((t.compute_cost || 0) / (cost.value.compute?.unit_cost || 1)))
  computeLineChart.setOption(
    makeLineOption(months, [{ name: 'ECML 运行次数', data: runCounts, area: true }], false),
    true,
  )
  computeLineChart.resize()
}

function onResize() {
  projectPieChart?.resize()
  taskBarChart?.resize()
  teamPieChart?.resize()
  costLineChart?.resize()
  computeLineChart?.resize()
}

// ECharts 初始化重试：容器宽度为 0 时（DOM 未就绪）按 100ms 间隔重试，最多 20 次
let renderRetryTimer = null
let renderRetryCount = 0
const RENDER_RETRY_MAX = 20

function tryRenderCharts() {
  const refs = [projectPieRef.value, taskBarRef.value, teamPieRef.value, costLineRef.value, computeLineRef.value]
  const ready = refs.every((el) => el && el.clientWidth > 0)
  if (!ready) {
    renderRetryCount += 1
    if (renderRetryCount <= RENDER_RETRY_MAX) {
      renderRetryTimer = setTimeout(tryRenderCharts, 100)
    }
    return
  }
  renderProjectPie()
  renderTaskBar()
  renderTeamPie()
  renderCostLine()
  renderComputeLine()
}

async function fetchAll() {
  loading.value = true
  try {
    const params = buildParams()
    const [ov, c, r] = await Promise.all([
      getDashboardOverview(params),
      getDashboardCost(params),
      getDashboardResources(params),
    ])
    overview.value = ov || {}
    cost.value = c || {}
    resources.value = r || {}
    await nextTick()
    renderRetryCount = 0
    tryRenderCharts()
  } catch (e) {
    message.error('数据加载失败，请稍后重试或联系管理员')
  } finally {
    loading.value = false
  }
  // T-056 监控数据独立加载，失败不影响主看板
  fetchMonitoring()
}

onMounted(async () => {
  // 给所有 chart 容器固定高度
  await nextTick()
  // 默认时间范围：近 30 天（setRange 内部会触发首次 fetchAll）
  setRange('30d')
  window.addEventListener('resize', onResize)
  loadUnitSymbols()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (renderRetryTimer) {
    clearTimeout(renderRetryTimer)
    renderRetryTimer = null
  }
  projectPieChart?.dispose()
  taskBarChart?.dispose()
  teamPieChart?.dispose()
  costLineChart?.dispose()
  computeLineChart?.dispose()
})
</script>

<style scoped>
.mgmt-dashboard {
  max-width: 1400px;
  overflow-x: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.dashboard-toolbar {
  margin-bottom: 16px;
  padding: 10px 12px;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  flex-shrink: 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
  flex: 1;
  min-width: 200px;
}

.refresh-btn {
  flex-shrink: 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.chart-grid:last-child {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
}

.chart-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.chart-card :deep(.ant-card-head) {
  min-height: 40px;
  padding: 8px 16px;
}

.chart-card :deep(.ant-card-head-title) {
  padding: 4px 0;
}

.chart-card :deep(.ant-card-body) {
  padding: 12px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.title-tag {
  margin-left: 8px;
  font-size: 11px;
}

.chart-box {
  width: 100%;
  height: 300px;
}

/* --- 资源使用率 --- */
.resource-card :deep(.ant-card-body) {
  padding: 16px;
}

.resource-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 300px;
  overflow-y: auto;
}

.resource-item {
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}

.resource-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.resource-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.resource-value {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.resource-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sample-tag {
  font-size: 11px;
  margin: 0;
}

.alert-item .resource-label {
  /* 对比度修复：#f53f3f 作 13px 小字仅 3.7:1，加深至 #dc2626（4.5:1+） */
  color: #dc2626;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.alert-row {
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border);
}

.alert-row:last-child {
  border-bottom: none;
}

.alert-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.alert-name {
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.alert-inventory {
  font-family: monospace;
  font-weight: 600;
  color: #dc2626;
  font-variant-numeric: tabular-nums;
}

.alert-context {
  margin-top: 2px;
  color: var(--text-muted);
  line-height: 1.5;
}

.alert-action {
  margin-top: 2px;
  /* 对比度修复：#1d4ed8 作 12px 小字仅 2.8:1，加深至 #1e40af */
  color: #1e40af;
  line-height: 1.5;
}

.alert-more {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.empty-inline {
  font-size: 12px;
  color: var(--text-muted);
}

/* --- T-056 系统监控 --- */
.monitor-card :deep(.ant-card-body) {
  padding: 16px;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 768px) {
  .monitor-grid {
    grid-template-columns: 1fr;
  }
}

.monitor-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--light-bg, #fafafa);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
}

.monitor-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
