/* 深度巡检：完整路由 + 逐个点击所有按钮/tab/表单，收集 error+warning */
import { chromium } from 'playwright'

// 目标前端地址可用环境变量覆盖（默认 5173；端口被占用时如 AUDIT_BASE=http://localhost:5174）
const BASE = process.env.AUDIT_BASE || 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

const allIssues = []
let logCursor = 0
const logs = []
page.on('console', (msg) => {
  const t = msg.type()
  if (t === 'error' || t === 'warning') logs.push(`[${t}] ${msg.text()}`)
})
page.on('pageerror', (err) => logs.push(`[pageerror] ${err.message}`))
page.on('response', (res) => {
  if (res.status() === 401) logs.push(`[401] ${res.request().method()} ${new URL(res.url()).pathname}`)
})

function newIssues() {
  const slice = logs.slice(logCursor)
  logCursor = logs.length
  return slice
}

// 拦截所有写操作 API，返回模拟成功（防破坏数据，同时验证按钮发出请求）
// 放行登录/当前用户等认证请求，保证登录态正常
const writeCalls = []
await page.route('**/api/**', (route) => {
  const req = route.request()
  const url = req.url()
  if (url.includes('/auth/') || url.includes('/users/me') || url.includes('/me') || url.includes('/permissions')) {
    route.continue()
    return
  }
  const m = req.method()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(m)) {
    writeCalls.push(`${m} ${new URL(url).pathname}`)
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, message: 'mock' }),
    })
  } else {
    route.continue()
  }
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

const DANGER_TEXT = /删除|移除|取消|终止|停止|作废|重置|清空|退出|释放|驳回|放弃|归档|删除.*[？?]|确认删除/

async function interactPage(label, path) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2800)
  let errs = newIssues()
  if (errs.length) {
    allIssues.push(`[LOAD] ${label} (${path})`)
    for (const e of errs) allIssues.push(`    ${e.slice(0, 200)}`)
  }

  // 1. 点击所有可见按钮（每个按钮独立尝试，避免连锁）
  let btnIdx = 0
  while (true) {
    const btns = page.locator('button:visible:not([disabled])')
    const n = await btns.count()
    if (btnIdx >= n) break
    const btn = btns.nth(btnIdx)
    btnIdx++
    let text = ''
    try { text = ((await btn.innerText()) || '').trim().replace(/\s+/g, ' ').slice(0, 24) } catch { continue }
    // 跳过危险按钮（有 popconfirm/confirm 的删除类）——点击会在 Modal 拦截，只确认按钮存在
    if (DANGER_TEXT.test(text)) continue
    const before = logs.length
    try {
      await btn.scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => {})
      await btn.click({ timeout: 2500 })
      await page.waitForTimeout(350)
    } catch { continue }
    const diff = logs.slice(before)
    if (diff.length) {
      allIssues.push(`[BTN] ${label}(${path}) 按钮「${text}」: ${diff[0].slice(0, 220)}`)
    }
    // 若弹出 Modal/Drawer，点掉
    await closePopups()
  }

  // 2. 切换所有 tab
  const tabCount = await page.locator('.ant-tabs-tab:visible').count()
  for (let i = 0; i < tabCount; i++) {
    const before = logs.length
    try {
      await page.locator('.ant-tabs-tab:visible').nth(i).click({ timeout: 2000 })
      await page.waitForTimeout(400)
      await closePopups()
    } catch { continue }
    const diff = logs.slice(before)
    if (diff.length) {
      allIssues.push(`[TAB] ${label}(${path}) tab${i}: ${diff[0].slice(0, 220)}`)
    }
  }

  // 3. 输入框填值触发 watch/change
  const inputs = page.locator('input:visible:not([disabled]):not([type="hidden"])')
  const nInputs = Math.min(await inputs.count(), 6)
  for (let i = 0; i < nInputs; i++) {
    const before = logs.length
    try {
      const el = inputs.nth(i)
      const type = await el.getAttribute('type')
      if (type === 'checkbox' || type === 'radio') { await el.check({ force: true }).catch(() => {}) }
      else { await el.fill('测试内容'.slice(0, 2), { timeout: 1500 }).catch(() => {}) }
      await page.waitForTimeout(250)
    } catch { continue }
    const diff = logs.slice(before)
    if (diff.length) {
      allIssues.push(`[INPUT] ${label}(${path}) 输入框${i}: ${diff[0].slice(0, 220)}`)
    }
  }

  // 4. 下拉选择器展开
  const selCount = await page.locator('.ant-select-selector:visible').count()
  for (let i = 0; i < Math.min(selCount, 4); i++) {
    const before = logs.length
    try {
      await page.locator('.ant-select-selector:visible').nth(i).click({ timeout: 2000 })
      await page.waitForTimeout(400)
      const opt = page.locator('.ant-select-dropdown:visible .ant-select-item-option:not(.ant-select-item-option-disabled)')
      if (await opt.count()) await opt.first().click({ timeout: 2000 })
      await page.waitForTimeout(300)
    } catch { continue }
    const diff = logs.slice(before)
    if (diff.length) {
      allIssues.push(`[SELECT] ${label}(${path}) 下拉${i}: ${diff[0].slice(0, 220)}`)
    }
  }
}

async function closePopups() {
  // 关闭 drawer
  const closeBtns = page.locator('.ant-drawer-close:visible, .ant-modal-close:visible')
  if (await closeBtns.count()) {
    await closeBtns.first().click().catch(() => {})
    await page.waitForTimeout(300)
  }
}

await login()
newIssues() // 清空登录期间的日志（未登录 401 属正常现象）

const routes = [
  ['总览', '/'], ['管理看板', '/dashboard'], ['我的待办', '/my-tasks'],
  ['项目管理', '/projects'], ['新建项目', '/projects/new'], ['候选材料设计', '/workbench'],
  ['实验闭环迭代', '/ecml'], ['迭代历史', '/ecml/runs'], ['实验数据', '/experiments'],
  ['实验数据看板', '/experiment-dashboard'], ['实验工作台', '/experiment-workbench'],
  ['收益账单', '/value-report'], ['数据接入', '/data-ingest'], ['能力契约', '/capability-center'],
  ['控制平面', '/control-plane'], ['预算看板', '/budgets'], ['评估中心', '/eval-center'],
  ['数据质量', '/data-quality'], ['物料规格库', '/materials'], ['样品管理', '/samples'],
  ['合成路径', '/synthesis'], ['配方与工艺', '/formula-design'], ['工具与连接器', '/tools'],
  ['调用关系', '/topology'], ['智能编排', '/orchestration'], ['研发工作台', '/research'],
  ['智能体管理', '/agents'], ['映射控制台', '/mappings'], ['技术情报', '/technology-intelligence'],
  ['知识库', '/knowledge-base'], ['知识图谱', '/knowledge-graph'], ['属性字典', '/properties'],
  ['主数据治理', '/mdm'], ['设备台账', '/equipment'], ['用户管理', '/users'],
  ['审计日志', '/audit'], ['系统设置', '/settings'], ['导航可见性', '/nav-visibility'],
  ['无权限页', '/forbidden'],
]

for (const [label, path] of routes) {
  writeCalls.length = 0
  await interactPage(label, path)
}

console.log('\n========== 巡检结果 ==========')
if (allIssues.length === 0) {
  console.log('PASS: 所有页面所有交互零错误')
} else {
  console.log(`${allIssues.length} 处问题:`)
  for (const i of allIssues) console.log('  ' + i)
}

await browser.close()
