import client from './client'

// 决策 4-C：映射控制台 API
// 业务活动↔智能体↔工具 三层绑定的 CRUD + 新工具注册

export const getMappingOverview = () => client.get('/mappings/overview')

export const listActivityBindings = (category = '') =>
  client.get('/mappings/activities', { params: category ? { category } : undefined })

export const upsertActivityBinding = (activityId, data) =>
  client.put(`/mappings/activities/${encodeURIComponent(activityId)}`, data)

export const deleteActivityBinding = (bindingId) =>
  client.delete(`/mappings/activities/${encodeURIComponent(bindingId)}`)

export const listToolBindings = (agentId = '') =>
  client.get('/mappings/agent-tools', { params: agentId ? { agent_id: agentId } : undefined })

export const upsertToolBinding = (agentId, capability, data) =>
  client.put(`/mappings/agent-tools/${encodeURIComponent(agentId)}/${encodeURIComponent(capability)}`, data)

export const deleteToolBinding = (bindingId) =>
  client.delete(`/mappings/agent-tools/${encodeURIComponent(bindingId)}`)

export const listToolRegistrations = (source = '') =>
  client.get('/mappings/tools', { params: source ? { source } : undefined })

export const registerTool = (data) => client.post('/mappings/tools', data)

export const updateTool = (toolId, data) =>
  client.put(`/mappings/tools/${encodeURIComponent(toolId)}`, data)

export const deleteTool = (toolId) =>
  client.delete(`/mappings/tools/${encodeURIComponent(toolId)}`)

export const getAgentAvailableTools = (agentId) =>
  client.get(`/mappings/agents/${encodeURIComponent(agentId)}/tools`)
