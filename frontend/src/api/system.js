import client from './client'

export const getHealth = () => client.get('/health')
export const getTools = (params) => client.get('/tools', params ? { params } : undefined)
export const getMcpManifest = () => client.get('/mcp/manifest')
export const getStats = () => client.get('/stats')
export const getConfig = () => client.get('/config')
export const updateConfig = (data) => client.post('/config', data)
export const getModelCatalog = () => client.get('/settings/model_catalog')
// 全局后台异步任务（供右下角浮动指示器轮询展示运行中的计算任务）
export const getAsyncTasks = () => client.get('/v1/async-tasks')
// 工具可用性自测：部分工具（LLM/SCP）响应较慢，放宽超时到 90s
export const testTool = (name) => client.post(`/tools/${encodeURIComponent(name)}/test`, null, { timeout: 90000 })
