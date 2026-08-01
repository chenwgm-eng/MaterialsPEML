import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getHealth, getTools, getMcpManifest, getConfig, updateConfig } from '@/api/system'

const HEALTH_TTL = 30000 // 30s 内复用健康状态，避免多组件重复请求

export const useSystemStore = defineStore('system', () => {
  const health = ref(null)
  const tools = ref([])
  const mcpManifest = ref(null)
  const config = ref(null)
  const loading = ref(false)
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

  async function init() {
    await Promise.all([fetchHealth(), fetchTools(), fetchMcpManifest(), fetchConfig()])
  }

  return {
    health, tools, mcpManifest, config, loading,
    fetchHealth, fetchTools, fetchMcpManifest, fetchConfig, saveConfig,
    init,
  }
})
