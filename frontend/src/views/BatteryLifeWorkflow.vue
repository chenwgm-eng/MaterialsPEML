<template>
  <div class="battery-life">
    <div class="page-header">
      <h1 class="page-title">性能寿命预测</h1>
      <p class="page-subtitle">Learner-Interpreter-Oracle 三 Agent 协作：学习衰减模式 → 解释失效机理 → 预测性能寿命</p>
    </div>

    <!-- 输入表单 -->
    <a-card class="input-card" :bordered="false">
      <a-form layout="horizontal" :label-col="{ span: 4 }" :wrapper-col="{ span: 18 }">
        <a-form-item label="材料化学式" extra="可选：填写化学式用于基准数据库对比，如 LiFePO4、NMC532、催化剂配方等">
          <a-input v-model:value="formula" placeholder="例如 LiFePO4" style="width: 100%" />
        </a-form-item>
        <a-form-item label="循环数据" extra="JSON 数组，每项含 cycle（循环数）与 capacity（容量保持率，%），兼容 capacity_retention 字段">
          <a-textarea
            v-model:value="cycleDataText"
            :rows="5"
            placeholder='[{"cycle":0,"capacity":100},{"cycle":100,"capacity":95},{"cycle":200,"capacity":90.5}]'
            style="font-family: monospace; width: 100%"
          />
          <div v-if="parsedCount > 0" class="parsed-hint num">已解析 {{ parsedCount }} 个数据点</div>
        </a-form-item>
        <a-form-item label="预测循环数">
          <a-input-number v-model:value="futureCycles" :min="1" :max="10000" :step="100" style="width: 200px" />
        </a-form-item>
        <a-form-item :wrapper-col="{ offset: 4 }">
          <div class="form-actions">
            <a-button @click="loadSample"><ExperimentOutlined /> 加载示例数据</a-button>
            <a-button @click="cycleDataText = ''">清空</a-button>
            <a-button type="primary" :loading="loading" @click="onPredict">
              <ThunderboltOutlined /> 开始预测
            </a-button>
          </div>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 三 Agent 协作状态 -->
    <a-card class="steps-card" :bordered="false" v-if="hasRun || loading">
      <template #title>
        <span class="card-title-text"><RobotOutlined /> 三 Agent 协作流程</span>
      </template>
      <a-steps :current="activeStep" size="small">
        <a-step title="Learner 学习" :status="stepStatuses[0]">
          <template #description>{{ stepDescriptions[0] }}</template>
        </a-step>
        <a-step title="Interpreter 解释" :status="stepStatuses[1]">
          <template #description>{{ stepDescriptions[1] }}</template>
        </a-step>
        <a-step title="Oracle 预测" :status="stepStatuses[2]">
          <template #description>{{ stepDescriptions[2] }}</template>
        </a-step>
      </a-steps>
    </a-card>

    <!-- 结果区 -->
    <template v-if="result">
      <!-- 衰减曲线图 -->
      <a-card class="result-card" :bordered="false">
        <template #title>
          <span class="card-title-text"><LineChartOutlined /> 衰减曲线（实测 + 拟合 + 预测）</span>
        </template>
        <div ref="chartRef" class="decay-chart" aria-label="容量衰减曲线"></div>
      </a-card>

      <a-row :gutter="16">
        <!-- 机理分析 -->
        <a-col :xs="24" :md="12">
          <a-card class="result-card" :bordered="false">
            <template #title>
              <span class="card-title-text"><BulbOutlined /> 机理分析</span>
            </template>
            <div class="mech-dominant">
              <span class="mech-label">主导机理</span>
              <a-tag :color="severityColor(result.interpretation.severity)" class="mech-tag">
                {{ result.interpretation.dominant_mechanism }}
              </a-tag>
              <a-tag class="mech-tag">{{ result.interpretation.severity }}</a-tag>
            </div>
            <div class="mech-secondary" v-if="result.interpretation.secondary_mechanisms?.length">
              <span class="mech-label">次要机理</span>
              <a-tag v-for="m in result.interpretation.secondary_mechanisms" :key="m" color="blue">{{ m }}</a-tag>
            </div>
            <a-divider style="margin: 12px 0" />
            <div class="mech-list">
              <div v-for="(m, idx) in result.interpretation.mechanisms" :key="idx" class="mech-item">
                <div class="mech-item-head">
                  <span class="mech-item-name">{{ m.name }}</span>
                  <a-progress :percent="Math.round((m.confidence || 0) * 100)" size="small" class="mech-conf" />
                </div>
                <div class="mech-item-desc">{{ m.description }}</div>
              </div>
            </div>
            <a-divider style="margin: 12px 0" />
            <ul class="rec-list">
              <li v-for="(r, idx) in result.interpretation.recommendations" :key="idx">{{ r }}</li>
            </ul>
          </a-card>
        </a-col>

        <!-- 寿命预测 -->
        <a-col :xs="24" :md="12">
          <a-card class="result-card" :bordered="false">
            <template #title>
              <span class="card-title-text"><ThunderboltOutlined /> 寿命预测</span>
            </template>
            <!-- Task 17：低数据量与过拟合警告 -->
            <a-alert
              v-if="result.prediction.low_data_warning"
              style="margin-bottom: 12px"
              type="warning"
              show-icon
              message="数据量不足（< 30 点），预测可靠性受限，建议补充更多循环测试"
              :description="`置信度已封顶至 60%。当前样本：${result.prediction.sample_count} 点`"
            />
            <a-alert
              v-if="result.prediction.overfit_warning"
              style="margin-bottom: 12px"
              type="error"
              show-icon
              message="疑似过拟合"
              :description="`训练集 R² 与测试集 R² 差值 > 0.2（训练 ${result.prediction.train_r_squared ?? '-'} / 测试 ${result.prediction.test_r_squared ?? '-'}），外推预测需谨慎`"
            />
            <div class="life-grid">
              <div class="life-cell">
                <div class="life-cell-label">预测循环寿命</div>
                <div class="life-cell-value num">{{ lifeText }}</div>
                <div class="life-cell-sub">80% 容量保持率阈值</div>
              </div>
              <div class="life-cell">
                <div class="life-cell-label">@{{ result.future_cycles }} 循环容量保持率</div>
                <div class="life-cell-value num">{{ result.prediction.capacity_at_future_cycles }}%</div>
                <div class="life-cell-sub">
                  <a-tag :color="result.prediction.capacity_at_future_cycles >= 80 ? 'green' : 'red'">
                    {{ result.prediction.capacity_at_future_cycles >= 80 ? '未达 EOL' : '已达 EOL' }}
                  </a-tag>
                </div>
              </div>
              <div class="life-cell">
                <div class="life-cell-label">预测置信度</div>
                <div class="life-cell-value num">{{ Math.round((result.prediction.confidence || 0) * 100) }}%</div>
                <div class="life-cell-sub">
                  置信区间 {{ Math.round((result.prediction.confidence_interval_struct?.lower ?? 0) * 100) }}%~{{ Math.round((result.prediction.confidence_interval_struct?.upper ?? 0) * 100) }}%
                  <a-tooltip :title="`置信度封顶 95%，避免不合理的 100% 置信度。区间基于 CV 标准差或样本量启发式估计。原始值：${result.prediction.confidence_interval}`">
                    <InfoCircleOutlined style="margin-left: 4px; color: var(--text-muted)" />
                  </a-tooltip>
                </div>
              </div>
              <div class="life-cell">
                <div class="life-cell-label">衰减率</div>
                <div class="life-cell-value num">{{ result.learning.decay_rate_per_cycle }}/循环</div>
                <div class="life-cell-sub">初始容量 {{ result.learning.initial_capacity }}%</div>
              </div>
              <div class="life-cell">
                <div class="life-cell-label">模型版本</div>
                <div class="life-cell-value num">v{{ result.prediction.model_version }}</div>
                <div class="life-cell-sub">{{ result.learning.model_type }}</div>
              </div>
              <div class="life-cell">
                <div class="life-cell-label">训练集 / 测试集 R²</div>
                <div class="life-cell-value num">
                  {{ result.prediction.train_r_squared != null ? result.prediction.train_r_squared : '-' }}
                  <span style="color: var(--text-muted); font-size: 14px">/</span>
                  {{ result.prediction.test_r_squared != null ? result.prediction.test_r_squared : '-' }}
                </div>
                <div class="life-cell-sub">
                  CV R² 均值 {{ result.learning.cv_r_squared_mean != null ? result.learning.cv_r_squared_mean : '-' }}
                  <span v-if="result.learning.cv_r_squared_std != null">（σ {{ result.learning.cv_r_squared_std }}）</span>
                </div>
              </div>
            </div>
            <a-divider style="margin: 12px 0" />
            <div class="fit-info">
              <span>拟合优度 R² = <b class="num">{{ result.learning.fit_r_squared }}</b></span>
              <span>样本数 <b class="num">{{ result.learning.sample_count }}</b></span>
              <span v-if="result.learning.cv_folds != null">CV 折数 <b class="num">{{ result.learning.cv_folds }}</b></span>
              <span>模型 <b>{{ result.learning.model_type }} v{{ result.prediction.model_version }}</b></span>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 基准对比 -->
      <a-card class="result-card" :bordered="false" v-if="result.reference">
        <template #title>
          <span class="card-title-text"><DatabaseOutlined /> 基准对比（{{ result.reference.data_source }}）</span>
        </template>
        <a-descriptions :column="{ xs: 1, sm: 2, md: 4 }" size="small" bordered>
          <a-descriptions-item label="基准材料">{{ result.reference.name }}</a-descriptions-item>
          <a-descriptions-item label="化学式"><ChemicalFormula v-if="result.reference.formula" :formula="result.reference.formula" size="small" /><span v-else>-</span></a-descriptions-item>
          <a-descriptions-item label="正极">{{ result.reference.cathode }}</a-descriptions-item>
          <a-descriptions-item label="负极">{{ result.reference.anode }}</a-descriptions-item>
          <a-descriptions-item label="基准循环数">{{ result.reference.cycle_count }}</a-descriptions-item>
          <a-descriptions-item label="测试温度">{{ result.reference.temperature }}{{ tempUnit }}</a-descriptions-item>
          <a-descriptions-item label="材料类型">{{ result.reference.material_type }}</a-descriptions-item>
          <a-descriptions-item label="数据来源">{{ result.reference.data_source }}</a-descriptions-item>
        </a-descriptions>
        <a-alert
          style="margin-top: 12px"
          type="info"
          show-icon
          :message="`基准 ${result.reference.name} 标称循环 ${result.reference.cycle_count} 次，图中虚线为其容量保持率曲线，可与本材料实测/拟合曲线直观对比。`"
        />
      </a-card>
      <a-card class="result-card" :bordered="false" v-else-if="hasRun">
        <EmptyState type="data" description="基准数据库中未找到该化学式的对照材料，可尝试输入常见化学式（如 LiFePO4、LiCoO2）查看对比" />
      </a-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import * as echarts from 'echarts'
import {
  ThunderboltOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  BulbOutlined,
  RobotOutlined,
  DatabaseOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons-vue'
import { useUnitSymbols } from '@/utils/mdmDict'
import { runBatteryLifeWorkflow } from '@/api/battery'
import EmptyState from '@/components/EmptyState.vue'

const { load: loadUnitSymbols } = useUnitSymbols()

const formula = ref('LiFePO4')
const cycleDataText = ref('')
const futureCycles = ref(500)
const loading = ref(false)
const hasRun = ref(false)
const result = ref(null)

// 三 Agent 步骤状态
const activeStep = ref(-1)
const stepStatuses = ref(['wait', 'wait', 'wait'])
const stepDescriptions = ref(['', '', ''])

// 衰减曲线图
const chartRef = ref(null)
let chart = null
let resizeObserver = null

const parsedCount = computed(() => {
  try {
    const arr = JSON.parse(cycleDataText.value || '[]')
    return Array.isArray(arr) ? arr.filter((d) => d && d.cycle != null && (d.capacity != null || d.capacity_retention != null)).length : 0
  } catch {
    return 0
  }
})

function loadSample() {
  // 示例：NMC532 风格衰减曲线
  const data = []
  for (let n = 0; n <= 500; n += 25) {
    data.push({ cycle: n, capacity: +(100 * Math.exp(-0.0006 * n)).toFixed(2) })
  }
  cycleDataText.value = JSON.stringify(data, null, 0)
  formula.value = 'LiNi0.5Mn0.3Co0.2O2'
  message.success('已加载示例循环数据（NMC532 风格，0–500 循环）')
}

function severityColor(severity) {
  return { 严重: 'red', 中等: 'orange', 轻微: 'green' }[severity] || 'default'
}

const lifeText = computed(() => {
  if (!result.value) return '-'
  const life = result.value.prediction.predicted_cycle_life
  if (life > 0) return `≈ ${life} 循环`
  if (result.value.prediction.reaches_eol) return '已达寿命终点'
  return '预测范围内未达 EOL'
})

function resetSteps() {
  activeStep.value = -1
  stepStatuses.value = ['wait', 'wait', 'wait']
  stepDescriptions.value = ['', '', '']
}

async function onPredict() {
  let cycleData
  try {
    cycleData = JSON.parse(cycleDataText.value || '[]')
    if (!Array.isArray(cycleData) || cycleData.length === 0) {
      throw new Error('数据为空或不是数组')
    }
  } catch (e) {
    message.error(`循环数据 JSON 解析失败：${e.message}`)
    return
  }

  loading.value = true
  hasRun.value = true
  result.value = null
  resetSteps()
  // 学习阶段进行中
  activeStep.value = 0
  stepStatuses.value = ['process', 'wait', 'wait']
  stepDescriptions.value = ['学习衰减模式…', '', '']

  try {
    const data = await runBatteryLifeWorkflow({
      formula: formula.value,
      smiles: '',
      cycle_data: cycleData,
      future_cycles: futureCycles.value,
    })
    result.value = data
    // 渐进式揭示三步结果
    revealSteps(data)
    await nextTick()
    renderChart()
  } catch {
    stepStatuses.value = ['error', 'wait', 'wait']
    activeStep.value = 0
  } finally {
    loading.value = false
  }
}

const stepTimers = []
function revealSteps(data) {
  // Step 1: Learner 完成
  stepStatuses.value = ['finish', 'process', 'wait']
  const l = data.learning
  // Task 17：附训练/测试 R²，避免仅展示可能为 1.0 的全量拟合 R²
  const r2Info = l.test_r_squared != null
    ? `训练 R²=${l.train_r_squared}，测试 R²=${l.test_r_squared}`
    : `R²=${l.fit_r_squared}`
  stepDescriptions.value = [
    `初始容量 ${l.initial_capacity}%，衰减率 ${l.decay_rate_per_cycle}/循环，${r2Info}`,
    '解释衰减机理…',
    '',
  ]
  activeStep.value = 1
  stepTimers.push(setTimeout(() => {
    // Step 2: Interpreter 完成
    stepStatuses.value = ['finish', 'finish', 'process']
    const it = data.interpretation
    stepDescriptions.value[1] = `主导机理：${it.dominant_mechanism}（${it.severity}）`
    stepDescriptions.value[2] = '外推预测寿命…'
    activeStep.value = 2
    stepTimers.push(setTimeout(() => {
      // Step 3: Oracle 完成
      stepStatuses.value = ['finish', 'finish', 'finish']
      const p = data.prediction
      const lifeTxt = p.predicted_cycle_life > 0
        ? `≈${p.predicted_cycle_life} 循环`
        : (p.reaches_eol ? '已达 EOL' : '未达 EOL')
      stepDescriptions.value[2] = `寿命 ${lifeTxt}，置信 ${Math.round((p.confidence || 0) * 100)}%（v${p.model_version}）`
      activeStep.value = 3
    }, 400))
  }, 400))
}

function buildChartOption() {
  if (!result.value) return {}
  const learning = result.value.learning
  const prediction = result.value.prediction
  const reference = result.value.reference

  // 实测数据
  let measured = []
  try {
    const arr = JSON.parse(cycleDataText.value || '[]')
    measured = arr
      .filter((d) => d && d.cycle != null && (d.capacity != null || d.capacity_retention != null))
      .map((d) => [d.cycle, d.capacity != null ? d.capacity : d.capacity_retention])
      .sort((a, b) => a[0] - b[0])
  } catch {
    measured = []
  }

  // 拟合曲线
  const fitted = (learning.fitted_curve || []).map((p) => [p.cycle, p.capacity])
  // 预测曲线
  const predicted = (prediction.prediction_curve || []).map((p) => [p.cycle, p.capacity])
  // 基准参考曲线
  const refCurve = reference
    ? (reference.capacity_retention_curve || []).map((p) => [p.cycle, p.capacity_retention])
    : []

  const series = [
    {
      name: '实测容量',
      type: 'scatter',
      symbolSize: 6,
      data: measured,
      itemStyle: { color: '#2050d0' },
    },
    {
      name: '拟合曲线',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: fitted,
      lineStyle: { width: 2, color: '#4070e0' },
    },
    {
      name: '预测曲线',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: predicted,
      lineStyle: { width: 2, color: '#fa8c16', type: 'dashed' },
    },
  ]
  if (refCurve.length) {
    series.push({
      name: `基准：${reference.name}`,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: refCurve,
      lineStyle: { width: 1.5, color: '#13c2c2', type: 'dotted' },
    })
  }

  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 50, right: 24, top: 40, bottom: 40 },
    xAxis: {
      type: 'value',
      name: '循环数',
      nameLocation: 'middle',
      nameGap: 28,
    },
    yAxis: {
      type: 'value',
      name: '容量保持率 (%)',
      nameLocation: 'middle',
      nameGap: 36,
      min: 0,
      max: 105,
    },
    series,
    markLine: undefined,
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  const option = buildChartOption()
  // EOL 80% 阈值线：固定附加到预测曲线系列（索引 2）
  if (option.series && option.series.length > 2) {
    option.series[2].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { color: '#ff4d4f', type: 'dashed', width: 1 },
      data: [{ yAxis: 80, label: { formatter: 'EOL 80%' } }],
    }
  }
  chart.setOption(option, true)
  chart.resize()
}

function resizeChart() {
  chart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', resizeChart)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
  loadUnitSymbols()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  resizeObserver?.disconnect()
  stepTimers.forEach(clearTimeout)
  chart?.dispose()
  chart = null
})

watch(
  () => result.value,
  () => {
    if (result.value) {
      nextTick(renderChart)
    }
  },
)
</script>

<style scoped>
.battery-life {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #1f2937);
  margin: 0 0 6px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted, #6b7280);
  margin: 0;
}

.input-card,
.steps-card,
.result-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.card-title-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
}

.form-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.parsed-hint {
  display: block;
  margin-top: 6px;
  color: var(--text-muted, #6b7280);
  font-size: 12px;
}

.decay-chart {
  width: 100%;
  height: 350px;
}

.mech-dominant,
.mech-secondary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.mech-label {
  font-size: 13px;
  color: var(--text-muted, #6b7280);
  min-width: 64px;
}

.mech-tag {
  margin: 0;
}

.mech-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mech-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 2px;
}

.mech-item-name {
  font-weight: 600;
  font-size: 13px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mech-conf {
  width: 120px;
}

.mech-item-desc {
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  line-height: 1.5;
}

.rec-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  line-height: 1.7;
}

.life-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.life-cell {
  background: var(--light-bg, #f7f8fa);
  border-radius: 6px;
  padding: 12px;
}

.life-cell-label {
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  margin-bottom: 4px;
}

.life-cell-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #1f2937);
}

.life-cell-sub {
  font-size: 11px;
  color: var(--text-muted, #6b7280);
  margin-top: 4px;
}

.fit-info {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: var(--text-muted, #6b7280);
}

.num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}
</style>
