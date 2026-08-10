<template>
  <div class="login-page">
    <div class="login-panels">
      <!-- 左侧品牌区：深色面板 + 克制的材料结构线条 -->
      <section class="brand-panel">
        <div class="brand-logo">
          <svg class="brand-cube" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path d="M16 2 29 9.5v13L16 30 3 22.5v-13L16 2Z" fill="var(--primary)" opacity="0.9" />
            <path d="M16 2 29 9.5 16 17 3 9.5 16 2Z" fill="#93c5fd" />
            <path d="M16 17v13L3 22.5v-13L16 17Z" fill="var(--primary-active)" />
          </svg>
          <span class="brand-name">MaterialsPEML</span>
        </div>

        <div class="brand-body">
          <div class="brand-lead-wrap">
            <p class="brand-lead">AI 驱动的新材料研发平台</p>
            <p class="brand-sub">
              以 AI 预测为先导，第一性原理为基准，实证数据为校验，缩短新材料从设计到验证的周期。
            </p>
          </div>

          <figure class="brand-figure" aria-hidden="true">
            <svg viewBox="0 0 400 300" fill="none" xmlns="http://www.w3.org/2000/svg">
              <!-- 整体组合水平居中：晶体与预测曲线围绕画布中轴平衡排布 -->
              <g transform="translate(-42 0)">
              <!-- 晶体结构：通用材料晶胞 -->
              <g opacity="0.85">
                <path d="M150 200 L190 170 L230 200 L230 240 L190 270 L150 240 Z" fill="none" stroke="rgba(249,115,22,0.28)" stroke-width="1.5" stroke-linejoin="round" />
                <path d="M150 200 L190 230 L230 200" fill="none" stroke="rgba(249,115,22,0.14)" stroke-width="1" />
                <path d="M190 230 L190 270" fill="none" stroke="rgba(249,115,22,0.14)" stroke-width="1" />
                <circle cx="150" cy="200" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
                <circle cx="230" cy="200" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
                <circle cx="190" cy="170" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
                <circle cx="150" cy="240" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
                <circle cx="230" cy="240" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
                <circle cx="190" cy="270" r="5" fill="#1f140d" stroke="rgba(249,115,22,0.5)" stroke-width="1.5" />
              </g>
              <g opacity="0.4">
                <path d="M120 140 L160 110 L200 140 L200 180 L160 210 L120 180 Z" fill="none" stroke="rgba(249,115,22,0.22)" stroke-width="1.5" stroke-linejoin="round" />
                <circle cx="120" cy="140" r="4" fill="#1f140d" stroke="rgba(249,115,22,0.35)" stroke-width="1.5" />
                <circle cx="200" cy="140" r="4" fill="#1f140d" stroke="rgba(249,115,22,0.35)" stroke-width="1.5" />
                <circle cx="160" cy="110" r="4" fill="#1f140d" stroke="rgba(249,115,22,0.35)" stroke-width="1.5" />
                <circle cx="160" cy="210" r="4" fill="#1f140d" stroke="rgba(249,115,22,0.35)" stroke-width="1.5" />
              </g>

              <!-- 预测曲线：数据点 + 拟合线（AI 预测） -->
              <g transform="translate(240, 22)">
                <rect x="0" y="0" width="150" height="132" rx="8" fill="rgba(10,10,10,0.6)" stroke="rgba(249,115,22,0.2)" />
                <g transform="translate(14, 16)">
                  <rect x="0" y="0" width="52" height="6" rx="3" fill="rgba(226,232,244,0.22)" />
                  <rect x="0" y="20" width="122" height="1" rx="0.5" fill="rgba(226,232,244,0.1)" />
                  <rect x="0" y="40" width="122" height="1" rx="0.5" fill="rgba(226,232,244,0.1)" />
                  <rect x="0" y="60" width="122" height="1" rx="0.5" fill="rgba(226,232,244,0.1)" />
                  <rect x="0" y="80" width="122" height="1" rx="0.5" fill="rgba(226,232,244,0.1)" />
                  <!-- 拟合曲线 -->
                  <path d="M0 78 C 24 68, 38 62, 56 50 S 92 30, 122 14"
                    stroke="var(--primary)" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
                  <!-- 实测数据点 -->
                  <circle cx="20" cy="70" r="3" fill="none" stroke="#93c5fd" stroke-width="1.5" />
                  <circle cx="48" cy="52" r="3" fill="none" stroke="#93c5fd" stroke-width="1.5" />
                  <circle cx="78" cy="36" r="3" fill="none" stroke="#93c5fd" stroke-width="1.5" />
                  <circle cx="106" cy="20" r="3" fill="none" stroke="#93c5fd" stroke-width="1.5" />
                </g>
              </g>
              </g>
            </svg>
          </figure>

          <ol class="capability-list">
            <li>
              <span class="capability-index">01</span>
              <div>
                <span class="capability-name">AI 预测</span>
                <span class="capability-desc">外推候选材料的性质与合成可行性</span>
              </div>
            </li>
            <li>
              <span class="capability-index">02</span>
              <div>
                <span class="capability-name">第一性原理</span>
                <span class="capability-desc">从原子尺度计算能量、结构与稳定性</span>
              </div>
            </li>
            <li>
              <span class="capability-index">03</span>
              <div>
                <span class="capability-name">实证数据</span>
                <span class="capability-desc">以实验与既有数据交叉校验预测结论</span>
              </div>
            </li>
          </ol>
        </div>

        <footer class="brand-footer">
          <span class="brand-dot" aria-hidden="true" />
          仅授权企业账号可访问
        </footer>
      </section>

      <!-- 右侧登录表单区 -->
      <section class="form-panel">
        <div class="login-card">
          <h1 class="login-title">登录工作台</h1>
          <p class="login-subtitle">欢迎回来，请使用企业账号继续</p>

          <a-form layout="vertical" @submit.prevent="onLogin">
            <a-form-item label="企业账号">
              <a-input
                v-model:value="form.username"
                size="large"
                name="username"
                autocomplete="username"
                placeholder="请输入企业账号"
                @press-enter="onLogin"
              />
            </a-form-item>
            <a-form-item label="密码">
              <a-input-password
                v-model:value="form.password"
                size="large"
                name="password"
                autocomplete="current-password"
                placeholder="请输入密码"
                @press-enter="onLogin"
              />
            </a-form-item>
            <div class="login-options">
              <a-checkbox v-model:checked="form.remember">记住登录状态</a-checkbox>
              <a class="forgot-link" @click="onForgot">忘记密码？</a>
            </div>
            <a-button type="primary" size="large" block html-type="submit" :loading="loading" @click="onLogin">
              登录
            </a-button>
          </a-form>
        </div>
        <p class="login-footer">本系统仅限授权用户使用，登录即代表同意遵守企业数据安全与保密规范。</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { login as authLogin } from '@/api/auth'
import { setUserId } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import { useSystemStore } from '@/stores/system'
import { track } from '@/utils/telemetry'

const router = useRouter()
const route = useRoute()
const systemStore = useSystemStore()
const { setUser } = useAuth()

const loading = ref(false)
const form = ref({ username: '', password: '', remember: true })

async function onLogin() {
  if (loading.value) return
  if (!form.value.username?.trim() || !form.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const data = await authLogin({ username: form.value.username.trim(), password: form.value.password })
    // 记住登录状态 → localStorage（持久）；否则 → sessionStorage（关闭浏览器即失效）
    setUserId(data.user_id, data.token, form.value.remember)
    setUser({ id: data.user_id, role: data.role, token: data.token })
    await systemStore.fetchMe()
    message.success(`欢迎，${data.display_name || data.username}`)
    track('login', { user_id: data.user_id, role: data.role })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    router.replace(redirect && redirect.startsWith('/') ? redirect : '/')
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    loading.value = false
  }
}

function onForgot() {
  message.info('请联系系统管理员重置密码')
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: var(--light-bg);
  padding: var(--space-2xl);
  display: flex;
}

.login-panels {
  flex: 1;
  display: flex;
  gap: var(--space-2xl);
  width: 100%;
  min-height: 0;
}

/* —— 左侧品牌面板 —— */
.brand-panel {
  flex: 1 1 0%;
  min-width: 0;
  background: var(--sidebar-bg);
  border-radius: var(--radius-xl);
  padding: var(--space-2xl);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.brand-cube {
  width: 34px;
  height: 34px;
}

.brand-name {
  color: var(--text-on-dark);
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.01em;
}

.brand-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-2xl);
  padding: var(--space-xl) 0;
}

.brand-lead-wrap {
  max-width: 460px;
}

.brand-lead {
  color: var(--text-on-dark);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  line-height: 1.25;
  letter-spacing: 0.01em;
  margin: 0 0 var(--space-sm);
}

.brand-sub {
  color: var(--text-on-dark-muted);
  font-size: var(--font-size-md);
  line-height: 1.7;
  margin: 0;
}

.brand-figure {
  margin: 0;
  padding: 0;
  display: flex;
  justify-content: center;
}

.brand-figure svg {
  width: 100%;
  max-width: 360px;
  height: auto;
}

.capability-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-width: 460px;
  position: relative;
}

/* 连接各步骤标记的纵向引导线，强调“预测 → 计算 → 校验”的研发流程 */
.capability-list::before {
  content: '';
  position: absolute;
  left: 17px;
  top: 10px;
  bottom: 10px;
  width: 1px;
  background: linear-gradient(to bottom, rgba(249, 115, 22, 0.55), rgba(249, 115, 22, 0.06));
}

.capability-list li {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  padding: var(--space-md) 0;
}

.capability-index {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--sidebar-bg);
  border: 1px solid rgba(249, 115, 22, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}

.capability-list li > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.capability-name {
  color: var(--text-on-dark);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: 1.3;
}

.capability-desc {
  color: var(--text-on-dark-muted);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.brand-footer {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-on-dark-muted);
}

.brand-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
}

/* —— 右侧表单面板 —— */
.form-panel {
  flex: 1.618 1 0%;
  min-width: 320px;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-4xl);
  position: relative;
}

.login-card {
  width: 100%;
  max-width: 400px;
}

.login-title {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0 0 var(--space-xs);
}

.login-subtitle {
  font-size: var(--font-size-lg);
  color: var(--text-muted);
  margin: 0 0 var(--space-2xl);
}

.login-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: calc(-1 * var(--space-sm)) 0 var(--space-xl);
}

.forgot-link {
  font-size: var(--font-size-md);
}

.login-footer {
  position: absolute;
  bottom: var(--space-2xl);
  left: 0;
  right: 0;
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin: 0;
  padding: 0 var(--space-4xl);
}

/* 勾选框主色统一为系统橙 */
:deep(.ant-checkbox-checked .ant-checkbox-inner) {
  background-color: var(--primary);
  border-color: var(--primary);
}

:deep(.ant-checkbox-wrapper:hover .ant-checkbox-inner),
:deep(.ant-checkbox:hover .ant-checkbox-inner) {
  border-color: var(--primary);
}

/* 中等屏：左右两栏仍保留，但压缩左侧留白与字号 */
@media (max-width: 1080px) {
  .brand-panel {
    padding: var(--space-xl);
  }

  .brand-lead {
    font-size: var(--font-size-2xl);
  }

  .brand-figure svg {
    max-width: 300px;
  }
}

@media (max-width: 900px) {
  .login-panels {
    flex-direction: column;
  }

  .brand-panel {
    display: none;
  }

  .form-panel {
    flex: 1 1 auto;
    width: 100%;
    max-width: 420px;
    min-width: 0;
    margin: 0 auto;
  }

  .login-page {
    padding: var(--space-lg);
  }
}

/* 短屏：压缩左侧留白与插画，避免纵向溢出 */
@media (max-height: 780px) {
  .brand-body {
    gap: var(--space-lg);
    padding: var(--space-md) 0;
  }

  .brand-figure svg {
    max-width: 300px;
  }

  .capability-list li {
    padding: var(--space-sm) 0;
  }
}
</style>
