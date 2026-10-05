<template>
  <a-popover
    :disabled="!interactive"
    trigger="click"
    placement="top"
    overlay-class-name="agent-chip-popover"
  >
    <template #content>
      <AgentDetailCard
        :agent-id="agentId"
        :fallback-name="fallbackName"
        :fallback-desc="fallbackDesc"
      />
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

<script setup>
import { computed, onMounted, ref } from 'vue'
import { loadAgentsOnce } from '@/utils/agents'
import { isEmojiAvatar } from '@/utils/agentAvatar'
import AgentDetailCard from './AgentDetailCard.vue'

const props = defineProps({
  // 后端 Agent id，如 builtin_industrialization；提供后会从 /agents 拉取真实信息
  agentId: { type: String, default: '' },
  // 拉取失败时的兜底名称（与后端步骤映射保持一致）
  fallbackName: { type: String, default: '' },
  fallbackDesc: { type: String, default: '该环节由 AI 智能体自动执行' },
  // 是否可点击弹出智能体详情浮层；false 时仅静态展示（详情并入「步骤详情」抽屉，避免浮动重叠）
  interactive: { type: Boolean, default: true },
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
</style>
