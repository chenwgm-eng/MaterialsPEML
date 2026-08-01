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
await page.goto(`${BASE_URL}/capability-center`)
await wait(2500)

const capId = `debug_cap_${Date.now()}`

// 打开登记抽屉
await page.locator('button:has-text("登记能力")').first().click()
await wait(1000)
const drawer = page.locator('.ant-drawer').filter({ hasText: '登记能力契约' }).first()
await drawer.locator('input').first().fill(capId)
await drawer.locator('.ant-form-item').filter({ hasText: '名称' }).first().locator('input').first().fill('调试能力')
await drawer.locator('.ant-form-item').filter({ hasText: '提供方' }).first().locator('input').first().fill('browser-test')
await drawer.locator('.ant-form-item').filter({ hasText: '版本' }).first().locator('input').first().fill('v0.1')
await selectAntOption(page, '风险等级', '低')

// 提交并轮询
await drawer.locator('button').filter({ hasText: /保\s*存/ }).first().click()
for (let t = 0; t <= 5000; t += 200) {
  await wait(200)
  const text = await page.locator('.ant-message-notice-content').first().innerText().catch(() => '')
  if (text) {
    console.log(`t=${t}ms message:`, text)
  }
  const row = page.locator('.capability-center .ant-table-tbody tr', { hasText: capId }).first()
  const visible = await row.isVisible().catch(() => false)
  if (visible) {
    console.log(`t=${t}ms row visible for`, capId)
    break
  }
}

// 检查表格总行数
const rows = await page.locator('.capability-center .ant-table-tbody tr').all()
console.log('total rows:', rows.length)
const html = await page.content()
console.log('contains capId:', html.includes(capId))

// 检查分页
const pagination = await page.locator('.capability-center .ant-pagination').innerText().catch(() => '')
console.log('pagination:', pagination)

// 通过 API 查询
const caps = await axios.get(`${BASE_URL}/api/capabilities`, { headers: { 'X-Auth-Token': login.token } })
console.log('api count:', caps.data?.capabilities?.length || caps.data?.count)
console.log('api contains:', caps.data?.capabilities?.some(c => c.capability_id === capId))

await browser.close()
