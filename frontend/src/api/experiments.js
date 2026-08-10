import client from './client'

/**
 * 实验记录相关 API 封装。
 *
 * 替代各视图中直接拼 URL 调用 client 的散落写法，
 * 统一参数编码与错误处理。
 */

// --- 实验记录基础 ---

export const listExperimentTypes = (options = {}) =>
  client.get('/experiments/types', { skipErrorNotification: true, ...options })

export const listExperiments = (params = {}) =>
  client.get('/experiments', { params })

export const getExperiment = (recordId) =>
  client.get(`/experiments/${encodeURIComponent(recordId)}`)

export const updateExperiment = (recordId, data) =>
  client.put(`/experiments/${encodeURIComponent(recordId)}`, data)

export const deleteExperiment = (recordId) =>
  client.delete(`/experiments/${encodeURIComponent(recordId)}`)

// POST /experiments/query —— 复杂条件查询（stores/experiments.js 使用）
export const queryExperiments = (data) =>
  client.post('/experiments/query', data)

// --- 合成与验证 ---

export const checkSynthesis = (data) =>
  client.post('/synthesis/check', data)

export const verifyMaterial = (data) =>
  client.post('/verify', data)

// --- 合成路径规划 ---

export const getReactionNetwork = (smiles) =>
  client.get(`/synthesis/network/${encodeURIComponent(smiles)}`)

export const verifyRouteWithDFT = (data) =>
  client.post('/synthesis/verify-dft', data)

// --- 实验任务（orders） ---

export const listExperimentOrders = (params = {}) =>
  client.get('/experiments/orders', { params })

export const createExperimentOrder = (data) =>
  client.post('/experiments/orders', data)

// 订单元数据编辑 / 删除 / 审批
export const updateExperimentOrder = (orderId, data) =>
  client.patch(`/experiments/orders/${encodeURIComponent(orderId)}`, data)

export const deleteExperimentOrder = (orderId) =>
  client.delete(`/experiments/orders/${encodeURIComponent(orderId)}`)

export const approveExperimentOrder = (orderId, data) =>
  client.post(`/experiments/orders/${encodeURIComponent(orderId)}/approve`, data)

export const rejectExperimentOrder = (orderId, data) =>
  client.post(`/experiments/orders/${encodeURIComponent(orderId)}/reject`, data)

// --- 实验结果 ---

export const listExperimentResults = (params = {}) =>
  client.get('/experiments/results', { params })

export const createExperimentResultManual = (data) =>
  client.post('/experiments/results/manual', data)

export const createExperimentResultsBatch = (data) =>
  client.post('/experiments/results', data)

export const uploadExperimentFile = (formData) =>
  client.post('/experiments/results/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

// --- 实验分析与偏差 ---

export const getExperimentAnalysis = (orderId) =>
  client.get(`/experiments/analysis/${encodeURIComponent(orderId)}`)

export const checkDeviation = (data) =>
  client.post('/experiments/deviation-check', data)

export const markAnomalies = (data) =>
  client.post('/experiments/anomaly-mark', data)

// --- 审批规则（复用 approvals 模块，避免重复定义） ---

export { listApprovalRules } from './approvals'

// --- 数据质量待审 ---

export const listQCPending = () => client.get('/qc/pending')

export const triggerQC = (resultId) =>
  client.post(`/qc/check/${encodeURIComponent(resultId)}`)
