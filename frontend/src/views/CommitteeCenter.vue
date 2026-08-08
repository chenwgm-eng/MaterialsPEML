<template>
  <div class="committee-center" :class="{ 'embedded-mode': embedded }">
    <!-- Summary Metrics Cards -->
    <div class="metrics-row">
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--primary-bg); color: var(--primary)">
          <AuditOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ metrics.total_cases }}</div>
          <div class="metric-label">总案件数</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--success-bg); color: var(--success)">
          <CheckCircleOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ metrics.pass_rate != null ? (metrics.pass_rate * 100).toFixed(0) + '%' : '-' }}</div>
          <div class="metric-label">通过率</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--error-bg); color: var(--error)">
          <CloseCircleOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ metrics.reject_rate != null ? (metrics.reject_rate * 100).toFixed(0) + '%' : '-' }}</div>
          <div class="metric-label">拒绝率</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--warning-bg); color: var(--warning)">
          <UserSwitchOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ metrics.human_escalation_rate != null ? (metrics.human_escalation_rate * 100).toFixed(0) + '%' : '-' }}</div>
          <div class="metric-label">人工复核</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon" style="background: var(--info-bg); color: var(--info)">
          <SearchOutlined />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ metrics.avg_evidence_rounds != null ? metrics.avg_evidence_rounds : 'N/A' }}</div>
          <div class="metric-label">平均证据轮次</div>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="filters.committee_type"
          placeholder="委员会类型"
          allow-clear
          style="width: 160px"
          size="small"
          :options="committeeTypeOptions"
        />
        <a-select
          v-model:value="filters.status"
          placeholder="状态"
          allow-clear
          style="width: 140px"
          size="small"
          :options="caseStatusOptions"
        />
        <a-select
          v-model:value="filters.risk_level"
          placeholder="风险等级"
          allow-clear
          style="width: 120px"
          size="small"
        >
          <a-select-option value="low">低</a-select-option>
          <a-select-option value="medium">中</a-select-option>
          <a-select-option value="high">高</a-select-option>
          <a-select-option value="critical">严重</a-select-option>
        </a-select>
        <a-select
          v-model:value="filters.project_id"
          placeholder="项目"
          allow-clear
          style="width: 140px"
          size="small"
        >
          <a-select-option v-for="pid in projectIds" :key="pid" :value="pid">{{ pid }}</a-select-option>
        </a-select>
        <a-button size="small" type="primary" @click="fetchCases" :loading="loading">
          <SearchOutlined /> 查询
        </a-button>
        <a-button size="small" @click="resetFilters">
          <FilterOutlined /> 重置
        </a-button>
        <a-button size="small" @click="fetchCases" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
      </a-space>
    </div>

    <!-- Case Table -->
    <a-card size="small" :body-style="{ padding: '12px' }">
      <a-table
        :columns="columns"
        :data-source="cases"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.case_id"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'committee_type'">
            <span>{{ committeeTypeLabel(record.committee_type) }}</span>
          </template>
          <template v-if="column.key === 'risk_level'">
            <a-tag :color="riskLevelColor(record.risk_level)">{{ record.risk_level }}</a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'qc_status'">
            <a-tag v-if="record.qc_status" :color="qcStatusColor(record.qc_status)">{{ qcStatusLabel(record.qc_status) }}</a-tag>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-if="column.key === 'created_at'">
            <span class="tabular-nums">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-button size="small" type="link" @click="openDetail(record)">
                <EyeOutlined /> 查看详情
              </a-button>
              <a-tooltip :title="runTooltip(record)">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    type="primary"
                    @click="runCase(record)"
                    :loading="runningId === record.case_id"
                    :disabled="!canRun(record.status)"
                  >
                    <PlayCircleOutlined />
                  </a-button>
                </span>
              </a-tooltip>
              <a-tooltip :title="cancelTooltip(record)">
                <span class="tt-btn-wrap">
                  <a-popconfirm
                    title="确认取消该委员会案件？取消后无法恢复。"
                    ok-text="确认取消"
                    cancel-text="保留"
                    @confirm="cancelCase(record)"
                    :disabled="!canCancel(record.status)"
                  >
                    <a-button
                      size="small"
                      danger
                      :loading="cancellingId === record.case_id"
                      :disabled="!canCancel(record.status)"
                    >
                      <StopOutlined />
                    </a-button>
                  </a-popconfirm>
                </span>
              </a-tooltip>
            </a-space>
          </template>
        </template>
        <template #expandedRowRender="{ record }">
          <div v-if="record.qc_issues && record.qc_issues.length" class="qc-issues-detail">
            <div v-for="(issue, idx) in record.qc_issues" :key="idx" class="qc-issue-item">
              <a-tag v-if="issue.rule_id" color="blue">{{ issue.rule_id }}</a-tag>
              <a-tag v-if="issue.severity" :color="qcSeverityColor(issue.severity)">{{ issue.severity }}</a-tag>
              <span v-if="issue.rule_category" class="qc-rule-category">分类：{{ issue.rule_category }}</span>
              <span v-if="issue.suggested_action" class="qc-suggested-action">建议：{{ issue.suggested_action }}</span>
              <span v-if="issue.message" class="qc-message">{{ issue.message }}</span>
            </div>
          </div>
          <span v-else class="text-muted">无 QC 详情</span>
        </template>
      </a-table>
    </a-card>

    <!-- Metrics Panel -->
    <a-card size="small" :body-style="{ padding: '12px' }">
      <div class="card-title-row" @click="metricsExpanded = !metricsExpanded" style="cursor: pointer">
        <span class="card-title-text">委员会指标</span>
        <a-button size="small" type="link">{{ metricsExpanded ? '收起' : '展开' }}</a-button>
      </div>
      <div v-if="metricsExpanded" class="metrics-panel">
        <a-spin :spinning="metricsLoading">
          <div class="metrics-grid">
            <div class="metrics-item">
              <div class="metrics-item-label">触发次数</div>
              <div class="metrics-item-value">{{ committeeMetrics.total_cases != null ? committeeMetrics.total_cases : '-' }}</div>
            </div>
            <div class="metrics-item">
              <div class="metrics-item-label">通过率</div>
              <div class="metrics-item-value">{{ committeeMetrics.pass_rate != null ? (committeeMetrics.pass_rate * 100).toFixed(0) + '%' : '-' }}</div>
            </div>
            <div class="metrics-item">
              <div class="metrics-item-label">拒绝率</div>
              <div class="metrics-item-value">{{ committeeMetrics.reject_rate != null ? (committeeMetrics.reject_rate * 100).toFixed(0) + '%' : '-' }}</div>
            </div>
            <div class="metrics-item">
              <div class="metrics-item-label">平均证据轮次</div>
              <div class="metrics-item-value">{{ committeeMetrics.avg_evidence_rounds != null ? committeeMetrics.avg_evidence_rounds : 'N/A' }}</div>
            </div>
            <div class="metrics-item">
              <div class="metrics-item-label">平均延迟</div>
              <div class="metrics-item-value">{{ committeeMetrics.latency_avg_ms != null ? committeeMetrics.latency_avg_ms + 'ms' : '-' }}</div>
            </div>
            <div class="metrics-item">
              <div class="metrics-item-label">P95 延迟</div>
              <div class="metrics-item-value">{{ committeeMetrics.p95_latency_ms != null ? committeeMetrics.p95_latency_ms + 'ms' : 'N/A' }}</div>
            </div>
          </div>
        </a-spin>
      </div>
    </a-card>

    <!-- Case Detail Drawer -->
    <a-drawer
      :open="detailVisible"
      :title="'案件详情 — ' + (detailCase?.case_id || '')"
      placement="right"
      width="780px"
      :footer="null"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-spin :spinning="detailLoading">
        <a-tabs v-if="detailCase" v-model:activeKey="detailTab">
          <a-tab-pane key="overview" tab="概览">
            <a-descriptions size="small" :column="2" bordered>
              <a-descriptions-item label="案件 ID">{{ detailCase.case_id }}</a-descriptions-item>
              <a-descriptions-item label="委员会类型">{{ committeeTypeLabel(detailCase.committee_type) }}</a-descriptions-item>
              <a-descriptions-item label="项目 ID">{{ detailCase.project_id || '-' }}</a-descriptions-item>
              <a-descriptions-item label="风险等级">
                <a-tag :color="riskLevelColor(detailCase.risk_level)">{{ detailCase.risk_level }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="状态">
                <a-tag :color="statusColor(detailCase.status)">{{ statusLabel(detailCase.status) }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="当前步骤">{{ detailCase.current_step || '-' }}</a-descriptions-item>
              <a-descriptions-item label="触发代码" :span="2">
                <code class="trigger-code">{{ detailCase.trigger_code }}</code>
              </a-descriptions-item>
              <a-descriptions-item label="创建时间" :span="2">{{ formatTime(detailCase.created_at) }}</a-descriptions-item>
            </a-descriptions>
            <a-alert
              v-if="detailCase.verdict && ['pass', 'reject'].includes(detailCase.status)"
              type="success"
              show-icon
              style="margin-top: 12px"
              message="案件综合摘要"
              :description="caseSummary()"
            />
            <a-alert
              v-if="detailCase.status === 'pending'"
              type="info"
              show-icon
              style="margin-top: 12px"
              message="案件尚未执行"
              description="点击列表中的「执行」按钮启动委员会评估，系统将依次生成提案、收集证据并得出裁决。"
            />
            <a-alert
              v-else-if="detailCase.status === 'failed'"
              type="error"
              show-icon
              style="margin-top: 12px"
              message="案件执行失败"
              description="评估过程中发生错误，请查看事件日志了解详情，必要时可重新创建案件。"
            />
            <!-- 人工审核区：当案件处于 human_review 状态时，允许人工放行/拒绝 -->
            <div v-if="detailCase.status === 'human_review'" class="manual-review-block">
              <a-divider style="margin: 12px 0" />
              <div class="review-title">
                <UserSwitchOutlined /> 人工复核 — 请做出决策
              </div>
              <a-alert
                type="warning"
                show-icon
                style="margin-bottom: 12px"
                message="该案件需要人工复核"
                description="委员会评估已完成但未自动裁决，请审核提案与证据后做出决策。"
              />
              <a-textarea
                v-model:value="reviewComment"
                placeholder="审核意见（可选）"
                :rows="2"
                style="margin-bottom: 12px"
              />
              <a-space>
                <a-button type="primary" :loading="reviewing" @click="submitReview('approve')">
                  <CheckCircleOutlined /> 通过（放行）
                </a-button>
                <a-button danger :loading="reviewing" @click="submitReview('reject')">
                  <CloseCircleOutlined /> 拒绝
                </a-button>
                <a-button :loading="reviewing" @click="submitReview('request_evidence')">
                  <SearchOutlined /> 需补证据
                </a-button>
              </a-space>
            </div>
            <!-- 执行中状态提示 -->
            <a-alert
              v-else-if="['thinking', 'executing_evidence', 'verifying'].includes(detailCase.status)"
              type="info"
              show-icon
              style="margin-top: 12px"
              message="案件执行中"
              description="委员会正在评估中，请稍候刷新查看最新状态。"
            />
          </a-tab-pane>
          <a-tab-pane key="proposal" tab="提案">
            <div v-if="detailCase.proposal" class="tab-content">
              <h4 class="tab-section-title">假设</h4>
              <p class="tab-text">{{ detailCase.proposal.assumptions || '-' }}</p>
              <h4 class="tab-section-title">请求证据</h4>
              <ul v-if="detailCase.proposal.requested_evidence?.length" class="evidence-list">
                <li v-for="(item, idx) in detailCase.proposal.requested_evidence" :key="idx">{{ item }}</li>
              </ul>
              <span v-else class="text-muted">-</span>
            </div>
            <EmptyState v-else type="data" description="暂无提案数据" />
          </a-tab-pane>
          <a-tab-pane key="evidence" tab="证据">
            <div v-if="detailCase.evidence?.length" class="tab-content">
              <div v-for="(item, idx) in detailCase.evidence" :key="idx" class="evidence-item">
                <div class="evidence-header">
                  <span class="evidence-field"><span class="field-label">来源类型：</span><a-tag>{{ item.source_type }}</a-tag></span>
                  <span class="evidence-field"><span class="field-label">来源：</span><span class="evidence-source">{{ item.source_name }}</span></span>
                  <span class="evidence-field"><span class="field-label">能力：</span><a-tag size="small" color="blue">{{ item.capability || '-' }}</a-tag></span>
                  <span class="evidence-field"><span class="field-label">状态：</span><a-tag :color="evidenceStatusColor(item.status)">{{ evidenceStatusLabel(item.status) }}</a-tag></span>
                </div>
                <div class="evidence-confidence" v-if="item.confidence != null">
                  <span class="field-label">置信度：</span>{{ (item.confidence * 100).toFixed(0) }}%
                </div>
                <div class="evidence-value" v-if="item.value && Object.keys(item.value).length">
                  <div class="field-label">数值：</div>
                  <pre class="value-pre">{{ formatJson(item.value) }}</pre>
                </div>
              </div>
            </div>
            <EmptyState v-else type="data" description="暂无证据数据" />
          </a-tab-pane>
          <a-tab-pane key="verdict" tab="裁决">
            <div v-if="detailCase.verdict" class="tab-content">
              <h4 class="tab-section-title">计分卡</h4>
              <div v-if="detailCase.verdict.scorecard" class="scorecard">
                <div v-for="(val, key) in detailCase.verdict.scorecard" :key="key" class="scorecard-row">
                  <span class="scorecard-key">{{ key }}</span>
                  <span class="scorecard-val">{{ val }}</span>
                </div>
              </div>
              <span v-else class="text-muted">-</span>
              <h4 class="tab-section-title">阻断原因</h4>
              <ul v-if="detailCase.verdict.blocking_reasons?.length" class="evidence-list">
                <li v-for="(r, idx) in detailCase.verdict.blocking_reasons" :key="idx">{{ r }}</li>
              </ul>
              <span v-else class="text-muted">-</span>
              <h4 class="tab-section-title">警告</h4>
              <ul v-if="detailCase.verdict.warnings?.length" class="evidence-list">
                <li v-for="(w, idx) in detailCase.verdict.warnings" :key="idx">{{ w }}</li>
              </ul>
              <span v-else class="text-muted">-</span>
              <h4 class="tab-section-title">必要行动</h4>
              <ul v-if="detailCase.verdict.required_actions?.length" class="evidence-list">
                <li v-for="(a, idx) in detailCase.verdict.required_actions" :key="idx">{{ a }}</li>
              </ul>
              <span v-else class="text-muted">-</span>
              <h4 class="tab-section-title">决策</h4>
              <a-tag v-if="detailCase.verdict.decision" :color="statusColor(detailCase.verdict.decision)">
                {{ statusLabel(detailCase.verdict.decision) }}
              </a-tag>
              <span v-else class="text-muted">-</span>
            </div>
            <EmptyState v-else type="data" description="暂无裁决数据" />
          </a-tab-pane>
          <a-tab-pane key="events" tab="事件">
            <div v-if="detailCase.events?.length" class="tab-content">
              <div class="event-timeline">
                <div v-for="(evt, idx) in detailCase.events" :key="idx" class="event-item">
                  <div class="event-dot" :class="'dot-' + (eventColors[evt.event_type] || 'default')"></div>
                  <div class="event-body">
                    <div class="event-header">
                      <span class="event-type">{{ eventTypeLabel(evt.event_type) }}</span>
                      <span class="event-time">时间：{{ formatTime(evt.timestamp) }}</span>
                    </div>
                    <div class="event-detail" v-if="evt.data || evt.detail">
                      <template v-if="isPlainObject(evt.data || evt.detail)">
                        <div v-for="(val, key) in (evt.data || evt.detail)" :key="key" class="event-detail-row">
                          <span class="event-detail-key">{{ key }}：</span>
                          <span class="event-detail-val">{{ val }}</span>
                        </div>
                      </template>
                      <template v-else>{{ evt.data || evt.detail }}</template>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <EmptyState v-else type="data" description="暂无事件数据" />
          </a-tab-pane>
        </a-tabs>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import {
  AuditOutlined,
  SearchOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  UserSwitchOutlined,
  EyeOutlined,
  StopOutlined,
  ReloadOutlined,
  FilterOutlined,
} from '@ant-design/icons-vue'
import {
  getCommitteeCases,
  getCommitteeCase,
  runCommitteeCase,
  cancelCommitteeCase,
  reviewCommitteeCase,
  getCommitteeMetrics,
} from '@/api/committees'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'

// 从 MDM 加载委员会类型/案件状态选项（失败时使用硬编码兜底）
const { dimensionOptions: mdmDimensionOptions, statusOptions: mdmStatusOptions } = useMdmDict()
const committeeTypeOptions = ref([
  { label: '晶体构建', value: 'crystal_construction' },
  { label: '实验立项', value: 'experimental_readiness' },
  { label: '候选优先级', value: 'candidate_priority' },
  { label: '偏差复盘', value: 'deviation_review' },
  { label: '外部证据采纳', value: 'external_evidence' },
  { label: '候选质量审核', value: 'candidate_quality' },
  { label: '系统健康度', value: 'system_health' },
])
const caseStatusOptions = ref([
  { label: '待处理', value: 'pending' },
  { label: '思考中', value: 'thinking' },
  { label: '收集证据中', value: 'executing_evidence' },
  { label: '验证中', value: 'verifying' },
  { label: '通过', value: 'pass' },
  { label: '拒绝', value: 'reject' },
  { label: '需补证据', value: 'request_evidence' },
  { label: '人工复核', value: 'human_review' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
])

// 审查意见0726：支持嵌入到 DecisionCenter 标签页
const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['count-change'])

// --- State ---
const cases = ref([])
const loading = ref(false)
const metrics = reactive({
  total_cases: 0,
  pass_rate: null,
  reject_rate: null,
  human_escalation_rate: null,
  avg_evidence_rounds: null,
})
const committeeMetrics = ref({})
const metricsLoading = ref(false)
const metricsExpanded = ref(false)
const runningId = ref('')
const cancellingId = ref('')
const projectIds = ref([])

const filters = reactive({
  committee_type: undefined,
  status: undefined,
  risk_level: undefined,
  project_id: undefined,
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailCase = ref(null)
const detailTab = ref('overview')
const reviewComment = ref('')
const reviewing = ref(false)

// --- Table columns ---
const columns = [
  { title: '案件 ID', dataIndex: 'case_id', key: 'case_id', width: 140 },
  { title: '委员会类型', key: 'committee_type', width: 120 },
  { title: '项目 ID', dataIndex: 'project_id', key: 'project_id', width: 100 },
  { title: '风险等级', key: 'risk_level', width: 90 },
  { title: '状态', key: 'status', width: 110 },
  { title: 'QC', key: 'qc_status', width: 90 },
  { title: '触发代码', dataIndex: 'trigger_code', key: 'trigger_code', ellipsis: true },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 120, fixed: 'right' },
]

// QC 严重度颜色映射
function qcSeverityColor(severity) {
  const map = {
    low: 'blue',
    medium: 'gold',
    high: 'orange',
    critical: 'red',
  }
  return map[severity] || 'default'
}

// QC 状态颜色映射
function qcStatusColor(status) {
  if (!status) return 'default'
  const s = String(status).toLowerCase()
  if (s === 'valid' || s === 'pass') return 'green'
  if (s === 'valid_with_warning' || s === 'warning') return 'gold'
  if (s === 'invalid' || s === 'reject' || s === 'failed' || s === 'rejected') return 'red'
  if (s === 'pending') return 'blue'
  if (s === 'requires_review') return 'orange'
  return 'default'
}

// QC 状态中文标签（委员会判定域，兼容大小写）
function qcStatusLabel(status) {
  if (!status) return '-'
  const s = String(status).toLowerCase()
  const map = {
    pass: '通过',
    valid: '有效',
    valid_with_warning: '有效(警告)',
    warning: '有效(警告)',
    fail: '失败',
    failed: '失败',
    invalid: '无效',
    pending: '待检',
    requires_review: '复核中',
    reject: '已拒绝',
    rejected: '已拒绝',
  }
  return map[s] || status
}

// --- Label helpers ---
function committeeTypeLabel(type) {
  const found = committeeTypeOptions.value.find(o => o.value === type)
  return found ? found.label : (type || '-')
}

function statusLabel(s) {
  const found = caseStatusOptions.value.find(o => o.value === s)
  return found ? found.label : (s || '-')
}

const statusColors = {
  pending: 'blue',
  thinking: 'purple',
  executing_evidence: 'cyan',
  verifying: 'orange',
  pass: 'green',
  reject: 'red',
  request_evidence: 'gold',
  human_review: 'volcano',
  failed: 'red',
  cancelled: 'default',
}

function statusColor(s) {
  return statusColors[s] || 'default'
}

const evidenceStatusLabel = (status) => {
  const map = { success: '成功', failed: '失败', unknown: '未知' }
  return map[status] || status
}
const evidenceStatusColor = (status) => {
  const map = { success: 'green', failed: 'red', unknown: 'default' }
  return map[status] || 'default'
}

const riskLevelColors = {
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'magenta',
}

function riskLevelColor(level) {
  return riskLevelColors[level] || 'default'
}

const eventColors = {
  case_created: 'blue',
  proposal_ready: 'purple',
  evidence_collected: 'cyan',
  verdict_ready: 'orange',
  human_review_requested: 'volcano',
  case_closed: 'green',
  case_completed: 'green',
  case_failed: 'red',
  default: 'default',
}

// 事件类型中文映射
const eventTypeLabels = {
  case_created: '案件已创建',
  proposal_ready: '提案就绪',
  evidence_collected: '证据已收集',
  verdict_ready: '裁决就绪',
  case_failed: '案件失败',
  case_completed: '案件已完成',
  human_review_requested: '请求人工复核',
  case_closed: '案件已关闭',
}

function eventTypeLabel(type) {
  return eventTypeLabels[type] || type
}

// --- Action helpers ---
const runnableStatuses = ['pending']
const cancellableStatuses = ['pending', 'thinking']

function canRun(status) {
  return runnableStatuses.includes(status)
}

function canCancel(status) {
  return cancellableStatuses.includes(status)
}

// 禁用态 tooltip：明确告知用户为何不可点击，避免靠试错发现
function runTooltip(record) {
  if (canRun(record.status)) return '点击后系统将依次：① 生成评估提案 → ② 自动收集证据（调用对应 Agent 和工具）→ ③ 得出裁决结论 → ④ 如需人工复核则进入待审状态'
  return `该案件状态为「${statusLabel(record.status)}」，无法执行（仅「待处理」状态可执行）`
}

function cancelTooltip(record) {
  if (canCancel(record.status)) return '取消该案件'
  return `该案件状态为「${statusLabel(record.status)}」，无法取消（仅「待处理/思考中」状态可取消）`
}

// --- Formatting ---
const formatTime = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

const formatJson = (obj) => {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

// 判断是否为普通对象（dict），用于事件详情格式化显示
function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

// 案件综合摘要：当案件已完成时生成一段解释性文本
function caseSummary() {
  const c = detailCase.value
  if (!c || !c.verdict) return ''
  const evidenceCount = c.evidence?.length || 0
  const decision = c.verdict.decision ? statusLabel(c.verdict.decision) : '-'
  let text = `本案由 ${c.trigger_code || '-'} 触发，经 ${committeeTypeLabel(c.committee_type)} 委员会评估，收集了 ${evidenceCount} 条证据，最终裁决为 ${decision}。`
  if (c.verdict.blocking_reasons?.length) {
    text += ` 阻断原因：${c.verdict.blocking_reasons.join('；')}`
  }
  if (c.verdict.warnings?.length) {
    text += ` 警告：${c.verdict.warnings.join('；')}`
  }
  return text
}

// --- API calls ---
async function fetchCases() {
  loading.value = true
  try {
    const params = {}
    if (filters.committee_type) params.committee_type = filters.committee_type
    if (filters.status) params.status = filters.status
    if (filters.project_id) params.project_id = filters.project_id
    const res = await getCommitteeCases(params)
    let list = res.items || res.cases || []
    // risk_level is not supported by the backend, filter client-side
    if (filters.risk_level) {
      list = list.filter((c) => c.risk_level === filters.risk_level)
    }
    cases.value = list
    projectIds.value = [...new Set(cases.value.map((c) => c.project_id).filter(Boolean))]
    // 审查意见0726：向上 emit 待处理数量（pending=待执行 / human_review=待人工复核）
    const pendingCount = cases.value.filter((c) =>
      ['pending', 'human_review', 'request_evidence'].includes(c.status)
    ).length
    emit('count-change', pendingCount)
  } catch {
    cases.value = []
    emit('count-change', 0)
  } finally {
    loading.value = false
  }
}

async function fetchMetrics() {
  try {
    const res = await getCommitteeMetrics()
    if (res) {
      metrics.total_cases = res.total_cases ?? 0
      metrics.pass_rate = res.pass_rate ?? null
      metrics.reject_rate = res.reject_rate ?? null
      metrics.human_escalation_rate = res.human_escalation_rate ?? null
      metrics.avg_evidence_rounds = res.avg_evidence_rounds ?? null
    }
  } catch {
    // keep defaults
  }
}

async function fetchCommitteeMetricsData() {
  metricsLoading.value = true
  try {
    const res = await getCommitteeMetrics()
    committeeMetrics.value = res || {}
  } catch {
    committeeMetrics.value = {}
  } finally {
    metricsLoading.value = false
  }
}

async function openDetail(record) {
  detailCase.value = null
  detailVisible.value = true
  detailTab.value = 'overview'
  detailLoading.value = true
  try {
    const res = await getCommitteeCase(record.case_id)
    detailCase.value = { ...res.case, evidence: res.evidence || [], verdict: res.verdict || null, events: res.events || [], proposal: res.proposal || null }
  } catch {
    detailCase.value = null
  } finally {
    detailLoading.value = false
  }
}

async function runCase(record) {
  runningId.value = record.case_id
  try {
    await runCommitteeCase(record.case_id)
    message.success('案件已开始执行，请稍候查看状态变化')
    await fetchCases()
    // 审查意见V5 P0-2：异步任务可能需要时间，启动轮询（最多 60 次，间隔 2 秒）
    pollCaseStatus(record.case_id)
  } catch {
    // handled by interceptor
  } finally {
    runningId.value = ''
  }
}

// 轮询案件状态，直到离开执行中状态或达到最大轮询次数
// 审查意见V5 P0-2：pending 视作"仍在执行中"继续轮询，避免提前结束
const _pollTimers = new Set()
function pollCaseStatus(caseId, count = 0, maxCount = 60) {
  if (count >= maxCount) {
    message.warning(`案件 ${caseId} 评估超时，请稍后查看案件状态`, 5)
    return
  }
  const tid = setTimeout(async () => {
    _pollTimers.delete(tid)
    try {
      const updated = await getCommitteeCase(caseId)
      const runningStatuses = ['pending', 'thinking', 'executing_evidence', 'verifying']
      // 找到列表中对应案件并更新状态
      const idx = cases.value.findIndex((c) => c.case_id === caseId)
      if (idx >= 0) {
        cases.value[idx] = { ...cases.value[idx], ...updated, status: updated.status }
      }
      // 如果仍在执行中状态，继续轮询
      if (runningStatuses.includes(updated.status)) {
        pollCaseStatus(caseId, count + 1, maxCount)
      } else {
        // 状态已变化，刷新整个列表以更新指标
        await fetchCases()
        // 从 events 中查找 case_failed 事件，提取失败原因
        let failReason = ''
        const events = updated?.events || []
        for (const ev of events) {
          if (ev?.event_type === 'case_failed' || ev?.type === 'case_failed') {
            failReason = ev?.payload?.reason || ev?.data?.reason || ''
            break
          }
        }
        if (updated.status === 'human_review') {
          message.info(`案件 ${caseId} 需要人工复核，请在详情中审核`, 5)
        } else if (updated.status === 'pass') {
          message.success(`案件 ${caseId} 已通过`, 5)
        } else if (updated.status === 'reject') {
          message.warning(`案件 ${caseId} 已拒绝`, 5)
        } else if (updated.status === 'failed') {
          const detail = failReason ? `：${failReason}` : ''
          message.error(`案件 ${caseId} 执行失败${detail}`, 8)
        }
      }
    } catch {
      // 轮询失败，静默处理
    }
  }, 2000)
  _pollTimers.add(tid)
}

// 组件卸载时清理所有轮询定时器
onBeforeUnmount(() => {
  _pollTimers.forEach(clearTimeout)
  _pollTimers.clear()
})

// 人工审核提交
async function submitReview(decision) {
  if (!detailCase.value) return
  reviewing.value = true
  try {
    await reviewCommitteeCase(detailCase.value.case_id, {
      decision,
      comment: reviewComment.value || undefined,
    })
    const decisionLabel = { approve: '通过', reject: '拒绝', request_evidence: '需补证据' }[decision]
    message.success(`已提交审核：${decisionLabel}`)
    reviewComment.value = ''
    // 刷新详情
    await openDetail(detailCase.value)
    // 刷新列表
    await fetchCases()
  } catch {
    // handled by interceptor
  } finally {
    reviewing.value = false
  }
}

async function cancelCase(record) {
  cancellingId.value = record.case_id
  try {
    await cancelCommitteeCase(record.case_id)
    message.success('案件已取消')
    await fetchCases()
  } catch {
    // handled by interceptor
  } finally {
    cancellingId.value = ''
  }
}

function resetFilters() {
  filters.committee_type = undefined
  filters.status = undefined
  filters.risk_level = undefined
  filters.project_id = undefined
  fetchCases()
}

// --- Lifecycle ---
onMounted(async () => {
  fetchCases()
  fetchMetrics()
  fetchCommitteeMetricsData()
  // 从 MDM 加载委员会类型/案件状态选项（失败时保留硬编码兜底）
  try {
    const [typeOpts, statusOpts] = await Promise.all([
      mdmDimensionOptions('committee_type'),
      mdmStatusOptions('case'),
    ])
    if (typeOpts.length) committeeTypeOptions.value = typeOpts
    if (statusOpts.length) caseStatusOptions.value = statusOpts
  } catch (e) {
    console.warn('从 MDM 加载委员会选项失败，使用硬编码兜底:', e)
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})
</script>

<style scoped>
.committee-center {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

/* 嵌入模式：去除自身外边距，由父容器统一布局 */
.committee-center.embedded-mode {
  background: transparent;
  box-shadow: none;
  border: none;
  padding: 0;
}

/* Metrics Row */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
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

/* Card Title Row */
.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title-text {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

/* Metrics Panel */
.metrics-panel {
  margin-top: 12px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.metrics-item {
  background: var(--light-bg-hover);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 12px;
  text-align: center;
}

.metrics-item-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.metrics-item-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* Tab Content */
.tab-content {
  padding: 4px 0;
}

.tab-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 12px 0 6px;
}

.tab-section-title:first-child {
  margin-top: 0;
}

.tab-text {
  font-size: 13px;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.6;
}

.evidence-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

/* Evidence Items */
.evidence-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
}

.evidence-item:last-child {
  border-bottom: none;
}

.evidence-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.evidence-source {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.evidence-field {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.evidence-confidence {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.evidence-value {
  margin-top: 8px;
}

.value-pre {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--light-bg-hover);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow-y: auto;
}

/* Scorecard */
.scorecard {
  background: var(--light-bg-hover);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 8px 12px;
}

.scorecard-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}

.scorecard-key {
  color: var(--text-secondary);
}

.scorecard-val {
  color: var(--text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* Event Timeline */
.event-timeline {
  padding-left: 4px;
}

.event-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
}

.event-item:last-child {
  border-bottom: none;
}

.event-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

/* 角色色统一引用 design-tokens 的 --role-* 变量，box-shadow 用对应色的低透明度 */
.dot-blue { background: var(--primary); box-shadow: 0 0 0 3px var(--primary-bg); }
.dot-purple { background: var(--role-dft); box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15); }
.dot-cyan { background: var(--role-experiment); box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.15); }
.dot-green { background: var(--success); box-shadow: 0 0 0 3px var(--success-bg); }
.dot-orange { background: var(--warning); box-shadow: 0 0 0 3px var(--warning-bg); }
.dot-red { background: var(--error); box-shadow: 0 0 0 3px var(--error-bg); }
.dot-default { background: var(--text-muted); box-shadow: 0 0 0 3px var(--secondary-bg); }

.event-body {
  flex: 1;
  min-width: 0;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.event-type {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.event-time {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.event-detail {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
  line-height: 1.5;
}

.event-detail-row {
  display: flex;
  gap: 4px;
  padding: 1px 0;
}

.event-detail-key {
  color: var(--text-muted);
  flex-shrink: 0;
}

.event-detail-val {
  color: var(--text-primary);
  word-break: break-all;
}

/* Trigger Code */
.trigger-code {
  font-size: 12px;
  background: var(--light-bg-hover);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-family-mono);
  word-break: break-all;
}

/* Misc */
.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}

/* QC 展开详情 */
.qc-issues-detail {
  padding: 4px 0;
}
.qc-issue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border-color);
  font-size: 13px;
}
.qc-issue-item:last-child {
  border-bottom: none;
}
.qc-suggested-action {
  color: var(--warning);
}
.qc-rule-category {
  color: var(--text-secondary);
}
.qc-message {
  color: var(--text-secondary);
}

/* 人工复核区 */
.manual-review-block {
  margin-top: 12px;
}

.review-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}

/* Responsive */
@media (max-width: 1024px) {
  .metrics-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>