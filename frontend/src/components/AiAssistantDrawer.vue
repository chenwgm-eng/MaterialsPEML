<template>
  <div class="ai-assistant">
    <!-- 右侧竖 rail：AI 入口 -->
    <button
      class="ai-rail"
      :class="{ 'is-open': drawerOpen }"
      title="AI 助手"
      @click="store.openDrawer()"
    >
      <RobotOutlined class="ai-rail-icon" />
      <span class="ai-rail-text">AI</span>
    </button>

    <!-- 遮罩 + 悬浮抽屉 -->
    <transition name="fade">
      <div v-if="drawerOpen" class="ai-mask" @click="store.closeDrawer()" />
    </transition>
    <transition name="slide">
      <aside v-if="drawerOpen" class="ai-drawer" aria-label="AI 助手">
        <!-- 头部：标题 + 会话操作 -->
        <div class="ai-header">
          <div class="ai-header-left">
            <RobotOutlined class="ai-logo" />
            <div class="ai-title-box">
              <div class="ai-title">AI 助手</div>
              <div class="ai-subtitle">研发 Copilot · 对话助手</div>
            </div>
          </div>
          <div class="ai-header-actions">
            <a-tooltip title="新建会话">
              <a-button size="small" type="text" @click="onNew">
                <PlusOutlined />
              </a-button>
            </a-tooltip>
            <a-tooltip title="关闭">
              <a-button size="small" type="text" @click="store.closeDrawer()">
                <CloseOutlined />
              </a-button>
            </a-tooltip>
          </div>
        </div>

        <!-- 会话列表 -->
        <div class="ai-session-bar">
          <a-select
            v-model:value="store.currentSessionId"
            class="ai-session-select"
            size="small"
            placeholder="选择会话"
            :loading="store.loadingSessions"
            @change="store.loadMessages()"
          >
            <template v-for="s in store.sessions" :key="s.session_id">
              <a-select-option :value="s.session_id">
                <div class="session-option">
                  <span class="session-option-title">{{ s.title || '新会话' }}</span>
                  <a
                    class="session-option-del"
                    title="删除会话"
                    @click.stop="onDelete(s.session_id)"
                  ><DeleteOutlined /></a>
                </div>
              </a-select-option>
            </template>
          </a-select>
          <span v-if="store.sessions.length" class="session-count">{{ store.sessions.length }}</span>
        </div>

        <!-- 消息流 -->
        <div ref="scrollRef" class="ai-messages">
          <div v-if="!store.messages.length" class="ai-empty">
            <RobotOutlined class="ai-empty-icon" />
            <div class="ai-empty-title">有什么可以帮你？</div>
            <div class="ai-empty-desc">我会基于当前页面上下文作答，并标注来源与耗时。</div>
          </div>
          <template v-for="m in store.messages" :key="m.message_id">
            <!-- 用户消息 -->
            <div v-if="m.role === 'user'" class="msg msg-user">
              <div class="msg-user-bubble">{{ m.content }}</div>
            </div>
            <!-- 助手消息 -->
            <div v-else-if="m.role === 'assistant'" class="msg msg-ai">
              <div class="msg-ai-head">
                <RobotOutlined class="msg-ai-avatar" />
                <span class="msg-ai-name">Copilot</span>
                <span v-if="m.status === 'streaming'" class="msg-ai-streaming">思考中…</span>
                <span v-else-if="m.status === 'error'" class="msg-ai-error">出错了</span>
              </div>
              <div class="msg-ai-bubble" :class="{ 'is-error': m.status === 'error' }">
                <span v-if="m.content" class="msg-ai-text">{{ m.content }}</span>
                <span v-else-if="m.status === 'streaming'" class="msg-ai-cursor" />
              </div>
              <!-- 信任元数据：来源/置信度/耗时 -->
              <div v-if="m.meta && m.meta.provider" class="msg-ai-meta">
                <span class="meta-chip">{{ m.meta.provider }}</span>
                <span v-if="m.meta.model" class="meta-chip">{{ m.meta.model }}</span>
                <span v-if="m.meta.duration_ms" class="meta-chip">
                  {{ (m.meta.duration_ms / 1000).toFixed(1) }}s
                </span>
                <span v-if="m.meta.fallback_used" class="meta-chip warn">已回退备选</span>
              </div>
              <!-- 反馈操作 -->
              <div v-if="m.status === 'done'" class="msg-ai-ops">
                <a-tooltip title="复制">
                  <button class="op-btn" @click="copy(m.content)"><CopyOutlined /></button>
                </a-tooltip>
                <a-tooltip title="有帮助">
                  <button class="op-btn" :class="{ on: m.meta._fb === 1 }" @click="feedback(m, 1)">
                    <LikeOutlined />
                  </button>
                </a-tooltip>
                <a-tooltip title="没帮助">
                  <button class="op-btn" :class="{ on: m.meta._fb === -1 }" @click="feedback(m, -1)">
                    <DislikeOutlined />
                  </button>
                </a-tooltip>
              </div>
            </div>
          </template>
        </div>

        <!-- 建议 chips + 输入区 -->
        <div class="ai-footer">
          <div v-if="store.suggestions.length" class="ai-chips">
            <button
              v-for="c in store.suggestions"
              :key="c.key"
              class="chip"
              :disabled="store.busy"
              @click="sendSuggestion(c)"
            >
              {{ c.label }}
            </button>
          </div>
          <div class="ai-composer">
            <a-textarea
              v-model:value="draft"
              class="ai-input"
              :rows="1"
              :auto-size="{ minRows: 1, maxRows: 4 }"
              placeholder="输入问题，或 @ 提及资源…"
              :disabled="store.busy"
              @press-enter.prevent="onSend"
            />
            <button class="ai-send" :class="{ on: draft.trim() }" :disabled="store.busy || !draft.trim()" @click="onSend">
              <SendOutlined />
            </button>
          </div>
        </div>
      </aside>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useAiStore } from '@/stores/ai'
import {
  RobotOutlined, PlusOutlined, CloseOutlined, DeleteOutlined,
  CopyOutlined, LikeOutlined, DislikeOutlined, SendOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

const store = useAiStore()
const draft = ref('')
const scrollRef = ref(null)

const drawerOpen = computed(() => store.drawerOpen)

async function scrollToBottom() {
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

watch(
  () => store.messages.length,
  () => scrollToBottom(),
)

watch(drawerOpen, (open) => {
  if (open) scrollToBottom()
})

function onNew() {
  store.newSession()
}

function onDelete(sessionId) {
  store.removeSession(sessionId)
}

function sendSuggestion(c) {
  if (store.busy) return
  const ctx = store.currentContext
  let q = c.label
  if (c.key === 'summarize') {
    q = `请基于当前页面（${ctx.page?.title || '当前页'}）内容做简要总结。`
  } else if (c.key === 'next') {
    q = '基于当前上下文，给我下一步建议。'
  }
  draft.value = q
  onSend()
}

function feedback(m, v) {
  store.feedback(m, v)
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    message.success('已复制')
  } catch {
    message.warning('复制失败，请手动选择复制')
  }
}

function onSend() {
  const text = draft.value.trim()
  if (!text || store.busy) return
  draft.value = ''
  store.send(text)
}
</script>

<style scoped>
.ai-assistant {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1000;
}

/* —— 右侧竖 rail —— */
.ai-rail {
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 44px;
  padding: 12px 0;
  border: none;
  border-radius: 10px 0 0 10px;
  background: linear-gradient(180deg, var(--primary), var(--primary-light));
  color: #fff;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(var(--primary-rgb, 232, 116, 34), 0.35);
  transition: width 0.2s ease, opacity 0.2s ease;
}
.ai-rail:hover {
  width: 52px;
}
.ai-rail.is-open {
  opacity: 0.55;
}
.ai-rail-icon {
  font-size: 18px;
}
.ai-rail-text {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

/* —— 遮罩 —— */
.ai-mask {
  position: fixed;
  inset: 0;
  pointer-events: auto;
  background: rgba(11, 18, 32, 0.35);
  backdrop-filter: blur(1px);
}

/* —— 抽屉 —— */
.ai-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 420px;
  max-width: 92vw;
  pointer-events: auto;
  background: var(--surface, #fff);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 28px rgba(11, 18, 32, 0.18);
  display: flex;
  flex-direction: column;
  z-index: 1001;
}

/* —— 头部 —— */
.ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ai-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ai-logo {
  font-size: 22px;
  color: var(--primary);
}
.ai-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.ai-subtitle {
  font-size: 11px;
  color: var(--text-muted);
}
.ai-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* —— 会话栏 —— */
.ai-session-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ai-session-select {
  flex: 1;
}
.session-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.session-option-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-option-del {
  color: var(--text-muted);
  font-size: 12px;
  padding: 0 4px;
}
.session-option-del:hover {
  color: var(--danger);
}
.session-count {
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* —— 消息流 —— */
.ai-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ai-empty {
  margin: auto;
  text-align: center;
  color: var(--text-muted);
  max-width: 260px;
}
.ai-empty-icon {
  font-size: 34px;
  color: var(--primary);
  opacity: 0.6;
}
.ai-empty-title {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.ai-empty-desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.msg {
  display: flex;
  flex-direction: column;
}
.msg-user {
  align-items: flex-end;
}
.msg-user-bubble {
  background: var(--primary);
  color: #fff;
  padding: 9px 12px;
  border-radius: 12px 12px 2px 12px;
  max-width: 82%;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-ai {
  align-items: flex-start;
  max-width: 100%;
}
.msg-ai-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.msg-ai-avatar {
  color: var(--primary);
  font-size: 14px;
}
.msg-ai-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.msg-ai-streaming {
  font-size: 11px;
  color: var(--text-muted);
}
.msg-ai-error {
  font-size: 11px;
  color: var(--danger);
}
.msg-ai-bubble {
  background: var(--bg, #f5f6fa);
  border: 1px solid var(--border);
  border-radius: 2px 12px 12px 12px;
  padding: 10px 12px;
  max-width: 100%;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-ai-bubble.is-error {
  border-color: var(--danger);
  color: var(--danger);
}
.msg-ai-text {
  color: var(--text-primary);
}
.msg-ai-cursor {
  display: inline-block;
  width: 8px;
  height: 14px;
  background: var(--primary);
  animation: blink 1s steps(2, start) infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}

/* 信任元数据 */
.msg-ai-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.meta-chip {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg, #f0f1f5);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
}
.meta-chip.warn { color: var(--warning); border-color: var(--warning); }

.msg-ai-ops {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}
.op-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
}
.op-btn:hover {
  background: var(--bg);
  color: var(--primary);
}
.op-btn.on {
  color: var(--primary);
}

/* —— 底部输入 —— */
.ai-footer {
  border-top: 1px solid var(--border);
  padding: 10px 12px 12px;
  flex-shrink: 0;
  background: var(--surface, #fff);
}
.ai-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.chip {
  border: 1px solid var(--border);
  background: var(--bg, #f5f6fa);
  color: var(--text-primary);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.chip:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}
.chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ai-composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.ai-input {
  flex: 1;
  resize: none;
  font-size: 13px;
}
.ai-send {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: var(--bg, #eceef3);
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}
.ai-send.on {
  background: var(--primary);
  color: #fff;
}
.ai-send:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* —— 动画 —— */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>