import client from './client'

export const getHealth = () => client.get('/health')
export const getTools = (params) => client.get('/tools', params ? { params } : undefined)
export const getMcpManifest = () => client.get('/mcp/manifest')
export const getStats = () => client.get('/stats')
export const getConfig = (params = {}) => client.get('/config', { params })
export const updateConfig = (data) => client.post('/config', data)
export const getModelCatalog = () => client.get('/settings/model_catalog')
// 研发领域（DB 持久化，系统启动按该领域执行）
export const getActiveDomain = () => client.get('/settings/domain')
export const setActiveDomain = (data) => client.post('/settings/domain', data)
// 全局后台异步任务（供右下角浮动指示器轮询展示运行中的计算任务）
export const getAsyncTasks = () => client.get('/v1/async-tasks')
// 工具可用性自测：部分工具（LLM/SCP）响应较慢，放宽超时到 90s
export const testTool = (name) => client.post(`/tools/${encodeURIComponent(name)}/test`, null, { timeout: 90000 })
