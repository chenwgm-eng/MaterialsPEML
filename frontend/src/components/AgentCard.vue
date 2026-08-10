<template>
  <div
    class="agent-card"
    :class="{
      selected,
      selectable: selectable && !isDev,
      'agent-dev': isDev,
    }"
    :role="selectable && !isDev ? 'button' : undefined"
    :tabindex="selectable && !isDev ? 0 : undefined"
    :aria-pressed="selectable && !isDev ? selected : undefined"
    :aria-label="selectable && !isDev ? `选择智能体 ${agent.name}` : undefined"
    @click="onSelect"
    @keydown.enter.prevent="onSelect"
    @keydown.space.prevent="onSelect"
  >
    <div class="card-main">
      <div class="avatar">
        <component :is="avatarIcon || RobotOutlined" v-if="!customAvatarText" aria-hidden="true" />
        <template v-else>{{ agent.avatar }}</template>
      </div>
      <div class="info">
        <div class="info-head">
          <span class="name">{{ agent.name }}</span>
          <a-tag :color="roleColor" class="role-tag">{{ roleLabel }}</a-tag>
          <a-tag v-if="isDev" color="default" class="dev-tag">能力开发中</a-tag>
        </div>
        <div class="desc">{{ agent.description || '—' }}</div>
        <div v-if="agent.expertise?.length" class="expertise">
          <a-tag v-for="e in agent.expertise" :key="e" class="small-tag">{{ e }}</a-tag>
        </div>
      </div>
    </div>

    <div class="card-foot">
      <div class="meta-group">
        <span class="meta">工具 · {{ agent.tools?.length || 0 }}</span>
        <span class="meta">模型 · {{ agent.llm_model || '—' }}</span>
        <span v-if="health" class="meta">
          <a-tag :color="healthColor" size="small">{{ healthLabel }}</a-tag>
        </span>
        <template v-if="stats">
          <span class="meta">调用 · {{ stats.invocations }}</span>
          <span class="meta" :class="{ 'meta-warn': stats.success_rate !== null && stats.success_rate < 1 }">
            成功率 · {{ stats.success_rate === null ? '—' : `${Math.round(stats.success_rate * 100)}%` }}
          </span>
        </template>
        <span v-else class="meta">调用 · 0</span>
      </div>
      <div class="actions">
        <a-button size="small" type="text" @click.stop="emit('detail', agent.id)">详情</a-button>
        <template v-if="editable">
          <a-button size="small" type="text" @click.stop="emit('edit', agent.id)">编辑</a-button>
          <a-button
            v-if="!agent.is_builtin"
            size="small"
            type="text"
            danger
            @click.stop="emit('delete', agent.id)"
          >删除</a-button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RobotOutlined } from '@ant-design/icons-vue'
import { agentRoleColor, agentRoleLabel } from '@/constants/agentMeta'
import { resolveAgentIcon, isEmojiAvatar } from '@/utils/agentAvatar'

const props = defineProps({
  agent: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  selectable: { type: Boolean, default: false },
  editable: { type: Boolean, default: true },
  // P1-2：来自统一 Agent 调用事件日志的统计（invocations/success_rate 等）
  stats: { type: Object, default: null },
  // P1-008：健康状态 { health: 'healthy'|'degraded'|'unknown'|'builtin', meta: string }
  health: { type: Object, default: null },
})

const emit = defineEmits(['select', 'edit', 'delete', 'detail'])

const roleColor = computed(() => agentRoleColor(props.agent.role))
const roleLabel = computed(() => agentRoleLabel(props.agent.role))
const isDev = computed(() => props.agent.status === 'development')
const avatarIcon = computed(() => resolveAgentIcon(props.agent.avatar))
const customAvatarText = computed(() => props.agent.avatar && !isEmojiAvatar(props.agent.avatar))

const HEALTH_LABEL = {
  healthy: '正常',
  degraded: '降级',
  unknown: '未配置',
  builtin: '内置可用',
}
const HEALTH_COLOR = {
  healthy: 'success',
  degraded: 'warning',
  unknown: 'default',
  builtin: 'blue',
}
const healthLabel = computed(() => {
  if (!props.health) return '未配置'
  return HEALTH_LABEL[props.health.health] || props.health.health || '未配置'
})
const healthColor = computed(() => {
  if (!props.health) return 'default'
  return HEALTH_COLOR[props.health.health] || 'default'
})

function onSelect() {
  if (props.selectable && !isDev.value) emit('select', props.agent.id)
}
</script>

<style scoped>
.agent-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 12px 14px;
  box-shadow: var(--shadow-card);
  transition: border-color var(--transition), box-shadow var(--transition), transform var(--transition);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-card.selectable {
  cursor: pointer;
}

.agent-card.selectable:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-hover);
}

.agent-card.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.15), var(--shadow-hover);
}

.agent-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.card-main {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--light-bg-active);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
  line-height: 1;
}

.info {
  flex: 1;
  min-width: 0;
}

.info-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.role-tag {
  margin: 0;
  border: none !important;
  color: var(--light-bg-card) !important;
  font-size: 11px;
  line-height: 18px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
}

.desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.expertise {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.small-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  background: var(--light-bg-active);
  border-color: var(--border-light);
  color: var(--text-secondary);
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
}

.meta-group {
  display: flex;
  gap: 14px;
}

.meta {
  font-size: 12px;
  color: var(--text-muted);
}

.meta-warn {
  color: var(--warning);
}

.actions {
  display: flex;
  gap: 2px;
}

.agent-dev {
  opacity: 0.6;
}

/* 「能力开发中」仅视觉提示，不阻止详情/编辑等按钮的点击 */
.agent-dev .actions {
  pointer-events: auto;
}

.dev-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
}
</style>
