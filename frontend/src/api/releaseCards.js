import client from './client'

/** 创建放行卡（传 case_id 则从委员会 case 生成，否则按手工字段创建） */
export function createReleaseCard(data) {
  return client.post('/release-cards', data)
}

/** 获取放行卡列表（status / recommendation / project_id / case_id 过滤） */
export function getReleaseCards(params = {}) {
  return client.get('/release-cards', { params })
}

/** 获取单个放行卡详情 */
export function getReleaseCard(cardId) {
  return client.get(`/release-cards/${cardId}`)
}

/** 人工复核（reviewer / review_opinion / final_decision） */
export function reviewReleaseCard(cardId, data) {
  return client.post(`/release-cards/${cardId}/review`, data)
}

/** 获取放行卡治理指标汇总 */
export function getReleaseCardMetrics() {
  return client.get('/release-cards/metrics/summary')
}
