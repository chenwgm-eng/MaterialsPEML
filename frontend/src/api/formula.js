import client from './client'

export function listFormulas(params = {}) {
  return client.get('/formulas', { params })
}

export function getFormula(formulaId, versionId = '') {
  const params = versionId ? { version_id: versionId } : {}
  return client.get(`/formulas/${encodeURIComponent(formulaId)}`, { params })
}

export function saveFormula(data) {
  return client.post('/formulas', data)
}

export function getFormulaHistory(formulaId) {
  return client.get(`/formulas/${encodeURIComponent(formulaId)}/history`)
}

export function activateFormulaVersion(formulaId, versionId) {
  return client.post(`/formulas/${encodeURIComponent(formulaId)}/versions/${encodeURIComponent(versionId)}/activate`)
}
