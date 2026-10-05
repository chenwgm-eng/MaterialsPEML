<template>
  <div class="agent-detail-card">
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

<script setup>
import { computed, onMounted, ref } from 'vue'
import { loadAgentsOnce, agentRoleLabel } from '@/utils/agents'
import { isEmojiAvatar } from '@/utils/agentAvatar'

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
// 头像取非 emoji 的自定义文本；emoji 或空时回退为名称首字母
const avatarText = computed(() => {
  const av = agent.value?.avatar
  if (av && !isEmojiAvatar(av)) return av
  return displayName.value.charAt(0) || 'A'
})

const roleLabel = computed(() => agentRoleLabel(agent.value?.role))
</script>

<style scoped>
.agent-detail-card {
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
