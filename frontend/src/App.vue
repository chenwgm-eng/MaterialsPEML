<template>
  <a-config-provider :theme="themeConfig" :locale="zhCN" :get-popup-container="getPopupContainer">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { theme as antdTheme } from 'ant-design-vue'
import { useSystemStore } from '@/stores/system'
import { useThemeStore } from '@/stores/theme'
import zhCN from 'ant-design-vue/es/locale/zh_CN'

const systemStore = useSystemStore()
const themeStore = useThemeStore()

// 评测修复 P1-4：全局将下拉/浮层挂载到触发元素父级，
// 避免 body 级 teleport overlay 与触发元素不在同一 DOM 子树导致指针事件被拦截
const getPopupContainer = (triggerNode) => {
  return triggerNode?.parentNode || document.body
}

onMounted(() => {
  systemStore.init().catch(() => {
    /* ignore network errors */
  })
})

// 基础 token：两种模式共用（主色 / 圆角 / 字体 / 控件高度等）
const baseToken = {
  colorPrimary: '#f97316',
  colorSuccess: '#16a34a',
  colorWarning: '#f59e0b',
  colorError: '#ef4444',
  colorInfo: '#f97316',
  borderRadius: 10,
  borderRadiusLG: 16,
  borderRadiusSM: 6,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
  fontSize: 13,
  controlHeight: 36,
}

// 浅色模式专有 token：显式锁定底色/文字基色，保持既有视觉一致
const lightToken = {
  colorTextBase: '#1d2129',
  colorBgContainer: '#ffffff',
  colorBgLayout: '#f7f7f8',
}

// 深色模式专有 token：交由 darkAlgorithm 生成底色，仅覆盖必要项
const darkToken = {
  colorBgLayout: '#0a0a0a',
}

// 浅色模式组件级 token
const lightComponents = {
  Layout: {
    siderBg: '#0a0a0a',
    headerBg: '#ffffff',
    headerHeight: 56,
    bodyBg: '#f7f7f8',
  },
  Menu: {
    darkItemBg: 'transparent',
    darkSubMenuItemBg: 'transparent',
    darkItemSelectedBg: 'rgba(249, 115, 22, 0.22)',
    darkItemHoverBg: 'rgba(249, 115, 22, 0.12)',
    darkItemColor: '#94a3b8',
    darkItemSelectedColor: '#ffffff',
    darkSubMenuItemColor: '#94a3b8',
  },
  Table: {
    headerBg: '#f3f4f6',
    headerColor: '#475569',
    rowHoverBg: '#f9fafb',
    borderColor: '#e5e7eb',
  },
  Card: {
    headerBg: 'transparent',
    paddingLG: 24,
    borderRadiusLG: 20,
  },
  Button: {
    primaryShadow: 'none',
    defaultBorderColor: '#dbe4f0',
    borderRadiusLG: 999,
    borderRadius: 999,
  },
  Tag: {
    defaultBg: '#f1f5f9',
    defaultColor: '#475569',
  },
  Input: {
    borderRadius: 10,
  },
  Select: {
    borderRadiusLG: 10,
  },
  Steps: {
    colorPrimary: '#f97316',
  },
  Timeline: {
    colorPrimary: '#f97316',
  },
}

// 深色模式组件级 token：侧边栏保持深黑渐变；主区组件切换为深色底
const darkComponents = {
  Layout: {
    siderBg: '#0a0a0a',
    headerBg: '#141414',
    headerHeight: 56,
    bodyBg: '#0a0a0a',
  },
  Menu: {
    darkItemBg: 'transparent',
    darkSubMenuItemBg: 'transparent',
    darkItemSelectedBg: 'rgba(249, 115, 22, 0.22)',
    darkItemHoverBg: 'rgba(249, 115, 22, 0.12)',
    darkItemColor: '#94a3b8',
    darkItemSelectedColor: '#ffffff',
    darkSubMenuItemColor: '#94a3b8',
  },
  Table: {
    headerBg: '#1a1a1a',
    headerColor: '#a8b4cc',
    rowHoverBg: '#1f1f1f',
    borderColor: '#2a2a2a',
  },
  Card: {
    headerBg: 'transparent',
    paddingLG: 24,
    borderRadiusLG: 20,
  },
  Button: {
    primaryShadow: 'none',
    defaultBorderColor: '#2a2a2a',
    borderRadiusLG: 999,
    borderRadius: 999,
  },
  Tag: {
    defaultBg: '#1a1a1a',
    defaultColor: '#a8b4cc',
  },
  Input: {
    borderRadius: 10,
  },
  Select: {
    borderRadiusLG: 10,
  },
  Steps: {
    colorPrimary: '#f97316',
  },
  Timeline: {
    colorPrimary: '#f97316',
  },
}

const themeConfig = computed(() => {
  const isDark = themeStore.mode === 'dark'
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      ...baseToken,
      ...(isDark ? darkToken : lightToken),
    },
    components: isDark ? darkComponents : lightComponents,
  }
})
</script>
