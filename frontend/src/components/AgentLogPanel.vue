<template>
  <div class="agent-log-panel" :style="{ height }">
    <div class="log-header">
      <span class="log-title">执行日志</span>
      <a-button size="small" type="text" class="clear-btn" @click="emit('clear')">清空</a-button>
    </div>
    <div
      ref="bodyRef"
      class="log-body"
      role="log"
      aria-live="polite"
      aria-label="执行日志"
    >
      <div v-if="displayedEvents.length === 0" class="log-empty">暂无日志</div>
      <div v-for="(ev, i) in displayedEvents" :key="i" class="log-line" :class="ev.event_type">
        <span class="log-time">{{ formatTime(ev.timestamp) }}</span>
        <span class="log-agent" :style="{ color: agentColor(ev.agent_id) }">
          {{ ev.agent_name || ev.agent_id || 'system' }}
        </span>
        <span class="log-icon">{{ iconFor(ev.event_type) }}</span>
        <span class="log-content">{{ ev.content }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { agentRoleColor, AGENT_FALLBACK_COLOR } from '@/constants/agentMeta'

const props = defineProps({
  events: { type: Array, default: () => [] },
  height: { type: String, default: '400px' },
  agents: { type: Array, default: () => [] },
})

const emit = defineEmits(['clear'])

const EVENT_ICON = {
  thinking: '💭',
  tool_call: '🔧',
  tool_result: '✅',
  step_start: '▶',
  step_complete: '✔',
  error: '❌',
  complete: '🎉',
}

const bodyRef = ref(null)

// 虚拟滚动优化：超过 100 条时只渲染最近 100 条
const displayedEvents = computed(() => {
  const list = props.events || []
  return list.length > 100 ? list.slice(list.length - 100) : list
})

function agentColor(agentId) {
  if (!agentId) return AGENT_FALLBACK_COLOR
  const agent = props.agents.find((a) => a.id === agentId)
  if (!agent) return AGENT_FALLBACK_COLOR
  return agentRoleColor(agent.role)
}

function iconFor(type) {
  return EVENT_ICON[type] || '·'
}

function formatTime(ts) {
  if (!ts) return '--:--:--'
  const d = ts instanceof Date ? ts : new Date(ts)
  if (Number.isNaN(d.getTime())) return '--:--:--'
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

watch(
  () => displayedEvents.value.length,
  () => {
    nextTick(() => {
      if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
    })
  },
)
</script>

<style scoped>
.agent-log-panel {
  display: flex;
  flex-direction: column;
  background: var(--dark-bg-deep);
  border-radius: var(--radius-lg);
  border: 1px solid var(--dark-border);
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--dark-bg);
  border-bottom: 1px solid var(--dark-border);
  flex-shrink: 0;
}

.log-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-on-dark);
  letter-spacing: 0.02em;
}

.clear-btn {
  color: var(--text-on-dark-muted) !important;
  font-size: 12px;
}

.clear-btn:hover {
  color: var(--text-on-dark) !important;
}

.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px;
  font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
  font-size: 12.5px;
  line-height: 1.7;
}

.log-empty {
  color: var(--text-on-dark-muted);
  text-align: center;
  padding: 30px 0;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

.log-time {
  color: var(--text-on-dark-muted);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.log-agent {
  flex-shrink: 0;
  font-weight: 600;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
}

.log-content {
  color: var(--text-on-dark-secondary);
  min-width: 0;
}

.log-line.error .log-content {
  color: var(--error);
}

.log-line.complete .log-content {
  color: var(--success);
}

.log-line.step_complete .log-content {
  color: var(--success);
}

.log-line.tool_result .log-content {
  color: var(--success);
}
</style>
