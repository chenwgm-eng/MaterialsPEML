/* 弹窗专项：打开每个 Drawer/Modal，点击弹窗内部全部按钮，验证无错 */
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
const OPEN_TEXT = /详情|查看|编辑|新增|创建|配置|设置|注册|导入|导出|运行|执行|下发|提交|部署|启动|上线|续跑|继续|生成|调试|测试|申请|授权|绑定|同步|刷新/

async function scan(label, path) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2800)
  fresh()

  // 尝试打开弹窗（每类文本一个，最多 5 个弹窗）
  const opened = new Set()
  const btns = page.locator('button:visible:not([disabled])')
  const n = await btns.count()
  for (let i = 0; i < n; i++) {
    if (opened.size >= 5) break
    let text = ''
    try { text = ((await btns.nth(i).innerText()) || '').trim().replace(/\s+/g, ' ') } catch { continue }
    if (!OPEN_TEXT.test(text) || opened.has(text)) continue
    const before = logs.length
    try {
      await btns.nth(i).scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => {})
      await btns.nth(i).click({ timeout: 2500 })
      await page.waitForTimeout(800)
    } catch { continue }
    const drawer = page.locator('.ant-drawer:visible')
    const modal = page.locator('.ant-modal:visible')
    const isModal = await modal.count() > 0
    const isDrawer = await drawer.count() > 0
    const diff1 = logs.slice(before)
    if (diff1.length && !isModal && !isDrawer) {
      issues.push(`[${label}] 按钮「${text.slice(0, 20)}」: ${diff1[0].slice(0, 200)}`)
    }
    if (isModal || isDrawer) {
      opened.add(text)
      // 点弹窗内所有按钮（确认类也点，写请求被 mock）
      const root = isModal ? modal.first() : drawer.first()
      const inner = root.locator('button:visible:not([disabled])')
      for (let j = 0; j < await inner.count(); j++) {
        const t2 = ((await inner.nth(j).innerText().catch(() => '')) || '').trim().replace(/\s+/g, ' ').slice(0, 20)
        const b2 = logs.length
        try {
          await inner.nth(j).click({ timeout: 2500 })
          await page.waitForTimeout(500)
        } catch { continue }
        const d2 = logs.slice(b2)
        if (d2.length) issues.push(`[${label}] 弹窗「${text.slice(0, 16)}」内按钮「${t2}」: ${d2[0].slice(0, 200)}`)
      }
      // 关闭弹窗
      const close = page.locator('.ant-modal-close:visible, .ant-drawer-close:visible')
      if (await close.count()) { await close.first().click().catch(() => {}); await page.waitForTimeout(400) }
      // 若有 confirm modal 残余，点取消
      const cancel = page.locator('.ant-modal-confirm-btns:visible')
      if (await cancel.count()) {
        const cbtns = cancel.first().locator('button')
        if (await cbtns.count() > 1) await cbtns.last().click().catch(() => {})
        await page.waitForTimeout(400)
      }
    }
  }
}

await login()
fresh()

const routes = [
  ['总览', '/'], ['项目管理', '/projects'], ['候选材料设计', '/workbench'],
  ['实验闭环迭代', '/ecml'], ['迭代历史', '/ecml/runs'], ['实验数据', '/experiments'],
  ['配方与工艺', '/formula-design'], ['合成路径', '/synthesis'], ['样品管理', '/samples'],
  ['物料规格库', '/materials'], ['设备台账', '/equipment'], ['知识库', '/knowledge-base'],
  ['知识图谱', '/knowledge-graph'], ['技术情报', '/technology-intelligence'],
  ['智能体管理', '/agents'], ['映射控制台', '/mappings'], ['主数据治理', '/mdm'],
  ['属性字典', '/properties'], ['我的待办', '/my-tasks'], ['研发工作台', '/research'],
  ['预算看板', '/budgets'], ['数据质量', '/data-quality'], ['工具与连接器', '/tools'],
  ['评估中心', '/eval-center'], ['数据接入', '/data-ingest'], ['用户管理', '/users'],
  ['审计日志', '/audit'], ['能力契约', '/capability-center'], ['控制平面', '/control-plane'],
  ['实验工作台', '/experiment-workbench'],
]

for (const [label, path] of routes) await scan(label, path)

console.log(issues.length === 0 ? 'PASS: 所有弹窗内部按钮零错误' : `${issues.length} 处问题:\n${issues.join('\n')}`)
await browser.close()
