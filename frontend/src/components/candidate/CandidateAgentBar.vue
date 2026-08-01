<template>
  <div class="agent-action-row">
    <a-popover trigger="click" placement="bottomLeft" overlay-class-name="agent-popover">
      <template #title>
        <span class="popover-title">智能体详情</span>
      </template>
      <template #content>
        <div class="agent-detail-card">
          <div class="agent-head">
            <div class="agent-avatar-lg">{{ agent?.avatar || '🔬' }}</div>
            <div class="agent-meta">
              <div class="agent-name-lg">{{ agent?.name || '首席材料学家' }}</div>
              <div class="agent-tags">
                <a-tag color="blue" size="small">材料发现</a-tag>
                <a-tag v-if="agent?.is_builtin" size="small">内置</a-tag>
              </div>
            </div>
          </div>
          <div v-if="agent?.description" class="agent-section">
            <div class="agent-section-title">职责描述</div>
            <div class="agent-desc">{{ agent.description }}</div>
          </div>
          <div v-if="agent?.expertise?.length" class="agent-section">
            <div class="agent-section-title">专长</div>
            <div class="agent-tags">
              <a-tag v-for="e in agent.expertise" :key="e" size="small">{{ e }}</a-tag>
            </div>
          </div>
          <div v-if="agent?.capabilities?.length" class="agent-section">
            <div class="agent-section-title">能力</div>
            <div class="agent-tags">
              <a-tag v-for="c in agent.capabilities" :key="c" size="small">{{ c }}</a-tag>
            </div>
          </div>
          <div class="agent-section">
            <div class="agent-section-title">基本信息</div>
            <a-descriptions size="small" :column="1" :colon="false">
              <a-descriptions-item label="模型">{{ agent?.llm_model || '默认' }}</a-descriptions-item>
              <a-descriptions-item label="工具数">{{ agent?.tools?.length || 0 }}</a-descriptions-item>
            </a-descriptions>
          </div>
        </div>
      </template>
      <span class="agent-chip" :class="{ 'agent-chip-loading': agentLoading }">
        <span class="agent-avatar">{{ agent?.avatar || '🔬' }}</span>
        <span class="agent-name">{{ agent?.name || '首席材料学家' }}</span>
        <a-tag color="orange" size="small" class="ai-tag">AI</a-tag>
      </span>
    </a-popover>

    <a-segmented
      v-model:value="innerMode"
      :options="modeOptions"
      size="small"
      class="mode-switch"
    />

    <a-button
      type="primary"
      size="small"
      :loading="loading"
      :disabled="disabled"
      @click="emit('run')"
    >
      <template #icon><ThunderboltOutlined /></template>
      {{ loading ? 'Agent 生成中…' : '调用智能体生成候选材料' }}
    </a-button>

    <span v-if="loading" class="loading-hint">
      <LoadingOutlined />
      {{ loadingHint }}
    </span>
    <span v-else-if="disabled" class="loading-hint muted">请先选择项目任务</span>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  ThunderboltOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import { listAgents } from '@/api/agents'

const props = defineProps({
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  generateMode: { type: String, default: 'pure_llm' },
})

const emit = defineEmits(['update:generateMode', 'run', 'agent-loaded'])

const innerMode = computed({
  get: () => props.generateMode,
  set: (v) => emit('update:generateMode', v),
})

// ── 首席材料学家 Agent 信息 ──
const agent = ref(null)
const agentLoading = ref(false)

// 生成模式选项
const modeOptions = ref([
  { label: 'AI 创造', value: 'pure_llm' },
  { label: 'AI+检索增强', value: 'llm_plus_retrieval' },
])

// 分阶段 loading 提示
const loadingHint = computed(() => {
  if (props.generateMode === 'llm_plus_retrieval') {
    return 'Agent 正在生成候选材料并用 Materials Project 检索验证，通常需要 30-90 秒'
  }
  return 'Agent 正在创造性地生成候选配方，通常需要 30-60 秒'
})

async function loadAgent() {
  agentLoading.value = true
  try {
    const res = await listAgents()
    const list = Array.isArray(res) ? res : (res?.agents || [])
    agent.value =
      list.find((a) => a.role === 'material_discovery') ||
      list.find((a) => a.id && a.id.includes('material_discovery')) ||
      null
    // 通知父组件当前选中的 agent id，供 API 调用使用
    emit('agent-loaded', agent.value)
  } catch {
    agent.value = null
    emit('agent-loaded', null)
  } finally {
    agentLoading.value = false
  }
}

onMounted(() => {
  loadAgent()
})
</script>

<style scoped>
.agent-action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 6px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 12px;
  line-height: 1;
  user-select: none;
}

.agent-chip:hover {
  border-color: var(--primary);
  background: var(--light-bg-card);
}

.agent-chip-loading {
  opacity: 0.6;
  cursor: default;
}

.agent-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--light-bg-active);
  font-size: 13px;
}

.agent-name {
  color: var(--text-primary, #333);
  font-weight: 500;
}

.ai-tag {
  margin-left: 2px;
  transform: scale(0.9);
  transform-origin: center;
}

.mode-switch {
  flex-shrink: 0;
}

.loading-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--primary);
}

.loading-hint.muted {
  color: var(--text-muted, #999);
}

/* ── Popover 内的 Agent 详情卡 ── */
.agent-detail-card {
  width: 280px;
  max-width: 100%;
}

.agent-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.agent-avatar-lg {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--light-bg-active);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.agent-meta {
  flex: 1;
  min-width: 0;
}

.agent-name-lg {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin-bottom: 4px;
}

.agent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.agent-section {
  margin-top: 10px;
}

.agent-section-title {
  font-size: 11px;
  color: var(--text-secondary, #666);
  margin-bottom: 4px;
  font-weight: 500;
}

.agent-desc {
  font-size: 12px;
  color: var(--text-primary, #333);
  line-height: 1.5;
}

.popover-title {
  font-weight: 600;
}
</style>
