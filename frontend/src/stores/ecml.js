import { defineStore } from 'pinia'
import { readonly, ref } from 'vue'
import { runECML, getECMLRun } from '@/api/ecml'

export const useECMLStore = defineStore('ecml', () => {
  const state = ref(null)
  const history = ref([])
  const loading = ref(false)
  const running = ref(false)
  let pollTimer = null

  async function run(target, targetProperty, maxIterations, targetProperties = null, parentRunId = null, scenarioId = '') {
    loading.value = true
    running.value = true
    try {
      const payload = { target, target_property: targetProperty, max_iterations: maxIterations }
      if (targetProperties && Array.isArray(targetProperties) && targetProperties.length > 0) {
        payload.target_properties = targetProperties
      }
      if (parentRunId) {
        payload.parent_run_id = parentRunId
      }
      if (scenarioId) {
        payload.scenario_id = scenarioId
      }
      const res = await runECML(payload)
      state.value = res
      // 同步完成（旧后端或瞬时任务）：直接落库并结束 running
      if (res?.is_complete) {
        running.value = false
        history.value = [
          { timestamp: new Date().toISOString(), ...res },
          ...history.value,
        ].slice(0, 50)
      }
      return res
    } finally {
      loading.value = false
    }
  }

  async function pollRun(run_id) {
    const res = await getECMLRun(run_id)
    state.value = res
    return res
  }

  async function restoreRun(run_id) {
    loading.value = true
    running.value = true
    try {
      const res = await getECMLRun(run_id)
      state.value = res
      if (res?.is_complete) {
        running.value = false
        history.value = [
          { timestamp: new Date().toISOString(), ...res },
          ...history.value,
        ].slice(0, 50)
      }
      return res
    } finally {
      loading.value = false
    }
  }

  function startPolling(run_id, intervalMs = 2000) {
    stopPolling()
    const tick = async () => {
      if (!running.value) return
      try {
        const res = await pollRun(run_id)
        if (res?.is_complete) {
          stopPolling()
          running.value = false
          history.value = [
            { timestamp: new Date().toISOString(), ...res },
            ...history.value,
          ].slice(0, 50)
          return
        }
      } catch {
        // 轮询失败（网络/后端错误）：停止轮询，错误已由 interceptor 提示
        stopPolling()
        running.value = false
        return
      }
      if (running.value) {
        pollTimer = setTimeout(tick, intervalMs)
      }
    }
    pollTimer = setTimeout(tick, intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  // 取消运行：停止轮询并标记 running=false
  function cancel() {
    stopPolling()
    running.value = false
  }

  // 重置 store 到初始状态
  function reset() {
    stopPolling()
    state.value = null
    running.value = false
    loading.value = false
  }

  function clearHistory() {
    history.value = []
  }

  // 标记当前运行为已取消（供 ECMLMonitor 调用，避免直接修改 readonly state）
  function markCancelled() {
    if (state.value) {
      state.value = { ...state.value, is_complete: true, cancelled: true }
    }
  }

  return {
    state: readonly(state),
    history: readonly(history),
    loading: readonly(loading),
    running: readonly(running),
    run,
    pollRun,
    restoreRun,
    startPolling,
    stopPolling,
    cancel,
    reset,
    clearHistory,
    markCancelled,
  }
})
