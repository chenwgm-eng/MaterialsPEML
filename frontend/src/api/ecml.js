import client from './client'

export const runECML = (data) => client.post('/discover', data, { timeout: 120000 })
export const runECMLStep = (data) => client.post('/ecml/run_step', data, { timeout: 120000 })
export const getECMLRun = (run_id) => client.get(`/ecml/runs/${encodeURIComponent(run_id)}`, { skipErrorNotification: true })
export const getEcmlRuns = (limit = 20) => client.get('/ecml/runs', { params: { limit } })
export const deleteECMLRun = (run_id) => client.delete(`/ecml/runs/${encodeURIComponent(run_id)}`)
export const bulkDeleteECMLRuns = (run_ids) => client.post('/ecml/runs/bulk-delete', { run_ids })
export const getECMLNextRound = (run_id) => client.get(`/ecml/runs/${encodeURIComponent(run_id)}/next-round`, { timeout: 60000 })

// ---- 贝叶斯优化 Round 决策引擎 ----
// 训练池统计预览（材料体系+目标属性维度）
export const getECMLPoolStats = (run_id, { material_family = '', target_property = '' } = {}) =>
  client.get(`/ecml/runs/${encodeURIComponent(run_id)}/pool-stats`, { params: { material_family, target_property } })

// 启动一轮 BO 推荐（产出推荐后停在复核门，不自动下发）
export const startECMLRound = (run_id, payload) =>
  client.post(`/ecml/runs/${encodeURIComponent(run_id)}/rounds`, payload, { timeout: 60000 })

// 列出 run 下所有 Round 记录
export const listECMLRounds = (run_id) =>
  client.get(`/ecml/runs/${encodeURIComponent(run_id)}/rounds`)

// 获取单个 Round 完整记录
export const getECMLRound = (round_id) =>
  client.get(`/ecml/rounds/${encodeURIComponent(round_id)}`)

// 课题负责人复核确认下发（为采纳候选创建实验任务）
export const confirmECMLRound = (round_id, adopted) =>
  client.post(`/ecml/rounds/${encodeURIComponent(round_id)}/confirm`, { adopted })

/**
 * 注入真实实验数据，唤醒 WAITING_FOR_DATA 状态的 ECML run 继续 Step7 反馈。
 * 半自动闭环：用户在实验单详情页录入数据后，前端拿到 pending_resume 标记，
 * 通过此接口提交数据触发反馈分析。
 *
 * 推荐用 from_order_id：后端自动从 result_records 表读取该单所有数据。
 */
export const resumeECMLFromData = (run_id, { from_order_id = '', experiment_results = null, target = '', target_property = '' } = {}) => {
  const payload = { target, target_property }
  if (from_order_id) {
    payload.from_order_id = from_order_id
  } else if (experiment_results) {
    payload.experiment_results = experiment_results
  }
  return client.post(`/ecml/runs/${encodeURIComponent(run_id)}/data`, payload, { timeout: 120000 })
}
