/**
 * 最小埋点 helper（Step E）。
 *
 * 受 VITE_FF_TELEMETRY 开关控制：关闭时为空操作（零开销）；开启时把关键导航事件
 * 结构化写入 console（便于后续接入真实上报端点，当前不引入任何外部依赖）。
 *
 * 使用方式：`track('entry_select', { entry: 'project' })`。
 * 保证：不抛异常、不阻塞调用方、不篡改业务数据 — 纯观测副作用。
 */

const ENABLED = import.meta.env.VITE_FF_TELEMETRY === 'true'

/**
 * 记录一条导航事件。
 * @param {string} event 事件名，如 'page_view' / 'entry_select' / 'create_click' / 'discipline_switch'
 * @param {object} [payload] 结构化载荷（保持小型、可序列化）
 */
export function track(event, payload = {}) {
  if (!ENABLED) return
  try {
    const entry = {
      event,
      ts: new Date().toISOString(),
      ...payload,
    }
    // 前端无后端聚合端点，本期仅落 console；后续可替换为 Beacon 发送。
    // eslint-disable-next-line no-console
    console.debug('[telemetry]', entry)
  } catch {
    /* 埋点失败绝不影响主流程 */
  }
}