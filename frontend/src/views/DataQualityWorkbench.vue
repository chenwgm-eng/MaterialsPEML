<template>
  <div class="dq-workbench">
    <div class="page-header">
      <div>
        <h1 class="page-title">数据质量</h1>
        <p class="page-subtitle">实验结果提交后自动触发 QC 检查，此处审核与追踪质量状态</p>
      </div>
    </div>

    <!-- 数据质量分布卡片（T-022）-->
    <a-card
      title="数据质量分布"
      size="small"
      :body-style="{ padding: '12px' }"
      class="dq-distribution-card"
    >
      <template #extra>
        <span class="dq-distribution-total">共 {{ dqStats.total }} 条</span>
        <a-button size="small" type="link" :loading="dqLoading" @click="fetchDataQualityDistribution">
          <ReloadOutlined /> 刷新
        </a-button>
      </template>
      <div class="stat-grid dq-distribution-grid">
        <a-card size="small" :bordered="false" class="stat-card dq-stat-verified">
          <a-statistic title="实测已审" :value="dqStats.verified">
            <template #suffix>
              <span class="dq-percent-suffix">{{ dqPercent('verified') }}</span>
            </template>
          </a-statistic>
        </a-card>
        <a-card size="small" :bordered="false" class="stat-card dq-stat-estimated">
          <a-statistic title="估算" :value="dqStats.estimated">
            <template #suffix>
              <span class="dq-percent-suffix">{{ dqPercent('estimated') }}</span>
            </template>
          </a-statistic>
        </a-card>
        <a-card size="small" :bordered="false" class="stat-card dq-stat-simulated">
          <a-statistic title="模拟" :value="dqStats.simulated">
            <template #suffix>
              <span class="dq-percent-suffix">{{ dqPercent('simulated') }}</span>
            </template>
          </a-statistic>
        </a-card>
        <a-card size="small" :bordered="false" class="stat-card dq-stat-literature">
          <a-statistic title="文献" :value="dqStats.literature">
            <template #suffix>
              <span class="dq-percent-suffix">{{ dqPercent('literature') }}</span>
            </template>
          </a-statistic>
        </a-card>
      </div>
    </a-card>

    <!-- 质量问题帕累托分析：按问题类型频次降序，叠加累计占比 -->
    <a-card
      title="质量问题帕累托分析"
      size="small"
      :body-style="{ padding: '12px' }"
      class="dq-pareto-card"
    >
      <template #extra>
        <span class="dq-distribution-total">共 {{ paretoDataSetTotal }} 项问题</span>
      </template>
      <ResultChart
        v-if="paretoData.length > 0"
        type="pareto"
        :data="paretoData"
        title=""
        :height="280"
      />
      <EmptyState v-else type="data" description="暂无质量问题记录可供分析" />
    </a-card>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <a-card size="small" :bordered="false" class="stat-card stat-pending">
        <a-statistic title="待检查" :value="stats.pending" />
      </a-card>
      <a-card size="small" :bordered="false" class="stat-card stat-review">
        <a-statistic title="需审核" :value="stats.requires_review" />
      </a-card>
      <a-card size="small" :bordered="false" class="stat-card stat-valid">
        <a-statistic title="有效" :value="stats.valid" />
      </a-card>
      <a-card size="small" :bordered="false" class="stat-card stat-rejected">
        <a-statistic title="已拒绝/无效" :value="stats.rejected" />
      </a-card>
    </div>

    <a-card title="QC 审核队列" size="small" :body-style="{ padding: '12px' }">
      <template #extra>
        <a-space>
          <a-select
            v-model:value="statusFilter"
            size="small"
            style="width: 140px"
            placeholder="状态筛选"
            allow-clear
            @change="fetchPending"
          >
            <a-select-option value="">全部</a-select-option>
            <a-select-option value="PENDING">待检</a-select-option>
            <a-select-option value="REQUIRES_REVIEW">复核中</a-select-option>
            <a-select-option value="VALID">有效</a-select-option>
            <a-select-option value="INVALID">无效</a-select-option>
            <a-select-option value="REJECTED">已拒绝</a-select-option>
          </a-select>
          <a-button size="small" @click="fetchPending">
            <ReloadOutlined /> 刷新
          </a-button>
        </a-space>
      </template>

      <!-- 审核流程说明 -->
      <a-steps :current="1" size="small" class="qc-flow-steps">
        <a-step title="提交" description="实验工作台录入结果，自动触发 QC 引擎初筛" />
        <a-step title="人工复核" description="需审核的记录由审核员确认有效或拒绝" />
        <a-step title="拒绝回路" description="被拒绝的记录返回实验工作台修改重提" />
        <a-step title="归档学习" description="有效且可学习的数据进入 ECML 训练库" />
      </a-steps>

      <!-- 审核人设置 -->
      <div class="reviewer-bar">
        <span class="reviewer-label">当前审核人：</span>
        <a-input v-model:value="reviewerName" size="small" style="width: 160px" placeholder="请输入审核人姓名" aria-label="审核人姓名" />
        <a-tooltip title="审核人姓名会记录到每条 QC 审核结果中，作为审核痕迹">
          <InfoCircleOutlined class="reviewer-tip" aria-label="审核人说明" />
        </a-tooltip>
      </div>

      <a-table
        v-if="records.length > 0 || loading"
        :columns="columns"
        :data-source="records"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.result_id"
        :loading="loading"
        :scroll="{ y: 500 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'result_id'">
            <router-link :to="{ path: '/experiments', query: { order_id: record.experiment_order_id } }" class="link-primary">
              {{ record.result_id }}
            </router-link>
          </template>
          <template v-if="column.key === 'experiment_order'">
            <router-link
              v-if="record.experiment_order"
              :to="{ path: '/experiment-workbench', query: record.experiment_order.order_id ? { order_id: record.experiment_order.order_id } : {} }"
              class="link-primary"
            >
              {{ record.experiment_order.order_id }}
            </router-link>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'sample'">
            <template v-if="record.sample">
              <router-link
                :to="{ path: '/samples', query: record.sample.sample_id ? { sample_id: record.sample.sample_id } : {} }"
                class="link-primary"
              >
                {{ record.sample.name || record.sample.sample_id }}
              </router-link>
              <a-tag :color="sampleStatusColor(record.sample.status)" class="sample-status-tag">
                {{ sampleStatusLabel(record.sample.status) }}
              </a-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'qc_status'">
            <a-tag :color="qcColor(record.qc_status)">{{ qcLabel(record.qc_status) }}</a-tag>
          </template>
          <template v-if="column.key === 'qc_issues'">
            <div v-if="record.qc_issues && record.qc_issues.length" class="qc-issues-cell">
              <a-tag v-if="hasDeviationIssue(record)" color="#ef4444">预测偏差</a-tag>
              <a-tooltip :title="record.qc_issues.join('；')">
                <a-tag color="#f59e0b">{{ record.qc_issues.length }} 项问题</a-tag>
              </a-tooltip>
            </div>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'deviation_analysis'">
            <a-tooltip v-if="getDeviationAnalysis(record)" :title="getDeviationAnalysis(record)">
              <span class="deviation-analysis-text">{{ getDeviationAnalysis(record) }}</span>
            </a-tooltip>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-button
                v-if="record.qc_status === 'PENDING'"
                type="link"
                size="small"
                @click="onTriggerQC(record)"
              >重新检查</a-button>
              <a-button
                v-if="record.qc_status === 'REQUIRES_REVIEW' || record.qc_status === 'PENDING'"
                type="link"
                size="small"
                @click="onApproveQC(record)"
              >确认有效</a-button>
              <a-button
                v-if="record.qc_status !== 'REJECTED' && record.qc_status !== 'INVALID'"
                type="link"
                size="small"
                danger
                @click="onRejectQC(record)"
              >拒绝</a-button>
            </a-space>
          </template>
          <template v-if="column.key === 'reviewed_by'">
            <span v-if="record.reviewed_by" class="reviewer-name">{{ record.reviewed_by }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </template>
      </a-table>
      <EmptyState
        v-else
        type="create"
        description="暂无待 QC 检查的实验数据。QC 检查在实验工作台录入数据后自动触发，请先到「实验工作台」录入实验结果。"
        action-text="前往实验工作台"
        @action="router.push('/experiment-workbench')"
      />
    </a-card>

    <!-- 拒绝原因模态框 -->
    <a-modal
      v-model:open="rejectModalVisible"
      title="拒绝 QC 数据"
      :confirm-loading="rejectSubmitting"
      @ok="confirmReject"
      @cancel="cancelReject"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="拒绝原因（必填）" required>
          <a-textarea
            v-model:value="rejectReason"
            :rows="3"
            placeholder="请说明拒绝原因，例如：测试条件异常、数据偏离过大、仪器校准问题等"
          />
        </a-form-item>
        <a-form-item label="是否允许重新提交">
          <a-switch v-model:checked="allowResubmit" />
          <span class="form-hint-inline">允许后，实验工作台可修改此结果并重新提交 QC</span>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import {
  triggerQC,
  listExperimentResults,
} from '@/api/experiments'
import { approveQCResult, rejectQCResult } from '@/api/approvals'
import { getDashboardDataQuality } from '@/api/dashboard'
import ScientificNotation from '@/components/ScientificNotation.vue'
import EmptyState from '@/components/EmptyState.vue'
import ResultChart from '@/components/ResultChart.vue'

const router = useRouter()

const loading = ref(false)
const allRecords = ref([])
const statusFilter = ref('PENDING')

// 数据质量分布（T-022）
const dqLoading = ref(false)
const dqStats = ref({ verified: 0, estimated: 0, simulated: 0, literature: 0, total: 0 })

// 审核人姓名：从 sessionStorage 持久化，避免每次刷新都要重填
const _REVIEWER_KEY = 'battery_qc_reviewer_name'
const reviewerName = ref(sessionStorage.getItem(_REVIEWER_KEY) || '')
function persistReviewer(val) {
  sessionStorage.setItem(_REVIEWER_KEY, val)
}

// 拒绝原因模态框
const rejectModalVisible = ref(false)
const rejectSubmitting = ref(false)
const rejectReason = ref('')
const allowResubmit = ref(true)
const rejectTarget = ref(null)

const records = computed(() => {
  if (!statusFilter.value) return allRecords.value
  return allRecords.value.filter((r) => r.qc_status === statusFilter.value)
})

const columns = [
  { title: '结果 ID', dataIndex: 'result_id', key: 'result_id', width: 140, className: 'tabular-nums' },
  { title: '样品 ID', dataIndex: 'sample_id', key: 'sample_id', width: 100 },
  { title: '属性', dataIndex: 'property_name', key: 'property_name', width: 120 },
  { title: '数值', dataIndex: 'value', key: 'value', width: 80, className: 'tabular-nums', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 60 },
  { title: 'QC 状态', key: 'qc_status', width: 100 },
  { title: '问题', key: 'qc_issues', width: 140 },
  { title: '偏差分析', key: 'deviation_analysis', width: 200, ellipsis: true },
  { title: '审核人', dataIndex: 'reviewed_by', key: 'reviewed_by', width: 100 },
  { title: '操作', key: 'actions', width: 180 },
]

const stats = computed(() => {
  const s = { pending: 0, requires_review: 0, valid: 0, rejected: 0 }
  allRecords.value.forEach((r) => {
    if (r.qc_status === 'PENDING') s.pending++
    else if (r.qc_status === 'REQUIRES_REVIEW') s.requires_review++
    else if (r.qc_status === 'VALID' || r.qc_status === 'VALID_WITH_WARNING') s.valid++
    else if (r.qc_status === 'REJECTED' || r.qc_status === 'INVALID') s.rejected++
  })
  return s
})

// 帕累托分析：按问题类型聚合频次（降序），并计算累计占比
const paretoData = computed(() => {
  const counts = {}
  allRecords.value.forEach((r) => {
    if (!Array.isArray(r.qc_issues)) return
    r.qc_issues.forEach((issue) => {
      if (typeof issue !== 'string' || !issue) return
      // 「交叉验证分析: xxx」为一类长文本，归并为同一类
      const key = issue.startsWith('交叉验证分析: ') ? '交叉验证分析' : issue
      counts[key] = (counts[key] || 0) + 1
    })
  })
  const items = Object.entries(counts).map(([x, y]) => ({ x, y }))
  items.sort((a, b) => b.y - a.y)
  const total = items.reduce((sum, it) => sum + it.y, 0)
  let acc = 0
  return items.map((it) => {
    acc += it.y
    return { x: it.x, y: it.y, cumulative: total ? Math.round((acc / total) * 100) : 0 }
  })
})
// 问题项总数（用于帕累托卡片副标题）
const paretoDataSetTotal = computed(() => paretoData.value.reduce((s, it) => s + it.y, 0))

function qcColor(status) {
  const map = {
    PENDING: '#f59e0b',
    VALID: '#10b981',
    VALID_WITH_WARNING: '#10b981',
    INVALID: '#ef4444',
    REQUIRES_REVIEW: '#f59e0b',
    REJECTED: '#ef4444',
  }
  return map[status] || '#64748b'
}

function qcLabel(status) {
  const map = {
    PENDING: '待检',
    VALID: '有效',
    VALID_WITH_WARNING: '有效(警告)',
    INVALID: '无效',
    REQUIRES_REVIEW: '复核中',
    REJECTED: '已拒绝',
  }
  return map[status] || status
}

function hasDeviationIssue(record) {
  return Array.isArray(record.qc_issues) && record.qc_issues.includes('预测偏差异常')
}

function getDeviationAnalysis(record) {
  if (!Array.isArray(record.qc_issues)) return ''
  for (const issue of record.qc_issues) {
    if (typeof issue === 'string' && issue.startsWith('交叉验证分析: ')) {
      return issue.substring('交叉验证分析: '.length)
    }
  }
  return ''
}

function sampleStatusColor(status) {
  const map = {
    created: '#64748b',
    in_storage: '#3b82f6',
    in_use: 'processing',
    consumed: '#f59e0b',
    discarded: '#ef4444',
  }
  return map[status] || '#64748b'
}

function sampleStatusLabel(status) {
  const map = {
    created: '已创建',
    in_storage: '在库',
    in_use: '使用中',
    consumed: '已消耗',
    discarded: '已废弃',
  }
  return map[status] || status
}

async function fetchPending() {
  loading.value = true
  try {
    // 加载全量记录，前端按 statusFilter 筛选显示，stats 基于全量计算
    allRecords.value = await listExperimentResults()
  } catch {
    allRecords.value = []
  } finally {
    loading.value = false
  }
}

// 数据质量分布占比
function dqPercent(key) {
  const total = dqStats.value.total
  if (!total) return '0%'
  return `${Math.round((dqStats.value[key] / total) * 100)}%`
}

async function fetchDataQualityDistribution() {
  dqLoading.value = true
  try {
    const data = await getDashboardDataQuality()
    const dist = { verified: 0, estimated: 0, simulated: 0, literature: 0 }
    for (const item of data.distribution || []) {
      if (item.data_quality in dist) dist[item.data_quality] = item.count
    }
    dqStats.value = { ...dist, total: data.total || 0 }
  } catch {
    // 错误由拦截器处理
  } finally {
    dqLoading.value = false
  }
}

async function onTriggerQC(record) {
  try {
    const result = await triggerQC(record.result_id)
    message.success(`QC 检查完成：${qcLabel(result.qc_status)}`)
    await fetchPending()
  } catch {
    // 错误由拦截器处理
  }
}

async function onApproveQC(record) {
  if (!reviewerName.value.trim()) {
    message.warning('请先在"当前审核人"输入框填写姓名')
    return
  }
  persistReviewer(reviewerName.value.trim())
  try {
    await approveQCResult(record.result_id, {
      reviewed_by: reviewerName.value.trim(),
      learning_eligible: true,
    })
    message.success('QC 审核通过')
    await fetchPending()
  } catch {
    // 错误由拦截器处理
  }
}

function onRejectQC(record) {
  if (!reviewerName.value.trim()) {
    message.warning('请先在"当前审核人"输入框填写姓名')
    return
  }
  rejectTarget.value = record
  rejectReason.value = ''
  allowResubmit.value = true
  rejectModalVisible.value = true
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    message.warning('请填写拒绝原因')
    return
  }
  persistReviewer(reviewerName.value.trim())
  rejectSubmitting.value = true
  try {
    await rejectQCResult(rejectTarget.value.result_id, {
      reviewed_by: reviewerName.value.trim(),
      learning_eligible: false,
      reason: rejectReason.value.trim(),
    })
    message.success(`已拒绝（原因：${rejectReason.value}）`)
    rejectModalVisible.value = false
    await fetchPending()
  } catch {
    // 错误由拦截器处理
  } finally {
    rejectSubmitting.value = false
  }
}

function cancelReject() {
  rejectModalVisible.value = false
  rejectTarget.value = null
  rejectReason.value = ''
}

onMounted(() => {
  fetchPending()
  fetchDataQualityDistribution()
})
</script>

<style scoped>
.dq-workbench {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  border-radius: var(--radius-md);
  background: var(--light-bg-card);
  border: 1px solid var(--border);
}

.stat-pending :deep(.ant-statistic-content) { color: var(--warning); }
.stat-review :deep(.ant-statistic-content) { color: var(--warning); }
.stat-valid :deep(.ant-statistic-content) { color: var(--success); }
.stat-rejected :deep(.ant-statistic-content) { color: var(--error); }

/* T-022：数据质量分布卡片 */
.dq-distribution-card {
  margin-bottom: 16px;
}

.dq-distribution-grid {
  margin-bottom: 0;
}

.dq-distribution-total {
  font-size: 13px;
  color: var(--text-muted);
  margin-right: 8px;
}

/* 帕累托分析卡片 */
.dq-pareto-card {
  margin-bottom: 16px;
}

.dq-stat-verified :deep(.ant-statistic-content) { color: var(--success); }
.dq-stat-estimated :deep(.ant-statistic-content) { color: var(--info); }
.dq-stat-simulated :deep(.ant-statistic-content) { color: var(--warning); }
.dq-stat-literature :deep(.ant-statistic-content) { color: #722ed1; }

.dq-percent-suffix {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 4px;
  font-weight: normal;
}

.text-muted {
  color: var(--text-muted);
}

.empty-hint {
  color: var(--text-muted);
  font-size: 13px;
  margin: 8px 0 16px;
}

.qc-flow-steps {
  margin-bottom: 8px;
  padding: 6px 8px;
  background: var(--light-bg, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: var(--radius-md, 6px);
}

.qc-flow-steps :deep(.ant-steps-item) {
  padding: 0 4px;
}

.qc-flow-steps :deep(.ant-steps-item-title) {
  font-size: 12px;
}

.qc-flow-steps :deep(.ant-steps-item-description) {
  font-size: 11px !important;
  line-height: 1.4 !important;
}

.reviewer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
}

.reviewer-label {
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
}

.reviewer-tip {
  color: var(--text-muted);
  cursor: help;
}

.reviewer-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
}

.form-hint-inline {
  margin-left: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.qc-issues-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.deviation-analysis-text {
  font-size: 12px;
  color: var(--text-secondary, #595959);
  cursor: help;
}

.link-primary {
  color: var(--primary);
  text-decoration: none;
}

.link-primary:hover {
  text-decoration: underline;
}

.sample-status-tag {
  margin-left: 4px;
}
</style>
