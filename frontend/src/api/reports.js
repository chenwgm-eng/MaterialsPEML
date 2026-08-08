import client from './client'

// 报表导出 / 定时报表（report.export 权限）
// exportReport 返回 Blob，调用方可结合 URL.createObjectURL 触发下载。
export function exportReport(payload) {
  return client.post('/report/export', payload, { responseType: 'blob' })
}
export function scheduleReport(payload) {
  return client.post('/report/schedule', payload)
}
export function getLastReport() {
  return client.get('/report/last')
}