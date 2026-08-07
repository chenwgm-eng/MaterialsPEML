import client from './client'

// AI 助手后端薄封装 API。
// 注意：CRUD 走统一 axios client（已带回 auth 头与错误转译）；
// 对话发送走原生 fetch 以支持 NDJSON 流式（SSE 风格，逐行读取）。

/** 创建会话 */
export const createAiSession = (data) => client.post('/ai/sessions', data)

/** 列出会话 */
export const listAiSessions = (params = {}) => client.get('/ai/sessions', { params })

/** 删除会话 */
export const deleteAiSession = (sessionId) => client.delete(`/ai/sessions/${sessionId}`)

/** 列出会话消息 */
export const listAiMessages = (sessionId, params = {}) =>
  client.get(`/ai/sessions/${sessionId}/messages`, { params })

/** 提交消息反馈（1 有帮助 / -1 没帮助 / 0 取消） */
export const submitAiFeedback = (messageId, value) =>
  client.post(`/ai/messages/${messageId}/feedback`, { value })

/**
 * 发送消息并消费 NDJSON 流。
 * @param {string} sessionId 会话 ID
 * @param {string} message 用户消息
 * @param {object} context 本次消息附带页面上下文/@提及
 * @param {(ev: object) => void} onEvent 事件回调（start/delta/done/error）
 */
export async function streamAiMessage(sessionId, message, context, onEvent) {
  const token = localStorage.getItem('authToken')
  const resp = await fetch(`/api/ai/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-Auth-Token': token } : {}),
    },
    body: JSON.stringify({ message, context }),
  })
  if (!resp.ok) {
    let detail = ''
    try {
      const j = await resp.json()
      detail = j.detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(detail || `请求失败（${resp.status}）`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // 使用取消信号：若组件卸载需调用 abort() 中断读取
  const abort = () => reader.cancel().catch(() => {})
  while (true) {
    // eslint-disable-next-line no-await-in-loop
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let nl
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (!line) continue
      try {
        onEvent(JSON.parse(line))
      } catch {
        /* 忽略非 JSON 行 */
      }
    }
  }
  return abort
}