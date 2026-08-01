import client from './client'

// 统一研发工作台 API。
// 注意：client 是 ./client 的默认导出（axios 实例，响应拦截器已返回 resp.data），
// 与 controlPlane.js 的导入方式一致，因此这里直接复用同一实例。
export const researchApi = {
  createRequest(data) {
    return client.post('/research/requests', data)
  },
  getRequest(requestId) {
    return client.get(`/research/requests/${requestId}`)
  },
  listRequests(limit = 50, status = null) {
    const params = { limit }
    if (status) params.status = status
    return client.get('/research/requests', { params })
  },
  startRun(requestId) {
    return client.post(`/research/requests/${requestId}/start`)
  },
  getRunEvents(runId) {
    return client.get(`/research/runs/${runId}/events`)
  },
  replanRun(planId) {
    return client.post(`/research/runs/${planId}/replan`)
  },
  explainRun(requestId) {
    return client.get(`/research/runs/${requestId}/explain`)
  },
}
