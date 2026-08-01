import client from './client'

export const runECML = (data) => client.post('/discover', data, { timeout: 120000 })
export const runECMLStep = (data) => client.post('/ecml/run_step', data, { timeout: 120000 })
export const getECMLRun = (run_id) => client.get(`/ecml/runs/${encodeURIComponent(run_id)}`, { skipErrorNotification: true })
export const getEcmlRuns = (limit = 20) => client.get('/ecml/runs', { params: { limit } })
export const deleteECMLRun = (run_id) => client.delete(`/ecml/runs/${encodeURIComponent(run_id)}`)
export const bulkDeleteECMLRuns = (run_ids) => client.post('/ecml/runs/bulk-delete', { run_ids })
export const getECMLNextRound = (run_id) => client.get(`/ecml/runs/${encodeURIComponent(run_id)}/next-round`, { timeout: 60000 })

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
