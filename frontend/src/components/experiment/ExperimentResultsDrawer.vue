<template>
  <!-- 任务结果查看抽屉 -->
  <a-drawer
    :open="open"
    :title="`任务 ${order?.order_id || '—'} 的实验结果`"
    placement="right"
    width="900px"
    :destroy-on-close="true"
    @update:open="(v) => emit('update:open', v)"
  >
    <a-tabs v-model:activeKey="resultsActiveTab" size="small" class="results-tabs">
      <!-- Tab 1：实验结果（物料消耗 + 实验结果表格） -->
      <a-tab-pane key="results" tab="实验结果">
        <!-- 物料消耗清单 -->
        <div v-if="order?.material_requirements?.length" class="material-section">
          <div class="material-section-title">物料消耗清单</div>
          <a-table
            :columns="materialColumns"
            :data-source="order.material_requirements"
            :pagination="false"
            size="small"
            :row-key="(r, idx) => r.material_id || idx"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'stock_status'">
                <a-tag :color="(record.inventory_kg || 0) >= (record.required_quantity_kg || 0) ? '#10b981' : '#ef4444'">
                  {{ (record.inventory_kg || 0) >= (record.required_quantity_kg || 0) ? '充足' : '不足' }}
                </a-tag>
              </template>
            </template>
          </a-table>
          <a-divider style="margin: 12px 0" />
        </div>
        <div class="results-toolbar">
          <a-space>
            <a-button type="primary" size="small" @click="onOpenDeviation">
              <SearchOutlined /> 检测偏差
            </a-button>
            <span v-if="deviationSummary" class="deviation-summary-text">{{ deviationSummary }}</span>
          </a-space>
        </div>
        <a-table
          :columns="resultColumns"
          :data-source="orderResults"
          :loading="resultsLoading"
          :pagination="{ pageSize: 8, size: 'small' }"
          size="small"
          :row-key="(r) => r.result_id"
          :scroll="{ y: 520 }"
          :row-class-name="(record) => isAnomalyRecord(record) ? 'anomaly-row' : ''"
          :expandable="deviationExpandable"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'qc_status'">
              <a-tooltip v-if="record.qc_rule_results?.length" :title="`规则版本 ${record.qc_rule_version || '-'}`">
                <a-tag :color="qcStatusColor(record.qc_status)">{{ qcStatusLabel(record.qc_status) }}</a-tag>
                <a-badge :count="record.qc_rule_results.filter(r => !r.passed).length"
                         :number-style="{ backgroundColor: qcSeverityColor(record.qc_severity) }"
                         style="margin-left: 4px" />
              </a-tooltip>
              <a-tag v-else :color="qcStatusColor(record.qc_status)">{{ qcStatusLabel(record.qc_status) }}</a-tag>
            </template>
            <template v-if="column.key === 'deviation'">
              <a-tag v-if="isAnomalyRecord(record)" color="#ef4444">预测偏差</a-tag>
              <span v-else-if="deviationMap[record.result_id]" class="text-muted">
                {{ deviationMap[record.result_id].deviation_pct }}%
              </span>
              <span v-else class="text-muted">—</span>
            </template>
          </template>
          <template #expandedRowRender="{ record }">
            <div class="deviation-detail">
              <!-- Task 12.6：QC 规则可解释详情 -->
              <div v-if="record.qc_rule_results?.length" class="deviation-detail-block">
                <div class="deviation-subtitle">
                  QC 规则详情
                  <a-tag color="blue" style="margin-left: 8px">规则版本 {{ record.qc_rule_version || '-' }}</a-tag>
                </div>
                <a-descriptions :column="2" size="small" bordered style="margin-bottom: 8px">
                  <a-descriptions-item label="主规则名称">{{ record.qc_primary_rule_name || record.qc_primary_rule_id || '-' }}</a-descriptions-item>
                  <a-descriptions-item label="主规则严重度">
                    <a-tag :color="qcSeverityColor(record.qc_severity)">{{ qcSeverityLabel(record.qc_severity) }}</a-tag>
                  </a-descriptions-item>
                  <a-descriptions-item label="决策路径" :span="2">
                    <code class="decision-path-code">{{ record.qc_decision_path || '-' }}</code>
                  </a-descriptions-item>
                  <a-descriptions-item label="置信度">{{ ((record.qc_confidence || 0) * 100).toFixed(0) }}%</a-descriptions-item>
                  <a-descriptions-item label="建议动作">{{ record.qc_suggested_action || '-' }}</a-descriptions-item>
                </a-descriptions>
                <a-table
                  :columns="qcRuleColumns"
                  :data-source="record.qc_rule_results"
                  :pagination="false"
                  size="small"
                  :row-key="(r) => r.rule_id"
                  :row-class-name="(r) => r.passed ? 'qc-rule-passed' : 'qc-rule-failed'"
                >
                  <template #bodyCell="{ column, record: rule }">
                    <template v-if="column.key === 'severity'">
                      <a-tag :color="qcSeverityColor(rule.severity)">{{ qcSeverityLabel(rule.severity) }}</a-tag>
                    </template>
                    <template v-if="column.key === 'passed'">
                      <a-tag :color="rule.passed ? '#10b981' : '#ef4444'">{{ rule.passed ? '通过' : '失败' }}</a-tag>
                    </template>
                    <template v-if="column.key === 'message'">
                      <span v-if="rule.message">{{ rule.message }}</span>
                      <span v-else class="text-muted">—</span>
                    </template>
                    <template v-if="column.key === 'suggested_action'">
                      <span v-if="rule.suggested_action">{{ rule.suggested_action }}</span>
                      <span v-else class="text-muted">—</span>
                    </template>
                  </template>
                </a-table>
              </div>
              <div v-if="deviationMap[record.result_id]" class="deviation-detail-block">
                <div class="deviation-subtitle">偏差详情</div>
                <a-descriptions :column="3" size="small" bordered>
                  <a-descriptions-item label="属性">{{ deviationMap[record.result_id].property_name }}</a-descriptions-item>
                  <a-descriptions-item label="预测值">{{ deviationMap[record.result_id].predicted }} {{ deviationMap[record.result_id].unit || '' }}</a-descriptions-item>
                  <a-descriptions-item label="实测值">{{ deviationMap[record.result_id].measured }} {{ deviationMap[record.result_id].unit || '' }}</a-descriptions-item>
                  <a-descriptions-item label="偏差" :span="3">
                    <a-tag color="#ef4444">{{ deviationMap[record.result_id].deviation_pct }}%</a-tag>
                  </a-descriptions-item>
                </a-descriptions>
              </div>
              <div v-if="anomalyAnalysis" class="deviation-detail-block">
                <div class="deviation-subtitle">交叉验证分析</div>
                <a-alert :message="anomalyAnalysis.summary" type="warning" show-icon style="margin-bottom: 8px" />
                <div v-for="(cause, idx) in anomalyAnalysis.causes" :key="idx" class="cause-item">
                  <a-tag color="#f59e0b">{{ cause.cause }}</a-tag>
                  <span class="cause-desc">{{ cause.description }}</span>
                  <span class="cause-conf">置信度 {{ (cause.confidence * 100).toFixed(0) }}%</span>
                </div>
                <div v-if="anomalyAnalysis.recommendations?.length" class="recommendations">
                  <b>建议：</b>
                  <ul>
                    <li v-for="(rec, idx) in anomalyAnalysis.recommendations" :key="idx">{{ rec }}</li>
                  </ul>
                </div>
              </div>
            </div>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- Tab 2：分析简报 -->
      <a-tab-pane key="analysis" tab="分析简报">
        <EmptyState
          v-if="!analysisBrief?.analysis"
          type="data"
          description="该任务单暂无分析简报，将在 QC 通过后自动生成"
        />
        <div v-else class="analysis-brief-section">
          <div class="analysis-section-title">分析简报</div>
          <a-alert :message="analysisBrief.analysis?.summary" type="info" show-icon style="margin-bottom: 12px" />
          <div v-if="analysisBrief.analysis?.statistics" class="analysis-stat-grid">
            <a-card size="small" class="stat-card">
              <a-statistic title="均值" :value="analysisBrief.analysis.statistics.mean" :precision="4" />
            </a-card>
            <a-card size="small" class="stat-card">
              <a-statistic title="标准差" :value="analysisBrief.analysis.statistics.std" :precision="4" />
            </a-card>
            <a-card size="small" class="stat-card">
              <a-statistic title="样本数" :value="analysisBrief.analysis.statistics.sample_count" />
            </a-card>
            <a-card size="small" class="stat-card">
              <div class="stat-label">趋势</div>
              <a-tag :color="trendColor(analysisBrief.analysis.statistics.trend)">
                {{ analysisBrief.analysis.statistics.trend }}
              </a-tag>
              <div class="stat-extra" v-if="analysisBrief.analysis.statistics.property_name">
                属性：{{ analysisBrief.analysis.statistics.property_name }}
              </div>
            </a-card>
          </div>
          <a-row :gutter="16" style="margin-top: 8px">
            <a-col :sm="12" v-if="analysisBrief.analysis?.anomalies?.length">
              <div class="analysis-subtitle">异常点（{{ analysisBrief.analysis.anomalies.length }}）</div>
              <a-list :data-source="analysisBrief.analysis.anomalies" size="small" :split="false" bordered>
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-tag color="#ef4444">{{ item.result_id }}</a-tag>
                    <span class="text-muted">值 {{ item.value }}，{{ item.reason }}</span>
                  </a-list-item>
                </template>
              </a-list>
            </a-col>
            <a-col :sm="12" v-if="analysisBrief.analysis?.recommendations?.length">
              <div class="analysis-subtitle">建议</div>
              <a-list :data-source="analysisBrief.analysis.recommendations" size="small" :split="false" bordered>
                <template #renderItem="{ item }">
                  <a-list-item>{{ item }}</a-list-item>
                </template>
              </a-list>
            </a-col>
          </a-row>
        </div>
      </a-tab-pane>

      <!-- Tab 3：委员会评审结论 -->
      <a-tab-pane key="committee" tab="委员会评审">
        <a-spin v-if="committeeLoading" tip="加载委员会数据..." />
        <EmptyState
          v-else-if="!committeeVerdict"
          type="data"
          description="暂无委员会评审结论"
        />
        <div v-else class="committee-section">
          <div class="committee-section-title">
            <AuditOutlined /> 委员会评审结论
          </div>
          <a-card size="small" class="committee-verdict-card">
            <div class="committee-verdict-header">
              <span class="committee-verdict-label">评审结果：</span>
              <a-tag :color="committeeDecisionColor(committeeVerdict.decision)">
                {{ committeeDecisionLabel(committeeVerdict.decision) }}
              </a-tag>
              <span class="committee-verdict-type">{{ committeeTypeLabel(committeeVerdict.committee_type) }}</span>
            </div>
            <!-- Scorecard -->
            <div v-if="committeeVerdict.scorecardList?.length" class="committee-detail-block">
              <div class="committee-subtitle">评分维度</div>
              <a-row :gutter="8">
                <a-col :span="8" v-for="dim in committeeVerdict.scorecardList" :key="dim.dimension">
                  <a-card size="small" class="scorecard-dim-card">
                    <div class="scorecard-dim-label">{{ dim.dimension }}</div>
                    <div class="scorecard-dim-score">{{ dim.score }}</div>
                  </a-card>
                </a-col>
              </a-row>
            </div>
            <!-- Blocking reasons -->
            <div v-if="committeeVerdict.blocking_reasons?.length" class="committee-detail-block">
              <div class="committee-subtitle blocking-title">
                <ExclamationCircleOutlined /> 阻断原因
              </div>
              <a-list :data-source="committeeVerdict.blocking_reasons" size="small" :split="false">
                <template #renderItem="{ item, idx }">
                  <a-list-item :key="idx">
                    <span>{{ item }}</span>
                  </a-list-item>
                </template>
              </a-list>
            </div>
            <!-- Warnings -->
            <div v-if="committeeVerdict.warnings?.length" class="committee-detail-block">
              <div class="committee-subtitle warning-title">警告</div>
              <a-list :data-source="committeeVerdict.warnings" size="small" :split="false">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-tag color="#f59e0b">{{ item }}</a-tag>
                  </a-list-item>
                </template>
              </a-list>
            </div>
          </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab 4：偏差复盘 -->
      <a-tab-pane key="deviation" tab="偏差复盘">
        <a-spin v-if="committeeLoading" tip="加载委员会数据..." />
        <EmptyState
          v-else-if="!deviationReview"
          type="data"
          description="暂无偏差复盘记录"
        />
        <div v-else class="committee-section">
          <div class="committee-section-title">
            <AuditOutlined /> 偏差复盘
          </div>
          <a-card size="small" class="deviation-review-card">
            <!-- 数据质量评估 -->
            <div v-if="deviationReview.data_quality_assessment" class="committee-detail-block">
              <div class="committee-subtitle">数据质量评估</div>
              <a-alert :message="deviationReview.data_quality_assessment" type="info" show-icon />
            </div>
            <!-- 可能原因 -->
            <div v-if="deviationReview.possible_causes?.length" class="committee-detail-block">
              <div class="committee-subtitle">可能原因</div>
              <a-space wrap>
                <a-tag v-for="cause in deviationReview.possible_causes" :key="cause.category" :color="causeCategoryColor(cause.category)">
                  {{ cause.category }}：{{ cause.description }}
                </a-tag>
              </a-space>
            </div>
            <!-- 建议行动 -->
            <div v-if="deviationReview.recommended_actions?.length" class="committee-detail-block">
              <div class="committee-subtitle">建议行动</div>
              <a-list :data-source="deviationReview.recommended_actions" size="small" :split="false">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-tag :color="actionColor(item.action)">{{ item.action }}</a-tag>
                    <span>{{ item.description }}</span>
                  </a-list-item>
                </template>
              </a-list>
            </div>
            <!-- 下一轮反馈动作 -->
            <div v-if="deviationReview.feedback_actions?.length" class="committee-detail-block">
              <div class="committee-subtitle">下一轮反馈动作</div>
              <a-list :data-source="deviationReview.feedback_actions" size="small" :split="false">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-tag :color="actionColor(item.action_type)">{{ item.action_type }}</a-tag>
                    <span>{{ item.description }}</span>
                  </a-list-item>
                </template>
              </a-list>
            </div>
          </a-card>
        </div>
      </a-tab-pane>
    </a-tabs>

    <!-- 偏差检测抽屉 -->
    <a-drawer
      :open="showDeviationModal"
      :title="`偏差检测 - 任务 ${order?.order_id || '—'}`"
      placement="right"
      width="860px"
      :destroy-on-close="true"
      @update:open="(v) => (showDeviationModal = v)"
    >
      <a-alert
        type="info"
        show-icon
        message="输入预测值（JSON 格式），系统将对比实测值计算偏差并标记异常样本"
        style="margin-bottom: 12px"
      />
      <div class="deviation-split">
        <!-- 左侧：JSON 输入 + 阈值 + 检测按钮 -->
        <div class="deviation-input-pane">
          <div class="deviation-pane-label">预测值输入</div>
          <a-textarea
            v-model:value="predictedValuesText"
            :rows="8"
            placeholder='例如：{"ionic_conductivity": 1.5e-4, "discharge_capacity_mAh_g": 120}'
            class="deviation-json-input"
          />
          <div class="deviation-threshold-row">
            <span>偏差阈值：</span>
            <a-input-number v-model:value="deviationThreshold" :min="0.01" :max="1" :step="0.05" size="small" style="width: 90px" />
            <span class="deviation-threshold-pct">{{ (deviationThreshold * 100).toFixed(0) }}%</span>
            <a-button type="primary" size="small" :loading="deviationLoading" @click="onCheckDeviation">
              <SearchOutlined /> 检测偏差
            </a-button>
          </div>
        </div>
        <!-- 右侧：检测结果展示 -->
        <div class="deviation-result-pane">
          <div class="deviation-pane-label">检测结果</div>
          <EmptyState
            v-if="!deviationSummary"
            type="data"
            description="暂无检测结果，请点击「检测偏差」"
          />
          <template v-else>
            <a-alert
              :message="deviationSummary"
              :type="anomalyList.length ? 'warning' : 'success'"
              show-icon
              style="margin-bottom: 8px"
            />
            <div v-if="anomalyList.length" class="deviation-anomaly-list">
              <div class="deviation-anomaly-title">异常样本（{{ anomalyList.length }}）</div>
              <div v-for="(a, idx) in anomalyList" :key="idx" class="deviation-anomaly-item">
                <span class="deviation-anomaly-id">{{ a.result_id }}</span>
                <span class="deviation-anomaly-prop">{{ a.property_name }}</span>
                <span class="deviation-anomaly-pct tabular-nums">{{ a.deviation_pct }}%</span>
              </div>
              <a-button type="primary" size="small" :loading="markingAnomalies" @click="onMarkAnomalies" style="margin-top: 8px">
                <FlagOutlined /> 标记异常 + 交叉验证分析
              </a-button>
            </div>
          </template>
        </div>
      </div>
    </a-drawer>
  </a-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { SearchOutlined, FlagOutlined, ExclamationCircleOutlined, AuditOutlined } from '@ant-design/icons-vue'
import { listExperimentResults, checkDeviation, markAnomalies, getExperimentAnalysis } from '@/api/experiments'
import { getCommitteeCases, getCommitteeCase, getFeedbackActions } from '@/api/committees'
import { qcStatusLabel, qcStatusColor } from '@/utils/enumLabels'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  order: { type: Object, default: null },
  // 单位符号（由父组件从 MDM 加载后传入，避免重复加载）
  massUnit: { type: String, default: 'kg' },
})

const emit = defineEmits(['update:open', 'refresh-orders'])

const resultsActiveTab = ref('results')
const orderResults = ref([])
const resultsLoading = ref(false)
const analysisBrief = ref(null)

// 偏差检测状态
const showDeviationModal = ref(false)
const predictedValuesText = ref('')
const deviationThreshold = ref(0.2)
const deviationLoading = ref(false)
const deviationMap = ref({})
const anomalyList = ref([])
const deviationSummary = ref('')
const anomalyAnalysis = ref(null)
const markingAnomalies = ref(false)

// 委员会评审结论 & 偏差复盘
const committeeVerdict = ref(null)
const deviationReview = ref(null)
const committeeLoading = ref(false)

const deviationExpandable = computed(() => ({
  rowExpandable: (record) =>
    !!deviationMap.value[record.result_id]?.is_anomaly ||
    (Array.isArray(record.qc_rule_results) && record.qc_rule_results.length > 0),
}))

function isAnomalyRecord(record) {
  return !!deviationMap.value[record.result_id]?.is_anomaly
}

// 当 order 变化时拉取结果数据
watch(
  () => props.order?.order_id,
  (orderId) => {
    if (!orderId || !props.open) return
    fetchResults(props.order)
  },
  { immediate: true }
)

// 当抽屉打开且无 order 时重置状态
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      deviationMap.value = {}
      anomalyList.value = []
      deviationSummary.value = ''
      anomalyAnalysis.value = null
      analysisBrief.value = null
      committeeVerdict.value = null
      deviationReview.value = null
    }
  }
)

async function fetchResults(record) {
  resultsActiveTab.value = 'results'
  resultsLoading.value = true
  // 重置偏差检测状态
  deviationMap.value = {}
  anomalyList.value = []
  deviationSummary.value = ''
  anomalyAnalysis.value = null
  analysisBrief.value = null
  committeeVerdict.value = null
  deviationReview.value = null
  try {
    orderResults.value = await listExperimentResults({ order_id: record.order_id })
  } catch {
    orderResults.value = []
  } finally {
    resultsLoading.value = false
  }
  // 拉取分析简报（404 表示暂无，静默处理）
  try {
    analysisBrief.value = await getExperimentAnalysis(record.order_id)
  } catch {
    analysisBrief.value = null
  }
  // 拉取委员会评审结论 & 偏差复盘
  fetchCommitteeData(record)
}

async function fetchCommitteeData(record) {
  committeeLoading.value = true
  try {
    const candidateId = record.candidate_id
    const orderId = record.order_id
    const res = await getCommitteeCases({ limit: 100 })
    const allCases = res.cases || res || []
    const caseList = allCases.filter((c) =>
      c.candidate_id === candidateId || (orderId && c.case_id?.includes(orderId))
    )
    // 查找实验立项（experimental_readiness）类型的评审结论
    const verdictCase = caseList.find(
      (c) => c.committee_type === 'experimental_readiness'
    )
    if (verdictCase) {
      try {
        const detail = await getCommitteeCase(verdictCase.case_id)
        committeeVerdict.value = detail.verdict || null
        if (committeeVerdict.value && detail.case?.committee_type) {
          committeeVerdict.value.committee_type = detail.case.committee_type
        }
        if (committeeVerdict.value?.scorecard && typeof committeeVerdict.value.scorecard === 'object') {
          committeeVerdict.value.scorecardList = Object.entries(committeeVerdict.value.scorecard).map(
            ([dimension, score]) => ({ dimension, score })
          )
        }
      } catch {
        committeeVerdict.value = null
      }
    }
    // 查找偏差复盘（deviation_review）类型的案件
    const reviewCase = caseList.find(
      (c) => c.committee_type === 'deviation_review'
    )
    if (reviewCase) {
      const reviewData = { ...reviewCase }
      try {
        const faRes = await getFeedbackActions(reviewCase.case_id)
        reviewData.feedback_actions = faRes.feedback_actions || []
      } catch {
        reviewData.feedback_actions = []
      }
      deviationReview.value = reviewData
    }
  } catch {
    committeeVerdict.value = null
    deviationReview.value = null
  } finally {
    committeeLoading.value = false
  }
}

function onOpenDeviation() {
  if (!orderResults.value.length) {
    message.warning('暂无实验结果，无法检测偏差')
    return
  }
  const props = [...new Set(orderResults.value.map((r) => r.property_name).filter(Boolean))]
  const template = props.reduce((acc, p) => {
    acc[p] = 0
    return acc
  }, {})
  predictedValuesText.value = JSON.stringify(template, null, 2)
  showDeviationModal.value = true
}

function validatePredictedValues(jsonStr) {
  try {
    const parsed = JSON.parse(jsonStr)
    if (typeof parsed !== 'object' || parsed === null) {
      return { valid: false, error: '请输入有效的JSON对象' }
    }
    return { valid: true, data: parsed }
  } catch (e) {
    return { valid: false, error: 'JSON格式错误：' + e.message }
  }
}

async function onCheckDeviation() {
  if (!props.order?.order_id) {
    message.warning('未选择任务')
    return
  }
  const validation = validatePredictedValues(predictedValuesText.value || '{}')
  if (!validation.valid) {
    message.error(validation.error)
    return
  }
  const predictedValues = validation.data
  if (!Object.keys(predictedValues).length) {
    message.warning('请输入至少一个预测值')
    return
  }
  deviationLoading.value = true
  try {
    const res = await checkDeviation({
      order_id: props.order.order_id,
      predicted_values: predictedValues,
      threshold: deviationThreshold.value,
    })
    const map = {}
    for (const d of res.deviations || []) {
      map[d.result_id] = d
    }
    deviationMap.value = map
    anomalyList.value = (res.deviations || []).filter((d) => d.is_anomaly)
    deviationSummary.value = `共检测 ${res.total_checked} 条，异常 ${res.anomaly_count} 条（阈值 ${(res.threshold * 100).toFixed(0)}%）`
    anomalyAnalysis.value = null
    if (res.anomaly_count > 0) {
      message.warning(`检测到 ${res.anomaly_count} 个异常样本`)
    } else {
      message.success('未检测到异常样本')
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    deviationLoading.value = false
  }
}

async function onMarkAnomalies() {
  if (!anomalyList.value.length) {
    message.warning('无异常样本可标记')
    return
  }
  markingAnomalies.value = true
  try {
    const res = await markAnomalies({ anomalies: anomalyList.value })
    anomalyAnalysis.value = res.analysis
    message.success(`已标记 ${res.marked} 个异常样本，交叉验证分析完成`)
    // 刷新结果列表以反映 QC 状态更新
    if (props.order?.order_id) {
      orderResults.value = await listExperimentResults({ order_id: props.order.order_id })
    }
    // 通知父组件刷新任务列表（result_count 可能变化）
    emit('refresh-orders')
  } catch {
    // 错误由拦截器处理
  } finally {
    markingAnomalies.value = false
  }
}

// ---- 列定义 ----
const resultColumns = [
  { title: '结果 ID', dataIndex: 'result_id', key: 'result_id', width: 110, className: 'tabular-nums' },
  { title: '样品', dataIndex: 'sample_id', key: 'sample_id', width: 90 },
  { title: '属性', dataIndex: 'property_name', key: 'property_name', width: 140 },
  { title: '数值', key: 'value', width: 100, className: 'tabular-nums', customRender: ({ record }) => `${record.value} ${record.unit || ''}` },
  { title: 'QC 状态', key: 'qc_status', width: 110 },
  { title: '偏差', key: 'deviation', width: 120, className: 'tabular-nums' },
  { title: '录入人', dataIndex: 'uploaded_by', key: 'uploaded_by', width: 90 },
]

const qcRuleColumns = [
  { title: '规则名称', key: 'rule_name', width: 220, customRender: ({ record }) => record.rule_name || record.rule_id },
  { title: '类别', dataIndex: 'rule_category', key: 'rule_category', width: 110 },
  { title: '严重度', key: 'severity', width: 90 },
  { title: '结果', key: 'passed', width: 80 },
  { title: '说明', key: 'message' },
  { title: '建议动作', key: 'suggested_action', width: 200 },
  { title: '字段', dataIndex: 'field_name', key: 'field_name', width: 120 },
  { title: '期望值', dataIndex: 'expected_value', key: 'expected_value', width: 120, className: 'tabular-nums' },
  { title: '实际值', dataIndex: 'actual_value', key: 'actual_value', width: 120, className: 'tabular-nums' },
  { title: '置信度', key: 'confidence', width: 80, className: 'tabular-nums', customRender: ({ record }) => `${(record.confidence * 100).toFixed(0)}%` },
]

const materialColumns = computed(() => [
  { title: '物料名称', dataIndex: 'name', key: 'name', width: 140 },
  { title: '规格', dataIndex: 'category', key: 'category', width: 90 },
  { title: `所需数量(${props.massUnit})`, dataIndex: 'required_quantity_kg', key: 'required_quantity_kg', width: 110, className: 'tabular-nums' },
  { title: `库存量(${props.massUnit})`, dataIndex: 'inventory_kg', key: 'inventory_kg', width: 110, className: 'tabular-nums' },
  { title: '库存状态', key: 'stock_status', width: 90 },
  { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 120 },
])

// ---- 辅助函数 ----
function qcSeverityColor(severity) {
  const map = { info: '#3b82f6', warning: 'gold', error: '#ef4444', critical: '#dc2626' }
  return map[severity] || '#64748b'
}

function qcSeverityLabel(severity) {
  const map = { info: '信息', warning: '警告', error: '错误', critical: '严重' }
  return map[severity] || severity || '-'
}

function trendColor(trend) {
  const map = { '上升': '#10b981', '下降': '#ef4444', '稳定': '#3b82f6' }
  return map[trend] || '#64748b'
}

function committeeDecisionColor(decision) {
  const map = { pass: '#10b981', reject: '#ef4444', request_evidence: 'gold', human_review: 'volcano' }
  return map[decision] || '#64748b'
}

function committeeDecisionLabel(decision) {
  const map = { pass: '通过', reject: '拒绝', request_evidence: '补证据', human_review: '人工复核' }
  return map[decision] || decision
}

function committeeTypeLabel(type) {
  const map = { crystal_construction: '晶体构建', experimental_readiness: '实验立项', candidate_priority: '候选优先级', deviation_review: '偏差复盘', external_evidence: '外部证据采纳' }
  return map[type] || type
}

function causeCategoryColor(category) {
  const map = { '数据质量': '#ef4444', '模型适用域': '#f59e0b', '工艺偏差': '#3b82f6', '新机理信号': '#06b6d4' }
  return map[category] || '#64748b'
}

function actionColor(action) {
  const map = { '补测': '#3b82f6', '复验': '#f59e0b', '模型更新': '#06b6d4', '策略调整': 'geekblue' }
  return map[action] || '#64748b'
}
</script>

<style scoped>
.material-section {
  margin-bottom: 4px;
}

.material-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 8px;
}

.results-toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.deviation-summary-text {
  font-size: 12px;
  color: var(--text-muted);
}

.text-muted {
  color: var(--text-muted);
}

:deep(.anomaly-row) {
  background: var(--error-bg) !important;
}

:deep(.anomaly-row:hover > td) {
  background: var(--error-bg) !important;
}

.deviation-detail {
  padding: 8px 12px;
  background: var(--light-bg, #fafafa);
}

.deviation-detail-block {
  margin-bottom: 12px;
}

.deviation-detail-block:last-child {
  margin-bottom: 0;
}

.deviation-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 8px;
}

.decision-path-code {
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  background: var(--light-bg, #f5f5f5);
  padding: 2px 6px;
  border-radius: 3px;
  color: var(--text-primary, #1a1a2e);
  word-break: break-all;
}

:deep(.qc-rule-failed) {
  background: var(--error-bg) !important;
}

:deep(.qc-rule-passed) {
  background: var(--success-bg) !important;
}

.cause-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.cause-desc {
  flex: 1;
  color: var(--text-secondary, #595959);
}

.cause-conf {
  color: var(--text-muted);
  font-size: 11px;
}

.recommendations {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary, #595959);
}

.recommendations ul {
  margin: 4px 0 0;
  padding-left: 18px;
}

.analysis-brief-section {
  margin-top: 8px;
}

.analysis-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 8px;
}

.analysis-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 4px;
}

.analysis-stat-grid .stat-card {
  text-align: center;
}

.analysis-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 6px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary, #595959);
  margin-bottom: 4px;
}

.stat-extra {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.deviation-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.deviation-input-pane,
.deviation-result-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.deviation-pane-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 8px;
}

.deviation-json-input {
  flex: 1;
  font-family: var(--font-family-mono, monospace);
  font-size: 12px;
}

.deviation-threshold-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}

.deviation-threshold-pct {
  color: var(--text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.deviation-result-pane {
  background: var(--light-bg, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: var(--radius-md, 6px);
  padding: 12px;
}

.deviation-anomaly-list {
  margin-top: 4px;
}

.deviation-anomaly-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 6px;
}

.deviation-anomaly-item {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border, #e8e8e8);
}

.deviation-anomaly-item:last-child {
  border-bottom: none;
}

.deviation-anomaly-id {
  color: var(--text-primary, #1a1a2e);
  font-weight: 500;
}

.deviation-anomaly-prop {
  color: var(--text-secondary, #595959);
}

.deviation-anomaly-pct {
  color: #ef4444;
  font-weight: 600;
}
</style>
