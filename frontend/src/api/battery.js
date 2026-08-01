import client from './client'

// G4.3: 电池寿命预测工作流（Learner → Interpreter → Oracle）
export function runBatteryLifeWorkflow(data) {
  return client.post('/workflows/battery_life', data)
}

// 查询电池循环基准数据库（供基准对比下拉选择）
export function listBatteryCycleDatabase(params = {}) {
  return client.get('/battery/cycle-database', { params })
}
