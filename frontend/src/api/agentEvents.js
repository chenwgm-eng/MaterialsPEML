import client from './client'

// P1-2：统一 Agent 调用事件日志
export const listAgentEvents = (params) => client.get('/agent-events', { params })
export const getAgentEventStats = () => client.get('/agent-events/stats')
