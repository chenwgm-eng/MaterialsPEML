<template>
  <div class="release-card-center" :class="{ 'embedded-mode': embedded }">
    <!-- 治理指标条 -->
    <div class="metrics-row">
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--primary-bg); color: var(--primary)">
          <AuditOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ formatRate(metrics.decision_coverage) }}</div>
          <div class="metric-label">决策覆盖率</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--success-bg); color: var(--success)">
          <CheckCircleOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ formatRate(metrics.evidence_completeness) }}</div>
          <div class="metric-label">证据完备率</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--warning-bg); color: var(--warning)">
          <UserSwitchOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ formatRate(metrics.human_review_hit_rate) }}</div>
          <div class="metric-label">人工复核命中率</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--info-bg); color: var(--info)">
          <ClockCircleOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ formatLatency(metrics.decision_latency) }}</div>
          <div class="metric-label">裁决时效</div>
        </div>
      </div>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="filters.status"
          placeholder="状态"
          allow-clear
          style="width: 120px"
          size="small"
          :options="statusOptions"
        />
        <a-select
          v-model:value="filters.recommendation"
          placeholder="推荐结论"
          allow-clear
          style="width: 130px"
          size="small"
          :options="recommendationOptions"
        />
        <a-input
          v-model:value="filters.keyword"
          placeholder="关键词（卡号 / 标题 / Case ID）"
          allow-clear
          style="width: 200px"
          size="small"
        />
        <a-button size="small" type="primary" @click="fetchCards" :loading="loading">
          <SearchOutlined /> 查询
        </a-button>
        <a-button size="small" @click="resetFilters">
          <FilterOutlined /> 重置
        </a-button>
        <a-button size="small" @click="fetchAll" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button size="small" type="primary" ghost @click="openGenerate">
          <FileAddOutlined /> 从委员会 Case 生成
        </a-button>
      </a-space>
    </div>

    <!-- 放行卡列表 -->
    <a-card size="small" :body-style="{ padding: '12px' }">
      <a-table
        :columns="columns"
        :data-source="filteredCards"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.card_id"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <span class="card-title-cell">{{ record.title || '-' }}</span>
          </template>
          <template v-if="column.key === 'recommendation'">
            <a-tag :color="recommendationColor(record.recommendation)">
              {{ recommendationLabel(record.recommendation) }}
            </a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'reviewer'">
            <span>{{ record.human_responsibility?.reviewer || '-' }}</span>
          </template>
          <template v-if="column.key === 'created_at'">
            <span class="tabular-nums">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-button size="small" type="link" @click="openDetail(record)">
                <EyeOutlined /> 查看详情
              </a-button>
              <a-tooltip :title="record.status !== 'pending_review' ? '仅「待审核」状态可人工复核' : '人工复核'">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    type="primary"
                    @click="openReview(record)"
                    :disabled="record.status !== 'pending_review'"
                  >
                    <EditOutlined />
                  </a-button>
                </span>
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 放行卡详情 Drawer -->
    <a-drawer
      :open="detailVisible"
      :width="820"
      :title="'放行卡详情 — ' + (detailCard?.card_id || '')"
      placement="right"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="detailCard">
          <!-- 推荐结论大字突出 -->
          <div class="rec-banner" :class="'rec-' + detailCard.recommendation">
            <div class="rec-banner-label">推荐结论</div>
            <div class="rec-banner-value">{{ recommendationLabel(detailCard.recommendation) }}</div>
            <div class="rec-banner-meta">
              <a-tag :color="statusColor(detailCard.status)">{{ statusLabel(detailCard.status) }}</a-tag>
              <span v-if="detailCard.case_id" class="rec-banner-case">关联 Case：{{ detailCard.case_id }}</span>
            </div>
          </div>

          <!-- 目标与成功窗口 -->
          <div class="section-title">目标与成功窗口</div>
          <a-descriptions v-if="hasTargetWindow" size="small" :column="1" bordered>
            <a-descriptions-item v-if="detailCard.target_window.metrics != null" label="目标指标">
              <pre class="json-block">{{ pretty(detailCard.target_window.metrics) }}</pre>
            </a-descriptions-item>
            <a-descriptions-item v-if="detailCard.target_window.success_range != null" label="成功窗口">
              <pre class="json-block">{{ pretty(detailCard.target_window.success_range) }}</pre>
            </a-descriptions-item>
            <a-descriptions-item v-if="detailCard.target_window.min_viable_outcome != null" label="最低可接受结果">
              <pre class="json-block">{{ pretty(detailCard.target_window.min_viable_outcome) }}</pre>
            </a-descriptions-item>
          </a-descriptions>
          <div v-else class="empty-line">未提供</div>

          <!-- 证据摘要（六类分区） -->
          <div class="section-title">证据摘要</div>
          <div v-for="cat in evidenceCategories" :key="cat.key" class="evidence-block">
            <div class="evidence-block-title">
              {{ cat.label }}
              <span v-if="detailCard.evidence_summary?.[cat.key]?.count != null" class="evidence-count">
                {{ detailCard.evidence_summary[cat.key].count }} 条
              </span>
            </div>
            <pre v-if="detailCard.evidence_summary?.[cat.key]" class="json-block">{{ pretty(detailCard.evidence_summary[cat.key]) }}</pre>
            <div v-else class="empty-line">未提供</div>
          </div>

          <!-- 不确定性 -->
          <div class="section-title">不确定性</div>
          <a-descriptions size="small" :column="1" bordered>
            <a-descriptions-item label="适用域">
              <template v-if="asList(detailCard.uncertainty?.applicability_domain).length">
                <ul class="plain-list">
                  <li v-for="(item, idx) in asList(detailCard.uncertainty.applicability_domain)" :key="idx">{{ item }}</li>
                </ul>
              </template>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="数据缺口">
              <template v-if="asList(detailCard.uncertainty?.data_gaps).length">
                <ul class="plain-list">
                  <li v-for="(item, idx) in asList(detailCard.uncertainty.data_gaps)" :key="idx">{{ item }}</li>
                </ul>
              </template>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="关键假设">
              <template v-if="asList(detailCard.uncertainty?.key_assumptions).length">
                <ul class="plain-list">
                  <li v-for="(item, idx) in asList(detailCard.uncertainty.key_assumptions)" :key="idx">{{ item }}</li>
                </ul>
              </template>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="潜在失败模式">
              <template v-if="asList(detailCard.uncertainty?.failure_modes).length">
                <ul class="plain-list">
                  <li v-for="(item, idx) in asList(detailCard.uncertainty.failure_modes)" :key="idx">{{ item }}</li>
                </ul>
              </template>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
          </a-descriptions>

          <!-- 推荐实验 -->
          <div class="section-title">推荐实验</div>
          <a-table
            v-if="detailCard.suggested_experiments?.length"
            :columns="experimentColumns"
            :data-source="detailCard.suggested_experiments"
            :pagination="false"
            size="small"
            :row-key="experimentRowKey"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'recipe'">
                <pre class="json-block compact">{{ pretty(record.recipe) }}</pre>
              </template>
              <template v-if="column.key === 'conditions'">
                <pre class="json-block compact">{{ pretty(record.conditions) }}</pre>
              </template>
            </template>
          </a-table>
          <div v-else class="empty-line">未提供</div>

          <!-- 停止条件 -->
          <div class="section-title">停止条件</div>
          <ul v-if="detailCard.stop_conditions?.length" class="plain-list">
            <li v-for="(item, idx) in detailCard.stop_conditions" :key="idx">{{ item }}</li>
          </ul>
          <div v-else class="empty-line">未提供</div>

          <!-- 人工责任 -->
          <div class="section-title">人工责任</div>
          <a-descriptions size="small" :column="2" bordered>
            <a-descriptions-item label="复核人">{{ detailCard.human_responsibility?.reviewer || '未复核' }}</a-descriptions-item>
            <a-descriptions-item label="最终裁决">
              <a-tag v-if="detailCard.human_responsibility?.final_decision" :color="finalDecisionColor(detailCard.human_responsibility.final_decision)">
                {{ finalDecisionLabel(detailCard.human_responsibility.final_decision) }}
              </a-tag>
              <span v-else class="text-muted">-</span>
            </a-descriptions-item>
            <a-descriptions-item label="复核意见" :span="2">{{ detailCard.human_responsibility?.review_opinion || '-' }}</a-descriptions-item>
            <a-descriptions-item label="裁决时间" :span="2">
              <span class="tabular-nums">{{ formatTime(detailCard.human_responsibility?.decided_at) }}</span>
            </a-descriptions-item>
          </a-descriptions>

          <!-- 溯源信息 -->
          <div class="section-title">溯源信息</div>
          <a-descriptions size="small" :column="1" bordered>
            <a-descriptions-item label="Case ID">{{ detailCard.provenance?.case_id || detailCard.case_id || '-' }}</a-descriptions-item>
            <a-descriptions-item label="Run ID">{{ detailCard.provenance?.run_id || '-' }}</a-descriptions-item>
            <a-descriptions-item label="模型版本">
              <pre v-if="hasKeys(detailCard.provenance?.model_versions)" class="json-block">{{ pretty(detailCard.provenance.model_versions) }}</pre>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="数据版本">
              <pre v-if="hasKeys(detailCard.provenance?.data_versions)" class="json-block">{{ pretty(detailCard.provenance.data_versions) }}</pre>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="规则版本">
              <pre v-if="hasKeys(detailCard.provenance?.rule_versions)" class="json-block">{{ pretty(detailCard.provenance.rule_versions) }}</pre>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="审计引用">
              <pre v-if="hasKeys(detailCard.provenance?.audit_refs)" class="json-block">{{ pretty(detailCard.provenance.audit_refs) }}</pre>
              <span v-else class="text-muted">未提供</span>
            </a-descriptions-item>
            <a-descriptions-item label="创建时间">{{ formatTime(detailCard.created_at) }}</a-descriptions-item>
          </a-descriptions>

          <!-- 待复核操作 -->
          <div v-if="detailCard.status === 'pending_review'" class="drawer-actions">
            <a-button type="primary" size="small" @click="openReview(detailCard)">
              <EditOutlined /> 人工复核
            </a-button>
          </div>
        </div>
        <EmptyState v-else-if="!detailLoading" type="data" :description="MESSAGES.empty" />
      </a-spin>
    </a-drawer>

    <!-- 人工复核抽屉 -->
    <a-drawer
      :open="reviewVisible"
      :title="'人工复核 — ' + (reviewTarget?.card_id || '')"
      placement="right"
      width="600px"
      @update:open="(v) => (reviewVisible = v)"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="系统推荐结论">
          <a-tag v-if="reviewTarget" :color="recommendationColor(reviewTarget.recommendation)">
            {{ recommendationLabel(reviewTarget.recommendation) }}
          </a-tag>
        </a-form-item>
        <a-form-item label="复核人" required>
          <a-input v-model:value="reviewForm.reviewer" placeholder="请输入复核人姓名" />
        </a-form-item>
        <a-form-item label="复核意见">
          <a-textarea v-model:value="reviewForm.review_opinion" :rows="3" placeholder="请输入复核意见" />
        </a-form-item>
        <a-form-item label="最终裁决" required>
          <a-select v-model:value="reviewForm.final_decision" placeholder="请选择最终裁决">
            <a-select-option value="agree">同意系统建议</a-select-option>
            <a-select-option value="modify">修改后执行</a-select-option>
            <a-select-option value="reject">拒绝</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="reviewSubmitting" @click="reviewVisible = false">取消</a-button>
          <a-button type="primary" :loading="reviewSubmitting" @click="submitReview">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 从委员会 Case 生成抽屉 -->
    <a-drawer
      :open="generateVisible"
      title="从委员会 Case 生成放行卡"
      placement="right"
      width="600px"
      @update:open="(v) => (generateVisible = v)"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="委员会 Case ID" required>
          <a-input v-model:value="generateCaseId" placeholder="请输入 Case ID（如 cmt-xxxxxxxx）" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="generateSubmitting" @click="generateVisible = false">取消</a-button>
          <a-button type="primary" :loading="generateSubmitting" @click="submitGenerate">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  AuditOutlined,
  CheckCircleOutlined,
  UserSwitchOutlined,
  ClockCircleOutlined,
  SearchOutlined,
  ReloadOutlined,
  FilterOutlined,
  EyeOutlined,
  EditOutlined,
  FileAddOutlined,
} from '@ant-design/icons-vue'
import {
  createReleaseCard,
  getReleaseCards,
  getReleaseCard,
  reviewReleaseCard,
  getReleaseCardMetrics,
} from '@/api/releaseCards'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'
import { MESSAGES } from '@/constants/glossary'

// 审查意见0726：支持嵌入到 DecisionCenter 标签页
const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['count-change'])

// --- State ---
const cards = ref([])
const loading = ref(false)
const metrics = ref({})
let isMounted = true
onUnmounted(() => { isMounted = false })

// 推荐实验表行 key：基于记录内容，避免使用弃用的 index 参数
const experimentRowKey = (r) => {
  if (!r) return Math.random().toString(36).slice(2)
  return JSON.stringify(r).slice(0, 64)
}

const filters = reactive({
  status: undefined,
  recommendation: undefined,
  keyword: '',
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailCard = ref(null)

const reviewVisible = ref(false)
const reviewSubmitting = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({
  reviewer: '',
  review_opinion: '',
  final_decision: undefined,
})

const generateVisible = ref(false)
const generateSubmitting = ref(false)
const generateCaseId = ref('')

// --- Table columns ---
const columns = [
  { title: '卡号', dataIndex: 'card_id', key: 'card_id', width: 130 },
  { title: '标题', key: 'title', ellipsis: true },
  { title: '推荐结论', key: 'recommendation', width: 100 },
  { title: '状态', key: 'status', width: 90 },
  { title: '复核人', key: 'reviewer', width: 90 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 110, fixed: 'right' },
]

const experimentColumns = [
  { title: '配方', key: 'recipe', width: 200 },
  { title: '条件', key: 'conditions', width: 200 },
  { title: '样品数', dataIndex: 'sample_count', key: 'sample_count', width: 70 },
  { title: '优先级', dataIndex: 'priority', key: 'priority', width: 70 },
  { title: '设备', dataIndex: 'equipment', key: 'equipment', width: 110 },
  { title: '预计成本', dataIndex: 'estimated_cost', key: 'estimated_cost', width: 90 },
]

// --- Label helpers ---
const evidenceCategoriesFallback = [
  { key: 'prediction', label: '预测' },
  { key: 'experiment_history', label: '实验历史' },
  { key: 'literature', label: '文献' },
  { key: 'cost', label: '成本' },
  { key: 'ehs', label: 'EHS' },
  { key: 'synthesis_feasibility', label: '合成可行性' },
]
const evidenceCategories = ref([...evidenceCategoriesFallback])

const recommendationLabelsFallback = {
  recommend: '推荐',
  conditional: '条件推荐',
  need_evidence: '需补证',
  human_review: '转人工',
  reject: '拒绝',
}
const recommendationOptions = ref(
  Object.entries(recommendationLabelsFallback).map(([value, label]) => ({ label, value })),
)
const recommendationColors = {
  recommend: 'green',
  conditional: 'blue',
  need_evidence: 'orange',
  human_review: 'purple',
  reject: 'red',
}

function recommendationLabel(r) {
  const opt = recommendationOptions.value.find((o) => o.value === r)
  return opt ? opt.label : r || '-'
}

function recommendationColor(r) {
  return recommendationColors[r] || 'default'
}

const statusLabelsFallback = {
  draft: '草稿',
  pending_review: '待复核',
  decided: '已裁决',
}
const statusOptions = ref(
  Object.entries(statusLabelsFallback).map(([value, label]) => ({ label, value })),
)
const statusColors = {
  draft: 'default',
  pending_review: 'orange',
  decided: 'green',
}

function statusLabel(s) {
  const opt = statusOptions.value.find((o) => o.value === s)
  return opt ? opt.label : s || '-'
}

function statusColor(s) {
  return statusColors[s] || 'default'
}

const finalDecisionLabels = {
  agree: '同意系统建议',
  modify: '修改后执行',
  reject: '拒绝',
}

const finalDecisionColors = {
  agree: 'green',
  modify: 'blue',
  reject: 'red',
}

function finalDecisionLabel(d) {
  return finalDecisionLabels[d] || d || '-'
}

function finalDecisionColor(d) {
  return finalDecisionColors[d] || 'default'
}

// --- Formatting ---
const formatTime = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

const formatRate = (m) => {
  if (!m || m.value == null) return MESSAGES.empty
  return (m.value * 100).toFixed(0) + '%'
}

const formatLatency = (m) => {
  if (!m || m.value == null) return MESSAGES.empty
  const seconds = m.value
  if (seconds < 60) return `${seconds.toFixed(0)} 秒`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} 分钟`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} 小时`
  return `${(seconds / 86400).toFixed(1)} 天`
}

const pretty = (v) => {
  if (v == null) return '-'
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

const asList = (v) => {
  if (v == null) return []
  return Array.isArray(v) ? v : [v]
}

const hasKeys = (v) => v && typeof v === 'object' && Object.keys(v).length > 0

// --- Computed ---
const filteredCards = computed(() => {
  const kw = (filters.keyword || '').trim().toLowerCase()
  if (!kw) return cards.value
  return cards.value.filter((c) =>
    (c.card_id || '').toLowerCase().includes(kw) ||
    (c.title || '').toLowerCase().includes(kw) ||
    (c.case_id || '').toLowerCase().includes(kw),
  )
})

const hasTargetWindow = computed(() => {
  const tw = detailCard.value?.target_window
  return hasKeys(tw)
})

// --- API calls ---
async function fetchCards() {
  loading.value = true
  try {
    const params = {}
    if (filters.status) params.status = filters.status
    if (filters.recommendation) params.recommendation = filters.recommendation
    const res = await getReleaseCards(params)
    if (!isMounted) return
    cards.value = res.items || []
    // 审查意见0726：向上 emit 待复核数量
    const pendingCount = cards.value.filter(c => ['pending_review', 'pending', 'hold'].includes(c.status)).length
    emit('count-change', pendingCount)
  } catch {
    if (isMounted) cards.value = []
    emit('count-change', 0)
  } finally {
    if (isMounted) loading.value = false
  }
}

async function fetchMetrics() {
  try {
    const res = await getReleaseCardMetrics()
    metrics.value = res || {}
  } catch {
    metrics.value = {}
  }
}

function fetchAll() {
  fetchCards()
  fetchMetrics()
}

async function openDetail(record) {
  detailCard.value = null
  detailVisible.value = true
  detailLoading.value = true
  try {
    const res = await getReleaseCard(record.card_id)
    if (!isMounted) return
    detailCard.value = res
  } catch {
    if (isMounted) detailCard.value = null
  } finally {
    if (isMounted) detailLoading.value = false
  }
}

function openReview(record) {
  reviewTarget.value = record
  reviewForm.reviewer = record.human_responsibility?.reviewer || ''
  reviewForm.review_opinion = record.human_responsibility?.review_opinion || ''
  reviewForm.final_decision = undefined
  reviewVisible.value = true
}

async function submitReview() {
  if (!reviewForm.reviewer.trim()) {
    message.warning('请填写复核人')
    return
  }
  if (!reviewForm.final_decision) {
    message.warning('请选择最终裁决')
    return
  }
  reviewSubmitting.value = true
  try {
    await reviewReleaseCard(reviewTarget.value.card_id, {
      reviewer: reviewForm.reviewer.trim(),
      review_opinion: reviewForm.review_opinion,
      final_decision: reviewForm.final_decision,
    })
    if (!isMounted) return
    message.success('复核已提交')
    reviewVisible.value = false
    await fetchCards()
    fetchMetrics()
    if (detailVisible.value && detailCard.value?.card_id === reviewTarget.value.card_id) {
      await openDetail(reviewTarget.value)
    }
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) reviewSubmitting.value = false
  }
}

function openGenerate() {
  generateCaseId.value = ''
  generateVisible.value = true
}

async function submitGenerate() {
  const caseId = generateCaseId.value.trim()
  if (!caseId) {
    message.warning('请输入委员会 Case ID')
    return
  }
  generateSubmitting.value = true
  try {
    const res = await createReleaseCard({ case_id: caseId })
    message.success(`放行卡已生成：${res.card_id}`)
    generateVisible.value = false
    await fetchCards()
    fetchMetrics()
    if (res.card_id) {
      await openDetail(res)
    }
  } catch {
    // handled by interceptor
  } finally {
    generateSubmitting.value = false
  }
}

function resetFilters() {
  filters.status = undefined
  filters.recommendation = undefined
  filters.keyword = ''
  fetchCards()
}

// --- Lifecycle ---
onMounted(async () => {
  const { statusOptions: mdmStatusOptions, dimensionOptions } = useMdmDict()
  let hasFallback = false

  try {
    const loadedStatus = await mdmStatusOptions('release_card')
    statusOptions.value = loadedStatus.length ? loadedStatus : Object.entries(statusLabelsFallback).map(([value, label]) => ({ label, value }))
    if (!loadedStatus.length) hasFallback = true
  } catch (e) {
    statusOptions.value = Object.entries(statusLabelsFallback).map(([value, label]) => ({ label, value }))
    hasFallback = true
  }

  try {
    const loadedRecommendation = await dimensionOptions('recommendation')
    recommendationOptions.value = loadedRecommendation.length ? loadedRecommendation : Object.entries(recommendationLabelsFallback).map(([value, label]) => ({ label, value }))
    if (!loadedRecommendation.length) hasFallback = true
  } catch (e) {
    recommendationOptions.value = Object.entries(recommendationLabelsFallback).map(([value, label]) => ({ label, value }))
    hasFallback = true
  }

  try {
    const loadedEvidence = await dimensionOptions('evidence_category')
    evidenceCategories.value = loadedEvidence.length
      ? loadedEvidence.map((o) => ({ key: o.value, label: o.label }))
      : [...evidenceCategoriesFallback]
    if (!loadedEvidence.length) hasFallback = true
  } catch (e) {
    evidenceCategories.value = [...evidenceCategoriesFallback]
    hasFallback = true
  }

  if (hasFallback) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }

  fetchAll()
})
</script>

<style scoped>
.release-card-center {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

/* 嵌入模式：去除自身外边距，由父容器统一布局 */
.release-card-center.embedded-mode {
  background: transparent;
  box-shadow: none;
  border: none;
  padding: 0;
}

/* Metrics Row */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: box-shadow var(--transition), border-color var(--transition);
}

.metric-card:hover {
  box-shadow: var(--shadow-hover);
  border-color: var(--primary-border);
}

.metric-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.metric-body {
  flex: 1;
  min-width: 0;
}

.metric-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Filter Bar */
.filter-bar {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  margin-bottom: 16px;
}

/* Recommendation Banner */
.rec-banner {
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid var(--border-light);
}

.rec-banner-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.rec-banner-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 8px;
}

.rec-banner-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rec-banner-case {
  font-size: 12px;
  color: var(--text-secondary);
}

.rec-recommend { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.3); }
.rec-recommend .rec-banner-value { color: var(--success); }
.rec-conditional { background: rgba(249, 115, 22, 0.06); border-color: rgba(249, 115, 22, 0.3); }
.rec-conditional .rec-banner-value { color: var(--primary); }
.rec-need_evidence { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.3); }
.rec-need_evidence .rec-banner-value { color: var(--warning); }
.rec-human_review { background: rgba(139, 92, 246, 0.08); border-color: rgba(139, 92, 246, 0.3); }
.rec-human_review .rec-banner-value { color: #8b5cf6; }
.rec-reject { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.3); }
.rec-reject .rec-banner-value { color: var(--error); }

/* Sections */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 16px 0 8px;
}

.evidence-block {
  margin-bottom: 8px;
}

.evidence-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.evidence-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 6px;
}

.json-block {
  margin: 0;
  padding: 8px 12px;
  background: var(--light-bg-hover);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 220px;
  overflow: auto;
}

.json-block.compact {
  max-height: 120px;
  padding: 4px 8px;
}

.plain-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

.empty-line {
  font-size: 13px;
  color: var(--text-muted);
  padding: 4px 0;
}

.card-title-cell {
  font-size: 13px;
  color: var(--text-primary);
}

.drawer-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* Misc */
.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}

/* Responsive */
@media (max-width: 1024px) {
  .metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }
}
</style>
