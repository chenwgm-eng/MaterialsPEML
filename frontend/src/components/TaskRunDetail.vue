<template>
  <a-drawer
    :open="visible"
    :title="run ? `Run 详情 · ${run.run_id.slice(0, 8)}` : 'Run 详情'"
    placement="right"
    width="560"
    @close="$emit('close')"
  >
    <a-spin :spinning="loading">
      <template v-if="run">
        <!-- 生命周期时间线 -->
        <div class="section-title">生命周期</div>
        <div class="lifecycle">
          <div
            v-for="stage in lifecycleStages"
            :key="stage.key"
            class="stage"
            :class="{ done: stage.done, current: stage.current, failed: stage.failed }"
          >
            <div class="stage-dot" />
            <div class="stage-body">
              <div class="stage-head">
                <span class="stage-name">{{ stage.label }}</span>
                <span class="stage-time">{{ stage.time || '—' }}</span>
              </div>
              <div class="stage-status" v-if="stage.note">{{ stage.note }}</div>
            </div>
          </div>
        </div>

        <a-descriptions :column="1" size="small" bordered class="run-meta">
          <a-descriptions-item label="Run ID"><code>{{ run.run_id }}</code></a-descriptions-item>
          <a-descriptions-item label="Task ID"><code>{{ run.task_id }}</code></a-descriptions-item>
          <a-descriptions-item label="服务">{{ run.service_id }}</a-descriptions-item>
          <a-descriptions-item label="命令"><code>{{ run.command }}</code></a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-badge :status="statusBadge" :text="run.status" />
          </a-descriptions-item>
          <a-descriptions-item label="错误信息" v-if="run.error_message">
            <a-typography-text type="danger">{{ run.error_message }}</a-typography-text>
          </a-descriptions-item>
        </a-descriptions>

        <!-- Artifacts -->
        <div class="section-title">
          <span>工件 (Artifacts)</span>
          <a-badge :count="artifacts.length" :number-style="{ backgroundColor: 'var(--primary)' }" />
        </div>
        <a-empty v-if="!artifactsLoading && artifacts.length === 0" description="暂无工件" :image="simpleImage" />
        <div v-else class="artifact-list">
          <div v-for="art in artifacts" :key="art.artifact_id" class="artifact-item">
            <div class="artifact-head" @click="toggleArtifact(art.artifact_id)">
              <span class="artifact-type" :class="`type-${art.type}`">{{ art.type }}</span>
              <span class="artifact-name">{{ art.name }}</span>
              <span class="artifact-expand">{{ expandedArtifacts.has(art.artifact_id) ? '收起' : '展开' }}</span>
            </div>
            <div class="artifact-desc" v-if="art.description">{{ art.description }}</div>
            <div class="artifact-json" v-if="expandedArtifacts.has(art.artifact_id)">
              <pre>{{ formatJson(art.data) }}</pre>
            </div>
          </div>
        </div>

        <!-- Evidence -->
        <div class="section-title">
          <span>证据 (Evidence)</span>
          <a-badge :count="evidenceList.length" :number-style="{ backgroundColor: 'var(--primary)' }" />
        </div>
        <a-empty v-if="!evidenceLoading && evidenceList.length === 0" description="暂无证据" :image="simpleImage" />
        <EvidenceCard
          v-for="ev in evidenceList"
          :key="ev.evidence_id"
          :evidence="ev"
          @click="onEvidenceClick(ev)"
        />

        <!-- 审批 -->
        <div class="section-title">
          <span>审批</span>
          <a-badge v-if="approvals.length" :count="approvals.length" :number-style="{ backgroundColor: 'var(--primary)' }" />
        </div>
        <a-empty v-if="!approvalsLoading && approvals.length === 0" description="暂无审批记录" :image="simpleImage" />
        <div v-else class="approval-list">
          <div v-for="apv in approvals" :key="apv.approval_id" class="approval-item">
            <div class="approval-head">
              <a-badge :status="approvalBadge(apv.status)" :text="approvalStatusLabel(apv.status)" />
              <span class="approval-evidence" :title="apv.evidence_id">证据: {{ apv.evidence_id?.slice(0, 8) }}…</span>
            </div>
            <div class="approval-meta" v-if="apv.reviewer">
              <span>评审人: {{ apv.reviewer }}</span>
            </div>
            <div class="approval-comment" v-if="apv.comment">{{ apv.comment }}</div>
            <div class="approval-actions" v-if="apv.status === 'pending'">
              <a-button size="small" type="primary" :loading="approvalLoading === apv.approval_id" @click="onApprove(apv)">通过</a-button>
              <a-button size="small" danger :loading="approvalLoading === apv.approval_id" @click="onReject(apv)">驳回</a-button>
            </div>
          </div>
        </div>
      </template>
      <a-empty v-else-if="!loading" description="请选择 Run 查看详情" />
    </a-spin>

    <!-- 审批输入对话框 -->
    <a-modal
      v-model:open="showReviewModal"
      :title="reviewAction === 'approve' ? '通过审批' : '驳回审批'"
      :confirm-loading="reviewSubmitting"
      @ok="submitReview"
    >
      <a-form layout="vertical">
        <a-form-item label="评审人">
          <a-input v-model:value="reviewForm.reviewer" placeholder="输入评审人姓名" />
        </a-form-item>
        <a-form-item label="评审意见">
          <a-textarea v-model:value="reviewForm.comment" :rows="3" placeholder="输入评审意见（可选）" />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-drawer>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Empty, message } from 'ant-design-vue'
import {
  getRun, getArtifacts, getRunEvidence,
  listApprovals, requestApproval, approve, reject,
} from '@/api/scientific'
import EvidenceCard from './EvidenceCard.vue'

const props = defineProps({
  runId: { type: String, default: null },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'evidence-click'])

const run = ref(null)
const artifacts = ref([])
const evidenceList = ref([])
const approvals = ref([])
const loading = ref(false)
const artifactsLoading = ref(false)
const evidenceLoading = ref(false)
const approvalsLoading = ref(false)
const expandedArtifacts = ref(new Set())
const approvalLoading = ref(null)
const showReviewModal = ref(false)
const reviewAction = ref('approve')
const reviewSubmitting = ref(false)
const reviewForm = ref({ reviewer: '', comment: '' })
const pendingApproval = ref(null)

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const statusBadge = computed(() => {
  const map = {
    queued: 'default', preparing: 'processing', running: 'processing',
    succeeded: 'success', failed: 'error', cancelled: 'warning', cancelling: 'warning',
  }
  return map[run.value?.status] || 'default'
})

// 生命周期阶段：created → started → completed
const lifecycleStages = computed(() => {
  if (!run.value) return []
  const r = run.value
  const failed = r.status === 'failed'
  const cancelled = r.status === 'cancelled' || r.status === 'cancelling'
  const running = r.status === 'running' || r.status === 'preparing'
  const succeeded = r.status === 'succeeded'
  return [
    {
      key: 'created', label: '已创建', time: formatTime(r.created_at),
      done: true, current: false, failed: false, note: '',
    },
    {
      key: 'started', label: '已开始', time: formatTime(r.started_at),
      done: !!r.started_at, current: running && !r.started_at, failed: false,
      note: running && !r.started_at ? '准备中…' : '',
    },
    {
      key: 'completed', label: succeeded ? '已成功' : failed ? '已失败' : cancelled ? '已取消' : '已完成',
      time: formatTime(r.completed_at),
      done: !!r.completed_at, current: running && !r.completed_at, failed,
      note: r.error_message || '',
    },
  ].map(s => ({ ...s, current: s.key === 'completed' ? (running && !s.done) : s.current }))
})

watch(() => props.runId, async (id) => {
  if (!id) {
    run.value = null
    return
  }
  loading.value = true
  try {
    const [runRes, artRes, evRes] = await Promise.all([
      getRun(id),
      getArtifacts(id),
      getRunEvidence(id),
    ])
    run.value = runRes
    artifacts.value = artRes || []
    evidenceList.value = evRes || []
    await loadApprovals(id)
  } catch (e) {
    console.error('Failed to load run detail:', e)
  } finally {
    loading.value = false
  }
}, { immediate: true })

async function loadApprovals (runId) {
  approvalsLoading.value = true
  try {
    const res = await listApprovals({ run_id: runId, limit: 100 })
    approvals.value = res || []
  } catch (e) {
    approvals.value = []
  } finally {
    approvalsLoading.value = false
  }
}

function formatTime (t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function formatJson (data) {
  if (data === null || data === undefined) return '—'
  try {
    return typeof data === 'string' ? JSON.stringify(JSON.parse(data), null, 2) : JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function toggleArtifact (id) {
  const next = new Set(expandedArtifacts.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedArtifacts.value = next
}

function onEvidenceClick (ev) {
  emit('evidence-click', ev)
}

function approvalStatusLabel (s) {
  const map = { pending: '待审批', approved: '已通过', rejected: '已驳回' }
  return map[s] || s
}

function approvalBadge (s) {
  const map = { pending: 'warning', approved: 'success', rejected: 'error' }
  return map[s] || 'default'
}

async function onApprove (apv) {
  pendingApproval.value = apv
  reviewAction.value = 'approve'
  reviewForm.value = { reviewer: '', comment: '' }
  showReviewModal.value = true
}

async function onReject (apv) {
  pendingApproval.value = apv
  reviewAction.value = 'reject'
  reviewForm.value = { reviewer: '', comment: '' }
  showReviewModal.value = true
}

async function submitReview () {
  if (!pendingApproval.value) return
  if (!reviewForm.value.reviewer.trim()) {
    message.warning('请输入评审人姓名')
    return
  }
  reviewSubmitting.value = true
  approvalLoading.value = pendingApproval.value.approval_id
  try {
    const fn = reviewAction.value === 'approve' ? approve : reject
    await fn(
      pendingApproval.value.approval_id,
      reviewForm.value.reviewer.trim(),
      reviewForm.value.comment.trim(),
    )
    message.success(reviewAction.value === 'approve' ? '审批已通过' : '审批已驳回')
    showReviewModal.value = false
    await loadApprovals(props.runId)
  } catch (e) {
    console.error('Review failed:', e)
  } finally {
    reviewSubmitting.value = false
    approvalLoading.value = null
  }
}
</script>

<style scoped>
.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: var(--space-lg) 0 var(--space-sm);
}
.section-title:first-child {
  margin-top: 0;
}

/* 生命周期时间线 */
.lifecycle {
  display: flex;
  flex-direction: column;
  padding-left: 4px;
  margin-bottom: var(--space-md);
}
.stage {
  display: flex;
  gap: var(--space-sm);
  position: relative;
  padding-bottom: var(--space-md);
}
.stage:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 12px;
  bottom: 0;
  width: 2px;
  background: var(--border);
}
.stage.done:not(:last-child)::before {
  background: var(--primary);
}
.stage-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--border);
  border: 2px solid var(--bg-card);
  flex-shrink: 0;
  margin-top: 2px;
  z-index: 1;
}
.stage.done .stage-dot { background: var(--primary); }
.stage.current .stage-dot {
  background: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-bg);
}
.stage.failed .stage-dot { background: var(--error); }
.stage-body { flex: 1; min-width: 0; }
.stage-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-sm);
}
.stage-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}
.stage.done .stage-name { color: var(--primary); }
.stage.failed .stage-name { color: var(--error); }
.stage-time {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.stage-status {
  font-size: var(--font-size-xs);
  color: var(--error);
  margin-top: 2px;
}

.run-meta {
  margin-bottom: var(--space-sm);
}
.run-meta code {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  word-break: break-all;
}

/* Artifact 列表 */
.artifact-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.artifact-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  overflow: hidden;
}
.artifact-head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.artifact-head:hover { background: var(--bg-hover); }
.artifact-type {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
}
/* Artifact 类型色：蓝(输入)/绿(结果)/紫(结构)/橙(报告) */
.artifact-type.type-input_table { color: var(--info); background: var(--info-bg); }
.artifact-type.type-result_table { color: var(--success); background: var(--success-bg); }
.artifact-type.type-structure { color: #7c3aed; background: rgba(124, 58, 237, 0.1); }
.artifact-type.type-report { color: var(--warning); background: var(--warning-bg); }
.artifact-type.type-plot { color: var(--primary); background: var(--primary-bg); }
.artifact-type.type-log { color: var(--text-secondary); background: var(--light-bg-hover); }
.artifact-type.type-checkpoint { color: var(--info); background: var(--info-bg); }
.artifact-name {
  flex: 1;
  font-size: var(--font-size-md);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.artifact-expand {
  font-size: var(--font-size-xs);
  color: var(--primary);
  flex-shrink: 0;
}
.artifact-desc {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  padding: 0 var(--space-md) var(--space-xs);
}
.artifact-json {
  border-top: 1px solid var(--border-light);
  background: var(--light-bg);
}
.artifact-json pre {
  margin: 0;
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-xs);
  font-family: 'SFMono-Regular', Consolas, monospace;
  color: var(--text-primary);
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 审批列表 */
.approval-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.approval-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-card);
}
.approval-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
}
.approval-evidence {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-family: 'SFMono-Regular', Consolas, monospace;
}
.approval-meta {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: var(--space-xs);
}
.approval-comment {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  background: var(--light-bg);
  border-radius: var(--radius-sm);
}
.approval-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}
</style>
