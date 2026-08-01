import client from './client'

export function getCapabilities(params = {}) {
  return client.get('/capabilities', { params })
}
export function getCapability(capabilityId) {
  return client.get(`/capabilities/${encodeURIComponent(capabilityId)}`)
}
export function createCapability(data) {
  return client.post('/capabilities', data)
}
export function updateCapability(capabilityId, data) {
  return client.put(`/capabilities/${encodeURIComponent(capabilityId)}`, data)
}
export function deleteCapability(capabilityId) {
  return client.delete(`/capabilities/${encodeURIComponent(capabilityId)}`)
}
export function approveCapability(capabilityId) {
  return client.post(`/capabilities/${encodeURIComponent(capabilityId)}/approve`)
}
export function deprecateCapability(capabilityId) {
  return client.post(`/capabilities/${encodeURIComponent(capabilityId)}/deprecate`)
}
export function getCapabilityFallbackChain(capabilityId) {
  return client.get(`/capabilities/${encodeURIComponent(capabilityId)}/fallback-chain`)
}
