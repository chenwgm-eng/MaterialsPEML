import client from './client'

export function getFieldDict(entityType) {
  return client.get(`/ingest/field-dict/${entityType}`)
}
export function previewIngest(data) {
  return client.post('/ingest/preview', data)
}
export function commitIngest(data) {
  return client.post('/ingest/commit', data)
}
export function listImports(params = {}) {
  return client.get('/ingest/imports', { params })
}
export function getImportDetail(importId) {
  return client.get(`/ingest/imports/${importId}`)
}
