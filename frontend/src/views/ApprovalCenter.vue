<template>
  <div class="approval-center-page" :class="{ 'embedded-mode': embedded }">
    <a-card size="small" :body-style="{ padding: '12px' }">
      <template #title>
        <span v-if="!embedded">审批中心</span>
        <span v-else class="embedded-title">审批事项</span>
      </template>
      <template #extra>
        <a-button size="small" @click="fetchData" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
      </template>

      <!-- 审批规则说明 -->
      <a-collapse size="small" class="rules-collapse" :bordered="false">
        <a-collapse-panel key="rules" header="审批规则说明">
          <a-spin :spinning="rulesLoading">
            <a-table
              v-if="rules.length > 0"
              :columns="ruleColumns"
              :data-source="rules"
              :pagination="false"
              size="small"
              :row-key="(r) => r.rule_id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'action'">
                  <a-tag :color="record.action === 'REQUIRE_MANUAL' ? 'orange' : 'green'">
                    {{ record.action === 'REQUIRE_MANUAL' ? '需人工审批' : '自动放行' }}
                  </a-tag>
                </template>
              </template>
            </a-table>
            <span v-else class="text-muted">暂无规则配置</span>
          </a-spin>
        </a-collapse-panel>
      </a-collapse>

      <!-- 审批队列（fixedType 模式下隐藏子 tab，直接展示固定类型） -->
      <a-tabs v-if="!fixedType" v-model:activeKey="activeTab" size="small" class="approval-tabs">
        <a-tab-pane key="all">
          <template #tab>
            全部 <a-badge :count="items.length" :number-style="{ backgroundColor: 'var(--primary)' }" :offset="[6, -2]" />
          </template>
        </a-tab-pane>
        <a-tab-pane key="experiment_order">
          <template #tab>
            实验审批 <a-badge :count="countByType.experiment_order" :number-style="{ backgroundColor: 'var(--primary)' }" :offset="[6, -2]" />
          </template>
        </a-tab-pane>
        <a-tab-pane key="qc_review">
          <template #tab>
            QC审批 <a-badge :count="countByType.qc_review" :number-style="{ backgroundColor: 'var(--primary)' }" :offset="[6, -2]" />
          </template>
        </a-tab-pane>
        <a-tab-pane key="material_request">
          <template #tab>
            物料审批 <a-badge :count="countByType.material_request" :number-style="{ backgroundColor: 'var(--primary)' }" :offset="[6, -2]" />
          </template>
        </a-tab-pane>
      </a-tabs>

      <a-table
        v-if="filteredItems.length > 0"
        :columns="columns"
        :data-source="filteredItems"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.type + '_' + r.id"
        :loading="loading"
        class="approval-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'type'">
            <a-space size="4" wrap>
              <a-tag :color="typeColor(record.type)">{{ typeLabel(record.type) }}</a-tag>
              <a-tag v-if="channelOf(record)" color="orange">{{ channelOf(record) }}</a-tag>
            </a-space>
          </template>
          <template v-if="column.key === 'created_at'">
            <span class="tabular-nums">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-if="column.key === 'details'">
            <span class="details-text">{{ detailsText(record) }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-button size="small" type="primary" @click="onApprove(record)" :loading="actingId === record.id">
                通过
              </a-button>
              <a-button size="small" danger @click="onReject(record)">
                驳回
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>

      <!-- 空状态引导 -->
      <div v-else class="empty-guide">
        <EmptyState
          :description="emptyDescription"
          type="create"
          action-text="前往实验工作台"
          secondary-text="前往数据质量"
          @action="$router.push('/experiment-workbench')"
          @secondary="$router.push('/data-quality')"
        />
      </div>
    </a-card>

    <!-- 驳回原因弹窗 -->
    <a-modal
      v-model:open="rejectModalVisible"
      title="驳回原因"
      @ok="confirmReject"
      :confirm-loading="rejecting"
      width="480px"
    >
      <a-form layout="vertical">
        <a-form-item label="驳回原因" required>
          <a-textarea v-model:value="rejectReason" :rows="3" placeholder="请输入驳回原因…" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  AuditOutlined,
  ReloadOutlined,
  ExperimentOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import {
  listPendingApprovals,
  listApprovalRules,
  approveExperimentOrder,
  rejectExperimentOrder,
  approveQCResult,
  rejectQCResult,
} from '@/api/approvals'

// 审查意见0726：支持嵌入到 DecisionCenter 标签页
// fixedType：固定展示某一审批类型，隐藏内部子 tab（用于 MyTasks 展开为一级 tab）
const props = defineProps({
  embedded: { type: Boolean, default: false },
  fixedType: { type: String, default: '' },
})
const emit = defineEmits(['count-change'])

const items = ref([])
const loading = ref(false)
const rules = ref([])
const rulesLoading = ref(false)
const actingId = ref('')
const rejectModalVisible = ref(false)
const rejectReason = ref('')
const rejecting = ref(false)
const rejectTarget = ref(null)
const activeTab = ref('all')

const columns = [
  { title: '类型', key: 'type', width: 100 },
  { title: '标题', dataIndex: 'title', key: 'title', width: 200, ellipsis: true },
  { title: '申请人', dataIndex: 'requester', key: 'requester', width: 100 },
  { title: '详情', key: 'details', ellipsis: true },
  { title: '创建时间', key: 'created_at', width: 160, className: 'tabular-nums' },
  { title: '操作', key: 'actions', width: 140, fixed: 'right' },
]

const countByType = computed(() => ({
  experiment_order: items.value.filter((i) => i.type === 'experiment_order').length,
  qc_review: items.value.filter((i) => i.type === 'qc_review').length,
  material_request: items.value.filter((i) => i.type === 'material_request').length,
}))

const filteredItems = computed(() => {
  if (props.fixedType) return items.value.filter((i) => i.type === props.fixedType)
  if (activeTab.value === 'all') return items.value
  return items.value.filter((i) => i.type === activeTab.value)
})

const emptyDescription = computed(() => {
  if (items.value.length === 0) {
    return '本页为聚合视图，仅展示已触发审批规则的事项。当前无待审批事项——实验任务的审批动作请在「实验工作台」内完成（提交任务、确认结果时触发），数据质量的审核请在「数据质量」页面进行。'
  }
  return '当前分类下暂无待审批事项，切换到「全部」可查看其他类型。'
})

const ruleColumns = [
  { title: '规则 ID', dataIndex: 'rule_id', key: 'rule_id', width: 80 },
  { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', width: 200 },
  { title: '条件字段', dataIndex: 'condition_field', key: 'condition_field', width: 140 },
  { title: '运算符', dataIndex: 'operator', key: 'operator', width: 80 },
  { title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 80 },
  { title: '动作', key: 'action', width: 120 },
  { title: '说明', dataIndex: 'description', key: 'description' },
]

function typeColor(type) {
  const map = { experiment_order: 'blue', qc_review: 'purple', material_request: 'orange' }
  return map[type] || 'default'
}

function typeLabel(type) {
  const map = { experiment_order: '实验任务', qc_review: 'QC审核', material_request: '物料申请' }
  return map[type] || type
}

// 审批目标通道标签（后端返回的 channel，如「实验审批」/「委员会评审」）
function channelOf(record) {
  return record?.channel || record?.details?.channel || ''
}

function detailsText(record) {
  const d = record.details || {}
  if (record.type === 'experiment_order') {
    const parts = []
    if (d.candidate_id) parts.push(`候选材料: ${d.candidate_id}`)
    if (d.priority) parts.push(`优先级: ${d.priority}`)
    if (d.project_id) parts.push(`项目: ${d.project_id}`)
    return parts.join('，')
  }
  if (record.type === 'qc_review') {
    const parts = []
    if (d.property_name) parts.push(d.property_name)
    if (d.value !== undefined) parts.push(`${d.value}${d.unit || ''}`)
    if (d.order_id) parts.push(`任务: ${d.order_id}`)
    return parts.join('，')
  }
  return ''
}

function formatTime(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function fetchData() {
  loading.value = true
  try {
    const res = await listPendingApprovals()
    items.value = res.items || []
    // 审查意见0726：向上 emit 待审批数量（fixedType 模式下只 emit 该类型的数量）
    const count = props.fixedType
      ? items.value.filter((i) => i.type === props.fixedType).length
      : items.value.length
    emit('count-change', count)
  } catch {
    items.value = []
    emit('count-change', 0)
  } finally {
    loading.value = false
  }
}

async function fetchRules() {
  rulesLoading.value = true
  try {
    rules.value = await listApprovalRules()
  } catch {
    rules.value = []
  } finally {
    rulesLoading.value = false
  }
}

async function onApprove(record) {
  actingId.value = record.id
  try {
    if (record.type === 'experiment_order') {
      await approveExperimentOrder(record.id, { approved_by: '', notes: '' })
    } else if (record.type === 'qc_review') {
      await approveQCResult(record.id, { reviewed_by: '', learning_eligible: false, reason: '' })
    }
    message.success('审批通过')
    await fetchData()
  } catch {
    /* handled by interceptor */
  } finally {
    actingId.value = ''
  }
}

function onReject(record) {
  rejectTarget.value = record
  rejectReason.value = ''
  rejectModalVisible.value = true
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    message.warning('请输入驳回原因')
    return
  }
  rejecting.value = true
  try {
    const record = rejectTarget.value
    if (record.type === 'experiment_order') {
      await rejectExperimentOrder(record.id, { approved_by: '', notes: rejectReason.value })
    } else if (record.type === 'qc_review') {
      await rejectQCResult(record.id, { reviewed_by: '', reason: rejectReason.value })
    }
    message.success('已驳回')
    rejectModalVisible.value = false
    await fetchData()
  } catch {
    /* handled by interceptor */
  } finally {
    rejecting.value = false
  }
}

onMounted(() => {
  fetchData()
  fetchRules()
})
</script>

<style scoped>
.approval-center-page {
  overflow-x: hidden;
}

/* 嵌入模式：去除自身外边距，由父容器统一布局 */
.approval-center-page.embedded-mode {
  background: transparent;
  box-shadow: none;
  border: none;
  padding: 0;
}

.embedded-mode :deep(.ant-card) {
  background: transparent;
  box-shadow: none;
  border: none;
}

.embedded-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.rules-collapse {
  margin-bottom: 12px;
}

.approval-tabs {
  margin-bottom: 8px;
}

.approval-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 8px;
}

.approval-table {
  margin-top: 0;
}

.details-text {
  font-size: 12px;
  color: var(--text-secondary);
}

.empty-guide {
  padding: 32px 0;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  color: var(--text-muted);
}

.text-muted {
  color: var(--text-muted);
  font-size: 12px;
}
</style>
