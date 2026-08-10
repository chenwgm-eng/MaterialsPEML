<template>
  <div class="project-new-page" :class="{ 'embedded': embedded }">
    <SectionHeader
      v-if="!embedded"
      title="项目新建"
      subtitle="输入项目目标 → AI 生成任务与交付物 → 人工确认 → 创建项目"
    >
      <template #extra>
        <a-button @click="onBack">
          <template #icon><ArrowLeftOutlined /></template>
          返回项目中心
        </a-button>
      </template>
    </SectionHeader>

    <div class="project-new-layout">
      <!-- 左侧：阶段卡片（目标输入 / 任务列表 / 创建完成） -->
      <div class="project-new-main">
    <!-- 步骤指示器 -->
    <a-steps :current="currentStepIndex" size="small" class="wizard-steps">
      <a-step title="目标输入" description="输入项目目标和基本信息" />
      <a-step title="任务拆解" description="AI 生成任务与交付物" />
      <a-step title="确认创建" description="确认并创建项目" />
    </a-steps>

    <!-- 阶段内容过渡动画 -->
    <transition :name="transitionName" mode="out-in">
      <div :key="phase" class="wizard-phase">
    <!-- 阶段 1：目标输入 -->
    <a-card v-if="phase === 'input'" :bordered="false" class="phase-card">
      <div class="phase-badge">阶段 1 · 目标输入</div>

      <a-form ref="formRef" layout="vertical" size="small" :model="form" :rules="formRules">
        <a-form-item label="项目名称" name="name" required>
          <a-input v-model:value="form.name" placeholder="如 高镍正极材料开发项目" />
        </a-form-item>

        <a-form-item label="研发目标" name="goal" required>
          <a-textarea
            v-model:value="form.goal"
            :rows="3"
            placeholder="例如：找到高离子电导率的固态电解质材料"
          />
          <div class="form-help">描述越具体，AI 拆解出的任务越贴合需求；可包含期望性能、应用场景等。</div>
        </a-form-item>

        <a-form-item label="目标应用" name="target_application" required>
          <a-input v-model:value="form.target_application" placeholder="如 锂镧锆氧（LLZO）固态电解质" />
        </a-form-item>

        <a-form-item label="负责人" name="owner" required>
          <a-select
            v-model:value="form.owner"
            :options="userOptions"
            placeholder="请选择负责人"
            show-search
            option-filter-prop="label"
            :loading="usersLoading"
            allow-clear
          />
        </a-form-item>

        <a-form-item label="项目截止日期" name="end_date">
          <a-date-picker
            v-model:value="form.end_date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
            placeholder="选择项目截止日期"
          />
        </a-form-item>

        <!-- 小屏幕回退：Agent 面板隐藏时显示此按钮 -->
        <a-form-item class="fallback-submit">
          <a-button
            type="primary"
            :loading="submitting"
            :disabled="!isFormValid"
            @click="onGenerateTasks"
          >
            <template #icon><ThunderboltOutlined /></template>
            {{ submitting ? 'Agent 执行中…' : 'Agent 执行' }}
          </a-button>
          <a-button v-if="submitting" size="small" @click="cancelDecompose">
            取消
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 阶段 2：任务列表确认与编辑 -->
    <a-card v-else-if="phase === 'tasks'" :bordered="false" class="phase-card">
      <div class="phase-header">
        <div class="phase-badge">阶段 2 · 任务列表</div>
        <a-space>
          <a-button size="small" @click="onRegenerate" :loading="submitting">
            <template #icon><RedoOutlined /></template>
            重新生成
          </a-button>
        </a-space>
      </div>

      <div class="tasks-summary">
        AI 已根据「{{ form.name }}」拆解出 <b>{{ tasks.length }}</b> 个任务，
        每个任务对应一个交付物（材料）及其目标属性。可在下方直接编辑后确认创建。
      </div>

      <div class="task-list">
        <div v-for="(task, idx) in tasks" :key="task._key" class="task-item">
          <div class="task-item-head">
            <span class="task-index">{{ idx + 1 }}</span>
            <a-input
              v-model:value="task.title"
              size="small"
              class="task-title-input"
              placeholder="任务标题"
            />
            <a-button type="text" danger size="small" aria-label="删除任务" @click="removeTask(idx)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>

          <div class="task-deliverable">
            <span class="field-label">交付物（材料）</span>
            <a-input
              v-model:value="task.deliverable"
              size="small"
              placeholder="如 锂镧锆氧（LLZO）固态电解质"
            />
          </div>

          <div class="task-props">
            <div class="field-label">目标属性</div>
            <div class="prop-editor">
              <div class="prop-row prop-header">
                <span class="prop-name">属性名</span>
                <span class="prop-dir">方向</span>
                <span class="prop-min">最小</span>
                <span class="prop-max">最大</span>
                <span class="prop-op"></span>
              </div>
              <div v-for="(p, pidx) in task.target_properties" :key="p._key" class="prop-row">
                <a-input
                  v-model:value="p.name"
                  size="small"
                  class="prop-name"
                  placeholder="如 ionic_conductivity"
                />
                <a-select v-model:value="p.direction" size="small" class="prop-dir">
                  <a-select-option value="maximize">最大化</a-select-option>
                  <a-select-option value="minimize">最小化</a-select-option>
                </a-select>
                <a-input
                  v-model:value="p._minText"
                  size="small"
                  class="prop-min prop-sci-input"
                  placeholder="如 1e-3"
                  @change="(e) => onPropNumberChange(p, 'min', e.target.value)"
                />
                <a-input
                  v-model:value="p._maxText"
                  size="small"
                  class="prop-max prop-sci-input"
                  placeholder="如 1e-2"
                  @change="(e) => onPropNumberChange(p, 'max', e.target.value)"
                />
                <a-button
                  type="text"
                  danger
                  size="small"
                  class="prop-op"
                  aria-label="删除属性"
                  @click="removeProperty(task, pidx)"
                >
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </div>
              <a-button size="small" type="dashed" block @click="addProperty(task)">
                <template #icon><PlusOutlined /></template>
                添加目标属性
              </a-button>
            </div>
          </div>
        </div>
      </div>

      <div class="confirm-actions">
        <a-button @click="onBackToInput" style="margin-right: 12px">返回上一步</a-button>
        <a-button @click="onCancel" style="margin-right: 12px">取消</a-button>
        <a-button
          type="primary"
          :loading="saving"
          :disabled="tasks.length === 0"
          @click="onConfirmSave"
        >
          <template #icon><CheckOutlined /></template>
          确认并创建项目
        </a-button>
      </div>
    </a-card>

    <!-- 阶段 3：创建完成 -->
    <a-card v-else :bordered="false" class="phase-card">
      <div class="phase-badge">阶段 3 · 创建完成</div>
      <a-result
        status="success"
        :title="`项目「${savedProjectName}」已创建`"
        sub-title="项目任务已生成，可在项目中心查看并启动执行。"
      >
        <template #extra>
          <a-button v-if="!embedded" type="primary" @click="goToProjects">
            <template #icon><ArrowLeftOutlined /></template>
            返回项目中心
          </a-button>
          <a-button v-else type="primary" @click="onResetForEmbedded">
            继续新建下一个
          </a-button>
        </template>
      </a-result>
    </a-card>
      </div>
    </transition>
      </div>

      <!-- 右侧：项目经理 Agent 详情面板 -->
      <aside class="pm-agent-panel">
        <a-spin :spinning="agentLoading">
          <div v-if="pmAgent" class="pm-agent-card">
            <div class="pm-panel-title">项目经理 Agent</div>

            <!-- 头像 + 名称 + 角色标签 -->
              <div class="pm-head">
                <div class="pm-avatar">
                  <component :is="pmAgentIcon" aria-hidden="true" />
                </div>
              <div class="pm-info">
                <div class="pm-name">{{ pmAgent.name || '项目经理' }}</div>
                <div class="pm-tags-row">
                  <a-tag color="blue" class="pm-role-tag">项目经理</a-tag>
                  <a-tag v-if="pmAgent.is_builtin" color="default" class="pm-builtin-tag">内置</a-tag>
                </div>
              </div>
            </div>

            <!-- 职责描述 -->
            <div class="pm-section">
              <div class="pm-section-title">职责描述</div>
              <div class="pm-desc">{{ pmAgent.description || '—' }}</div>
            </div>

            <!-- 专长 -->
            <div v-if="pmAgent.expertise?.length" class="pm-section">
              <div class="pm-section-title">专长</div>
              <div class="pm-tags">
                <a-tag v-for="e in pmAgent.expertise" :key="e" size="small" class="pm-tag">{{ e }}</a-tag>
              </div>
            </div>

            <!-- 基本信息 -->
            <div class="pm-section">
              <div class="pm-section-title">基本信息</div>
              <a-descriptions size="small" :column="1" :colon="false" class="pm-desc-list">
                <a-descriptions-item label="模型">{{ pmAgent.llm_model || '—' }}</a-descriptions-item>
                <a-descriptions-item label="状态">
                  <a-tag v-if="pmAgent.is_builtin" color="blue" size="small">内置可用</a-tag>
                  <span v-else>{{ pmAgent.status || '—' }}</span>
                </a-descriptions-item>
                <a-descriptions-item label="工具数">{{ pmAgent.tools?.length || 0 }}</a-descriptions-item>
              </a-descriptions>
            </div>

            <!-- 能力信息（V2） -->
            <div v-if="pmAgent.capabilities?.length" class="pm-section">
              <div class="pm-section-title">能力</div>
              <div class="pm-tags">
                <a-tag v-for="c in pmAgent.capabilities" :key="c" size="small" class="pm-tag">{{ c }}</a-tag>
              </div>
            </div>

            <!-- 自主等级 -->
            <div v-if="pmAgent.max_autonomy_level" class="pm-section">
              <div class="pm-section-title">自主等级</div>
              <a-tag color="orange" size="small" class="pm-tag">
                {{ autonomyLabel(pmAgent.max_autonomy_level) }}
              </a-tag>
            </div>

            <!-- 禁止动作 -->
            <div v-if="pmAgent.prohibited_actions?.length" class="pm-section">
              <div class="pm-section-title">禁止动作</div>
              <div class="pm-tags">
                <a-tag v-for="a in pmAgent.prohibited_actions" :key="a" color="red" size="small" class="pm-tag">
                  {{ a }}
                </a-tag>
              </div>
            </div>

            <!-- Agent 执行按钮：调用项目经理 Agent 拆解项目目标 -->
            <div class="pm-action-block">
              <a-button
                type="primary"
                block
                :loading="submitting"
                :disabled="!pmAgent || !isFormValid"
                @click="onGenerateTasks"
              >
                <template #icon><ThunderboltOutlined /></template>
                {{ submitting ? 'Agent 执行中…' : 'Agent 执行' }}
              </a-button>
              <div v-if="submitting" class="pm-action-hint">
                项目经理正在分析目标并拆解任务，通常需要 10-30 秒
                <a-button type="link" size="small" @click="cancelDecompose">取消</a-button>
              </div>
              <div v-else-if="!isFormValid" class="pm-action-hint">
                请先在左侧填写项目名称、研发目标、目标应用与负责人
              </div>
            </div>
          </div>
          <EmptyState
            v-else-if="!agentLoading"
            type="data"
            description="暂无项目经理 Agent"
          />
        </a-spin>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ThunderboltOutlined,
  ArrowLeftOutlined,
  RedoOutlined,
  PlusOutlined,
  DeleteOutlined,
  CheckOutlined,
} from '@ant-design/icons-vue'
import SectionHeader from '@/components/SectionHeader.vue'
import client from '@/api/client'
import { listAgents } from '@/api/agents'
import { listUsers } from '@/api/auth'
import { required, lengthRange } from '@/utils/formRules'
import EmptyState from '@/components/EmptyState.vue'
import { resolveAgentIcon } from '@/utils/agentAvatar'
import { useLeaveGuard } from '@/composables/useLeaveGuard'

// props.embedded: 嵌入到 Projects.vue 右侧面板使用时为 true，
// 此时隐藏顶部 SectionHeader 并通过 emit 与父组件通信，避免整页跳转
const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['created', 'cancel'])

const router = useRouter()

const phase = ref('input') // input | tasks | done
const transitionName = ref('slide-next')
const currentStepIndex = computed(() => {
  if (phase.value === 'input') return 0
  if (phase.value === 'tasks') return 1
  return 2
})
const submitting = ref(false)
const saving = ref(false)
const savedProjectName = ref('')
// D5 修复：AI 拆解支持取消，避免长时间卡住
let decomposeAbort = null

// P1-FORM-001：表单校验规则
const formRef = ref()
const formRules = {
  name: [...required('请输入项目名称'), ...lengthRange(3, 100, '项目名称长度需在 3-100 个字符之间')],
  goal: required('请输入研发目标'),
  target_application: required('请输入目标应用'),
  owner: required('请输入负责人'),
}

// ── 项目经理 Agent 信息（右侧面板展示） ──
const pmAgent = ref(null)
const agentLoading = ref(false)
const pmAgentIcon = computed(() => resolveAgentIcon(pmAgent.value?.avatar))

const AUTONOMY_LABELS = {
  L0: 'L0 · 仅建议（人工执行）',
  L1: 'L1 · 受监督执行（需人工确认）',
  L2: 'L2 · 自主执行（事后报备）',
  L3: 'L3 · 完全自主',
}

function autonomyLabel(level) {
  if (!level) return ''
  return AUTONOMY_LABELS[level] || level
}

async function loadPmAgent() {
  agentLoading.value = true
  try {
    const res = await listAgents()
    const list = Array.isArray(res) ? res : (res?.agents || [])
    // 优先匹配 role === 'project_manager'，回退到 id 包含 project_manager
    pmAgent.value =
      list.find((a) => a.role === 'project_manager') ||
      list.find((a) => a.id && a.id.includes('project_manager')) ||
      null
  } catch {
    pmAgent.value = null
  } finally {
    agentLoading.value = false
  }
}

// ── 系统用户列表（负责人下拉） ──
const userOptions = ref([])
const usersLoading = ref(false)

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await listUsersBrief()
    const list = Array.isArray(res) ? res : (res?.users || [])
    userOptions.value = list.map(u => ({
      label: u.display_name || u.username,
      value: u.user_id,
    }))
  } catch {
    userOptions.value = []
  } finally {
    usersLoading.value = false
  }
}

onMounted(() => {
  loadPmAgent()
  loadUsers()
})

const form = ref({
  name: '',
  goal: '',
  target_application: '',
  owner: '',
  end_date: '',
})

// T15 离开保护：表单有输入即视为 dirty，离开/刷新需确认
const { markDirty, markClean } = useLeaveGuard()
watch(
  form,
  (v) => {
    if (v.name || v.goal || v.target_application || v.owner || v.end_date) markDirty()
  },
  { deep: true },
)

// 表单必填项整体校验（后端同样校验，防止空值/占位符脏数据）
const isFormValid = computed(
  () =>
    !!form.value.name.trim() &&
    !!form.value.goal.trim() &&
    !!form.value.target_application.trim() &&
    !!form.value.owner.trim(),
)

// AI 拆解出的任务列表，每项含 task_id / title / deliverable / target_properties
const tasks = ref([])

// ── 阶段 1 → 2：生成任务（调用 AI 拆解） ──
async function onGenerateTasks() {
  if (!isFormValid.value) return
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  // D5 修复：支持取消 AI 拆解请求，避免长时间卡住
  decomposeAbort = new AbortController()
  try {
    const payload = {
      name: form.value.name.trim(),
      goal: form.value.goal.trim(),
      end_date: form.value.end_date || '',
      // 携带项目经理 Agent 的 ID，后端将使用该 Agent 的 llm_model 与人设进行调用
      agent_id: pmAgent.value?.id || '',
    }
    // AI 拆解可能耗时较长，放宽超时到 120s，并支持取消
    const data = await client.post('/projects/decompose', payload, {
      timeout: 120000,
      signal: decomposeAbort.signal,
    })
    const list = Array.isArray(data?.tasks) ? data.tasks : []
    if (!list.length) {
      message.warning('AI 未能拆解出任务，请尝试更具体的目标描述')
      return
    }
    // 为每个属性补上 _minText/_maxText 以支持科学计数法输入
    tasks.value = list.map((t) => normalizeTask(t))
    transitionName.value = 'slide-next'
    phase.value = 'tasks'
    message.success(`已生成 ${list.length} 个任务`)
  } catch (err) {
    // 用户主动取消时静默处理
    if (err?.code === 'ERR_CANCELED' || err?.message === 'canceled') return
    // 其他错误由 axios 拦截器统一提示
  } finally {
    submitting.value = false
    decomposeAbort = null
  }
}

// D5 修复：取消正在进行的 AI 拆解
function cancelDecompose() {
  if (decomposeAbort) {
    decomposeAbort.abort()
    submitting.value = false
    decomposeAbort = null
    message.info('已取消 AI 拆解')
  }
}

function normalizeTask(t) {
  const props = Array.isArray(t.target_properties) ? t.target_properties : []
  // 为每个任务生成前端唯一 key（_key），避免 v-for 因 task_id 为空/重复导致渲染错误
  return {
    task_id: t.task_id || '',
    _key: `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: t.title || '',
    deliverable: t.deliverable || '',
    target_properties: props.map((p) => ({
      _key: `prop-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: p.name || '',
      direction: p.direction === 'minimize' ? 'minimize' : 'maximize',
      min: p.min ?? null,
      max: p.max ?? null,
      _minText: p.min != null ? String(p.min) : '',
      _maxText: p.max != null ? String(p.max) : '',
    })),
  }
}

// ── 任务/属性编辑 ──
function removeTask(idx) {
  tasks.value.splice(idx, 1)
}

function addProperty(task) {
  task.target_properties.push({
    _key: `prop-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: '',
    direction: 'maximize',
    min: null,
    max: null,
    _minText: '',
    _maxText: '',
  })
}

function removeProperty(task, pidx) {
  task.target_properties.splice(pidx, 1)
}

function onPropNumberChange(prop, field, text) {
  const trimmed = (text || '').trim()
  if (trimmed === '') {
    prop[field] = null
    return
  }
  const num = Number(trimmed)
  if (!Number.isNaN(num)) {
    prop[field] = num
  }
}

// ── 阶段 2 → 1：返回上一步（保留任务数据，便于修改目标后重新生成） ──
function onBackToInput() {
  transitionName.value = 'slide-prev'
  phase.value = 'input'
}

// ── 阶段 2 → 1：重新生成（清空任务列表） ──
function onRegenerate() {
  transitionName.value = 'slide-prev'
  phase.value = 'input'
  tasks.value = []
}

// ── 阶段 2 → 3：保存项目 ──
async function onConfirmSave() {
  if (tasks.value.length === 0) return
  saving.value = true
  try {
    // 清理属性中的临时字段，转换为后端可接受的格式
    const cleanTasks = tasks.value.map((t) => ({
      task_id: t.task_id,
      title: t.title.trim(),
      deliverable: t.deliverable.trim(),
      target_properties: t.target_properties
        .filter((p) => p.name.trim())
        .map((p) => ({
          name: p.name.trim(),
          direction: p.direction,
          min: p.min,
          max: p.max,
        })),
    }))

    const projectPayload = {
      name: form.value.name.trim(),
      target_application: form.value.target_application.trim(),
      current_stage: '立项',
      target_properties: [],
      owner: form.value.owner.trim(),
      notes: form.value.goal.trim(),
      end_date: form.value.end_date || '',
      tasks: cleanTasks,
    }
    const project = await client.post('/projects', projectPayload)
    savedProjectName.value = project.name || form.value.name
    markClean()
    transitionName.value = 'slide-next'
    phase.value = 'done'
    message.success('项目创建成功')
    // 嵌入模式：通知父组件新项目已创建，便于刷新左侧列表
    if (props.embedded) {
      emit('created', project)
    }
  } catch {
    // 错误信息由 axios 拦截器统一提示
  } finally {
    saving.value = false
  }
}

function goToProjects() {
  router.push('/projects')
}

// 取消：嵌入模式下 emit cancel，路由模式返回项目中心
function onCancel() {
  if (props.embedded) {
    emit('cancel')
    return
  }
  router.push('/projects')
}

function onBack() {
  router.push('/projects')
}

// 嵌入模式下"继续新建下一个"：重置表单回到阶段 1
function onResetForEmbedded() {
  form.value = { name: '', goal: '', end_date: '' }
  tasks.value = []
  savedProjectName.value = ''
  transitionName.value = 'slide-prev'
  phase.value = 'input'
}
</script>

<style scoped>
.project-new-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0 var(--space-sm);
  display: flex;
  flex-direction: column;
}

/* 嵌入到 Projects.vue 右侧面板时：占满高度并允许纵向滚动 */
.project-new-page.embedded {
  height: 100%;
  overflow: hidden;
  padding: var(--space-md);
}

/* 两列布局：左侧阶段卡片 + 右侧项目经理 Agent 详情 */
.project-new-layout {
  display: flex;
  gap: var(--space-md);
  align-items: flex-start;
  flex: 1;
  min-height: 0;
}

/* 嵌入模式下：两列等高、独立滚动 */
.project-new-page.embedded .project-new-layout {
  align-items: stretch;
}

.project-new-main {
  flex: 1;
  min-width: 0;
  padding-right: var(--space-xs);
}

.project-new-page.embedded .project-new-main {
  overflow-y: auto;
  height: 100%;
}

/* 右侧项目经理 Agent 面板：固定宽度 */
.pm-agent-panel {
  flex-shrink: 0;
  width: 300px;
}

.project-new-page.embedded .pm-agent-panel {
  overflow-y: auto;
  height: 100%;
}

.phase-card {
  background: var(--realsee-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
}

/* 非嵌入模式：SectionHeader 与卡片之间留白 */
.project-new-page:not(.embedded) .phase-card {
  margin-top: var(--space-md);
}

.phase-card :deep(.ant-card-body) {
  padding: var(--space-xl);
}

.phase-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--primary);
  margin-bottom: var(--space-lg);
}

.phase-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-lg);
}

.phase-header .phase-badge {
  margin-bottom: 0;
}

.form-help {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-top: var(--space-xs);
  line-height: 1.5;
}

.app-loading-hint {
  margin-left: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

/* 任务列表 */
.tasks-summary {
  padding: var(--space-md);
  background: var(--light-bg-hover);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-md);
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: var(--space-lg);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.task-item {
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--realsee-surface);
}

.task-item-head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.task-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary-bg);
  color: var(--primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  flex-shrink: 0;
}

.task-title-input {
  flex: 1;
}

.task-deliverable {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.task-deliverable .field-label {
  flex-shrink: 0;
  width: 120px;
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.task-deliverable :deep(.ant-input) {
  flex: 1;
}

.task-props .field-label {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-bottom: var(--space-xs);
}

/* 目标属性编辑器 */
.prop-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.prop-row {
  display: grid;
  grid-template-columns: 1.8fr 1fr 0.8fr 0.8fr 32px;
  gap: var(--space-sm);
  align-items: center;
}

.prop-sci-input :deep(input) {
  font-family: var(--font-family-mono, "JetBrains Mono", Consolas, monospace);
  font-variant-numeric: tabular-nums;
}

.prop-header {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  padding: 0 0 2px;
}

.prop-header span {
  font-weight: var(--font-weight-semibold);
}

.confirm-actions {
  margin-top: var(--space-xl);
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border-light);
}

/* ── 右侧项目经理 Agent 面板 ── */
.pm-agent-card {
  background: var(--realsee-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.pm-panel-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-muted);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid var(--border-light);
}

.pm-head {
  display: flex;
  gap: var(--space-md);
  align-items: center;
}

.pm-avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
  line-height: 1;
}

.pm-info {
  flex: 1;
  min-width: 0;
}

.pm-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin-bottom: 4px;
}

.pm-tags-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.pm-role-tag,
.pm-builtin-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  border: none;
}

.pm-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pm-section-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--text-muted);
  letter-spacing: 0.3px;
}

.pm-desc {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  line-height: 1.6;
}

.pm-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pm-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
}

.pm-desc-list :deep(.ant-descriptions-item-label) {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  width: 60px;
}

.pm-desc-list :deep(.ant-descriptions-item-content) {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

/* Agent 执行按钮区块：与上方信息分隔，固定在面板底部 */
.pm-action-block {
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.pm-action-hint {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  line-height: 1.5;
  text-align: center;
}

/* 小屏幕回退按钮：默认隐藏，Agent 面板隐藏时显示 */
.fallback-submit {
  display: none;
}

@media (max-width: 1100px) {
  /* 中等屏幕：隐藏右侧 Agent 面板，避免挤压主表单 */
  .pm-agent-panel {
    display: none;
  }
  .project-new-layout {
    display: block;
  }
  .project-new-main {
    padding-right: 0;
  }
  /* 显示回退按钮 */
  .fallback-submit {
    display: block;
  }
  /* 嵌入模式下恢复整页滚动 */
  .project-new-page.embedded {
    overflow-y: auto;
  }
  .project-new-page.embedded .project-new-main {
    height: auto;
    overflow: visible;
  }
}

@media (max-width: 768px) {
  .prop-row {
    grid-template-columns: 1fr 1fr;
  }
  .prop-header {
    display: none;
  }
  .task-deliverable {
    flex-direction: column;
    align-items: flex-start;
  }
  .task-deliverable .field-label {
    width: auto;
  }
}

/* ── 步骤指示器 ── */
.wizard-steps {
  margin-bottom: var(--space-lg);
}

.project-new-page:not(.embedded) .wizard-steps {
  margin-top: var(--space-md);
}

/* 嵌入模式下步骤指示器紧凑显示 */
.project-new-page.embedded .wizard-steps {
  margin-top: 0;
}

/* 阶段内容容器：确保 transition 平滑 */
.wizard-phase {
  width: 100%;
}

/* ── 阶段过渡动画 ── */
.slide-next-enter-active,
.slide-next-leave-active,
.slide-prev-enter-active,
.slide-prev-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.slide-next-enter-from {
  transform: translateX(20px);
  opacity: 0;
}

.slide-next-leave-to {
  transform: translateX(-20px);
  opacity: 0;
}

.slide-prev-enter-from {
  transform: translateX(-20px);
  opacity: 0;
}

.slide-prev-leave-to {
  transform: translateX(20px);
  opacity: 0;
}
</style>
