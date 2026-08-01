import client from './client'

// 合成路径规划 API：异步任务模式（提交即返回 task_id，轮询获取结果），
// 避免逆合成服务耗时长导致前端 15s 超时（产品评审 P0）。

/** 提交异步合成规划任务 */
export const planSynthesisAsync = (data) => client.post('/synthesis/plan/async', data)

/** 轮询任务状态与结果 */
export const getSynthesisTask = (taskId) => client.get(`/synthesis/tasks/${taskId}`)

/** 最近的规划任务列表（含失败尝试） */
export const getSynthesisTasks = (limit = 50) =>
  client.get('/synthesis/tasks', { params: { limit } })

/** 合成规划统计（路线产出数、服务成功率、可用性） */
export const getSynthesisStats = () => client.get('/synthesis/stats')

/** 手动填写合成路径（服务不可用时的业务兜底） */
export const createManualRoute = (data) => client.post('/synthesis/manual', data)
