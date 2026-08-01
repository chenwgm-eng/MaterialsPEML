import client from './client'

export const listAgents = () => client.get('/agents')
export const createAgent = (data) => client.post('/agents', data)
export const updateAgent = (id, data) => client.put(`/agents/${encodeURIComponent(id)}`, data)
export const deleteAgent = (id) => client.delete(`/agents/${encodeURIComponent(id)}`)
export const getAgentsHealth = () => client.get('/agents/health')
export const sendHeartbeat = (id, data) => client.post(`/agents/${encodeURIComponent(id)}/heartbeat`, data)

// 获取智能体可选的模型提供方（llm / internlm）及其服务地址、模型名
export const getLlmOptions = () => client.get('/agents/llm-options')

// 与指定智能体进行测试对话
export const chatWithAgent = (id, data) =>
  client.post(`/agents/${encodeURIComponent(id)}/chat`, data, { timeout: 120000 })
