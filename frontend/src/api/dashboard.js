import client from './client'

/** 总览：项目/任务/候选/ECML/用户计数与状态分布（可选时间范围筛选） */
export const getDashboardOverview = (params) =>
  client.get('/dashboard/overview', params ? { params } : undefined)

/** 成本分析：项目物料成本 + 计算资源成本 + 月度趋势（可选时间范围筛选） */
export const getDashboardCost = (params) =>
  client.get('/dashboard/cost', params ? { params } : undefined)

/** 资源使用：设备使用率/样品库存/物料预警/计算队列（可选时间范围筛选） */
export const getDashboardResources = (params) =>
  client.get('/dashboard/resources', params ? { params } : undefined)

/** 数据质量分布：按 data_quality 分组统计实验结果记录（可选 project_id 筛选） */
export const getDashboardDataQuality = (params) =>
  client.get('/dashboard/data-quality', params ? { params } : undefined)

/** 系统监控（T-056）：P0/P1 复发率 + 操作成功率 + AI 采纳率（可选 days 筛选，默认 30 天） */
export const getDashboardMonitoring = (params) =>
  client.get('/dashboard/monitoring', params ? { params } : undefined)
