import client from './client'

export function listPendingApprovals(params = {}) {
  return client.get('/approvals/pending', { params })
}

export function listApprovalRules() {
  return client.get('/approvals/rules')
}

export function approveExperimentOrder(orderId, data) {
  return client.post(`/experiments/orders/${encodeURIComponent(orderId)}/approve`, data)
}

export function rejectExperimentOrder(orderId, data) {
  return client.post(`/experiments/orders/${encodeURIComponent(orderId)}/reject`, data)
}

export function approveQCResult(resultId, data) {
  return client.post(`/qc/${encodeURIComponent(resultId)}/approve`, data)
}

export function rejectQCResult(resultId, data) {
  return client.post(`/qc/${encodeURIComponent(resultId)}/reject`, data)
}
