<template>
  <a-tooltip :title="mode === 'dark' ? '切换到浅色模式' : '切换到深色模式'">
    <a-button
      type="text"
      class="theme-toggle-btn"
      :aria-label="mode === 'dark' ? '切换到浅色模式' : '切换到深色模式'"
      @click="toggleTheme"
    >
      <!-- 深色模式下显示太阳图标（点击切回浅色）；浅色模式下显示月亮图标（点击切到深色） -->
      <svg
        v-if="mode === 'dark'"
        viewBox="0 0 24 24"
        width="20"
        height="20"
        class="theme-icon"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2" />
        <path
          d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        />
      </svg>
      <svg
        v-else
        viewBox="0 0 24 24"
        width="20"
        height="20"
        class="theme-icon"
        aria-hidden="true"
      >
        <path
          d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </a-button>
  </a-tooltip>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const { mode } = storeToRefs(themeStore)
const { toggleTheme } = themeStore
</script>

<style scoped>
.theme-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-primary);
  padding: 4px 8px;
}

.theme-toggle-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--primary);
}

.theme-icon {
  display: block;
  color: inherit;
}
</style>
