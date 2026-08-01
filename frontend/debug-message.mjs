import { chromium } from 'playwright'
import axios from 'axios'

const BASE_URL = 'http://localhost:8000'

async function wait(ms) { return new Promise(r => setTimeout(r, ms)) }

async function apiLogin() {
  const res = await axios.post(`${BASE_URL}/api/auth/login`, { username: 'admin', password: 'admin123' })
  return res.data
}

async function selectAntOption(page, label, optionText) {
  const item = page.locator('.ant-form-item').filter({ hasText: label }).first()
  await item.locator('.ant-select').first().click()
  await wait(300)
  const opt = page.locator('.ant-select-dropdown').locator('.ant-select-item', { hasText: optionText }).first()
  await opt.click().catch(() => {})
  await wait(300)
}

const login = await apiLogin()
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto(`${BASE_URL}/`)
await wait(1000)
await page.evaluate(({ userId, token, role }) => {
  localStorage.setItem('userId', userId)
  localStorage.setItem('authToken', token)
  localStorage.setItem('userRole', role || 'admin')
}, { userId: login.user_id, token: login.token, role: login.role })
await page.goto(`${BASE_URL}/agents`)
await wait(2500)

// 打开新建抽屉
await page.locator('.agent-manager-page button:has-text("新建智能体")').first().click()
await wait(800)
const drawer = page.locator('.ant-drawer').filter({ hasText: '新建智能体' }).first()
await drawer.locator('input[placeholder="Agent 名称"]').first().fill(`调试智能体-${Date.now()}`)
await selectAntOption(page, '角色', '材料发现')
await drawer.locator('textarea[placeholder="Agent 职责描述"]').first().fill('调试')

// 点击保存并立即轮询消息
await drawer.locator('button').filter({ hasText: /保\s*存/ }).first().click()
for (let t = 0; t <= 3000; t += 100) {
  await wait(100)
  const html = await page.content()
  const msgMatch = html.match(/ant-message[^>]*>([\s\S]{0,500})/)
  const notifyMatch = html.match(/ant-notification[^>]*>([\s\S]{0,500})/)
  if (msgMatch || notifyMatch) {
    console.log(`t=${t}ms: message present`)
  }
  const text = await page.locator('.ant-message-notice-content').first().innerText().catch(() => '')
  if (text) {
    console.log(`t=${t}ms captured message:`, text)
    break
  }
}

// 最终检查
const finalMsg = await page.locator('.ant-message-notice-content').first().innerText().catch(() => '')
console.log('final message:', JSON.stringify(finalMsg))
const finalNotify = await page.locator('.ant-notification-notice-message').first().innerText().catch(() => '')
console.log('final notification:', JSON.stringify(finalNotify))

// 检查列表
const row = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: '调试智能体' }).first()
console.log('row visible:', await row.isVisible().catch(() => false))

await browser.close()
