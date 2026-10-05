<template>
  <div class="topology-view">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">调用关系</h1>
        <p class="page-subtitle">智能体 → 工具 → 能力契约 的调用链路与治理关系</p>
      </div>
      <div class="header-actions">
        <a-button :loading="loading" @click="loadAll">
          <template #icon><ReloadOutlined /></template>
          {{ loading ? MESSAGES.loading + '…' : '刷新' }}
        </a-button>
      </div>
    </div>

    <!-- 顶部引导条（默认折叠） -->
    <a-collapse :bordered="false" class="intro-collapse" :default-active-key="[]">
      <a-collapse-panel key="intro" header="这张页面是干什么的？">
        <div class="intro-content">
          <p>本页可视化展示三个核心概念之间的调用与治理关系：</p>
          <ul class="intro-list">
            <li><b>智能体（Agent）</b>：研发小队成员，决定<b>「谁去调」</b>。每个 Agent 绑定一组可调用的工具。</li>
            <li><b>工具（Tool）</b>：Agent 可调用的原子能力，决定<b>「调什么」</b>。来源有本地兜底、外部 SCP、InternLM 三种。</li>
            <li><b>能力契约（Capability）</b>：工具的契约化封装，决定<b>「能不能调、调不动怎么办」</b>。含 SLA、风险、降级链、审批状态。</li>
          </ul>
          <p class="intro-tip">
            <BulbOutlined /> <b>交互方式</b>：点击任意节点，三栏会高亮所有关联节点（调用方、被调用方、治理规则），不相关的节点变暗。
          </p>
          <p class="intro-flow">
            <b>数据流</b>：Agent 执行时 → 选工具 → 过契约门禁 → 调用工具 → 返回结果。改 Agent 不影响工具，改工具不影响契约，三者解耦但执行时协同。
          </p>
        </div>
      </a-collapse-panel>
    </a-collapse>

    <a-alert
      v-if="loadError"
      type="error"
      :message="loadError"
      show-icon
      closable
      @close="loadError = ''"
    />

    <!-- 三栏联动 -->
    <a-spin :spinning="loading">
      <div class="three-columns">
        <!-- 第 1 栏：Agent -->
        <div class="column">
          <div class="column-header">
            <div class="column-title">
              <RobotOutlined class="column-icon agent-icon" />
              <span class="column-name">智能体</span>
              <a-tag color="blue" class="column-count">{{ filteredAgents.length }}</a-tag>
            </div>
            <div class="column-subtitle">决定「谁去调」</div>
            <div class="column-filters">
              <a-input
                v-model:value="agentSearch"
                size="small"
                placeholder="搜索名称…"
                allow-clear
                class="filter-search"
              />
              <a-select
                v-model:value="agentRoleFilter"
                size="small"
                placeholder="角色"
                allow-clear
                :options="agentRoleOptions"
                class="filter-select"
              />
            </div>
          </div>
          <div class="column-list">
            <div
              v-for="agent in filteredAgents"
              :key="agent.id"
              class="node-card agent-card"
              :class="{
                'is-selected': selectedType === 'agent' && selectedId === agent.id,
                'is-related': relatedAgentIds.has(agent.id),
                'is-dimmed': hasSelection && !relatedAgentIds.has(agent.id) && !(selectedType === 'agent' && selectedId === agent.id),
              }"
              tabindex="0"
              role="button"
              :aria-pressed="selectedType === 'agent' && selectedId === agent.id"
              @click="onSelectAgent(agent)"
              @keydown.enter="onSelectAgent(agent)"
              @keydown.space.prevent="onSelectAgent(agent)"
            >
              <div class="node-header">
                <span class="node-avatar" aria-hidden="true">
                  <component :is="agentIcon(agent)" />
                </span>
                <span class="node-name">{{ agent.name }}</span>
              </div>
              <div class="node-meta">
                <a-tag :color="roleColor(agent.role)" class="meta-tag">{{ roleLabel(agent.role) }}</a-tag>
                <a-tag v-if="agent.max_autonomy_level" :color="autonomyColor(agent.max_autonomy_level)" class="meta-tag" translate="no">{{ agent.max_autonomy_level }}</a-tag>
                <a-tag v-if="agent.status !== 'active'" color="default" class="meta-tag" translate="no">{{ agent.status }}</a-tag>
              </div>
              <div class="node-footer">
                <span class="meta-text">绑定 {{ agent.tools?.length || 0 }} 个工具</span>
                <span v-if="agent.capabilities?.length" class="meta-text">· {{ agent.capabilities.length }} 项能力</span>
              </div>
            </div>
            <EmptyState v-if="!loading && filteredAgents.length === 0" type="search" :description="agents.length ? '无匹配结果' : '暂无智能体'" />
          </div>
        </div>

        <!-- 第 2 栏：Tool -->
        <div class="column">
          <div class="column-header">
            <div class="column-title">
              <AppstoreOutlined class="column-icon tool-icon" />
              <span class="column-name">工具</span>
              <a-tag color="cyan" class="column-count">{{ filteredTools.length }}</a-tag>
            </div>
            <div class="column-subtitle">决定「调什么」</div>
            <div class="column-filters">
              <a-input
                v-model:value="toolSearch"
                size="small"
                placeholder="搜索名称…"
                allow-clear
                class="filter-search"
              />
              <a-select
                v-model:value="toolRiskFilter"
                size="small"
                placeholder="风险等级"
                allow-clear
                :options="toolRiskOptions"
                class="filter-select"
              />
              <a-select
                v-model:value="toolStatusFilter"
                size="small"
                placeholder="启用状态"
                allow-clear
                :options="toolStatusOptions"
                class="filter-select"
              />
            </div>
          </div>
          <div class="column-list">
            <div
              v-for="tool in filteredTools"
              :key="tool.name"
              class="node-card tool-card"
              :class="{
                'is-selected': selectedType === 'tool' && selectedId === tool.name,
                'is-related': relatedToolNames.has(tool.name),
                'is-dimmed': hasSelection && !relatedToolNames.has(tool.name) && !(selectedType === 'tool' && selectedId === tool.name),
              }"
              tabindex="0"
              role="button"
              :aria-pressed="selectedType === 'tool' && selectedId === tool.name"
              @click="onSelectTool(tool)"
              @keydown.enter="onSelectTool(tool)"
              @keydown.space.prevent="onSelectTool(tool)"
            >
              <div class="node-header">
                <span class="node-name tool-name">{{ tool.name }}</span>
              </div>
              <div class="node-meta">
                <a-tag :color="sourceColor(tool.source)" class="meta-tag">{{ sourceLabel(tool.source) }}</a-tag>
                <a-tag v-if="tool.risk_level" :color="riskColor(tool.risk_level)" class="meta-tag" translate="no">风险 {{ tool.risk_level }}</a-tag>
                <a-tag v-if="tool.availability" :color="availabilityColor(tool.availability)" class="meta-tag">{{ availabilityLabel(tool.availability) }}</a-tag>
              </div>
              <div class="node-footer">
                <span class="meta-text">被 {{ callerAgentCount(tool.name) }} 个智能体调用</span>
              </div>
            </div>
            <EmptyState v-if="!loading && filteredTools.length === 0" type="search" :description="tools.length ? '无匹配结果' : '暂无工具'" />
          </div>
        </div>

        <!-- 第 3 栏：Capability -->
        <div class="column">
          <div class="column-header">
            <div class="column-title">
              <ApiOutlined class="column-icon cap-icon" />
              <span class="column-name">能力契约</span>
              <a-tag color="orange" class="column-count">{{ filteredCapabilities.length }}</a-tag>
            </div>
            <div class="column-subtitle">决定「能不能调」</div>
            <div class="column-filters">
              <a-input
                v-model:value="capSearch"
                size="small"
                placeholder="搜索名称…"
                allow-clear
                class="filter-search"
              />
              <a-select
                v-model:value="capStatusFilter"
                size="small"
                placeholder="状态"
                allow-clear
                :options="capStatusOptions"
                class="filter-select"
              />
            </div>
          </div>
          <div class="column-list">
            <div
              v-for="cap in filteredCapabilities"
              :key="cap.capability_id"
              class="node-card cap-card"
              :class="{
                'is-selected': selectedType === 'capability' && selectedId === cap.capability_id,
                'is-related': relatedCapabilityIds.has(cap.capability_id),
                'is-dimmed': hasSelection && !relatedCapabilityIds.has(cap.capability_id) && !(selectedType === 'capability' && selectedId === cap.capability_id),
              }"
              tabindex="0"
              role="button"
              :aria-pressed="selectedType === 'capability' && selectedId === cap.capability_id"
              @click="onSelectCapability(cap)"
              @keydown.enter="onSelectCapability(cap)"
              @keydown.space.prevent="onSelectCapability(cap)"
            >
              <div class="node-header">
                <span class="node-name">{{ cap.name }}</span>
              </div>
              <div class="node-meta">
                <a-tag :color="capStatusColor(cap.status)" class="meta-tag" translate="no">{{ capStatusLabel(cap.status) }}</a-tag>
                <a-tag v-if="cap.risk_level" :color="riskColor(cap.risk_level)" class="meta-tag" translate="no">{{ cap.risk_level }}</a-tag>
                <a-tag v-if="cap.fallback_chain?.length" color="blue" class="meta-tag">降级链 {{ cap.fallback_chain.length }}</a-tag>
              </div>
              <div class="node-footer">
                <span v-if="cap.latency_sla" class="meta-text" translate="no">SLA: {{ cap.latency_sla }}</span>
                <span v-if="cap.owner" class="meta-text">· {{ cap.owner }}</span>
              </div>
            </div>
            <EmptyState v-if="!loading && filteredCapabilities.length === 0" type="search" :description="capabilities.length ? '无匹配结果' : '暂无能力契约'" />
          </div>
        </div>
      </div>
    </a-spin>

    <!-- 关系说明条（底部固定） -->
    <div v-if="hasSelection" class="relation-bar">
      <div class="relation-content">
        <span class="relation-label">当前选中：</span>
        <a-tag :color="selectedColor">{{ selectedLabel }}</a-tag>
        <span class="relation-arrow">→</span>
        <span class="relation-text">{{ relationSummary }}</span>
        <a-button type="link" size="small" @click="clearSelection">清除选择</a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  ReloadOutlined,
  BulbOutlined,
  RobotOutlined,
  AppstoreOutlined,
  ApiOutlined,
} from '@ant-design/icons-vue'
import { useSystemStore } from '@/stores/system'
import { listAgents } from '@/api/agents'
import { getCapabilities } from '@/api/capabilities'
import { getSCPBindings } from '@/api/controlPlane'
import {
  riskLevelColor as sharedRiskColor,
  availabilityColor as sharedAvailabilityColor,
  availabilityLabel as sharedAvailabilityLabel,
} from '@/constants/toolMeta'
import { MESSAGES } from '@/constants/glossary'
import { resolveAgentIcon } from '@/utils/agentAvatar'

const systemStore = useSystemStore()

// --- 数据 ---
const agents = ref([])
const capabilities = ref([])
const scpBindings = ref([])
const loading = ref(false)
const loadError = ref('')

// --- 选中状态 ---
const selectedType = ref('') // 'agent' | 'tool' | 'capability' | ''
const selectedId = ref('')

const hasSelection = computed(() => !!selectedType.value)

// --- 衍生：工具列表（合并本地工具 + SCP 绑定） ---
const tools = computed(() => {
  const localTools = (systemStore.tools || []).map((t) => ({
    name: t.name,
    source: t.source || 'local',
    risk_level: t.risk_level || '',
    availability: t.availability || '',
    description: t.description || '',
    capability_refs: t.capability_refs || [],
  }))
  const scpTools = scpBindings.value
    .filter((b) => b.enabled)
    .map((b) => ({
      name: b.internal_name,
      source: 'scp',
      risk_level: b.risk_level || '',
      availability: b.enabled ? 'enabled' : 'disabled',
      description: b.description || b.summary || '',
      capability_refs: b.capability_refs || [],
    }))
  // 合并并按 name 去重（local 优先）
  const seen = new Set()
  return [...localTools, ...scpTools].filter((t) => {
    if (seen.has(t.name)) return false
    seen.add(t.name)
    return true
  })
})

// --- 各栏搜索与筛选（仅影响列表展示，不影响联动高亮逻辑） ---
const agentSearch = ref('')
const agentRoleFilter = ref(undefined)
const toolSearch = ref('')
const toolRiskFilter = ref(undefined)
const toolStatusFilter = ref(undefined)
const capSearch = ref('')
const capStatusFilter = ref(undefined)

// 筛选选项从当前数据动态提取，避免硬编码过期
const agentRoleOptions = computed(() => {
  const set = new Set(agents.value.map((a) => a.role).filter(Boolean))
  return [...set].sort().map((r) => ({ label: roleLabel(r), value: r }))
})
const toolRiskOptions = computed(() => {
  const set = new Set(tools.value.map((t) => t.risk_level).filter(Boolean))
  return [...set].sort().map((r) => ({ label: `风险 ${r}`, value: r }))
})
const toolStatusOptions = computed(() => {
  const set = new Set(tools.value.map((t) => t.availability).filter(Boolean))
  return [...set].sort().map((a) => ({ label: availabilityLabel(a), value: a }))
})
const capStatusOptions = computed(() => {
  const set = new Set(capabilities.value.map((c) => c.status).filter(Boolean))
  return [...set].sort().map((s) => ({ label: capStatusLabel(s), value: s }))
})

const filteredAgents = computed(() => {
  const kw = agentSearch.value.trim().toLowerCase()
  return agents.value.filter((a) => {
    if (kw && !(a.name || '').toLowerCase().includes(kw)) return false
    if (agentRoleFilter.value && a.role !== agentRoleFilter.value) return false
    return true
  })
})
const filteredTools = computed(() => {
  const kw = toolSearch.value.trim().toLowerCase()
  return tools.value.filter((t) => {
    if (kw && !(t.name || '').toLowerCase().includes(kw)) return false
    if (toolRiskFilter.value && t.risk_level !== toolRiskFilter.value) return false
    if (toolStatusFilter.value && t.availability !== toolStatusFilter.value) return false
    return true
  })
})
const filteredCapabilities = computed(() => {
  const kw = capSearch.value.trim().toLowerCase()
  return capabilities.value.filter((c) => {
    if (kw && !(c.name || '').toLowerCase().includes(kw)) return false
    if (capStatusFilter.value && c.status !== capStatusFilter.value) return false
    return true
  })
})

// --- 三栏联动高亮的核心逻辑 ---
// 关系基于后端 ToolBinding.capability_refs 显式映射，不再使用名称模糊匹配。

// 工具名 → 关联的 Capability ID 集合
function toolToCapabilityIds(toolName) {
  const tool = tools.value.find((t) => t.name === toolName)
  if (!tool || !tool.capability_refs?.length) return new Set()
  return new Set(tool.capability_refs)
}

// Capability ID → 关联的工具名集合
function capabilityToToolNames(capId) {
  return new Set(
    tools.value
      .filter((t) => t.capability_refs?.includes(capId))
      .map((t) => t.name)
  )
}

// 工具名 → 调用它的 Agent ID 集合
function toolToAgentIds(toolName) {
  return new Set(
    agents.value
      .filter((agent) => agent.tools?.includes(toolName))
      .map((agent) => agent.id)
  )
}

// Agent ID → 它绑定的工具名集合
function agentToToolNames(agentId) {
  const agent = agents.value.find((a) => a.id === agentId)
  return new Set(agent?.tools || [])
}

// --- 计算高亮集合 ---
const relatedAgentIds = computed(() => {
  if (!hasSelection.value) return new Set(agents.value.map((a) => a.id))
  const ids = new Set()
  if (selectedType.value === 'agent') {
    ids.add(selectedId.value)
  } else if (selectedType.value === 'tool') {
    toolToAgentIds(selectedId.value).forEach((id) => ids.add(id))
  } else if (selectedType.value === 'capability') {
    const toolNames = capabilityToToolNames(selectedId.value)
    toolNames.forEach((name) => {
      toolToAgentIds(name).forEach((id) => ids.add(id))
    })
  }
  return ids
})

const relatedToolNames = computed(() => {
  if (!hasSelection.value) return new Set(tools.value.map((t) => t.name))
  const names = new Set()
  if (selectedType.value === 'agent') {
    agentToToolNames(selectedId.value).forEach((name) => names.add(name))
  } else if (selectedType.value === 'tool') {
    names.add(selectedId.value)
  } else if (selectedType.value === 'capability') {
    capabilityToToolNames(selectedId.value).forEach((name) => names.add(name))
  }
  return names
})

const relatedCapabilityIds = computed(() => {
  if (!hasSelection.value) return new Set(capabilities.value.map((c) => c.capability_id))
  const ids = new Set()
  if (selectedType.value === 'agent') {
    agentToToolNames(selectedId.value).forEach((name) => {
      toolToCapabilityIds(name).forEach((id) => ids.add(id))
    })
  } else if (selectedType.value === 'tool') {
    toolToCapabilityIds(selectedId.value).forEach((id) => ids.add(id))
  } else if (selectedType.value === 'capability') {
    ids.add(selectedId.value)
    const cap = capabilities.value.find((c) => c.capability_id === selectedId.value)
    cap.fallback_chain?.forEach((fbId) => ids.add(fbId))
  }
  return ids
})

// --- 选中节点的展示信息 ---
const selectedLabel = computed(() => {
  if (selectedType.value === 'agent') {
    const a = agents.value.find((x) => x.id === selectedId.value)
    return a ? `智能体 · ${a.name}` : ''
  }
  if (selectedType.value === 'tool') {
    return `工具 · ${selectedId.value}`
  }
  if (selectedType.value === 'capability') {
    const c = capabilities.value.find((x) => x.capability_id === selectedId.value)
    return c ? `能力契约 · ${c.name}` : ''
  }
  return ''
})

const selectedColor = computed(() => {
  if (selectedType.value === 'agent') return 'purple'
  if (selectedType.value === 'tool') return 'cyan'
  if (selectedType.value === 'capability') return 'orange'
  return 'default'
})

const relationSummary = computed(() => {
  const agentCount = relatedAgentIds.value.size
  const toolCount = relatedToolNames.value.size
  const capCount = relatedCapabilityIds.value.size
  if (selectedType.value === 'agent') {
    return `绑定 ${toolCount} 个工具，关联 ${capCount} 个能力契约`
  }
  if (selectedType.value === 'tool') {
    return `被 ${agentCount} 个智能体调用，关联 ${capCount} 个能力契约`
  }
  if (selectedType.value === 'capability') {
    return `关联 ${toolCount} 个工具，间接影响 ${agentCount} 个智能体`
  }
  return ''
})

// --- 交互 ---
function onSelectAgent(agent) {
  if (selectedType.value === 'agent' && selectedId.value === agent.id) {
    clearSelection()
    return
  }
  selectedType.value = 'agent'
  selectedId.value = agent.id
}

function onSelectTool(tool) {
  if (selectedType.value === 'tool' && selectedId.value === tool.name) {
    clearSelection()
    return
  }
  selectedType.value = 'tool'
  selectedId.value = tool.name
}

function onSelectCapability(cap) {
  if (selectedType.value === 'capability' && selectedId.value === cap.capability_id) {
    clearSelection()
    return
  }
  selectedType.value = 'capability'
  selectedId.value = cap.capability_id
}

function clearSelection() {
  selectedType.value = ''
  selectedId.value = ''
}

function callerAgentCount(toolName) {
  return agents.value.filter((a) => a.tools?.includes(toolName)).length
}

// --- 标签辅助 ---
function agentIcon(agent) {
  return resolveAgentIcon(agent.avatar)
}

function roleColor(role) {
  const map = {
    material_discovery: 'purple',
    synthesis_planning: 'blue',
    dft_verification: 'cyan',
    experiment_analysis: 'green',
    project_manager: 'orange',
    literature_research: 'geekblue',
    quality_review: 'gold',
    industrialization: 'volcano',
    custom: 'default',
  }
  return map[role] || 'default'
}

function roleLabel(role) {
  const map = {
    material_discovery: '材料发现',
    synthesis_planning: '合成规划',
    dft_verification: 'DFT 验证',
    experiment_analysis: '实验分析',
    project_manager: '项目经理',
    literature_research: '文献调研',
    quality_review: '质量审核',
    industrialization: '工业化',
    custom: '自定义',
  }
  return map[role] || role || '—'
}

function autonomyColor(level) {
  const map = { L0: 'default', L1: 'blue', L2: 'orange', L3: 'red' }
  return map[level] || 'default'
}

function sourceColor(source) {
  const map = { local: 'green', scp: 'cyan', internlm: 'geekblue' }
  return map[source] || 'default'
}

function sourceLabel(source) {
  const map = { local: '本地', scp: '外部 SCP', internlm: 'InternLM' }
  return map[source] || source || '—'
}

// A/B/C/D 走共享映射；能力契约的 low/medium/high 单独处理
function riskColor(level) {
  const letter = sharedRiskColor(level)
  if (letter !== 'default') return letter
  const map = { low: 'success', medium: 'warning', high: 'error' }
  return map[level] || 'default'
}

const availabilityColor = sharedAvailabilityColor
const availabilityLabel = sharedAvailabilityLabel

function capStatusColor(status) {
  const map = { active: 'success', pending_approval: 'warning', deprecated: 'default' }
  return map[status] || 'default'
}

function capStatusLabel(status) {
  const map = { active: '已上线', pending_approval: '待审批', deprecated: '已废止' }
  return map[status] || status || '—'
}

// --- 数据加载 ---
// 错误提示使用友好文案，不直接展示 axios 原始消息（含 "status code 404" 等
// 内部细节），避免瞬时接口失败让页面被误读为路由 404，也符合不暴露内部错误的规范
function friendlyLoadError(reason, label) {
  const detail = reason?.response?.data?.detail
  if (detail && typeof detail === 'string') return `${label}：${detail}`
  return label
}

async function loadAll() {
  loading.value = true
  loadError.value = ''
  const results = await Promise.allSettled([
    listAgents(),
    getCapabilities(),
    getSCPBindings(),
    systemStore.fetchTools(),
  ])
  const [agentsRes, capsRes, scpRes, toolsRes] = results
  const errors = []
  if (agentsRes.status === 'fulfilled') {
    agents.value = agentsRes.value?.agents || agentsRes.value || []
  } else {
    errors.push(friendlyLoadError(agentsRes.reason, '智能体加载失败'))
  }
  if (capsRes.status === 'fulfilled') {
    capabilities.value = capsRes.value?.items || capsRes.value?.capabilities || capsRes.value || []
  } else {
    errors.push(friendlyLoadError(capsRes.reason, '能力契约加载失败'))
  }
  if (scpRes.status === 'fulfilled') {
    scpBindings.value = scpRes.value?.bindings || []
  } else {
    errors.push(friendlyLoadError(scpRes.reason, 'SCP 绑定加载失败'))
  }
  if (toolsRes.status === 'rejected') {
    errors.push(friendlyLoadError(toolsRes.reason, '本地工具加载失败'))
  }
  if (errors.length) {
    loadError.value = errors.join('；')
  }
  loading.value = false
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.topology-view {
  width: 100%;
  padding: 0 8px 80px;
}

/* 页面头部 */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 引导条 */
.intro-collapse {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 16px;
}

.intro-collapse :deep(.ant-collapse-header) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding: 10px 16px;
}

.intro-collapse :deep(.ant-collapse-content-box) {
  padding: 0 16px 12px;
}

.intro-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.intro-list {
  margin: 8px 0;
  padding-left: 20px;
}

.intro-list li {
  margin-bottom: 6px;
}

.intro-list b {
  color: var(--text-primary);
  font-weight: 600;
}

.intro-tip,
.intro-flow {
  margin: 12px 0 0;
  padding: 8px 12px;
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

/* 三栏布局 */
.three-columns {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.column {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.column-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--light-bg-hover);
  position: sticky;
  top: 0;
  z-index: 1;
}

.column-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.column-icon {
  font-size: 16px;
}

.agent-icon {
  color: var(--primary);
}

.tool-icon {
  color: var(--info);
}

.cap-icon {
  color: var(--warning);
}

.column-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.column-count {
  margin-left: 4px;
  font-size: 11px;
}

.column-subtitle {
  font-size: 12px;
  color: var(--text-muted);
}

.column-filters {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.filter-search {
  flex: 1;
  min-width: 0;
}

.filter-select {
  width: 96px;
  flex-shrink: 0;
}

.column-list {
  padding: 8px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 节点卡片 */
.node-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, opacity 0.2s, background 0.2s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.node-card:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.node-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.node-card.is-selected {
  border-color: var(--primary);
  background: var(--light-bg-hover);
  box-shadow: 0 0 0 2px var(--primary-light, rgba(24, 144, 255, 0.2));
}

.node-card.is-related {
  border-color: var(--primary-light, rgba(24, 144, 255, 0.4));
}

.node-card.is-dimmed {
  opacity: 0.35;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.node-avatar {
  width: 22px;
  height: 22px;
  border-radius: var(--radius-sm);
  background: var(--light-bg-hover);
  color: var(--primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
  line-height: 1;
}

.node-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-name {
  font-family: var(--font-family-mono);
  font-size: 12px;
}

.node-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.meta-tag {
  margin: 0;
  font-size: 11px;
  padding: 0 6px;
  line-height: 18px;
  height: 18px;
}

.node-footer {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-text {
  font-size: 11px;
  color: var(--text-muted);
}

/* 底部关系说明条 */
.relation-bar {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--light-bg-card);
  border-top: 1px solid var(--border);
  padding: 8px 20px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
  z-index: 10;
}

.relation-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.relation-label {
  font-weight: 600;
  color: var(--text-primary);
}

.relation-arrow {
  color: var(--text-muted);
  margin: 0 4px;
}

.relation-text {
  flex: 1;
}

/* 滚动条美化 */
.column-list::-webkit-scrollbar {
  width: 6px;
}

.column-list::-webkit-scrollbar-track {
  background: transparent;
}

.column-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.column-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* 响应式：窄屏时改为单列 */
@media (max-width: 1200px) {
  .three-columns {
    grid-template-columns: 1fr;
  }
  .column-list {
    max-height: 400px;
  }
}
</style>
