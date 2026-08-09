import axios from 'axios'
import { notification, Button } from 'ant-design-vue'
import { h } from 'vue'
import { translateError, isIdempotentRequest } from '@/utils/errorHandler'

// 认证凭证：登录后后端签发带 HMAC 签名与过期时间的 token，
// 本地保存 token（鉴权用）与 userId（路由守卫/展示用）。
export const setUserId = (id, token) => {
  if (!id) {
    localStorage.removeItem('userId')
    localStorage.removeItem('authToken')
    return
  }
  localStorage.setItem('userId', id)
  if (token) {
    localStorage.setItem('authToken', token)
  }
}

export const getUserId = () => {
  // 无 token 视为未登录（token 才是有效凭证）
  if (!localStorage.getItem('authToken')) return null
  return localStorage.getItem('userId')
}

const getAuthToken = () => localStorage.getItem('authToken')

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * 请求拦截器：登录后自动在请求头携带 X-Auth-Token（服务端 HMAC 签名），
 * 供后端权限中间件识别当前用户。未登录时不携带，后端按匿名处理（只读访问仍可用）。
 */
client.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers['X-Auth-Token'] = token
  }
  return config
})

/**
 * 全局错误提示：技术性报错统一转译为中文自然语言，附工单编号；
 * 幂等 GET 请求提供"重试"按钮，点击后重发请求并兑现原始 Promise。
 */
function showTranslatedError(error, reject, resolve) {
  const info = translateError(error)
  const config = error.config || {}
  const canRetry = info.retryable && isIdempotentRequest(config) && !config.__retried
  const key = `api-error-${info.errorId}`
  // 防重复结算：destroy 可能连带触发 onClose，确保 Promise 只结算一次
  let settled = false
  const safeReject = (err) => {
    if (settled) return
    settled = true
    reject(err)
  }
  const safeResolve = (val) => {
    if (settled) return
    settled = true
    resolve(val)
  }

  notification.error({
    key,
    message: info.title,
    description: `${info.message}（工单编号：${info.errorId}）`,
    duration: 6,
    btn: canRetry
      ? () =>
          h(
            Button,
            {
              type: 'primary',
              size: 'small',
              onClick: () => {
                notification.destroy(key)
                const retryConfig = { ...config, __retried: true }
                client(retryConfig).then(safeResolve).catch(safeReject)
              },
            },
            () => '重试',
          )
      : undefined,
    onClose: () => safeReject(error),
  })

  // 不可重试时直接拒绝，避免调用方 Promise 悬挂；通知保持展示
  if (!canRetry) {
    safeReject(error)
  }
}

client.interceptors.response.use(
  // M17: 此处仅返回 resp.data，丢弃了响应 headers。当前业务未使用响应头（如分页 link、ETag 等），
  // 若后续需要可改为返回 resp 或在 data 上挂载 _headers 字段。
  (resp) => resp.data,
  (error) => {
    // 401 会话失效：清除本地凭证，不在首页则整页跳转首页（清空内存态）。
    // 普通未登录（无 token）的 401 静默 reject，不弹错误通知。
    if (error.response?.status === 401) {
      const hadToken = !!getAuthToken()
      localStorage.removeItem('authToken')
      localStorage.removeItem('userId')
      localStorage.removeItem('userRole')
      localStorage.removeItem('permissions')
      if (hadToken && window.location.pathname !== (import.meta.env.BASE_URL || '/')) {
        window.location.href = import.meta.env.BASE_URL || '/'
      }
      return Promise.reject(error)
    }

    // 忽略请求被取消的情况（页面切换/组件卸载导致），避免弹无关错误
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED' || error.message === 'canceled' || error.message === 'Request aborted') {
      return Promise.reject(error)
    }

    // 忽略浏览器级请求中断（SPA 路由切换、组件卸载前请求未完成等）
    // 特征：无响应对象、XHR readyState=4 但 status=0（请求未收到任何响应即被中断）
    // 这与真实网络错误（服务器不可达）难以区分，但用户偏好简洁界面，不弹通知；
    // 若为真实网络故障，其他请求也会失败，用户可通过页面整体状态感知。
    if (!error.response && error.request &&
        (error.request.status === 0 || error.request.readyState === 0) &&
        !error.config?.__retried) {
      return Promise.reject(error)
    }

    // 请求显式声明跳过错误通知（如可选数据 404），直接 reject 不弹通知
    if (error.config?.skipErrorNotification) {
      return Promise.reject(error)
    }

    // 统一走转译层：网络错误 / 超时 / HTTP 状态码均转换为用户可读提示
    return new Promise((resolve, reject) => {
      showTranslatedError(error, reject, resolve)
    })
  },
)

export default client
