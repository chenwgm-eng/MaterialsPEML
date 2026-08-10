<template>
  <div class="orchestration-page">
    <div class="page-header page-header-row">
      <div>
        <h1 class="page-title">智能编排</h1>
        <p class="page-subtitle">AI 组织研发小队，agentic 执行研发任务</p>
      </div>
      <a-button v-if="phase !== 'input'" @click="onReset">
        <template #icon><ReloadOutlined /></template>
        重新开始
      </a-button>
    </div>

    <div class="orchestration-workspace">
      <!-- 左侧 -->
      <div class="orchestration-left">
        <!-- 失败状态提示 -->
        <a-alert
          v-if="error"
          type="error"
          :message="error"
          show-icon
          closable
          style="margin-bottom: 12px"
        >
          <template #action>
            <a-button size="small" type="primary" @click="onRetry">重试</a-button>
          </template>
        </a-alert>

        <!-- 阶段 1: 任务输入 -->
        <a-card v-if="phase === 'input'" :bordered="false" class="phase-card">
          <div class="phase-label">阶段 1 · 任务输入</div>
          <div class="input-hints">
            <div class="hint-label">目标模板：</div>
            <div class="hint-chips">
              <a-tag
                v-for="h in examples"
                :key="h"
                class="hint-chip"
                @click="target = h"
              >
                {{ h }}
              </a-tag>
            </div>
          </div>
          <div class="task-input-row">
            <a-textarea
              v-model:value="target"
              class="task-input-large"
              :rows="4"
              placeholder="例如：找到高离子电导率的固态电解质材料"
              :disabled="orchestrationStore.loading"
            />
            <div class="task-input-action">
              <a-tooltip :title="!target.trim() ? '请输入任务目标或选择模板' : ''">
                <a-button
                  type="primary"
                  size="large"
                  :loading="orchestrationStore.loading"
                  :disabled="!target.trim()"
                  @click="onAnalyze"
                >
                  <template #icon><ThunderboltOutlined /></template>
                  开始分析
                </a-button>
              </a-tooltip>
            </div>
          </div>
        </a-card>

        <!-- 阶段 2: 方案确认 -->
        <a-card v-else-if="phase === 'confirm'" :bordered="false" class="phase-card">
          <div class="phase-label">
            阶段 2 · 方案确认
            <a-button size="small" @click="backToInput">
              <template #icon><RedoOutlined /></template>
              返回修改目标
            </a-button>
          </div>
          <div class="reasoning-box">
            <div class="reasoning-title">
              <BulbOutlined /> AI 推荐理由
            </div>
            <div class="reasoning-text">
              {{ plan?.rationale || 'AI 已根据任务目标推荐合适的研发小队与执行步骤。' }}
            </div>
          </div>
          <div class="steps-section">
            <div class="section-title">执行步骤 <span class="section-sub">可删除不需要的步骤</span></div>
            <a-list size="small" bordered :data-source="confirmedSteps">
              <template #renderItem="{ item, index }">
                <a-list-item>
                  <!-- Committee step -->
                  <div v-if="isCommitteeStep(item)" class="step-item committee-step-item">
                    <div class="step-meta">
                      <span class="step-index committee-step-index">
                        <component :is="committeeStepIcon(item)" />
                      </span>
                      <span class="step-task">{{ item.task }}</span>
                      <a-tag v-if="committeeStepType(item)" size="small" color="blue">
                        <AuditOutlined /> {{ committeeStepType(item) }}
                      </a-tag>
                      <a-tag v-if="committeeStepRole(item)" size="small" color="cyan">
                        {{ committeeStepRole(item) }}
                      </a-tag>
                      <a-tag v-if="committeeStepRoleLabel(item)" size="small">
                        {{ committeeStepRoleLabel(item) }}
                      </a-tag>
                    </div>
                    <a-button type="text" danger size="small" @click="removeStep(index)">
                      <template #icon><DeleteOutlined /></template>
                      删除
                    </a-button>
                  </div>
                  <!-- Normal step -->
                  <div v-else class="step-item">
                    <div class="step-meta">
                      <span class="step-index">{{ index + 1 }}</span>
                      <span class="step-task">{{ item.task }}</span>
                      <a-tag size="small">{{ agentName(item.agent_id) }}</a-tag>
                    </div>
                    <a-button type="text" danger size="small" @click="removeStep(index)">
                      <template #icon><DeleteOutlined /></template>
                      删除
                    </a-button>
                  </div>
                </a-list-item>
              </template>
            </a-list>
          </div>
          <div class="flow-section">
            <div class="section-title">执行流程图</div>
            <div class="flow-graph-wrap">
              <AgentFlowGraph
                :steps="confirmedSteps"
                :agents="teamAgents.length > 0 ? teamAgents : (plan?.team || [])"
              />
            </div>
          </div>
        </a-card>

        <!-- 阶段 3: 执行监控 -->
        <a-card v-else :bordered="false" class="phase-card">
          <div class="phase-label">
            阶段 3 · 执行监控
            <a-space>
              <a-tag v-if="recordStatus" :color="statusColor" class="status-tag">
                {{ retrying ? '重试中…' : statusText }}
              </a-tag>
              <a-button
                v-if="orchestrationStore.executing"
                size="small"
                danger
                @click="onCancel"
              >
                <template #icon><CloseCircleOutlined /></template>
                取消执行
              </a-button>
            </a-space>
          </div>
          <div class="flow-section">
            <div class="section-title">执行流程</div>
            <div class="flow-graph-wrap">
              <AgentFlowGraph
                :steps="confirmedSteps"
                :agents="teamAgents.length > 0 ? teamAgents : (plan?.team || [])"
                :current-step-id="currentStepId"
                :completed-steps="completedSteps"
                :failed-steps="failedSteps"
              />
            </div>
          </div>
          <div class="log-section">
            <div class="section-title">执行日志</div>
            <AgentLogPanel
              :events="displayEvents"
              :agents="teamAgents.length > 0 ? teamAgents : (plan?.team || [])"
              height="300px"
            />
          </div>
          <ExecutionResultPanel
            v-if="!orchestrationStore.executing && recordStatus === 'completed'"
            :events="displayEvents"
            :agents="teamAgents.length > 0 ? teamAgents : (plan?.team || [])"
            :total-count="confirmedSteps.length || plan?.steps?.length || 0"
            :completed-count="completedSteps.length"
            :warning-count="warningSteps.length"
            @view-runs="$router.push('/orchestration/runs')"
            @run-again="onReset"
            @rerun-tool="onRerunTool"
          />
          <a-alert
            v-else-if="!orchestrationStore.executing && recordStatus === 'failed'"
            type="error"
            show-icon
            class="result-alert"
            message="执行失败"
          >
            <template #description>
              <div class="failed-desc">
                <div>{{ resultSummary || '执行过程中出现错误，请查看日志了解详情。' }}</div>
                <div class="retry-actions">
                  <a-button
                    v-for="step in failedStepObjects"
                    :key="step.step_id"
                    size="small"
                    type="primary"
                    @click="retryStep(step)"
                  >
                    <template #icon><RedoOutlined /></template>
                    重试“{{ step.task }}”
                  </a-button>
                  <a-button size="small" @click="retryFailedSteps">
                    <template #icon><RedoOutlined /></template>
                    保留成功步骤，重试失败步骤
                  </a-button>
                </div>
              </div>
            </template>
          </a-alert>
        </a-card>
      </div>

      <!-- 右侧：Agent 小队面板 -->
      <div class="orchestration-right">
        <a-card :bordered="false" class="phase-card team-panel">
          <div class="panel-header">
            <div class="panel-title">
              <TeamOutlined /> Agent 小队
              <a-tooltip title="小队成员来自「Agent 管理」页的内置角色库；输入任务目标并点击「开始分析」后，AI 会自动推荐合适的小队成员。">
                <QuestionCircleOutlined class="panel-help-icon" />
              </a-tooltip>
            </div>
            <a-tag color="blue" class="team-count">{{ selectedAgentIds.size }} / {{ teamAgents.length }}</a-tag>
          </div>

          <EmptyState
            v-if="teamAgents.length === 0"
            type="create"
            description="暂无小队成员。在左侧输入任务目标并点击「开始分析」，AI 将从 Agent 角色库自动推荐小队成员。"
            action-text="前往 Agent 管理查看角色库"
            @action="$router.push('/agents')"
          />

          <a-collapse
            v-else
            class="team-collapse"
            :active-key="teamRoleKeys"
            :bordered="false"
          >
            <a-collapse-panel
              v-for="role in teamRoleKeys"
              :key="role"
              :header="`${ROLE_LABEL[role] || role} (${teamByRole[role].length})`"
            >
              <div class="team-group">
                <AgentCard
                  v-for="agent in teamByRole[role]"
                  :key="agent.id"
                  :agent="agent"
                  :selectable="true"
                  :selected="selectedAgentIds.has(agent.id)"
                  @select="onToggleAgent"
                />
              </div>
            </a-collapse-panel>
          </a-collapse>

          <div class="panel-actions">
            <a-button
              block
              :disabled="orchestrationStore.executing"
              @click="addModalVisible = true"
            >
              <template #icon><PlusOutlined /></template>
              添加 Agent
            </a-button>
            <a-button
              v-if="phase === 'confirm'"
              type="primary"
              block
              :loading="orchestrationStore.loading"
              :disabled="selectedAgentIds.size === 0"
              @click="onExecute"
            >
              <template #icon><PlayCircleOutlined /></template>
              开始执行
            </a-button>
          </div>
        </a-card>
      </div>
    </div>

    <!-- Agent 扩容确认弹窗 -->
    <a-modal
      v-model:open="showAgentConfirm"
      title="AI 建议追加团队成员"
      ok-text="采纳"
      cancel-text="暂不采纳"
      @ok="onAdoptAgents"
      @cancel="onRejectAgents"
    >
      <p>AI 分析后建议新增以下 Agent，是否采纳？</p>
      <a-list size="small" :data-source="plan?.suggested_agents || []">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="item.name" :description="item.role || item.description" />
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 添加 Agent 抽屉 -->
    <a-drawer
      :open="addModalVisible"
      title="添加 Agent"
      placement="right"
      width="640px"
      :footer="null"
      @update:open="(v) => (addModalVisible = v)"
    >
      <a-input
        v-model:value="addSearch"
        placeholder="搜索 Agent 名称或专长"
        class="modal-search"
        allow-clear
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <div class="modal-agent-list">
        <EmptyState v-if="filteredAddableAgents.length === 0" type="data" description="没有可添加的 Agent" />
        <AgentCard
          v-for="agent in filteredAddableAgents"
          :key="agent.id"
          :agent="agent"
          :selectable="true"
          :selected="false"
          @select="onAddAgent"
        />
      </div>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  ThunderboltOutlined,
  BulbOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  PlusOutlined,
  TeamOutlined,
  SearchOutlined,
  DeleteOutlined,
  RedoOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  AuditOutlined,
  ToolOutlined,
  SafetyOutlined,
} from '@ant-design/icons-vue'
import { useOrchestrationStore } from '@/stores/orchestration'
import { listAgents } from '@/api/agents'
import { useMdmDict } from '@/utils/mdmDict'
import AgentFlowGraph from '@/components/AgentFlowGraph.vue'
import AgentLogPanel from '@/components/AgentLogPanel.vue'
import AgentCard from '@/components/AgentCard.vue'
import ExecutionResultPanel from '@/components/ExecutionResultPanel.vue'
import EmptyState from '@/components/EmptyState.vue'

const orchestrationStore = useOrchestrationStore()

const phase = ref('input')
const target = ref('')
const allAgents = ref([])
const teamAgents = ref([])
// 注意：selectedAgentIds 用 ref 包装 Set，必须通过整体替换（new Set(...)）修改才能触发响应式
// 不要直接调用 .add()/.delete()，否则模板中的 .size 等不会更新
const selectedAgentIds = ref(new Set())
const addModalVisible = ref(false)
const addSearch = ref('')
const confirmedSteps = ref([])
const preservedEvents = ref([])
const retrying = ref(false)
const error = ref('')
const showAgentConfirm = ref(false)

const examples = [
  '设计高离子电导率的固态电解质',
  '筛选锂金属负极保护层材料',
  '优化聚合物电解质机械强度',
]

const ROLE_LABEL_FALLBACK = {
  project_manager: '项目经理',
  material_discovery: '材料发现',
  synthesis_planning: '合成规划',
  dft_verification: 'DFT 验证',
  experiment_analysis: '实验分析',
  literature_research: '文献调研',
  quality_review: '质量审核',
  custom: '自定义',
}
const ROLE_LABEL = ref({ ...ROLE_LABEL_FALLBACK })

const plan = computed(() => orchestrationStore.plan)

const displayEvents = computed(() => {
  const current = orchestrationStore.currentRecord?.events || []
  return [...preservedEvents.value, ...current]
})

const completedSteps = computed(() =>
  displayEvents.value
    .filter((e) => e.event_type === 'step_complete' && e.step_id && e.status !== 'error' && e.status !== 'warning')
    .map((e) => e.step_id),
)

const warningSteps = computed(() =>
  displayEvents.value
    .filter((e) => e.event_type === 'step_complete' && e.step_id && e.status === 'warning')
    .map((e) => e.step_id),
)

const failedSteps = computed(() =>
  displayEvents.value
    .filter((e) => e.event_type === 'error' && e.step_id)
    .map((e) => e.step_id),
)

const failedStepObjects = computed(() =>
  confirmedSteps.value.filter((s) => failedSteps.value.includes(s.step_id)),
)

const currentStepId = computed(() => {
  const starts = displayEvents.value.filter((e) => e.event_type === 'step_start' && e.step_id)
  if (starts.length === 0) return ''
  const last = starts[starts.length - 1]
  const finished = [...completedSteps.value, ...warningSteps.value, ...failedSteps.value]
  return finished.includes(last.step_id) ? '' : last.step_id
})

const recordStatus = computed(() => orchestrationStore.currentRecord?.status || '')

const RUN_STATUS_OPTIONS_FALLBACK = [
  { value: 'pending', label: '等待中…' },
  { value: 'running', label: '执行中…' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]
const runStatusOptions = ref([...RUN_STATUS_OPTIONS_FALLBACK])

const statusText = computed(() => {
  if (retrying.value) return '重试中…'
  const opt = runStatusOptions.value.find((o) => o.value === recordStatus.value)
  return opt?.label || ''
})

const statusColor = computed(
  () =>
    ({
      pending: 'default',
      running: 'processing',
      completed: 'success',
      failed: 'error',
    })[recordStatus.value] || 'default',
)

const resultSummary = computed(
  () => orchestrationStore.currentRecord?.result_summary || '',
)

watch(recordStatus, (status) => {
  if (status === 'completed' || status === 'failed') {
    retrying.value = false
  }
})

watch(() => plan.value, (newPlan) => {
  if (newPlan?.suggested_agents?.length > 0) {
    showAgentConfirm.value = true
  }
})

function onAdoptAgents() {
  if (plan.value?.suggested_agents) {
    // 后端 analyze 返回的 team 与 suggested_agents 为同一批推荐；
    // 采纳时按 id 去重，避免角色被重复添加（角色数量翻倍）。
    const existing = new Set(teamAgents.value.map((a) => a.id))
    const toAdd = plan.value.suggested_agents.filter((a) => !existing.has(a.id))
    teamAgents.value = [...teamAgents.value, ...toAdd]
    plan.value.suggested_agents = []
    // 采纳后同步选中新增成员
    if (toAdd.length) {
      const next = new Set(selectedAgentIds.value)
      toAdd.forEach((a) => next.add(a.id))
      selectedAgentIds.value = next
    }
  }
  showAgentConfirm.value = false
}

function onRejectAgents() {
  if (plan.value) {
    plan.value.suggested_agents = []
  }
  showAgentConfirm.value = false
}

const addableAgents = computed(() => {
  const ids = new Set(teamAgents.value.map((a) => a.id))
  return allAgents.value.filter((a) => !ids.has(a.id) && a.status !== 'development')
})

const teamByRole = computed(() => {
  const groups = {}
  for (const agent of teamAgents.value) {
    const role = agent.role || 'custom'
    if (!groups[role]) groups[role] = []
    groups[role].push(agent)
  }
  return groups
})

const teamRoleKeys = computed(() => Object.keys(teamByRole.value))

const filteredAddableAgents = computed(() => {
  if (!addSearch.value) return addableAgents.value
  const q = addSearch.value.toLowerCase()
  return addableAgents.value.filter(
    (a) =>
      a.name?.toLowerCase().includes(q) ||
      a.description?.toLowerCase().includes(q) ||
      a.expertise?.some((e) => e.toLowerCase().includes(q)),
  )
})

function normalizeTeam(planData) {
  // 优先取 team，空数组则回退到 suggested_agents / recommended_agents
  const team = (planData?.team?.length > 0
    ? planData.team
    : planData?.suggested_agents?.length > 0
      ? planData.suggested_agents
      : planData?.recommended_agents) || []
  return team
    .map((t) => {
      if (typeof t === 'string') {
        return (
          allAgents.value.find((a) => a.id === t) || {
            id: t,
            name: t,
            role: 'custom',
            avatar: '',
            tools: [],
            expertise: [],
            llm_model: 'LongCat-2.0',
          }
        )
      }
      return t
    })
    .filter(Boolean)
    .filter((a) => a.status !== 'development')
}

async function onAnalyze() {
  if (!target.value.trim()) return
  try {
    const planData = await orchestrationStore.analyze(target.value)
    teamAgents.value = normalizeTeam(planData)
    selectedAgentIds.value = new Set(teamAgents.value.map((a) => a.id))
    confirmedSteps.value = planData?.steps || plan.value?.steps || []
    preservedEvents.value = []
    retrying.value = false
    phase.value = 'confirm'
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '分析失败'
  }
}

async function onExecute() {
  if (selectedAgentIds.value.size === 0) {
    message.warning('请至少选择一个 Agent')
    return
  }
  if (!target.value.trim()) {
    message.warning('请输入任务目标')
    return
  }
  try {
    const team = teamAgents.value.filter((a) => selectedAgentIds.value.has(a.id))
    const steps = confirmedSteps.value.length > 0 ? confirmedSteps.value : (plan.value?.steps || [])
    preservedEvents.value = []
    retrying.value = false
    await orchestrationStore.execute(target.value, team, steps)
    phase.value = 'monitor'
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '执行失败'
  }
}

function agentName(agentId) {
  return teamAgents.value.find((a) => a.id === agentId)?.name || agentId
}

// Committee workflow step helpers

const COMMITTEE_ROLE_MAP = {
  thinker_propose: { role: 'Thinker', label: '提案生成' },
  collect_evidence: { role: 'Doer', label: '证据收集' },
  verify_gate: { role: 'Verifier', label: '门禁验证' },
  persist_verdict: { role: 'Verifier', label: '结论持久化' },
}

const COMMITTEE_TYPE_LABEL = {
  crystal_construction: '晶体构建',
  experimental_readiness: '实验立项',
  candidate_priority: '候选优先级',
  deviation_review: '偏差复盘',
  external_evidence: '外部证据采纳',
}

function isCommitteeStep(step) {
  if (!step) return false
  if (step.agent_id?.startsWith('committee_')) return true
  if (step.committee_type || step.committee_role) return true
  return false
}

function committeeStepRole(step) {
  const type = step?.step_type || step?.type || ''
  return COMMITTEE_ROLE_MAP[type]?.role || step?.committee_role || ''
}

function committeeStepRoleLabel(step) {
  const type = step?.step_type || step?.type || ''
  const mapped = COMMITTEE_ROLE_MAP[type]
  if (mapped) return mapped.label
  // Don't return step.committee_role as fallback for label - only for role
  return ''
}

function committeeStepType(step) {
  const ct = step?.committee_type || ''
  return COMMITTEE_TYPE_LABEL[ct] || ct
}

function committeeStepIcon(step) {
  const role = committeeStepRole(step)
  if (role === 'Thinker') return BulbOutlined
  if (role === 'Doer') return ToolOutlined
  if (role === 'Verifier') return SafetyOutlined
  return AuditOutlined
}

function removeStep(index) {
  confirmedSteps.value.splice(index, 1)
}

function backToInput() {
  error.value = ''
  phase.value = 'input'
}

function onRetry() {
  error.value = ''
  if (phase.value === 'input') {
    onAnalyze()
  } else if (phase.value === 'confirm') {
    onExecute()
  }
}

function onCancel() {
  orchestrationStore.cancel()
  retrying.value = false
  message.info('已停止前端轮询')
}

async function retryStep(step) {
  if (!step) return
  preservedEvents.value = (orchestrationStore.currentRecord?.events || []).filter(
    (e) => !(e.event_type === 'error' && e.step_id === step.step_id),
  )
  retrying.value = true
  try {
    const team = teamAgents.value.filter((a) => selectedAgentIds.value.has(a.id))
    await orchestrationStore.execute(target.value, team, [step])
  } catch {
    retrying.value = false
  }
}

async function onRerunTool(item) {
  if (!item) return
  const step = confirmedSteps.value.find((s) => s.step_id === item.step_id)
  if (!step) {
    message.warning('未找到对应步骤，无法重新执行')
    return
  }
  message.info(`重新执行: ${item.agent_name} · ${item.tool}`)
  await retryStep(step)
}

async function retryFailedSteps() {
  const steps = failedStepObjects.value
  if (steps.length === 0) return
  const failedIds = new Set(steps.map((s) => s.step_id))
  preservedEvents.value = (orchestrationStore.currentRecord?.events || []).filter(
    (e) => !(e.event_type === 'error' && failedIds.has(e.step_id)),
  )
  retrying.value = true
  try {
    const team = teamAgents.value.filter((a) => selectedAgentIds.value.has(a.id))
    await orchestrationStore.execute(target.value, team, steps)
  } catch {
    retrying.value = false
  }
}

function onToggleAgent(id) {
  const next = new Set(selectedAgentIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedAgentIds.value = next
}

function onAddAgent(id) {
  const agent = allAgents.value.find((a) => a.id === id)
  if (!agent || agent.status === 'development') return
  if (!teamAgents.value.find((a) => a.id === id)) {
    teamAgents.value = [...teamAgents.value, agent]
  }
  const next = new Set(selectedAgentIds.value)
  next.add(id)
  selectedAgentIds.value = next
}

function onReset() {
  orchestrationStore.reset()
  phase.value = 'input'
  teamAgents.value = []
  selectedAgentIds.value = new Set()
  confirmedSteps.value = []
  preservedEvents.value = []
  retrying.value = false
}

onMounted(async () => {
  try {
    const res = await listAgents()
    allAgents.value = Array.isArray(res) ? res : (res?.agents || [])
  } catch {
    /* handled by interceptor */
  }

  const { dimensionOptions, statusOptions } = useMdmDict()
  let hasFallback = false
  try {
    const roleOpts = await dimensionOptions('agent_role')
    if (roleOpts && roleOpts.length > 0) {
      ROLE_LABEL.value = Object.fromEntries(roleOpts.map((o) => [o.value, o.label]))
    } else {
      throw new Error('empty')
    }
  } catch {
    hasFallback = true
  }
  try {
    const statusOpts = await statusOptions('run')
    if (statusOpts && statusOpts.length > 0) {
      runStatusOptions.value = statusOpts
    } else {
      throw new Error('empty')
    }
  } catch {
    hasFallback = true
  }
  if (hasFallback) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})

onBeforeUnmount(() => {
  orchestrationStore.stopPolling()
})
</script>

<style scoped>
.orchestration-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0 8px;
}

.page-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.phase-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-tag {
  margin: 0;
  text-transform: none;
  letter-spacing: 0;
}

.task-input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.task-input-row .task-input-large {
  flex: 1;
  min-width: 0;
}

.task-input-action {
  flex-shrink: 0;
}

.input-hints {
  margin-bottom: 12px;
}

.hint-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.hint-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.hint-chip {
  cursor: pointer;
  margin: 0;
  touch-action: manipulation;
  transition: border-color var(--transition), color var(--transition), background var(--transition);
}

.hint-chip:hover {
  border-color: var(--primary-border);
  color: var(--primary);
  background: var(--primary-bg);
}

.reasoning-box {
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  margin-bottom: 16px;
}

.reasoning-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.reasoning-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.steps-section {
  margin-bottom: 16px;
}

.section-sub {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 400;
  margin-left: 8px;
}

.step-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-bg);
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.step-task {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Committee step styles */
.committee-step-item {
  background: linear-gradient(135deg, rgba(249, 115, 22, 0.04) 0%, rgba(249, 115, 22, 0.01) 100%);
  border-radius: 6px;
  padding: 2px 8px;
  margin: -2px -8px;
}

.committee-step-index {
  background: rgba(249, 115, 22, 0.12);
  color: var(--warning);
}

.flow-section {
  margin-top: 4px;
}

.flow-graph-wrap {
  height: 400px;
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  overflow: hidden;
}

.log-section {
  margin-top: 16px;
}

.result-alert {
  margin-top: 16px;
}

.failed-desc {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.retry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.team-count {
  font-variant-numeric: tabular-nums;
}

.panel-help-icon {
  color: var(--text-muted);
  font-size: 13px;
  cursor: help;
}

.team-empty-hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  margin: 8px 0;
  text-align: center;
}

.team-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.team-collapse {
  margin-bottom: 12px;
}

.team-collapse :deep(.ant-collapse-content-box) {
  padding: 10px 0 4px;
}

.team-group {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.panel-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}

.modal-search {
  margin-bottom: 12px;
}

.modal-agent-list {
  max-height: 480px;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.task-input-large :deep(.ant-input) {
  font-size: 14px;
  padding: 10px 12px;
}

.team-panel :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
}
</style>
