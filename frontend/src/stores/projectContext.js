import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listProjects } from '@/api/projects'
import { safeParseJson } from '@/utils/errorHandler'

/**
 * 全局当前项目上下文
 * 审查意见0726：避免候选设计、实验数据、预算看板、决策记录各自重新选择项目/scope
 */
export const useProjectContextStore = defineStore('projectContext', () => {
  const currentProject = ref(null) // { project_id, name, ... }
  const projectList = ref([])
  const loading = ref(false)

  const currentProjectId = computed(() => currentProject.value?.project_id || '')

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
    if (!project) return
    currentProject.value = project
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

  function clearCurrentProject() {
    currentProject.value = null
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
    fetchProjects,
    setCurrentProject,
    clearCurrentProject,
    restoreFromStorage,
  }
})
