<template>
  <div>
    <!-- Committee Gate -->
    <a-card class="detail-card" :bordered="false" v-if="committeeCases.length">
      <template #title>
        <span class="card-title-text"><SafetyOutlined /> 委员会门禁</span>
      </template>
      <template #extra>
        <a-button size="small" type="link" @click="goToCommitteeCenter">前往委员会中心</a-button>
      </template>
      <!-- 区块用途说明 -->
      <a-alert
        type="info"
        show-icon
        :message="`多智能体委员会对候选材料进行立项/优先级/偏差等门禁审查，决策通过后方可进入下一环节`"
        style="margin-bottom: 12px"
      />
      <a-alert
        v-if="blockedReason"
        type="error"
        :message="`阻断原因：${blockedReason}`"
        show-icon
        style="margin-bottom: 12px"
      />
      <div v-for="c in committeeCases" :key="c.case_id || c.id" class="committee-case-row">
        <div class="committee-case-header">
          <span class="committee-type-label">{{ committeeTypeLabel(c.committee_type || c.type) }}</span>
          <a-tag :color="committeeDecisionColor(c.verdict?.decision || c.decision)">{{ c.verdict?.decision || c.decision || '待定' }}</a-tag>
          <a-tag v-if="c.status" :color="c.status === 'pass' ? 'green' : (c.status === 'thinking' || c.status === 'executing_evidence' || c.status === 'verifying') ? 'processing' : 'default'">
            {{ c.status === 'pass' ? '已完成' : (c.status === 'thinking' || c.status === 'executing_evidence' || c.status === 'verifying') ? '运行中' : c.status }}
          </a-tag>
        </div>
        <div v-if="(c.verdict?.blocking_reasons || c.blocking_reasons || []).length" class="committee-case-detail">
          <span class="committee-detail-label">阻断原因：</span>
          <span class="committee-detail-text committee-text-danger">{{ (c.verdict?.blocking_reasons || c.blocking_reasons || []).join('；') }}</span>
        </div>
        <div v-if="(c.verdict?.warnings || c.warnings || []).length" class="committee-case-detail">
          <span class="committee-detail-label">警告：</span>
          <span class="committee-detail-text committee-text-warning">{{ (c.verdict?.warnings || c.warnings || []).join('；') }}</span>
        </div>
        <!-- 人工复核操作：仅在 human_review 决策时显示 -->
        <div v-if="needsHumanReview(c)" class="committee-case-actions">
          <a-button size="small" type="primary" :loading="reviewingCaseId === (c.case_id || c.id)" @click="onReviewCase(c, 'pass')">审批通过</a-button>
          <a-button size="small" danger :loading="reviewingCaseId === (c.case_id || c.id)" @click="onReviewCase(c, 'reject')">驳回</a-button>
          <a-button size="small" :loading="reviewingCaseId === (c.case_id || c.id)" @click="onReviewCase(c, 'request_evidence')">要求补充材料</a-button>
        </div>
      </div>
    </a-card>

    <!-- DFT Queue -->
    <a-card class="detail-card" :bordered="false" v-if="dftQueueData" title="DFT 队列与保留池">
      <a-row :gutter="16">
        <a-col :sm="12">
          <div class="queue-section-title">DFT 队列</div>
          <div v-if="dftQueueData.queue && dftQueueData.queue.length" class="queue-list">
            <div v-for="(item, idx) in dftQueueData.queue" :key="idx" class="queue-item">
              <div class="queue-item-name">{{ item.name || item.formula || item.smiles || '-' }}</div>
              <div class="queue-item-meta">
                <span>优先级：{{ item.priority_score != null ? Number(item.priority_score).toFixed(3) : '-' }}</span>
                <span>资源：{{ item.resource_estimate || '-' }}</span>
              </div>
              <div v-if="item.reason" class="queue-item-reason">{{ item.reason }}</div>
            </div>
          </div>
          <EmptyState v-else type="data" description="队列为空" />
        </a-col>
        <a-col :sm="12">
          <div class="queue-section-title">保留池</div>
          <div v-if="dftQueueData.reserved_pool && dftQueueData.reserved_pool.length" class="queue-list">
            <div v-for="(item, idx) in dftQueueData.reserved_pool" :key="idx" class="queue-item">
              <div class="queue-item-name">{{ item.name || item.formula || item.smiles || '-' }}</div>
              <div class="queue-item-meta">
                <span>优先级：{{ item.priority_score != null ? Number(item.priority_score).toFixed(3) : '-' }}</span>
                <span>资源：{{ item.resource_estimate || '-' }}</span>
              </div>
              <div v-if="item.reason" class="queue-item-reason">{{ item.reason }}</div>
            </div>
          </div>
          <EmptyState v-else type="data" description="保留池为空" />
        </a-col>
      </a-row>
      <div v-if="dftQueueData.pareto_info" class="queue-pareto-info" style="margin-top: 12px">
        <a-tag color="blue">帕累托关系</a-tag>
        <span class="text-muted">{{ dftQueueData.pareto_info }}</span>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SafetyOutlined } from '@ant-design/icons-vue'
import { getCommitteeCases, getPriorityQueue, reviewCommitteeCase } from '@/api/committees'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  // 当前 ECML run id（驱动 committeeCases 拉取）
  runId: { type: String, default: '' },
  // 阻断原因（来自 ecmlStore.state?.blocked_reason）
  blockedReason: { type: String, default: '' },
})

const emit = defineEmits(['reviewed'])

const router = useRouter()
const committeeCases = ref([])
const dftQueueData = ref(null)
const reviewingCaseId = ref('')

// 拉取委员会门禁案件
watch(() => props.runId, async (runId) => {
  committeeCases.value = []
  dftQueueData.value = null
  if (!runId) return
  try {
    const res = await getCommitteeCases({ limit: 100 })
    committeeCases.value = (res.cases || res || []).filter((c) => c.ecml_run_id === runId)
  } catch {
    committeeCases.value = []
  }
}, { immediate: true })

// 拉取 DFT 优先级队列
watch(committeeCases, async (cases) => {
  dftQueueData.value = null
  const priorityCase = cases.find((c) => (c.committee_type || c.type) === 'candidate_priority')
  if (priorityCase) {
    try {
      const res = await getPriorityQueue(priorityCase.case_id)
      dftQueueData.value = res
    } catch {
      dftQueueData.value = null
    }
  }
})

function committeeTypeLabel(type) {
  const map = {
    crystal_construction: '晶体构建',
    experimental_readiness: '实验立项',
    candidate_priority: '候选优先级',
    deviation_review: '偏差复盘',
    external_evidence: '外部证据采纳',
  }
  return map[type] || type || '未知'
}

function committeeDecisionColor(decision) {
  const map = {
    pass: 'green',
    reject: 'red',
    request_evidence: 'gold',
    human_review: 'volcano',
    failed: 'red',
  }
  return map[decision] || 'default'
}

// 判断案件是否需要人工复核
function needsHumanReview(c) {
  const decision = c.verdict?.decision || c.decision
  return decision === 'human_review' && (c.case_id || c.id)
}

// 提交人工复核结果
async function onReviewCase(c, decision) {
  const caseId = c.case_id || c.id
  if (!caseId) return
  reviewingCaseId.value = caseId
  try {
    await reviewCommitteeCase(caseId, { decision })
    const labelMap = { pass: '审批通过', reject: '已驳回', request_evidence: '已要求补充材料' }
    message.success(`委员会案件「${committeeTypeLabel(c.committee_type || c.type)}」${labelMap[decision] || decision}`)
    // 刷新案件列表
    const res = await getCommitteeCases({ limit: 100 })
    committeeCases.value = (res.cases || res || []).filter((cc) => cc.ecml_run_id === props.runId)
    emit('reviewed', { caseId, decision })
  } catch {
    /* 错误由拦截器统一处理 */
  } finally {
    reviewingCaseId.value = ''
  }
}

function goToCommitteeCenter() {
  router.push({ path: '/my-tasks', query: { tab: 'committee' } })
}
</script>

<style scoped>
.detail-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

/* Committee Gate */
.committee-case-row {
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--light-bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.committee-case-row:last-child {
  margin-bottom: 0;
}

.committee-case-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.committee-type-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.committee-case-detail {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.committee-detail-label {
  color: var(--text-secondary);
}

.committee-detail-text {
  color: var(--text-primary);
}

.committee-text-danger {
  color: var(--error);
}

.committee-text-warning {
  color: var(--warning);
}

.committee-case-actions {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* DFT Queue */
.queue-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item {
  padding: 8px 10px;
  background: var(--light-bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.queue-item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}

.queue-item-meta {
  display: flex;
  gap: 16px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.queue-item-reason {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.queue-pareto-info {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
