import client from './client'

/** 获取委员会案件列表 */
export function getCommitteeCases(params = {}) {
  return client.get('/committees/cases', { params })
}

/** 获取单个案件详情 */
export function getCommitteeCase(caseId) {
  return client.get(`/committees/cases/${caseId}`)
}

/** 创建或预览委员会案件 */
export function createCommitteeCase(data) {
  return client.post('/committees/cases', data)
}

/** 异步执行案件 */
export function runCommitteeCase(caseId) {
  return client.post(`/committees/cases/${caseId}/run`)
}

/** 人工复核 */
export function reviewCommitteeCase(caseId, data) {
  return client.post(`/committees/cases/${caseId}/review`, data)
}

/** 取消案件 */
export function cancelCommitteeCase(caseId) {
  return client.post(`/committees/cases/${caseId}/cancel`)
}

/** 获取委员会指标 */
export function getCommitteeMetrics() {
  return client.get('/committees/metrics')
}

/** 获取候选优先级队列 */
export function getPriorityQueue(caseId) {
  return client.get(`/committees/cases/${caseId}/priority-queue`)
}

/** 获取偏差复盘反馈动作 */
export function getFeedbackActions(caseId) {
  return client.get(`/committees/cases/${caseId}/feedback-actions`)
}

/** 获取外部证据采纳状态 */
export function getEvidenceAdoption(caseId) {
  return client.get(`/committees/cases/${caseId}/evidence-adoption`)
}

/** 获取策略配置 */
export function getCommitteePolicies() {
  return client.get('/committee/policies')
}

/** 更新策略配置 */
export function updateCommitteePolicies(data) {
  return client.put('/committee/policies', data)
}