/**
 * 全局错误转译层：将技术性报错（HTTP 状态码、axios 超时、英文原始错误）
 * 转换为材料研发人员可理解的自然语言提示，并生成工单编号便于技术支持排查。
 *
 * 设计原则（对应产品评审 P0）：
 * - 终端用户永远不应看到 "Method Not Allowed" / "timeout of 15000ms exceeded"
 *   / "Network Error" 这类技术性英文报错；
 * - 每条错误提示附带工单编号（errorId），用户反馈时可直接提供给技术支持；
 * - 可重试的错误（网络波动、超时、5xx）明确告知用户可以重试。
 */

let errorSeq = 0

/** 生成工单编号：ERR-<时间基36>-<序号>，如 ERR-LX3K2A-07 */
export function generateErrorId() {
  errorSeq = (errorSeq + 1) % 1296 // 36^2，两位基36循环
  const ts = Date.now().toString(36).toUpperCase()
  const seq = errorSeq.toString(36).toUpperCase().padStart(2, '0')
  return `ERR-${ts}-${seq}`
}

/** 技术性英文错误片段 → 中文说明（命中即替换） */
const TECHNICAL_PATTERNS = [
  { pattern: /method not allowed/i, text: '该操作当前不被支持' },
  { pattern: /timeout of \d+ms exceeded/i, text: '服务响应超时' },
  { pattern: /network error/i, text: '网络连接异常' },
  { pattern: /request failed with status code (\d+)/i, text: '请求失败' },
  { pattern: /internal server error/i, text: '服务器内部错误' },
  { pattern: /service unavailable/i, text: '服务暂不可用' },
  { pattern: /bad gateway/i, text: '网关异常' },
  { pattern: /not found/i, text: '请求的资源不存在' },
  { pattern: /econnrefused|econnreset|econnaborted/i, text: '连接被中断' },
  { pattern: /<html[\s\S]*<\/html>/i, text: '服务返回了异常页面' },
  { pattern: /the JSON object must be str, bytes or bytearray, not dict/i, text: '数据格式解析异常' },
  { pattern: /json\.loads|json decoder/i, text: '数据序列化异常' },
]

/** 检测并清洗错误文本中的技术性英文片段 */
export function sanitizeMessage(raw) {
  if (!raw || typeof raw !== 'string') return ''
  let text = raw.trim()
  // HTML 响应体（如 nginx 错误页）整体替换
  if (/<\s*html|<\s*!doctype/i.test(text)) {
    return '服务返回了异常页面，通常是服务未就绪或反向代理配置问题'
  }
  for (const { pattern, text: cn } of TECHNICAL_PATTERNS) {
    if (pattern.test(text)) {
      // 保留状态码信息
      const statusMatch = text.match(/status code (\d+)/i)
      text = text.replace(pattern, statusMatch ? `${cn}（${statusMatch[1]}）` : cn)
    }
  }
  return text
}

/**
 * 将 axios 错误对象转译为结构化用户提示。
 * 返回 { title, message, errorId, retryable, status }
 */
export function translateError(error, context = '') {
  const errorId = generateErrorId()
  const resp = error?.response
  const status = resp?.status || 0

  // 1. 网络层错误（无响应）
  if (!resp) {
    if (error?.code === 'ECONNABORTED' || /timeout/i.test(error?.message || '')) {
      return {
        title: '请求超时',
        message: '本次计算耗时较长未能在时限内完成。服务可能仍在处理中，请稍后重试；若多次出现，请联系管理员检查算力资源。',
        errorId, retryable: true, status: 0,
      }
    }
    return {
      title: '网络连接失败',
      message: '无法连接到后端服务，请确认服务已启动且网络正常，然后重试。',
      errorId, retryable: true, status: 0,
    }
  }

  // 2. 提取后端 detail（FastAPI HTTPException: string | object | 校验错误数组）
  const detail = resp.data?.detail
  let rawMsg = ''
  let hint = ''
  let service = ''
  if (typeof detail === 'string') {
    rawMsg = detail
  } else if (detail && typeof detail === 'object') {
    if (Array.isArray(detail)) {
      // FastAPI 422 校验错误：detail 为数组 [{ loc, msg, type, input }]，逐条转中文
      const parts = detail
        .map((item) => {
          if (!item || typeof item !== 'object') return ''
          const loc = Array.isArray(item.loc) ? item.loc.filter((x) => typeof x === 'string').join('.') : ''
          let msg = item.msg || ''
          if (/field required|missing/i.test(msg)) msg = '必填项缺失'
          else if (/not a valid|input should be/i.test(msg)) msg = '格式不正确'
          return loc ? `字段 ${loc}：${msg}` : msg
        })
        .filter(Boolean)
      if (parts.length) rawMsg = parts.join('；')
    } else {
      rawMsg = detail.message || ''
      hint = detail.hint || ''
      service = detail.service || ''
    }
  }
  if (!rawMsg && typeof resp.data === 'string') rawMsg = resp.data
  rawMsg = sanitizeMessage(rawMsg)

  // 3. 按状态码生成标题与默认文案
  const prefix = context ? `${context}：` : ''
  const serviceTag = service ? `[${service}] ` : ''
  switch (status) {
    case 400:
      return { title: '请求参数有误', message: `${prefix}${rawMsg || '提交的信息未通过校验，请检查输入内容'}`, errorId, retryable: false, status }
    case 401:
      return { title: '登录状态已失效', message: '请重新登录后再试。', errorId, retryable: false, status }
    case 403:
      // 能力契约门禁：detail.error === 'capability_blocked'
      if (detail && detail.error === 'capability_blocked') {
        return {
          title: '能力已被禁用',
          message: `${prefix}${rawMsg || '该能力契约已被废止且无可用兜底，相关功能暂时不可用。请联系管理员在「能力契约」页面重新启用或配置 fallback。'}`,
          errorId, retryable: false, status,
        }
      }
      return { title: '没有操作权限', message: `${prefix}${rawMsg || '当前账号无权执行此操作，如需权限请联系管理员。'}`, errorId, retryable: false, status }
    case 404:
      return { title: '功能暂未开放', message: `${prefix}${rawMsg || '请求的功能或数据不存在。'} 如该功能应可用，请联系管理员并提供工单编号。`, errorId, retryable: false, status }
    case 405:
      return { title: '操作暂不支持', message: `${prefix}当前操作未被系统支持。如该功能应可用，请联系管理员并提供工单编号。`, errorId, retryable: false, status }
    case 409:
      return { title: '操作冲突', message: `${prefix}${rawMsg || '与现有数据冲突，请刷新后重试。'}`, errorId, retryable: true, status }
    case 422:
      return { title: '数据校验未通过', message: `${prefix}${rawMsg || '提交的数据格式不正确，请检查后重试。'}`, errorId, retryable: false, status }
    case 429:
      return { title: '请求过于频繁', message: '请稍等片刻后再试。', errorId, retryable: true, status }
    case 500:
      return { title: '服务内部错误', message: `${prefix}${rawMsg || '服务处理时发生异常'}。如持续出现，请联系管理员并提供工单编号。`, errorId, retryable: true, status }
    case 502:
      return { title: '外部服务调用失败', message: `${prefix}${rawMsg || '依赖的外部服务响应异常'}，请稍后重试。`, errorId, retryable: true, status }
    case 503:
      return {
        title: `${serviceTag}服务暂不可用`.trim(),
        message: `${prefix}${rawMsg || '服务当前不可用'}${hint ? `。建议：${hint}` : '，请稍后重试'}`,
        errorId, retryable: true, status,
      }
    default:
      return {
        title: '操作未完成',
        message: `${prefix}${rawMsg || `请求失败（${status}）`}。如持续出现，请联系管理员并提供工单编号。`,
        errorId, retryable: status >= 500, status,
      }
  }
}

/** 判断请求配置是否为幂等 GET（可安全自动/手动重试） */
export function isIdempotentRequest(config) {
  return (config?.method || 'get').toLowerCase() === 'get'
}

/**
 * 安全解析JSON：如果数据已经是对象则直接返回，避免重复解析导致的TypeError
 * @param {*} data - 待解析的数据（字符串或对象）
 * @param {*} fallback - 解析失败时的返回值
 * @returns {*} 解析后的对象或fallback
 */
export function safeParseJson(data, fallback = null) {
  if (data == null) return fallback
  if (typeof data === 'object') return data
  if (typeof data === 'string') {
    try {
      return JSON.parse(data)
    } catch {
      return fallback
    }
  }
  return fallback
}
