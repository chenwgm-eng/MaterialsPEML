import client from './client'

export const listCandidates = (candidateType = '') =>
  client.get('/candidates', { params: candidateType ? { candidate_type: candidateType } : {} })

export const getCandidate = (candidateId) =>
  client.get(`/candidates/${candidateId}`)

// ── 两层流程（Phase B：工艺深化阶段） ─────────────────────────
// 独立"合成路径"页定位为工艺人员专业工作台，对接以下接口。

/** 工艺人员工作台：列出进入工艺深化流水线的候选配方及其工艺方案 */
export const getProcessEngineerWorkbench = (status = '') =>
  client.get('/process-engineer/workbench', { params: status ? { status } : {} })

/** 对候选配方执行工艺深化（SCP 优先 + 本地回退），产出/更新工艺方案 */
export const runProcessDeepening = (candidateId, data) =>
  client.post(`/candidates/${candidateId}/process-deepening`, data)

/** 更新候选材料状态（Phase A 两层状态机：feasible → process_planning → ... → ready_for_experiment） */
export const updateCandidateStatus = (candidateId, data) =>
  client.patch(`/candidates/${candidateId}/status`, data)

/** 更新工艺方案状态（draft → reviewing → confirmed / abandoned） */
export const updateProcessSchemeStatus = (processId, data) =>
  client.patch(`/process-schemes/${processId}/status`, data)

/** 从已确认的工艺方案生成配方（BOM），打通 深化→配方 链路 */
export const createBomFromProcess = (candidateId, data) =>
  client.post(`/candidates/${candidateId}/bom-from-process`, data)
