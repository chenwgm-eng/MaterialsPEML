import client from './client'

// 编排类接口涉及 LLM 调用，超时设为 120 秒
const ORCHESTRATION_TIMEOUT = 120000

export const analyzeTask = (data) =>
  client.post('/orchestrate/analyze', data, { timeout: ORCHESTRATION_TIMEOUT })
export const executePlan = (data) =>
  client.post('/orchestrate/execute', data, { timeout: ORCHESTRATION_TIMEOUT })
export const getRecord = (id) => client.get(`/orchestrate/record/${id}`)
export const getHistory = () => client.get('/orchestrate/history')
