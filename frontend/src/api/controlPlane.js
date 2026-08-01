import client from './client'

export function getRuns(params = {}) {
  return client.get('/control-plane/runs', { params })
}
export function getRun(runId) {
  return client.get(`/control-plane/runs/${runId}`)
}
export function resumeRun(runId) {
  return client.post(`/control-plane/runs/${runId}/resume`)
}
export function cancelRun(runId) {
  return client.post(`/control-plane/runs/${runId}/cancel`)
}
export function getTrace(correlationId) {
  return client.get(`/control-plane/traces/${correlationId}`)
}
export function getBudgets(params = {}) {
  return client.get('/control-plane/budgets', { params })
}
export function updateBudget(scope, data) {
  return client.put(`/control-plane/budgets/${scope}`, data)
}
export function getTools() {
  return client.get('/control-plane/tools')
}
export function contractTestTool(toolId) {
  return client.post(`/control-plane/tools/${toolId}/contract-test`)
}
export function getSCPBindings() {
  return client.get('/tools/scp-bindings')
}
export function updateSCPBinding(internalName, data) {
  return client.put(`/tools/scp-bindings/${internalName}`, data)
}
export function getSkills() {
  return client.get('/tools/skills')
}
export function testSkill(skillId, arguments_ = {}) {
  return client.post('/tools/skills/test', { skill_id: skillId, arguments: arguments_ }, { timeout: 120000 })
}
export function getProviders() {
  return client.get('/control-plane/providers')
}
export function getPolicies() {
  return client.get('/control-plane/policies')
}
export function getMemoryCards(params = {}) {
  return client.get('/memory/cards', { params })
}
export function createEvalRun(data) {
  return client.post('/evals/runs', data)
}
export function listEvalRuns(params = {}) {
  return client.get('/evals/runs', { params })
}
export function getEvalRun(evalRunId) {
  return client.get(`/evals/runs/${evalRunId}`)
}
export function promoteEval(data) {
  return client.post('/evals/promote', data)
}

export const getAgentEligibility = (agentId) => client.get(`/agents/${encodeURIComponent(agentId)}/eligibility`)
export const updateAgentEligibility = (agentId, rules) => client.put(`/agents/${encodeURIComponent(agentId)}/eligibility`, rules)
export const getModelRoutes = () => client.get('/model-routes')
export const updateModelRoute = (routeId, updates) => client.patch(`/model-routes/${encodeURIComponent(routeId)}`, updates)
