import client from './client'

// 研发收益证明层（Value Realization）
export function getBaseline(projectId) {
  return client.get(`/value-baselines/${encodeURIComponent(projectId)}`)
}
export function saveBaseline(projectId, data) {
  return client.put(`/value-baselines/${encodeURIComponent(projectId)}`, data)
}
export function getCostRules(params = {}) {
  return client.get('/cost-rules', { params })
}
export function createCostRule(data) {
  return client.post('/cost-rules', data)
}
export function updateCostRule(ruleId, data) {
  return client.put(`/cost-rules/${encodeURIComponent(ruleId)}`, data)
}
export function deleteCostRule(ruleId) {
  return client.delete(`/cost-rules/${encodeURIComponent(ruleId)}`)
}
export function getValueReport(projectId) {
  return client.get(`/value-reports/${encodeURIComponent(projectId)}`)
}
export function getValueReportMarkdown(projectId) {
  return client.get(`/value-reports/${encodeURIComponent(projectId)}/markdown`, {
    responseType: 'text',
  })
}
