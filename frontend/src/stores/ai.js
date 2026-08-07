import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  createAiSession,
  listAiSessions,
  deleteAiSession,
  listAiMessages,
  streamAiMessage,
  submitAiFeedback,
} from '@/api/ai'
import { message } from 'ant-design-vue'

/**
 * 全局 AI 助手（Copilot）会话状态。
 * 负责：抽屉开关、会话列表、当前会话与消息、发送（NDJSON 流式）、页面上下文感知。
 */
export const useAiStore = defineStore('ai', () => {
  const drawerOpen = ref(false)
  const sessions = ref([])
  const currentSessionId = ref('')
  const messages = ref([])
  const busy = ref(false)
  const loadingSessions = ref(false)
  // 当前页面上下文（MainLayout 在路由变化时更新）
  const currentContext = ref({ page: {}, project: null, mentions: [] })
  // 系统建议 chips（主题化，随上下文展示）
  const suggestions = ref([
    { key: 'summarize', label: '总结当前页面' },
    { key: 'explain', label: '解释当前数据' },
    { key: 'next', label: '下一步建议' },
  ])

  const currentSession = computed(() =>
    sessions.value.find((s) => s.session_id === currentSessionId.value) || null
  )

  function openDrawer() {
    drawerOpen.value = true
    if (!sessions.value.length && !loadingSessions.value) loadSessions()
  }
  function closeDrawer() {
    drawerOpen.value = false
  }

  function setPageContext(page, project, mentions = []) {
    currentContext.value = { page, project, mentions }
  }

  async function loadSessions() {
    loadingSessions.value = true
    try {
      // 按当前项目隔离会话列表（与 newSession 写入的 project_id 保持一致）
      const project = currentContext.value.project
      const res = await listAiSessions({ limit: 50, project_id: project?.project_id || '' })
      sessions.value = res.sessions || []
      if (sessions.value.length && !currentSessionId.value) {
        currentSessionId.value = sessions.value[0].session_id
        await loadMessages()
      }
    } catch {
      sessions.value = []
    } finally {
      loadingSessions.value = false
    }
  }

  async function newSession() {
    const project = currentContext.value.project
    const data = await createAiSession({
      title: '新会话',
      project_id: project?.project_id || '',
      mode: 'global',
      context: currentContext.value,
    })
    sessions.value.unshift(data)
    currentSessionId.value = data.session_id
    messages.value = []
    return data
  }

  async function selectSession(sessionId) {
    if (busy.value) return
    currentSessionId.value = sessionId
    await loadMessages()
  }

  async function loadMessages() {
    if (!currentSessionId.value) {
      messages.value = []
      return
    }
    const res = await listAiMessages(currentSessionId.value, { limit: 200 })
    messages.value = res.messages || []
  }

  async function removeSession(sessionId) {
    if (busy.value) return
    await deleteAiSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = sessions.value[0]?.session_id || ''
      await loadMessages()
    }
  }

  /**
   * 提交消息反馈（真实持久化，非本地假信号）。
   * 仅对已落库的消息（非 local- 前缀）生效；乐观更新，失败回滚。
   */
  async function feedback(m, v) {
    if (!m || m.message_id.startsWith('local-')) return
    m.meta = m.meta || {}
    const prev = m.meta._fb || 0
    const next = prev === v ? 0 : v
    m.meta._fb = next
    try {
      await submitAiFeedback(m.message_id, next)
    } catch {
      m.meta._fb = prev
      message.warning('反馈保存失败')
    }
  }

  /**
   * 发送消息（流式）。
   * 本地先追加 user 消息与空的 assistant 消息，随后按 delta 增量填充。
   */
  async function send(text) {
    const content = (text || '').trim()
    if (!content || busy.value) return
    if (!currentSessionId.value) await newSession()

    const sessionId = currentSessionId.value
    busy.value = true
    const userMsg = { message_id: `local-${Date.now()}`, role: 'user', content }
    const asstMsg = { message_id: `local-asst-${Date.now()}`, role: 'assistant', content: '', meta: {}, status: 'streaming' }
    messages.value.push(userMsg, asstMsg)

    try {
      await streamAiMessage(sessionId, content, currentContext.value, (ev) => {
        if (ev.type === 'delta') {
          asstMsg.content += ev.content || ''
        } else if (ev.type === 'done') {
          asstMsg.message_id = ev.message_id
          asstMsg.content = ev.reply || asstMsg.content
          asstMsg.meta = ev.meta || {}
          asstMsg.status = 'done'
        } else if (ev.type === 'error') {
          asstMsg.status = 'error'
          asstMsg.content = ev.detail || '对话出错'
        }
      })
      // 刷新会话列表（updated_at / title 变化）
      loadSessions()
    } catch (e) {
      asstMsg.status = 'error'
      asstMsg.content = e.message || '发送失败'
      message.error(asstMsg.content)
    } finally {
      busy.value = false
    }
  }

  return {
    drawerOpen, sessions, currentSessionId, currentSession, messages, busy,
    loadingSessions, currentContext, suggestions,
    openDrawer, closeDrawer, setPageContext, loadSessions, newSession,
    selectSession, loadMessages, removeSession, feedback, send,
  }
})