<template>
  <a-popover trigger="click" placement="top" overlay-class-name="agent-chip-popover">
    <template #content>
      <div class="agent-chip-card">
        <div class="chip-card-head">
          <span class="chip-avatar-lg">{{ avatarText }}</span>
          <div class="chip-head-meta">
            <div class="chip-name-row">
              <span class="chip-name-lg">{{ displayName }}</span>
              <a-tag v-if="agent?.is_builtin" color="blue" size="small">内置</a-tag>
              <a-tag v-if="roleLabel" size="small" class="chip-role-tag">{{ roleLabel }}</a-tag>
            </div>
            <div class="chip-sub">{{ agent?.description || fallbackDesc }}</div>
          </div>
        </div>
        <div v-if="agent?.expertise?.length" class="chip-section">
          <div class="chip-section-title">专长</div>
          <a-tag v-for="e in agent.expertise" :key="e" size="small" class="chip-tag">{{ e }}</a-tag>
        </div>
        <div class="chip-meta-row">
          <span>模型 · {{ agent?.effective_model_primary || agent?.effective_model || agent?.llm_model || '—' }}</span>
          <span>工具 · {{ agent?.tools?.length || 0 }}</span>
        </div>
        <div class="chip-foot">本环节由该智能体实际执行，调用过程可在「智能体管理」中审计</div>
      </div>
    </template>
    <span
      class="agent-chip"
      role="button"
      tabindex="0"
      :aria-label="`查看 ${displayName} 智能体详情`"
    >
      <span class="chip-avatar">{{ avatarText }}</span>
      <span class="chip-name">{{ displayName }}</span>
      <span class="chip-ai-badge">AI</span>
    </span>
  </a-popover>
</template>

<script>
import { listAgents } from '@/api/agents'

// 模块级缓存：同一页面多个 chip 只拉取一次 agents 列表
// 带 TTL（5 分钟），避免在「智能体管理」编辑后其他页面仍显示旧信息
const AGENTS_CACHE_TTL = 5 * 60 * 1000
let agentsCache = null // { promise, timestamp }

function loadAgentsOnce() {
  const now = Date.now()
  if (agentsCache && now - agentsCache.timestamp < AGENTS_CACHE_TTL) {
    return agentsCache.promise
  }
  agentsCache = {
    promise: listAgents()
      .then((res) => (Array.isArray(res) ? res : res?.agents || []))
      .catch(() => []),
    timestamp: now,
  }
  return agentsCache.promise
}
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  // 后端 Agent id，如 builtin_industrialization；提供后会从 /agents 拉取真实信息
  agentId: { type: String, default: '' },
  // 拉取失败时的兜底名称（与后端步骤映射保持一致）
  fallbackName: { type: String, default: '' },
  fallbackDesc: { type: String, default: '该环节由 AI 智能体自动执行' },
})

const agent = ref(null)

onMounted(async () => {
  if (!props.agentId) return
  const list = await loadAgentsOnce()
  agent.value = list.find((a) => a.id === props.agentId) || null
})

const displayName = computed(() => agent.value?.name || props.fallbackName || '智能体')
const avatarText = computed(() => agent.value?.avatar || displayName.value.charAt(0) || '🤖')

const ROLE_LABEL = {
  project_manager: '项目经理',
  material_discovery: '材料发现',
  synthesis_planning: '合成规划',
  dft_verification: 'DFT 验证',
  experiment_analysis: '实验分析',
  literature_research: '文献调研',
  quality_review: '质量审核',
  custom: '自定义',
}
const roleLabel = computed(() => (agent.value?.role ? ROLE_LABEL[agent.value.role] || agent.value.role : ''))
</script>

<style scoped>
.agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px 1px 2px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--light-bg-card);
  cursor: pointer;
  transition: border-color var(--transition), box-shadow var(--transition);
  line-height: 20px;
}

.agent-chip:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-hover);
}

.chip-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--light-bg-active);
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chip-name {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.chip-ai-badge {
  font-size: 9px;
  font-weight: 700;
  color: var(--light-bg-card);
  background: var(--primary);
  border-radius: 3px;
  padding: 0 3px;
  line-height: 12px;
  letter-spacing: 0.5px;
}

/* ── 弹窗卡片 ── */
.agent-chip-card {
  max-width: 320px;
}

.chip-card-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.chip-avatar-lg {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--light-bg-active);
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chip-head-meta {
  flex: 1;
  min-width: 0;
}

.chip-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.chip-name-lg {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.chip-role-tag {
  margin: 0;
}

.chip-sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

.chip-section {
  margin-top: 8px;
}

.chip-section-title {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.chip-tag {
  margin: 0 4px 4px 0;
  font-size: 11px;
}

.chip-meta-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-muted);
}

.chip-foot {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
