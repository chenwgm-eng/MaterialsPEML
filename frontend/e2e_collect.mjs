// E2E 采集脚本：登录 admin，遍历菜单路由，采集导航树/页面快照/console/网络错误/截图
// 用法: node e2e_collect.mjs
import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://localhost:5173'
const OUT = path.join(__dirname, '..', 'doc', 'e2e_evidence')
fs.mkdirSync(OUT, { recursive: true })

// 需要逐一访问的路由（含不在菜单但需覆盖的管理页）
const ROUTES = [
  '/', '/dashboard', '/my-tasks', '/projects', '/projects/new',
  '/workbench', '/prediction', '/battery-life', '/ecml', '/ecml/runs',
  '/experiments', '/experiment-workbench', '/value-report',
  '/data-ingest', '/capability-center', '/control-plane', '/budgets',
  '/eval-center', '/data-quality', '/materials', '/samples', '/synthesis',
  '/formula-design', '/tools', '/topology', '/orchestration', '/research',
  '/agents', '/mappings', '/technology-intelligence', '/knowledge-base',
  '/knowledge-graph', '/properties', '/mdm', '/equipment', '/users',
  '/settings', '/forbidden', '/nonexistent-random-page-xyz',
]

const results = []
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

const pageErrors = []
const networkErrors = []
page.on('pageerror', (e) => pageErrors.push(`[pageerror] ${e.message}`))
page.on('console', (m) => {
  if (m.type() === 'error') pageErrors.push(`[console] ${m.text()}`)
})
page.on('requestfailed', (r) => {
  const u = r.url()
  if (u.includes('/api/')) networkErrors.push(`[reqfail] ${r.method()} ${u} ${r.failure()?.errorText || ''}`)
})
page.on('response', (r) => {
  if (r.url().includes('/api/') && r.status() >= 400) {
    networkErrors.push(`[http${r.status()}] ${r.request().method()} ${r.url()}`)
  }
})

await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 }).catch(()=>{})

// ---- 登录 ----
let loggedIn = await page.evaluate(() => !!localStorage.getItem('authToken'))
if (!loggedIn) {
  const loginBtn = page.locator('.ant-layout-header button').filter({ hasText: '登录' }).first()
  if (await loginBtn.count()) { await loginBtn.click(); await page.waitForTimeout(600) }
  await page.locator('input[name="username"]').fill('admin')
  await page.locator('input[name="password"]').fill('admin123')
  await page.locator('.ant-modal .ant-btn-primary').click()
  await page.waitForTimeout(1500)
  loggedIn = await page.evaluate(() => !!localStorage.getItem('authToken'))
}
results.push({ step: 'login', loggedIn, pageErrorsAtLogin: [...pageErrors] })
pageErrors.length = 0

// ---- 采集导航树 ----
const navTree = await page.evaluate(() => {
  const items = []
  document.querySelectorAll('.sidebar-menu .ant-menu-item').forEach((el) => {
    items.push(el.innerText.replace(/\s+/g, ' ').trim())
  })
  const groups = []
  document.querySelectorAll('.sidebar-menu .ant-menu-submenu-title').forEach((el) => {
    groups.push(el.innerText.replace(/\s+/g, ' ').trim())
  })
  return { groups, items }
})
results.push({ step: 'nav_tree', navTree })

// ---- 遍历路由 ----
for (const route of ROUTES) {
  const rec = { route, title: '', textLen: 0, text: '', hasEmpty: false, emptyText: '', errors: [], screenshot: '' }
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 60000 }).catch(()=>{})
  await page.waitForTimeout(1200)
  rec.title = await page.title().catch(()=> '')
  const body = await page.evaluate(() => {
    const el = document.querySelector('.main-content')
    return el ? el.innerText : ''
  }).catch(()=> '')
  rec.textLen = body.length
  rec.text = body.slice(0, 3000)
  // 空态检测
  const empties = await page.evaluate(() => {
    const out = []
    document.querySelectorAll('.empty-state, .ant-empty, .ant-empty-description, [class*="empty"]').forEach((e) => {
      const t = e.innerText.replace(/\s+/g,' ').trim()
      if (t) out.push(t.slice(0,120))
    })
    return out
  }).catch(()=>[])
  rec.emptyText = empties.slice(0,5).join(' | ')
  rec.hasEmpty = empties.length > 0
  // loading 残留
  const stuck = await page.evaluate(() => document.querySelectorAll('.ant-spin-spinning').length).catch(()=>0)
  rec.stuckLoading = stuck
  rec.errors = [...pageErrors]
  pageErrors.length = 0
  const shot = path.join(OUT, `page_${route.replace(/[^a-z0-9]/gi,'_') || 'home'}.png`)
  await page.screenshot({ path: shot, fullPage: false }).catch(()=>{})
  rec.screenshot = shot
  results.push(rec)
}

results.push({ step: 'network_summary', networkErrors: [...new Set(networkErrors)] })

await browser.close()
fs.writeFileSync(path.join(OUT, 'evidence.json'), JSON.stringify(results, null, 2))
console.log('DONE pages:', results.length, 'networkErrors total:', networkErrors.length)