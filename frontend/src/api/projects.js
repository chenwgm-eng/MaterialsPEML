import client from './client'

/**
 * 项目空间相关 API 封装。
 *
 * 替代 Projects.vue 中直接拼 URL 调用 client 的散落写法，
 * 统一参数编码与错误处理。
 */

export const listProjects = () => client.get('/projects')

export const getProject = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}`)

export const getProjectProgress = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/progress`)

export const getProjectStageStatus = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/stage-status`)

export const updateProject = (projectId, data) =>
  client.put(`/projects/${encodeURIComponent(projectId)}`, data)

export const deleteProject = (projectId) =>
  client.delete(`/projects/${encodeURIComponent(projectId)}`)

export const decomposeProject = (data) =>
  client.post('/projects/decompose', data)

// --- 项目任务 ---

export const listProjectTasks = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/tasks`)

export const createProjectTask = (projectId, data) =>
  client.post(`/projects/${encodeURIComponent(projectId)}/tasks`, data)

export const updateProjectTask = (projectId, taskId, data) =>
  client.put(`/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`, data)

export const deleteProjectTask = (projectId, taskId) =>
  client.delete(`/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`)

// --- 项目聚合数据 ---

export const getProjectEntityGraph = (projectId, params = {}) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/entity-graph`, { params })

export const getProjectOrders = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/orders`)

export const getProjectCandidates = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/candidates`)

export const getProjectSamples = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/samples`)

export const getProjectResults = (projectId) =>
  client.get(`/projects/${encodeURIComponent(projectId)}/results`)
