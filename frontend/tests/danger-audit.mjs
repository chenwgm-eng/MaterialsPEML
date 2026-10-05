/* 危险按钮专项：popconfirm / Modal 确认类按钮点击 + 确认流程无错 */
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

const logs = []
let cursor = 0
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`) })
page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`))
const fresh = () => { const s = logs.slice(cursor); cursor = logs.length; return s }

await page.route('**/api/**', (route) => {
  const req = route.request()
  const url = req.url()
  if (url.includes('/auth/') || url.includes('/me') || url.includes('/permissions')) return route.continue()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method())) {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
  } else route.continue()
})

async function login() {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
  await page.evaluate(() => localStorage.setItem('dashboard_onboarding_seen', 'true'))
  await page.waitForTimeout(2500)
  const u = page.locator('input[name="username"]')
  if (await u.count()) {
    await u.fill('admin')
    await page.locator('input[name="password"]').fill('admin123')
    await page.locator('.login-card button[type="submit"], .ant-modal .ant-btn-primary').first().click()
    await page.waitForTimeout(4000)
  }
}

const issues = []

async function scan(label, path) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2800)
  fresh()

  // 危险文本按钮（含 popconfirm 包裹）
  const btns = page.locator('button:visible:not([disabled])')
  const n = await btns.count()
  const DANGER = /删除|移除|作废|终止|停止|重置|清空|放弃|归档|释放|驳回|注销|退出/
  for (let i = 0; i < n; i++) {
    let text = ''
    try { text = ((await btns.nth(i).innerText()) || '').trim().replace(/\s+/g, ' ').slice(0, 20) } catch { continue }
    if (!DANGER.test(text)) continue
    const before = logs.length
    try {
      await btns.nth(i).scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => {})
      await btns.nth(i).click({ timeout: 2500 })
      await page.waitForTimeout(600)
    } catch { continue }
    // 处理确认弹层
    const pop = page.locator('.ant-popconfirm:visible .ant-btn-primary, .ant-popover:visible .ant-btn-primary, .ant-modal-confirm-btns .ant-btn-dangerous, .ant-modal-confirm-btns .ant-btn-primary')
    if (await pop.count()) {
      await pop.first().click({ timeout: 2000 }).catch(() => {})
      await page.waitForTimeout(600)
    }
    const diff = logs.slice(before)
    if (diff.length) issues.push(`[${label}] 危险按钮「${text}」: ${diff[0].slice(0, 220)}`)
    await closePopups()
  }
}

async function closePopups() {
  const c = page.locator('.ant-drawer-close:visible, .ant-modal-close:visible')
  if (await c.count()) { await c.first().click().catch(() => {}); await page.waitForTimeout(300) }
}

await login()
fresh()

const routes = [
  ['总览', '/'], ['项目管理', '/projects'], ['候选材料设计', '/workbench'],
  ['实验闭环迭代', '/ecml'], ['迭代历史', '/ecml/runs'], ['实验数据', '/experiments'],
  ['样品管理', '/samples'], ['物料规格库', '/materials'], ['设备台账', '/equipment'],
  ['知识库', '/knowledge-base'], ['知识图谱', '/knowledge-graph'], ['技术情报', '/technology-intelligence'],
  ['智能体管理', '/agents'], ['映射控制台', '/mappings'], ['主数据治理', '/mdm'],
  ['属性字典', '/properties'], ['我的待办', '/my-tasks'], ['研发工作台', '/research'],
  ['预算看板', '/budgets'], ['数据质量', '/data-quality'], ['配方与工艺', '/formula-design'],
  ['合成路径', '/synthesis'], ['工具与连接器', '/tools'], ['评估中心', '/eval-center'],
  ['数据接入', '/data-ingest'], ['用户管理', '/users'], ['审计日志', '/audit'],
]

for (const [label, path] of routes) await scan(label, path)

console.log(issues.length === 0 ? 'PASS: 所有危险按钮确认流程零错误' : issues.join('\n'))
await browser.close()
