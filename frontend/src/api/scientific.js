import client from './client'

/**
 * 科学工作台 API 客户端
 *
 * 覆盖：
 *  - 任务/Run 管理（scientific_runs.py）
 *  - Artifact / Evidence 查询（artifacts.py / evidence.py）
 *  - 审批管理（approvals.py）
 *  - 12 个原生科学服务的核心命令入口
 *  - 混编工作流执行（workflow_routes.py）
 *
 * 路由约定：client baseURL 为 /api，后端科学路由统一挂载在 /v1 下，
 * 因此此处路径写作 '/v1/...'，经 vite proxy rewrite 后命中后端。
 */

// ── 任务管理 ────────────────────────────────────────────────

export function createTask (params) {
  return client.post('/v1/tasks', params)
}

export function getTask (taskId) {
  return client.get(`/v1/tasks/${taskId}`)
}

export function listTasks (params) {
  return client.get('/v1/tasks', { params })
}

// ── Run 管理 ────────────────────────────────────────────────

export function submitRun (params) {
  return client.post('/v1/runs', params)
}

export function getRun (runId) {
  return client.get(`/v1/runs/${runId}`)
}

export function listRuns (params) {
  return client.get('/v1/runs', { params })
}

export function cancelRun (runId) {
  return client.post(`/v1/runs/${runId}/cancel`)
}

export function resumeRun (runId) {
  return client.post(`/v1/runs/${runId}/resume`)
}

// ── Artifact 查询 ───────────────────────────────────────────

export function getArtifacts (runId) {
  return client.get(`/v1/runs/${runId}/artifacts`)
}

export function storeArtifact (params) {
  return client.post('/v1/artifacts', params)
}

// ── Evidence 查询 ───────────────────────────────────────────

export function getEvidence (evidenceId) {
  return client.get(`/v1/evidence/${evidenceId}`)
}

export function getRunEvidence (runId) {
  return client.get(`/v1/runs/${runId}/evidence`)
}

export function storeEvidence (params) {
  return client.post('/v1/evidence', params)
}

// ── 审批管理 ────────────────────────────────────────────────

export function requestApproval (evidenceId) {
  return client.post(`/v1/approvals/request/${evidenceId}`)
}

export function approve (approvalId, reviewer, comment = '') {
  return client.post(`/v1/approvals/${approvalId}/approve`, { reviewer, comment })
}

export function reject (approvalId, reviewer, comment = '') {
  return client.post(`/v1/approvals/${approvalId}/reject`, { reviewer, comment })
}

export function getApproval (approvalId) {
  return client.get(`/v1/approvals/${approvalId}`)
}

export function listApprovals (params) {
  return client.get('/v1/approvals', { params })
}

// ── 12 个原生科学服务调用入口 ────────────────────────────────
// 每个服务至少暴露一个核心命令；多数服务同时提供直接执行（返回 Artifact）
// 与全生命周期执行（返回 EvidencePackage）两个入口。

// 1. MPA 分子性质预测 — /v1/mpa
export const mpa = {
  predict: (params) => client.post('/v1/mpa/predict', params),
  predictFull: (params) => client.post('/v1/mpa/predict/full', params),
  listProperties: () => client.get('/v1/mpa/properties'),
}

// 2. 化学性质查询 — /v1/chemical
export const chemical = {
  query: (params) => client.post('/v1/chemical/query', params),
  queryFull: (params) => client.post('/v1/chemical/query/full', params),
  listModules: () => client.get('/v1/chemical/modules'),
}

// 3. 材料结构生成与优化 — /v1/structure
export const structure = {
  generate: (params) => client.post('/v1/structure/generate', params),
  optimize: (params) => client.post('/v1/structure/optimize', params),
  convert: (params) => client.post('/v1/structure/convert', params),
  listFormats: () => client.get('/v1/structure/formats'),
}

// 4. 配方与堆积优化 — /v1/formulation
export const formulation = {
  optimize: (params) => client.post('/v1/formulation/optimize', params),
  pack: (params) => client.post('/v1/formulation/pack', params),
  candidateComponents: (candidateId) => client.get('/v1/formulation/candidate-components', { params: { candidate_id: candidateId } }),
  listCapabilities: () => client.get('/v1/formulation/capabilities'),
}

// 5. 分子动力学模拟 — /v1/molecular-simulation
export const molecularSimulation = {
  run: (params) => client.post('/v1/molecular-simulation/run', params),
  runFull: (params) => client.post('/v1/molecular-simulation/run/full', params),
  listMetrics: () => client.get('/v1/molecular-simulation/metrics'),
}

// 6. 电池建模与仿真 — /v1/battery-modeling
export const batteryModeling = {
  simulate: (params) => client.post('/v1/battery-modeling/simulate', params),
  simulateFull: (params) => client.post('/v1/battery-modeling/simulate/full', params),
  listTracks: () => client.get('/v1/battery-modeling/tracks'),
}

// 7. 合成路线规划 — /v1/synthesis-planning
export const synthesisPlanning = {
  plan: (params) => client.post('/v1/synthesis-planning/plan', params),
  planFull: (params) => client.post('/v1/synthesis-planning/plan/full', params),
}

// 8. 化工过程建模 — /v1/process-modeling
export const processModeling = {
  calculate: (params) => client.post('/v1/process-modeling/calculate', params),
  calculateFull: (params) => client.post('/v1/process-modeling/calculate/full', params),
  listModules: () => client.get('/v1/process-modeling/modules'),
}

// 9. 反应网络分析 — /v1/reaction-network
export const reactionNetwork = {
  enumerate: (params) => client.post('/v1/reaction-network/enumerate', params),
  tsSearch: (params) => client.post('/v1/reaction-network/ts-search', params),
  grow: (params) => client.post('/v1/reaction-network/grow', params),
}

// 10. 波函数分析 — /v1/wavefunction-analysis
export const wavefunctionAnalysis = {
  analyzeEsp: (params) => client.post('/v1/wavefunction-analysis/esp', params),
  analyzeEspFull: (params) => client.post('/v1/wavefunction-analysis/esp/full', params),
  analyzeOrbitals: (params) => client.post('/v1/wavefunction-analysis/orbitals', params),
  analyzeOrbitalsFull: (params) => client.post('/v1/wavefunction-analysis/orbitals/full', params),
  render: (params) => client.post('/v1/wavefunction-analysis/render', params),
  renderFull: (params) => client.post('/v1/wavefunction-analysis/render/full', params),
  listFormats: () => client.get('/v1/wavefunction-analysis/formats'),
  listSurfaceTypes: () => client.get('/v1/wavefunction-analysis/surface-types'),
}

// 11. 流体动力学模拟 — /v1/fluid-simulation
export const fluidSimulation = {
  run: (params) => client.post('/v1/fluid-simulation/run', params),
  runFull: (params) => client.post('/v1/fluid-simulation/run/full', params),
  resume: (params) => client.post('/v1/fluid-simulation/resume', params),
  analyze: (params) => client.post('/v1/fluid-simulation/analyze', params),
  sweep: (params) => client.post('/v1/fluid-simulation/sweep', params),
  listSolvers: () => client.get('/v1/fluid-simulation/solvers'),
}

// 12. 分子对接 — /v1/molecular-docking
export const molecularDocking = {
  dock: (params) => client.post('/v1/molecular-docking/dock', params),
  dockFull: (params) => client.post('/v1/molecular-docking/dock/full', params),
  batch: (params) => client.post('/v1/molecular-docking/batch', params),
  batchFull: (params) => client.post('/v1/molecular-docking/batch/full', params),
  analyze: (params) => client.post('/v1/molecular-docking/analyze', params),
  analyzeFull: (params) => client.post('/v1/molecular-docking/analyze/full', params),
  export: (params) => client.post('/v1/molecular-docking/export', params),
  exportFull: (params) => client.post('/v1/molecular-docking/export/full', params),
  listFormats: () => client.get('/v1/molecular-docking/formats'),
}

// 服务 ID → API 命名空间映射表，供工作台动态派发
export const SERVICE_API_MAP = {
  mpa,
  chemical,
  structure,
  formulation,
  molecular_simulation: molecularSimulation,
  battery_modeling: batteryModeling,
  synthesis_planning: synthesisPlanning,
  process_modeling: processModeling,
  reaction_network: reactionNetwork,
  wavefunction_analysis: wavefunctionAnalysis,
  fluid_simulation: fluidSimulation,
  molecular_docking: molecularDocking,
}

// 服务 ID → 智能体映射表（通过 AgentProxy 调用）
// capability 与后端 agent_team/activity_mapping.py 中的 AgentToolBinding 一致
export const SERVICE_AGENT_MAP = {
  mpa: { agent_id: 'builtin_battery_oracle', capability: 'sci_mpa' },
  chemical: { agent_id: 'builtin_battery_oracle', capability: 'sci_chem_properties' },
  structure: { agent_id: 'builtin_material_discovery', capability: 'sci_materials_structure' },
  formulation: { agent_id: 'builtin_industrialization', capability: 'sci_formulation_packing' },
  molecular_simulation: { agent_id: 'builtin_battery_oracle', capability: 'sci_molecular_simulation' },
  battery_modeling: { agent_id: 'builtin_battery_oracle', capability: 'sci_battery_modeling' },
  synthesis_planning: { agent_id: 'builtin_synthesis_planner', capability: 'sci_synthesis_planning' },
  process_modeling: { agent_id: 'builtin_industrialization', capability: 'sci_process_modeling' },
  reaction_network: { agent_id: 'builtin_synthesis_planner', capability: 'sci_reaction_network' },
  wavefunction_analysis: { agent_id: 'builtin_dft_verifier', capability: 'sci_wavefunction_analysis' },
  fluid_simulation: { agent_id: 'builtin_industrialization', capability: 'sci_fluid_simulation' },
  molecular_docking: { agent_id: 'builtin_material_discovery', capability: 'sci_molecular_docking' },
}

// 通过匹配的智能体调用工具（AgentProxy → MCPToolRegistry → 科学服务）
export function invokeAgentTool (data) {
  return client.post('/v1/agent-tools/invoke', data, { timeout: 180000 })
}

// 查询智能体可调用的工具列表
export function listAgentTools (agentId) {
  return client.get(`/v1/agent-tools/agents/${encodeURIComponent(agentId)}/tools`)
}

// ── 混编工作流执行 ──────────────────────────────────────────

export function executeWorkflow (params) {
  return client.post('/v1/workflow/execute', params)
}

export function listWorkflowServices () {
  return client.get('/v1/workflow/services')
}
