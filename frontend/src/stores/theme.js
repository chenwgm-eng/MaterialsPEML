import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'theme-mode'
const VALID_MODES = ['light', 'dark']

function getInitialMode() {
  if (typeof window === 'undefined') return 'light'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored && VALID_MODES.includes(stored)) return stored
  } catch {
    // localStorage 不可用（隐私模式等），回退到默认值
  }
  return 'light'
}

function applyTheme(mode) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', mode)
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref(getInitialMode())

  // store 创建时立即应用主题，确保首屏渲染前 data-theme 已就位
  applyTheme(mode.value)

  function setTheme(next) {
    if (!VALID_MODES.includes(next) || next === mode.value) return
    mode.value = next
    applyTheme(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // 写入失败时忽略，内存态仍生效
    }
  }

  function toggleTheme() {
    setTheme(mode.value === 'light' ? 'dark' : 'light')
  }

  return { mode, setTheme, toggleTheme }
})
