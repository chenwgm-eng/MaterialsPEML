import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getHealth, getTools, getMcpManifest, getConfig, updateConfig } from '@/api/system'
import { getCurrentUser } from '@/api/auth'
import { getNavVisibility } from '@/api/navVisibility'

const HEALTH_TTL = 30000 // 30s 内复用健康状态，避免多组件重复请求

export const useSystemStore = defineStore('system', () => {
  const health = ref(null)
  const tools = ref([])
  const mcpManifest = ref(null)
  const config = ref(null)
  const loading = ref(false)
  // Step B：当前用户 / 导航可见入口 / 权限点 / 专业画像
  const currentUser = ref(null)
  const visibleEntries = ref([])
  const permissions = ref([])
  const disciplines = ref([])
  const primaryDiscipline = ref('')
  let _healthLastFetch = 0

  async function fetchHealth(force = false) {
    const now = Date.now()
    if (!force && health.value && now - _healthLastFetch < HEALTH_TTL) {
      return health.value
    }
    health.value = await getHealth()
    _healthLastFetch = now
    return health.value
  }

  async function fetchTools() {
    loading.value = true
    try {
      const res = await getTools()
      tools.value = res.tools || []
      return res
    } finally {
      loading.value = false
    }
  }

  async function fetchMcpManifest() {
    loading.value = true
    try {
      mcpManifest.value = await getMcpManifest()
      return mcpManifest.value
    } finally {
      loading.value = false
    }
  }

  async function fetchConfig() {
    config.value = await getConfig()
    return config.value
  }

  async function saveConfig(data) {
    const res = await updateConfig(data)
    config.value = res
    return res
  }

  async function fetchMe() {
    // Step B：拉取当前用户信息 + 权限点 + 专业画像 + 导航可见入口。
    // 失败时静默（后端不可达不阻塞页面）。
    try {
      const data = await getCurrentUser()
      currentUser.value = data
      permissions.value = data.permissions || []
      disciplines.value = data.disciplines || []
      primaryDiscipline.value = data.primary_discipline || ''
      // 写一份轻量同步缓存供路由守卫同步读取（守卫不可 await）
      localStorage.setItem('permissions', JSON.stringify(permissions.value))
      try {
        const nav = await getNavVisibility()
        if (Array.isArray(nav.visible)) {
          // 普通角色：直接取可见入口列表
          visibleEntries.value = nav.visible
        } else if (nav.matrix && currentUser.value?.role) {
          // 管理员：取当前角色矩阵中可见的 key 列表
          const m = nav.matrix[currentUser.value.role] || {}
          visibleEntries.value = Object.keys(m).filter((k) => m[k])
        }
      } catch {
        // nav_visibility 不可达不阻塞
      }
      return data
    } catch {
      // 静默失败
      return null
    }
  }

  async function init() {
    await Promise.all([fetchHealth(), fetchTools(), fetchMcpManifest(), fetchConfig()])
  }

  return {
    health, tools, mcpManifest, config, loading,
    currentUser, visibleEntries, permissions, disciplines, primaryDiscipline,
    fetchHealth, fetchTools, fetchMcpManifest, fetchConfig, saveConfig,
    fetchMe,
    init,
  }
})
