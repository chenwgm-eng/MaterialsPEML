import client from './client'

// P3-1：统一研发事件流水（首页看板/迭代历史/控制平面共享数据源）
export const listResearchEvents = (params) => client.get('/research-events', { params })
export const getResearchEventStats = () => client.get('/research-events/stats')
