<template>
  <div class="research-page">
    <SectionHeader
      title="研发工作台"
      subtitle="统一研发请求入口：目标输入 → 计划确认 → 执行与结果"
    >
      <template #extra>
        <a-space>
          <!-- 审查意见0726：智能编排改为同页内模式切换，不再整页跳转，避免丢失已填写内容 -->
          <a-tooltip :title="mode === 'standard' ? '让 AI 自动组建 Agent 小队执行任务（agentic 模式）' : '返回标准研发流程'">
            <a-button size="small" :type="mode === 'orchestration' ? 'primary' : 'default'" @click="toggleMode">
              <RobotOutlined /> {{ mode === 'orchestration' ? '返回标准模式' : '智能编排模式' }}
            </a-button>
          </a-tooltip>
          <a-button v-if="phase !== 'input' && mode === 'standard'" @click="onReset">
            <template #icon><ReloadOutlined /></template>
            重新开始
          </a-button>
        </a-space>
      </template>
    </SectionHeader>

    <!-- 智能编排模式：内嵌 Orchestration 组件，保留当前页状态 -->
    <Orchestration v-if="mode === 'orchestration'" />

    <!-- 标准研发流程模式 -->
    <div v-if="mode === 'standard'">
    <!-- 阶段 1：目标输入 -->
    <a-card v-if="phase === 'input'" :bordered="false" class="phase-card">
      <div class="phase-badge">阶段 1 · 目标输入</div>

      <a-form layout="vertical" size="small">
        <a-form-item label="研发目标" required>
          <a-textarea
            id="rw-goal-input"
            v-model:value="form.goal"
            :rows="3"
            placeholder="例如：找到高离子电导率的固态电解质材料"
          />
          <div class="form-help">描述越具体，生成的计划越贴合需求；可包含期望性能、应用场景等。</div>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="材料体系">
              <a-select
                id="rw-scope-select"
                v-model:value="form.material_system"
                placeholder="选择材料体系"
                :loading="materialSystemLoading"
              >
                <a-select-option
                  v-for="opt in materialSystemOptions"
                  :key="opt.value"
                  :value="opt.value"
                >{{ opt.label }}</a-select-option>
              </a-select>
              <div class="form-help">体系由当前领域包配置驱动，系统据此匹配元素空间与工具链。</div>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="执行偏好">
              <a-radio-group
                id="rw-preference-radio"
                v-model:value="form.preference"
                button-style="solid"
                size="small"
              >
                <a-radio-button
                  v-for="mode in EXECUTION_PREFERENCE_MODES"
                  :key="mode.value"
                  :value="mode.value"
                >{{ mode.label }}</a-radio-button>
              </a-radio-group>
              <a-alert
                v-if="currentPreferenceDescription"
                type="info"
                :message="currentPreferenceDescription"
                show-icon
                class="preference-alert"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="项目 ID">
              <!-- 项目 ID 自动从全局当前项目上下文获取（ProjectContextBar 中切换项目即同步） -->
              <a-input :value="currentProjectDisplay" readonly placeholder="未选择项目" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="目标属性">
          <div class="prop-editor">
            <div class="prop-row prop-header">
              <span class="prop-name">属性名</span>
              <span class="prop-unit">单位</span>
              <span class="prop-dir">方向</span>
              <span class="prop-min">最小</span>
              <span class="prop-max">最大</span>
              <span class="prop-weight">权重</span>
              <span class="prop-op"></span>
            </div>
            <div v-for="(p, idx) in form.target_properties" :key="idx" class="prop-row">
              <a-select
                v-model:value="p.name"
                size="small"
                show-search
                :options="propOptions"
                :filter-option="filterPropOption"
                placeholder="从属性字典选择"
                class="prop-name"
                aria-label="属性名"
              />
              <span class="prop-unit prop-unit-value">{{ propUnitMap[p.name] || '—' }}</span>
              <a-select v-model:value="p.direction" size="small" class="prop-dir" aria-label="优化方向">
                <a-select-option value="maximize">最大化</a-select-option>
                <a-select-option value="minimize">最小化</a-select-option>
              </a-select>
              <a-input
                v-model:value="p.min"
                size="small"
                class="prop-min prop-sci-input"
                placeholder="如 1e-3"
                aria-label="最小值"
                @change="(e) => onPropNumberChange(p, 'min', e.target.value)"
              />
              <a-input
                v-model:value="p.max"
                size="small"
                class="prop-max prop-sci-input"
                placeholder="如 1e-2"
                aria-label="最大值"
                @change="(e) => onPropNumberChange(p, 'max', e.target.value)"
              />
              <a-input-number v-model:value="p.weight" size="small" class="prop-weight" :min="0" :max="1" :step="0.1" aria-label="权重" />
              <a-button type="text" danger size="small" class="prop-op" aria-label="删除属性" @click="removeProperty(idx)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button size="small" type="dashed" block @click="addProperty">
              <template #icon><PlusOutlined /></template>
              添加目标属性
            </a-button>
          </div>
          <div class="form-help">属性名统一取自属性字典（材料属性）；方向和阈值用于筛选与排序候选材料。最小/最大值支持科学计数法（如 1e-3 表示 1×10⁻³）。</div>
        </a-form-item>

        <a-form-item>
          <a-button
            id="rw-generate-btn"
            type="primary"
            :loading="submitting"
            :disabled="!form.goal.trim()"
            @click="onGeneratePlan"
          >
            <template #icon><ThunderboltOutlined /></template>
            {{ submitting ? 'AI 正在生成计划…' : '生成研发计划' }}
          </a-button>
          <span v-if="submitting" class="app-loading-hint">AI 正在分析目标并匹配工具链，通常需要 10-30 秒</span>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 阶段 2：系统计划卡 -->
    <a-card v-else-if="phase === 'confirm'" :bordered="false" class="phase-card">
      <div class="phase-header">
        <div class="phase-badge">阶段 2 · 系统计划</div>
        <a-button size="small" @click="onRegenerate">
          <template #icon><RedoOutlined /></template>
          重新生成
        </a-button>
      </div>

      <template v-if="plan">
        <div class="plan-meta">
          <a-tag :color="profileColor(plan.execution_profile)">{{ profileLabel(plan.execution_profile) }}</a-tag>
          <a-tag>步骤 {{ plan.steps?.length || 0 }}</a-tag>
          <a-tag v-if="plan.status" :color="planStatusColor(plan.status)">{{ planStatusLabel(plan.status) }}</a-tag>
          <span class="plan-rationale">{{ plan.rationale }}</span>
        </div>

        <SectionHeader title="执行步骤" />
        <a-timeline class="plan-steps">
          <a-timeline-item v-for="(s, i) in (plan.steps || [])" :key="s.step_id || i" color="blue">
            <div class="step-head">
              <span class="step-index">{{ i + 1 }}</span>
              <span class="step-action">{{ actionLabel(s.action) }}</span>
              <a-tag size="small" color="blue">{{ agentLabel(s.agent_id) }}</a-tag>
              <a-tag size="small" :color="autonomyColor(s.autonomy_level)">{{ s.autonomy_level }}</a-tag>
            </div>
            <div class="step-tools" v-if="s.allowed_tool_aliases?.length">
              <a-tag v-for="a in s.allowed_tool_aliases" :key="a" size="small">{{ a }}</a-tag>
            </div>
          </a-timeline-item>
        </a-timeline>

        <a-row :gutter="16" class="plan-footer">
          <a-col :span="12">
            <SectionHeader title="预估预算" />
            <div class="budget-grid">
              <MetricCard :value="plan.estimated_budget?.tokens ?? 0" label="Tokens" />
              <MetricCard :value="plan.estimated_budget?.scp_calls ?? 0" label="SCP 调用" />
              <MetricCard :value="plan.estimated_budget?.dft_jobs ?? 0" label="DFT 任务" />
            </div>
          </a-col>
          <a-col :span="12">
            <SectionHeader title="风险摘要" />
            <div class="risk-card">{{ plan.risk_summary || '无风险提示' }}</div>
          </a-col>
        </a-row>

        <div class="confirm-actions">
          <a-button
            id="rw-confirm-btn"
            type="primary"
            :loading="executing"
            :disabled="plan.status === 'invalid'"
            @click="onConfirmExecute"
          >
            <template #icon><PlayCircleOutlined /></template>
            确认执行
          </a-button>
        </div>

        <!-- P0-101: 计划生成后即提供派生子任务入口，目标与约束参数随路由传递，避免下游重复录入 -->
        <div class="derived-section derived-section-confirm">
          <span class="derived-label">或直接进入派生子任务（已自动带入目标与属性）：</span>
          <a-space wrap>
            <a-button size="small" @click="openDerived('discovery')">
              <template #icon><ExperimentOutlined /></template>
              材料发现
            </a-button>
            <a-button size="small" @click="openDerived('prediction')">
              <template #icon><LineChartOutlined /></template>
              临时材料性能预测
            </a-button>
            <a-button size="small" @click="openDerived('synthesis')">
              <template #icon><BranchesOutlined /></template>
              合成路径
            </a-button>
            <a-button size="small" @click="openDerived('ecml')">
              <template #icon><SyncOutlined /></template>
              闭环迭代
            </a-button>
          </a-space>
        </div>
      </template>
    </a-card>

    <!-- 阶段 3：执行与结果 -->
    <a-card v-else :bordered="false" class="phase-card">
      <div class="phase-header">
        <div class="phase-badge">阶段 3 · 执行与结果</div>
        <a-space>
          <a-tag v-if="runStatus" :color="planStatusColor(runStatus)">{{ planStatusLabel(runStatus) }}</a-tag>
          <a-button size="small" :loading="replanning" @click="onReplan">
            <template #icon><RedoOutlined /></template>
            重新规划
          </a-button>
        </a-space>
      </div>

      <a-alert
        v-if="executing"
        type="info"
        message="正在执行研发计划…"
        :description="executingHint"
        show-icon
        style="margin-bottom: 16px"
      />
      <a-progress
        v-if="executing && plan?.steps?.length"
        :percent="executionProgress"
        :status="executing ? 'active' : 'normal'"
        style="margin-bottom: 16px"
      />

      <SectionHeader title="步骤进度" />
      <a-steps
        v-if="plan?.steps?.length"
        size="small"
        :current="currentStepIndex"
        :status="stepsStatus"
      >
        <a-step
          v-for="(s, i) in plan.steps"
          :key="s.step_id || i"
          :title="actionLabel(s.action)"
          :status="stepAStepStatus(stepStatusMap[s.step_id])"
        />
      </a-steps>

      <SectionHeader title="执行事件流" style="margin-top: 20px" />
      <a-timeline v-if="events.length" class="event-stream">
        <a-timeline-item
          v-for="(e, i) in events"
          :key="i"
          :color="eventColor(e)"
        >
          <div class="event-head">
            <a-tag size="small" :color="eventColor(e)">{{ eventLabel(e.event_type) }}</a-tag>
            <span v-if="e.step_id" class="event-step">{{ e.step_id }}</span>
            <span v-if="e.agent_id" class="event-agent">{{ agentLabel(e.agent_id) }}</span>
            <span class="event-time">{{ shortTime(e.timestamp) }}</span>
          </div>
          <div v-if="e.content" class="event-content">{{ e.content }}</div>
          <div v-if="e.action" class="event-content">{{ actionLabel(e.action) }}</div>
        </a-timeline-item>
      </a-timeline>
      <EmptyAction
        v-else
        title="暂无执行事件"
        description="点击确认执行后，系统会实时返回步骤事件。"
        action-text=""
        :icon="markRaw(ClockCircleOutlined)"
      />

      <!-- 结果摘要 -->
      <div v-if="!executing && runResult" class="result-section">
        <SectionHeader title="结果摘要" />
        <a-descriptions size="small" bordered :column="3">
          <a-descriptions-item label="状态">{{ planStatusLabel(runResult.status) }}</a-descriptions-item>
          <a-descriptions-item label="完成步骤">{{ runResult.completed_steps?.length || 0 }} / {{ plan?.steps?.length || 0 }}</a-descriptions-item>
          <a-descriptions-item label="计划 ID">{{ runResult.plan_id }}</a-descriptions-item>
        </a-descriptions>

        <SectionHeader title="业务解释" style="margin-top: 16px">
          <template #extra>
            <a-button size="small" type="link" :loading="explaining" @click="fetchExplain">刷新</a-button>
          </template>
        </SectionHeader>
        <a-alert
          v-if="explainData"
          :type="runResult.status === 'completed' ? 'success' : 'info'"
          :message="explainData.explanation"
          show-icon
        />

        <SectionHeader title="证据卡" style="margin-top: 16px" />
        <a-collapse :bordered="false" class="evidence-collapse">
          <a-collapse-panel
            v-for="(s, i) in completedStepsWithEvidence"
            :key="s.step_id || i"
            :header="evidenceHeader(s)"
          >
            <div class="evidence-body">
              <div class="evidence-row">
                <span class="evidence-label">来源类型</span>
                <a-tag size="small" :color="sourceColor(evidenceOf(s).source_type)">{{ sourceLabel(evidenceOf(s).source_type) }}</a-tag>
              </div>
              <div class="evidence-row">
                <span class="evidence-label">结论</span>
                <span>{{ evidenceOf(s).conclusion }}</span>
              </div>
              <div class="evidence-row">
                <span class="evidence-label">局限性</span>
                <span>{{ evidenceOf(s).limitations || '无' }}</span>
              </div>
              <div class="evidence-row">
                <span class="evidence-label">版本</span>
                <span class="evidence-version">{{ evidenceOf(s).version }}</span>
              </div>
              <div class="evidence-detail">
                <span class="evidence-label">实现细节</span>
                <pre class="evidence-raw">{{ evidenceOf(s).detail }}</pre>
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
        <EmptyAction
          v-if="!completedStepsWithEvidence.length"
          title="暂无证据"
          description="步骤执行完成后会在这里汇总证据。"
          action-text=""
          :icon="markRaw(InboxOutlined)"
        />
      </div>
    </a-card>

    </div><!-- /标准研发流程模式 -->

    <OnboardingTooltip
      :open="tourOpen"
      :steps="tourSteps"
      storage-key="research_onboarding_seen"
      @close="onTourClose"
      @finish="onTourFinish"
    />
  </div>
</template>

<script setup>
import { ref, computed, markRaw, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import Orchestration from '@/views/Orchestration.vue'
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RedoOutlined,
  PlusOutlined,
  DeleteOutlined,
  ClockCircleOutlined,
  InboxOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  BranchesOutlined,
  SyncOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyAction from '@/components/EmptyAction.vue'
import MetricCard from '@/components/MetricCard.vue'
import OnboardingTooltip from '@/components/OnboardingTooltip.vue'
import { researchApi } from '@/api/research'
import { getFields } from '@/api/properties'
import { useTaskStore } from '@/stores/tasks'
import { buildDerivedQuery } from '@/utils/researchContext'
import { RESEARCH_MATERIAL_SCOPES, EXECUTION_PREFERENCE_MODES } from '@/constants/materialTypes'
import { useProjectContextStore } from '@/stores/projectContext'
import { getConfig } from '@/api/system'
import client from '@/api/client'

const taskStore = useTaskStore()
const projectContextStore = useProjectContextStore()
const router = useRouter()

const phase = ref('input') // input | confirm | execute
// 审查意见0726：同页内模式切换，避免整页跳转丢失已填写内容
const mode = ref('standard') // standard | orchestration
function toggleMode() {
  mode.value = mode.value === 'standard' ? 'orchestration' : 'standard'
}
const submitting = ref(false)
const executing = ref(false)
const replanning = ref(false)
const explaining = ref(false)

const form = ref({
  goal: '',
  material_scope: 'crystal', // 材料类型枚举（crystal/polymer），由领域包驱动
  material_system: '', // 材料体系名（领域包 material_systems.name），下拉选择
  target_properties: [],
  preference: 'balanced',
  project_id: '',
})

// 项目 ID 自动从全局当前项目上下文获取（ProjectContextBar 中切换项目即同步）
watch(
  () => projectContextStore.currentProjectId,
  (newId) => {
    form.value.project_id = newId || ''
  },
  { immediate: true },
)

const currentProjectDisplay = computed(() => {
  const p = projectContextStore.currentProject
  return p?.name || p?.project_id || ''
})

const currentPreferenceDescription = computed(() => {
  const mode = EXECUTION_PREFERENCE_MODES.find((m) => m.value === form.value.preference)
  return mode?.description || ''
})

// 材料类型：完全由领域注册表（/domain-packs）驱动。
// 与 material_system（体系名）解耦——material_scope 只用于下游路由/生成通道选择。
const domainPacks = ref([])
const materialKind = computed(() => {
  const active = domainPacks.value.find((p) => p.is_active)
  const primary = active || domainPacks.value.find((p) => p.material_kind) || domainPacks.value[0]
  return primary?.material_kind || 'crystal'
})

async function loadDomainPacks() {
  try {
    const res = await client.get('/domain-packs')
    domainPacks.value = res?.packs || []
    // 同步材料类型，保证提交/派生路由使用领域类型
    form.value.material_scope = materialKind.value
  } catch {
    domainPacks.value = []
  }
}

// 材料体系下拉：数据源切换到 /config 接口（material_domain.material_systems），
// 展示并回传体系名到 material_system（与 material_scope 解耦）；
// /config 不可用或未配置体系时回退静态材料类型。
const materialSystems = ref([])
const materialSystemLoading = ref(false)
const materialSystemOptions = computed(() => {
  if (materialSystems.value.length) {
    return materialSystems.value.map((s) => ({ value: s.name, label: s.name }))
  }
  return RESEARCH_MATERIAL_SCOPES.map((s) => ({ value: s.value, label: s.label }))
})

async function loadMaterialSystems() {
  materialSystemLoading.value = true
  try {
    const res = await getConfig()
    const systems = res?.material_domain?.material_systems || []
    materialSystems.value = Array.isArray(systems) ? systems : []
    // 已加载体系：默认选中第一个，保证提交时有值
    if (materialSystems.value.length && !materialSystems.value.some((s) => s.name === form.value.material_system)) {
      form.value.material_system = materialSystems.value[0].name
    } else if (!materialSystems.value.length && !form.value.material_system) {
      form.value.material_system = 'crystal'
    }
  } catch {
    materialSystems.value = []
    if (!form.value.material_system) form.value.material_system = 'crystal'
  } finally {
    materialSystemLoading.value = false
  }
}

const scenarioId = ref('')
const plan = ref(null)
const requestId = ref('')
const runResult = ref(null)
const explainData = ref(null)

let pollTimer = null

const tourOpen = ref(false)
const STORAGE_KEY = 'research_onboarding_seen'

onMounted(() => {
  loadPropDictionary()
  loadMaterialSystems()
  loadDomainPacks()
  try {
    if (!localStorage.getItem(STORAGE_KEY)) {
      tourOpen.value = true
    }
  } catch {
    /* ignore */
  }
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

const tourSteps = [
  {
    target: '#rw-goal-input',
    title: '输入研发目标',
    description: '描述你想要的材料或性能，系统将据此生成完整计划。',
    placement: 'bottom',
  },
  {
    target: '#rw-generate-btn',
    title: '生成研发计划',
    description: '点击后系统会分析目标、匹配工具并生成可执行步骤。',
    placement: 'top',
  },
  {
    target: '#rw-confirm-btn',
    title: '确认执行',
    description: '检查计划步骤和预算后，点击确认开始执行。',
    placement: 'top',
  },
]

function markOnboardingSeen() {
  try {
    localStorage.setItem(STORAGE_KEY, 'true')
  } catch {
    /* ignore */
  }
}

function onTourFinish() {
  tourOpen.value = false
  markOnboardingSeen()
}

function onTourClose() {
  tourOpen.value = false
  markOnboardingSeen()
}

// ── 目标属性编辑器 ──
// P1-4：属性名统一从属性字典（材料属性分类）读取，单位随属性自动带出
const propOptions = ref([])
const propUnitMap = ref({})

function filterPropOption(input, option) {
  return (option.label || '').toLowerCase().includes(input.toLowerCase())
}

async function loadPropDictionary() {
  try {
    // 属性字典按"可预测"用途加载（领域无关），不再硬编码电池分类。
    const res = await getFields({ usable_in: 'predictable' })
    const fields = res?.fields || []
    // P1-101: 仅展示中文标签与单位，不再暴露 ionic_conductivity 等代码字段名
    propOptions.value = fields.map((f) => ({
      value: f.key,
      label: f.unit ? `${f.label_cn} · ${f.unit}` : f.label_cn,
    }))
    propUnitMap.value = Object.fromEntries(fields.map((f) => [f.key, f.unit || '']))
  } catch (err) {
    // 属性字典加载失败时不静默吞掉，提示用户但允许继续手动输入
    console.error('属性字典加载失败', err)
    propOptions.value = []
    propUnitMap.value = {}
  }
}

function addProperty() {
  form.value.target_properties.push({
    name: '',
    direction: 'maximize',
    min: null,
    max: null,
    weight: 0.5,
    _minText: '',
    _maxText: '',
  })
}
function removeProperty(idx) {
  form.value.target_properties.splice(idx, 1)
}

// P2-104：支持科学计数法输入。a-input-number 会强制转换为普通数字格式，
// 改用 a-input + 字符串解析，允许用户保留 1e-3 这样的输入形式。
function onPropNumberChange(prop, field, text) {
  const trimmed = (text || '').trim()
  if (trimmed === '') {
    prop[field] = null
    return
  }
  // 支持科学计数法：1e-3、1.5E-4、1.2e3 等
  const num = Number(trimmed)
  if (!Number.isNaN(num)) {
    prop[field] = num
  }
  // 如果不是合法数字，保留原值不强制转换，让用户继续编辑
}

// ── 阶段 1 → 2：生成计划 ──
async function onGeneratePlan() {
  if (!form.value.goal.trim()) return
  submitting.value = true
  try {
    // P0-001：创建全局场景 ID，贯穿研发链路
    if (!scenarioId.value) {
      scenarioId.value = `SCN-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`
    }
    const payload = {
      scenario_id: scenarioId.value,
      goal: form.value.goal.trim(),
      material_scope: materialKind.value || form.value.material_scope,
      material_system: form.value.material_system,
      target_properties: form.value.target_properties.filter((p) => p.name),
      constraints: {},
      preference: form.value.preference,
      project_id: form.value.project_id?.trim() || '',
    }
    const data = await researchApi.createRequest(payload)
    requestId.value = data.request_id
    scenarioId.value = data.scenario_id || scenarioId.value
    plan.value = data.plan
    runResult.value = null
    explainData.value = null
    phase.value = 'confirm'
    message.success('已生成研发计划')
  } catch {
    // 错误信息由 axios 拦截器统一提示
  } finally {
    submitting.value = false
  }
}

// ── 阶段 2 → 1：重新生成（保留输入） ──
function onRegenerate() {
  phase.value = 'input'
  plan.value = null
}

// ── 阶段 2 → 3：确认执行 ──
async function onConfirmExecute() {
  executing.value = true
  phase.value = 'execute'
  runResult.value = null
  explainData.value = null
  const taskId = `research_${requestId.value}`
  taskStore.addTask({ id: taskId, name: form.value.goal || '研发计划执行', type: 'research' })
  try {
    const data = await researchApi.startRun(requestId.value)
    const runId = data.run_id
    // 启动轮询：每 2 秒拉取事件流，直到 completed/failed
    const poll = async () => {
      try {
        const res = await researchApi.getRunEvents(runId)
        runResult.value = res
        const progress = Math.round(
          ((res.events?.length || 0) / Math.max(plan.value?.steps?.length || 1, 1)) * 100
        )
        taskStore.updateTask(taskId, { progress: Math.min(progress, 95), detail: executingHint.value })
        if (res.status === 'completed' || res.status === 'failed') {
          executing.value = false
          if (res.status === 'completed') {
            if (plan.value) plan.value.status = res.plan?.status || 'completed'
            if (plan.value?.steps) {
              const done = new Set(res.completed_steps || [])
              plan.value.steps.forEach((s) => {
                s.status = done.has(s.step_id) ? 'completed' : s.status
              })
            }
            message.success('执行完成')
            fetchExplain()
            taskStore.updateTask(taskId, { status: 'completed', progress: 100, detail: '' })
          } else {
            message.error('执行失败，请稍后重试或联系管理员')
            taskStore.updateTask(taskId, { status: 'failed', detail: res.error || '' })
          }
          taskStore.prune()
          return
        }
      } catch (err) {
        executing.value = false
        message.error('轮询失败，请稍后重试或联系管理员')
        taskStore.updateTask(taskId, { status: 'failed', detail: err.message || '' })
        taskStore.prune()
        return
      }
      if (executing.value) {
        pollTimer = setTimeout(poll, 2000)
      }
    }
    pollTimer = setTimeout(poll, 1000) // 1 秒后开始首次轮询
  } catch (err) {
    executing.value = false
    message.error('启动失败，请稍后重试或联系管理员')
    taskStore.updateTask(taskId, { status: 'failed', detail: err.message || '' })
    taskStore.prune()
  }
}

// ── 重新规划 ──
async function onReplan() {
  if (!plan.value?.plan_id) return
  replanning.value = true
  try {
    const data = await researchApi.replanRun(plan.value.plan_id)
    plan.value = data.plan
    runResult.value = null
    explainData.value = null
    phase.value = 'confirm'
    message.success('已重新规划')
  } catch {
    // 拦截器已提示
  } finally {
    replanning.value = false
  }
}

// ── 业务解释 ──
async function fetchExplain() {
  if (!requestId.value) return
  explaining.value = true
  try {
    explainData.value = await researchApi.explainRun(requestId.value)
  } catch {
    // 拦截器已提示
  } finally {
    explaining.value = false
  }
}

function onReset() {
  if (pollTimer) clearTimeout(pollTimer)
  executing.value = false
  phase.value = 'input'
  plan.value = null
  runResult.value = null
  explainData.value = null
  requestId.value = ''
  scenarioId.value = ''
}

// ── P3-2：派生子任务入口 ──
// 工作台是唯一顶层需求录入口；跳转子模块时携带目标与约束参数，避免重复录入
// 注：材料发现已合并到候选设计（/workbench），路径 /discovery 由 router 顶层 redirect 处理
const DERIVED_PATHS = {
  discovery: '/workbench',
  prediction: '/workbench',
  synthesis: '/synthesis',
  ecml: '/ecml',
}

function openDerived(moduleKey) {
  const query = buildDerivedQuery(moduleKey, {
    goal: form.value.goal.trim(),
    material_scope: materialKind.value || form.value.material_scope,
    material_system: form.value.material_system,
    target_properties: form.value.target_properties,
    scenario_id: scenarioId.value,
  })
  // 性质预测已并入「材料设计」工作台的临时材料性能预测模式
  if (moduleKey === 'prediction') query.mode = 'temp'
  router.push({ path: DERIVED_PATHS[moduleKey], query })
}

// ── 计算属性：步骤状态 / 进度 ──
const events = computed(() => runResult.value?.events || [])

const stepStatusMap = computed(() => {
  const map = {}
  plan.value?.steps?.forEach((s) => {
    map[s.step_id] = s.status || 'pending'
  })
  for (const e of events.value) {
    if (e.event_type === 'step_start' && e.step_id) map[e.step_id] = 'running'
    if (e.event_type === 'step_complete' && e.step_id) {
      map[e.step_id] = e.status === 'error' ? 'failed' : 'completed'
    }
    if (e.event_type === 'error' && e.step_id) map[e.step_id] = 'failed'
  }
  return map
})

const currentStepIndex = computed(() => {
  const steps = plan.value?.steps || []
  let idx = 0
  steps.forEach((s, i) => {
    const st = stepStatusMap.value[s.step_id]
    if (st === 'completed' || st === 'running') idx = i + 1
  })
  return Math.min(idx, steps.length)
})

// 执行进度百分比
const executionProgress = computed(() => {
  const total = plan.value?.steps?.length || 1
  return Math.round((currentStepIndex.value / total) * 100)
})

// 执行中提示文案
const executingHint = computed(() => {
  const steps = plan.value?.steps || []
  if (!steps.length) {
    return '正在等待后端返回事件流…耗时操作可能需要数分钟，请耐心等待。'
  }
  // 优先查找 running 状态的步骤
  let runningIdx = -1
  steps.forEach((s, i) => {
    if (stepStatusMap.value[s.step_id] === 'running') runningIdx = i
  })
  const idx = runningIdx >= 0 ? runningIdx : Math.min(currentStepIndex.value, steps.length - 1)
  const stepName = steps[idx]?.action
  if (stepName) {
    return `当前步骤 ${idx + 1}/${steps.length}：${actionLabel(stepName)}。耗时操作（如 DFT 计算、AI 推理）可能需要数分钟，请耐心等待。`
  }
  return '正在等待后端返回事件流…耗时操作可能需要数分钟，请耐心等待。'
})

const runStatus = computed(() => runResult.value?.status || plan.value?.status || '')

const stepsStatus = computed(() => {
  if (executing.value) return 'process'
  if (runStatus.value === 'failed') return 'error'
  if (runStatus.value === 'completed') return 'finish'
  return 'process'
})

const completedStepsWithEvidence = computed(() => {
  return (plan.value?.steps || []).filter(
    (s) => stepStatusMap.value[s.step_id] === 'completed',
  )
})

// ── 证据卡：从步骤与事件派生展示数据 ──
function evidenceOf(step) {
  const aliases = step.allowed_tool_aliases || []
  const isScp = aliases.some((a) => String(a).startsWith('scp:'))
  const isVerifier = step.agent_id === 'verifier'
  let sourceType = 'local_mcp'
  if (isScp) sourceType = 'scp'
  else if (isVerifier) sourceType = 'human'
  else if (step.action?.includes('predict') || step.action?.includes('verify')) sourceType = 'model'
  const prog = events.value.find(
    (e) => e.event_type === 'step_progress' && e.step_id === step.step_id,
  )
  return {
    source_type: sourceType,
    conclusion: `${actionLabel(step.action)} 已完成`,
    limitations: plan.value?.risk_summary || '无',
    version: plan.value?.plan_id || '-',
    detail: prog?.content || '无实现细节',
  }
}

function evidenceHeader(step) {
  const ev = evidenceOf(step)
  return `${actionLabel(step.action)} · ${sourceLabel(ev.source_type)}`
}

// ── 文案 / 颜色映射 ──
function profileLabel(p) {
  return ({ standard: '标准', internlm_assisted: 'InternLM 辅助', committee_governed: '委员会治理' })[p] || p || '标准'
}
function profileColor(p) {
  return ({ standard: 'blue', internlm_assisted: 'purple', committee_governed: 'orange' })[p] || 'blue'
}
function planStatusLabel(s) {
  return ({ draft: '草稿', confirmed: '已确认', running: '执行中', completed: '已完成', failed: '失败', invalid: '校验失败' })[s] || s || ''
}
function planStatusColor(s) {
  return ({ draft: 'default', confirmed: 'blue', running: 'processing', completed: 'success', failed: 'error', invalid: 'error' })[s] || 'default'
}
function actionLabel(a) {
  return ({
    route_material: '材料路由',
    generate_crystal_candidates: '晶体候选生成',
    generate_polymer_candidates: '聚合物候选生成',
    predict_crystal_properties: '晶体性质预测',
    predict_polymer_properties: '聚合物性质预测',
    check_synthesis_feasibility: '合成可行性检查',
    verify_dft: 'DFT 验证',
    design_formula: '配方设计',
    compliance_check: '合规检查',
  })[a] || a || ''
}
function agentLabel(id) {
  return ({ planner: '规划员', thinker: '思考者', doer: '执行者', verifier: '验证员' })[id] || id || ''
}
function autonomyColor(l) {
  return ({ L0: 'red', L1: 'orange', L2: 'green' })[l] || 'default'
}
function sourceLabel(s) {
  return ({ local_mcp: '本地计算', scp: '外部数据库', experiment: '实验', model: '模型预测', human: '人工' })[s] || s || ''
}
function sourceColor(s) {
  return ({ local_mcp: 'blue', scp: 'cyan', experiment: 'green', model: 'purple', human: 'orange' })[s] || 'default'
}
function eventLabel(t) {
  return ({ plan_start: '计划开始', step_start: '步骤开始', step_progress: '进度', step_complete: '步骤完成', plan_complete: '计划完成', error: '错误', committee_triggered: '委员会触发' })[t] || t || ''
}
function eventColor(e) {
  if (e.event_type === 'error') return 'red'
  if (e.event_type === 'step_complete') return e.status === 'error' ? 'red' : 'green'
  if (e.event_type === 'plan_complete') return 'green'
  if (e.event_type === 'committee_triggered') return 'orange'
  if (e.event_type === 'plan_start' || e.event_type === 'step_start') return 'blue'
  return 'gray'
}
function stepAStepStatus(st) {
  return ({ pending: 'wait', running: 'process', completed: 'finish', failed: 'error', skipped: 'wait' })[st] || 'wait'
}
function shortTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.research-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0 var(--space-sm);
}

.phase-card {
  margin-top: var(--space-md);
  background: var(--realsee-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
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

/* P3-2：派生子任务入口 */
.derived-section {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-md);
}

.derived-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--primary);
}

.form-help {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-top: var(--space-xs);
  line-height: 1.5;
}

.preference-alert {
  margin-top: var(--space-xs);
}

/* 目标属性编辑器 */
.prop-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.prop-row {
  display: grid;
  grid-template-columns: 1.8fr 0.6fr 1fr 0.8fr 0.8fr 0.7fr 32px;
  gap: var(--space-sm);
  align-items: center;
}

.prop-unit-value {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

/* P2-104：科学计数法输入框，使用等宽字体便于辨识 */
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

/* 计划卡 */
.plan-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  padding: var(--space-md);
  background: var(--light-bg-hover);
  border-radius: var(--radius-lg);
}

.plan-rationale {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  flex: 1;
  min-width: 200px;
}

.plan-steps {
  margin-top: 4px;
}

.step-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
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
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  flex-shrink: 0;
}

.step-action {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  font-weight: var(--font-weight-semibold);
}

.step-tools {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.plan-footer {
  margin-top: var(--space-xl);
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
}

.risk-card {
  padding: var(--space-md);
  background: var(--light-bg-hover);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-md);
  color: var(--text-secondary);
  line-height: 1.6;
}

.confirm-actions {
  margin-top: var(--space-xl);
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border-light);
}

/* 执行阶段 */
.event-stream {
  margin-top: 4px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.event-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.event-step,
.event-agent {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.event-time {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.event-content {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: 2px;
}

.result-section {
  margin-top: var(--space-xl);
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border-light);
}

/* 证据卡 */
.evidence-collapse :deep(.ant-collapse-header) {
  font-size: var(--font-size-md);
  padding: 8px 12px !important;
}

.evidence-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.evidence-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.evidence-label {
  color: var(--text-muted);
  min-width: 64px;
}

.evidence-version {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
}

.evidence-detail {
  margin-top: 4px;
  padding-top: var(--space-sm);
  border-top: 1px dashed var(--border-light);
}

.evidence-raw {
  margin: 4px 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  padding: var(--space-sm);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .budget-grid {
    grid-template-columns: 1fr;
  }
  .prop-row {
    grid-template-columns: 1fr 1fr;
  }
  .prop-header {
    display: none;
  }
}
</style>
