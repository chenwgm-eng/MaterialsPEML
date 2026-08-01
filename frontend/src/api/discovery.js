import client from './client'

export const discoverCrystal = (data) => client.post('/discover/crystal', data)
export const discoverPolymer = (data) => client.post('/discover/polymer', data)
export const routeMaterial = (data) => client.post('/route', data)
export const generateCandidates = (data) => client.post('/discover/generate', data)
export const agentGenerateCandidates = (data) => client.post('/discover/agent-generate', data, { timeout: 120000 })

// 异步 Agent 生成（返回 task_id，轮询进度）
export const agentGenerateAsync = (data) => client.post('/discover/agent-generate/async', data)
export const getAgentGenerateStatus = (taskId) => client.get(`/discover/agent-generate/${taskId}/status`)

// 需求7：批量预测候选材料属性（返回三点状态）
export const batchPredictCandidates = (data) => client.post('/discover/batch-predict', data, { timeout: 120000 })
