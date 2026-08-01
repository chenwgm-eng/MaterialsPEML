import client from './client'

/** 提交物料申请（add / update / delete） */
export const createMaterialRequest = (payload) =>
  client.post('/material-requests', payload)

/** 查询物料申请列表，可选按状态筛选 */
export const listMaterialRequests = (status = '') =>
  client.get('/material-requests', { params: status ? { status } : {} })

/** 审批通过（自动写入物料库 + 创建版本快照） */
export const approveMaterialRequest = (requestId, payload) =>
  client.post(`/material-requests/${encodeURIComponent(requestId)}/approve`, payload)

/** 审批驳回 */
export const rejectMaterialRequest = (requestId, payload) =>
  client.post(`/material-requests/${encodeURIComponent(requestId)}/reject`, payload)
