import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 全局任务状态管理：跟踪跨页面的耗时异步任务。
 * 各页面（ResearchWorkbench、ECMLMonitor 等）在启动/轮询任务时调用 taskStore 更新状态。
 */
export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref([])

  const activeCount = computed(() => tasks.value.filter((t) => t.status === 'running').length)

  function addTask(task) {
    tasks.value.push({
      id: task.id || `task_${Date.now()}`,
      name: task.name || '未命名任务',
      type: task.type || 'research', // research / ecml / prediction
      status: 'running', // running / completed / failed
      progress: 0, // 0-100
      detail: '',
      startedAt: Date.now(),
      completedAt: null,
    })
  }

  function updateTask(id, updates) {
    const task = tasks.value.find((t) => t.id === id)
    if (task) {
      Object.assign(task, updates)
      if (updates.status === 'completed' || updates.status === 'failed') {
        task.completedAt = Date.now()
      }
    }
  }

  function removeTask(id) {
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx >= 0) tasks.value.splice(idx, 1)
  }

  // 自动清理：保留最近 5 条已完成任务，超过的移除最早的
  function prune() {
    const done = tasks.value.filter((t) => t.status !== 'running')
    if (done.length > 5) {
      const toRemove = done.slice(0, done.length - 5)
      tasks.value = tasks.value.filter((t) => !toRemove.includes(t))
    }
  }

  return { tasks, activeCount, addTask, updateTask, removeTask, prune }
})
