import { defineStore } from 'pinia'
import { ref } from 'vue'
import { analyzeTask, executePlan, getRecord, getHistory } from '@/api/orchestration'

export const useOrchestrationStore = defineStore('orchestration', () => {
  const plan = ref(null) // AI 推荐的编排方案
  const currentRecord = ref(null) // 当前执行记录
  const history = ref([]) // 历史记录
  const loading = ref(false)
  const executing = ref(false)
  let pollTimer = null // 定时器 ID 无需响应式

  async function analyze(target, constraints = {}) {
    loading.value = true
    try {
      plan.value = await analyzeTask({ target, constraints })
      return plan.value
    } finally {
      loading.value = false
    }
  }

  async function execute(target, team, steps) {
    loading.value = true
    executing.value = true
    try {
      const res = await executePlan({ target, team, steps })
      // 开始轮询执行记录
      startPolling(res.record_id)
      return res
    } finally {
      loading.value = false
    }
  }

  function startPolling(recordId) {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const record = await getRecord(recordId)
        currentRecord.value = record
        if (record.status === 'completed' || record.status === 'failed') {
          stopPolling()
          executing.value = false
        }
      } catch (e) {
        stopPolling()
        executing.value = false
      }
    }, 1500)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function fetchHistory() {
    const res = await getHistory()
    history.value = res.history || []
    return res
  }

  function reset() {
    plan.value = null
    currentRecord.value = null
    stopPolling()
    executing.value = false
  }

  // 取消执行：停止轮询并标记 executing=false
  function cancel() {
    stopPolling()
    executing.value = false
  }

  return {
    plan,
    currentRecord,
    history,
    loading,
    executing,
    analyze,
    execute,
    fetchHistory,
    reset,
    cancel,
    stopPolling,
  }
})
