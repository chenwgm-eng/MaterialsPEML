<template>
  <div class="icon-rail">
    <!-- 顶部 logo -->
    <div class="rail-logo" title="MaterialsPEML">
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
        <defs>
          <linearGradient id="rail-logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="var(--primary)" />
            <stop offset="100%" stop-color="var(--primary-light)" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="6" fill="url(#rail-logo-grad)" />
        <path d="M8 22V10h2v10h6v2H8z" fill="white" opacity="0.95" />
        <circle cx="22" cy="16" r="3.5" fill="none" stroke="white" stroke-width="1.5" />
        <path d="M22 13v6M19 16h6" stroke="white" stroke-width="1.2" />
      </svg>
    </div>

    <!-- 中部：稳定一级入口图标按钮 -->
    <nav class="rail-nav">
      <a-tooltip
        v-for="entry in entries"
        :key="entry.key"
        :title="entry.label"
        placement="right"
      >
        <button
          type="button"
          class="rail-entry"
          :class="{ active: entry.key === activeEntry }"
          :aria-label="entry.label"
          @click="$emit('select', entry.key)"
        >
          <component :is="entry.icon" class="rail-entry-icon" />
        </button>
      </a-tooltip>
    </nav>

    <!-- 底部：状态色点 -->
    <div class="rail-footer">
      <a-tooltip placement="right" :title="userName">
        <div class="rail-dot-wrap">
          <span class="rail-dot" :style="{ background: roleDotColor }"></span>
        </div>
      </a-tooltip>
      <a-tooltip placement="right" :title="healthText">
        <div class="rail-dot-wrap">
          <span class="rail-dot health-dot" :class="healthClass"></span>
        </div>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  activeEntry: { type: String, default: '' },
  entries: { type: Array, default: () => [] },
  user: { type: Object, default: null },
  healthText: { type: String, default: '连接中…' },
  healthClass: { type: String, default: 'health-pending' },
})

defineEmits(['select'])

// 角色 → 色点颜色（与 antd Tag 角色色近似，用于底部状态点）
const ROLE_DOT = {
  admin: '#f5222d',
  pm: '#fa8c16',
  researcher: '#1677ff',
  reviewer: '#722ed1',
  experimenter: '#13c2c2',
  data_engineer: '#52c41a',
  viewer: '#8c8c8c',
}

const userName = computed(() => {
  const u = props.user
  return u ? u.display_name || u.username : '未登录'
})

const roleDotColor = computed(() => {
  const u = props.user
  return u ? ROLE_DOT[u.role] || '#8c8c8c' : '#8c8c8c'
})
</script>

<style scoped>
.icon-rail {
  width: 64px;
  height: 100%;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  box-shadow: 2px 0 16px rgba(11, 18, 32, 0.22);
}

.rail-logo {
  width: 100%;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--sidebar-border);
  flex-shrink: 0;
}

.rail-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding-top: 14px;
  overflow-y: auto;
  overflow-x: hidden;
}

.rail-entry {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--sidebar-text);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.rail-entry:hover {
  color: var(--text-on-dark);
  background: var(--sidebar-hover);
}

.rail-entry.active {
  color: var(--sidebar-text-active);
  background: var(--sidebar-active);
}

.rail-entry-icon {
  font-size: 20px;
}

.rail-footer {
  width: 100%;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-top: 1px solid var(--sidebar-border);
}

.rail-dot-wrap {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  cursor: default;
}

.rail-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.health-dot.health-ok {
  background: var(--success);
  box-shadow: 0 0 4px var(--success);
}

.health-dot.health-error {
  background: var(--danger);
  box-shadow: 0 0 4px var(--danger);
}

.health-dot.health-pending {
  background: var(--text-on-dark-muted);
  animation: pulse 1.5s ease-in-out infinite;
}
</style>