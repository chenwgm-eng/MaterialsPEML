import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listProjects, listProjectTasks } from '@/api/projects'
import { safeParseJson } from '@/utils/errorHandler'

/**
 * 全局当前项目上下文
 * 审查意见0726：避免候选设计、实验数据、预算看板、决策记录各自重新选择项目/scope
 * 三栏方案 #1：新增任务级上下文（currentTask）+ 「全部项目/全部任务」语义
 */
export const useProjectContextStore = defineStore('projectContext', () => {
  const currentProject = ref(null) // { project_id, name, ... }；null=全部项目
  const projectList = ref([])
  const loading = ref(false)
  // 任务级上下文（项目空间 #1）：currentTask=null 表示全部任务
  const currentTask = ref(null)
  const taskList = ref([])
  const tasksLoading = ref(false)

  const currentProjectId = computed(() => currentProject.value?.project_id || '')
  const currentTaskId = computed(() => currentTask.value?.task_id || '')

  async function fetchProjects() {
    loading.value = true
    try {
      const res = await listProjects()
      projectList.value = Array.isArray(res) ? res : (res.projects || res.items || [])
      // 默认选中第一个项目
      if (projectList.value.length > 0 && !currentProject.value) {
        setCurrentProject(projectList.value[0])
      } else if (projectList.value.length > 0 && currentProject.value) {
        // 切换后若旧的项目不在列表中，重置为第一个
        const exists = projectList.value.find(p => p.project_id === currentProject.value.project_id)
        if (!exists) setCurrentProject(projectList.value[0])
      }
      return projectList.value
    } finally {
      loading.value = false
    }
  }

  function setCurrentProject(project) {
    currentProject.value = project || null
    // 项目切换时任务上下文失效
    currentTask.value = null
    taskList.value = []
    if (!project) {
      try {
        localStorage.removeItem('currentProject')
        localStorage.removeItem('currentProjectId')
        localStorage.removeItem('currentProjectName')
      } catch {
        /* ignore */
      }
      return
    }
    // 持久化完整项目对象到 localStorage，避免刷新后字段丢失
    try {
      localStorage.setItem('currentProject', JSON.stringify(project))
      // 保留 id/name 冗余键以兼容旧逻辑读取
      localStorage.setItem('currentProjectId', project.project_id)
      localStorage.setItem('currentProjectName', project.name || '')
    } catch {
      // ignore
    }
  }

  /** 拉取当前项目下的任务列表（用于任务级过滤） */
  async function fetchTasks(projectId = '') {
    const pid = projectId || currentProjectId.value
    if (!pid) {
      taskList.value = []
      return []
    }
    tasksLoading.value = true
    try {
      const res = await listProjectTasks(pid)
      taskList.value = Array.isArray(res) ? res : (res.tasks || res.items || [])
      return taskList.value
    } catch {
      taskList.value = []
      return []
    } finally {
      tasksLoading.value = false
    }
  }

  function setCurrentTask(task) {
    currentTask.value = task || null
  }

  function clearCurrentProject() {
    currentProject.value = null
    currentTask.value = null
    taskList.value = []
    try {
      localStorage.removeItem('currentProject')
      localStorage.removeItem('currentProjectId')
      localStorage.removeItem('currentProjectName')
    } catch {
      // ignore
    }
  }

  /** 从 localStorage 恢复会话（优先读取完整对象，兜底旧 id/name 键） */
  function restoreFromStorage() {
    try {
      const raw = localStorage.getItem('currentProject')
      if (raw) {
        const obj = safeParseJson(raw)
        if (obj && obj.project_id) {
          currentProject.value = obj
          return obj
        }
      }
    } catch {
      // JSON 解析失败，回退到旧格式
    }
    const pid = localStorage.getItem('currentProjectId')
    if (!pid) return null
    const name = localStorage.getItem('currentProjectName') || ''
    currentProject.value = { project_id: pid, name }
    return currentProject.value
  }

  return {
    currentProject,
    projectList,
    loading,
    currentProjectId,
    currentTask,
    taskList,
    tasksLoading,
    currentTaskId,
    fetchProjects,
    setCurrentProject,
    fetchTasks,
    setCurrentTask,
    clearCurrentProject,
    restoreFromStorage,
  }
})
