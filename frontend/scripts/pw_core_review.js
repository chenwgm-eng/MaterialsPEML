import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const BASE = 'http://localhost:5173'
const API = 'http://localhost:8000'
const ADMIN = { username: 'admin', password: 'admin123' }
const SCREENSHOT_DIR = 'd:/BattleFish/BatteryEMCL Lab/frontend/screenshots/pw_core'
const REPORT_MD = 'd:/BattleFish/BatteryEMCL Lab/doc/review_core_playwright.md'

const TEST_PROJECT_ID = 'PROJ-3DB94354'
const TEST_TASK_ID = 'c7952d32-41c4-40f2-94af-a01237a76422'
const TEST_PROJECT2_ID = 'PROJ-34890B52'

let evCounter = 100
function newEv() {
  return `EV-20260729-${evCounter++}`
}
function shotPath(name) {
  return path.join(SCREENSHOT_DIR, `${name}.png`)
}

async function httpPost(url, body, headers = {}) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  return { status: r.status, data }
}
async function httpGet(url, headers = {}) {
  const r = await fetch(url, { headers })
  const data = await r.json().catch(() => ({}))
  return { status: r.status, data }
}

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true })
}

function safeFileName(route) {
  return (route === '/' ? 'home' : route.replace(/^\//, '').replace(/\//g, '_')).replace(/[^a-z0-9_\-]/gi, '_')
}

const consoleBuf = []
const failedRequests = []
function attachListeners(page) {
  page.on('console', (msg) => {
    if (['error', 'warning'].includes(msg.type())) {
      consoleBuf.push(`[${msg.type()}] ${msg.text()}`.slice(0, 400))
    }
  })
  page.on('pageerror', (err) => {
    consoleBuf.push(`[pageerror] ${String(err)}`.slice(0, 400))
  })
  page.on('requestfailed', (req) => {
    failedRequests.push({ url: req.url(), error: req.failure()?.errorText || '' })
  })
  page.on('response', (resp) => {
    if (resp.status() >= 500) {
      failedRequests.push({ url: resp.url(), status: resp.status() })
    }
  })
}
function flushBuffers() {
  const c = [...new Set(consoleBuf)]
  const f = [...failedRequests]
  consoleBuf.length = 0
  failedRequests.length = 0
  return { console: c, failed: f }
}

function isExcluded(text, href, tag) {
  const t = (text || '').toLowerCase()
  const h = (href || '').toLowerCase()
  if (t.includes('跳转到主内容')) return true
  if (t.includes('退出登录') || t.includes('登出') || t.includes('logout')) return true
  if (t.includes('删除') || t.includes('移除')) return true
  if (h.startsWith('http') && !h.includes('localhost:5173')) return true
  if (h.startsWith('mailto:')) return true
  if (h.startsWith('/') && h.length > 1 && !h.startsWith('#')) return true
  if (t.includes('返回项目中心')) return true
  if (t.includes('发起审批') && t.length < 6) return false
  return false
}

async function collectClickables(page) {
  const selector = 'button, a, [role="button"], .ant-select, .ant-tabs-tab, .ant-pagination-item, .ant-table-row, .ant-card, .ant-btn, [onclick]'
  const locators = await page.locator(selector).all()
  const list = []
  for (const loc of locators) {
    try {
      if (!(await loc.isVisible())) continue
      const text = (await loc.innerText().catch(() => '')).trim().slice(0, 80)
      const tag = await loc.evaluate((el) => el.tagName).catch(() => '')
      const disabled = await loc.evaluate((el) => el.disabled || el.getAttribute('aria-disabled') === 'true').catch(() => false)
      const href = (await loc.getAttribute('href').catch(() => '')) || ''
      if (disabled) continue
      if (isExcluded(text, href, tag)) continue
      list.push({ loc, text, tag, href })
    } catch {}
  }
  return list
}

async function handleOverlays(page) {
  const popups = []
  const confirm = page.locator('.ant-modal-confirm, .ant-modal-wrap').first()
  if (await confirm.isVisible().catch(() => false)) {
    const title = await confirm.locator('.ant-modal-confirm-title, .ant-modal-title').innerText().catch(() => '')
    popups.push({ type: 'modal', title })
    await confirm.locator('.ant-modal-confirm-btns button, .ant-modal-footer button').last().click({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(400)
  }
  const modal = page.locator('.ant-modal-root .ant-modal-wrap').first()
  if (await modal.isVisible().catch(() => false)) {
    popups.push({ type: 'modal2' })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
  }
  const drawer = page.locator('.ant-drawer-open').first()
  if (await drawer.isVisible().catch(() => false)) {
    popups.push({ type: 'drawer' })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
  }
  return popups
}

async function sweepClickables(page, result) {
  const clickables = await collectClickables(page)
  result.clickCount = clickables.length
  for (const c of clickables.slice(0, 80)) {
    const before = page.url()
    flushBuffers()
    try {
      await c.loc.click({ timeout: 3000 })
      await page.waitForTimeout(500)
      const after = page.url()
      const popups = await handleOverlays(page)
      const { console: errs, failed: fails } = flushBuffers()
      result.clicks.push({
        text: c.text,
        tag: c.tag,
        href: c.href,
        status: 'clicked',
        urlChanged: before !== after,
        popups,
        errors: errs,
        failedRequests: fails,
      })
    } catch (e) {
      result.clicks.push({
        text: c.text,
        tag: c.tag,
        href: c.href,
        status: 'error',
        error: String(e.message || e).slice(0, 200),
      })
      flushBuffers()
    }
  }
}

async function waitNoLoading(page, textMarks, timeoutMs) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const body = await page.locator('body').innerText().catch(() => '')
    const hasLoading = textMarks.some((m) => body.includes(m))
    const spin = await page.locator('.ant-spin-dot').count().catch(() => 0)
    if (!hasLoading && spin === 0) return true
    await page.waitForTimeout(1000)
  }
  return false
}

async function screenshot(page, name) {
  const p = shotPath(name)
  await page.screenshot({ path: p, fullPage: false })
  return p
}

// ---------- core actions ----------
async function actionProjectNew(page) {
  await page.waitForSelector('.phase-card', { timeout: 10000 })
  const ts = Date.now()
  const name = `PW核心测评项目-${ts}`
  const item = (label) => page.locator('.ant-form-item').filter({ hasText: label })
  await item('项目名称').locator('input').fill(name)
  await item('研发目标').locator('textarea').fill('通过AI生成候选硫化物固态电解质并验证离子电导率')
  await item('目标应用').locator('input').fill('高离子电导率硫化物固态电解质')
  try {
    await item('负责人').locator('.ant-select').click()
    await page.waitForSelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', { timeout: 5000 })
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option').filter({ hasText: '系统管理员' }).click()
    await page.waitForTimeout(500)
  } catch (e) {
    return { status: 'owner_select_failed', note: String(e.message || e).slice(0, 200) }
  }
  await page.locator('.pm-action-block button:has-text("Agent 执行")').first().click({ timeout: 10000 })
  let phase2 = false
  try {
    await page.waitForSelector('.phase-badge:has-text("阶段 2"), .task-list', { timeout: 60000 })
    phase2 = true
  } catch {
    return { status: 'timeout_to_tasks', note: 'AI 拆解未在 60s 内完成' }
  }
  await page.locator('button:has-text("确认并创建项目")').first().click({ timeout: 10000 })
  let done = false
  try {
    await page.waitForSelector('.ant-result-success', { timeout: 30000 })
    done = true
  } catch {}
  return { status: done ? 'success' : 'create_failed', projectName: name, phase2 }
}

async function actionWorkbench(page) {
  await page.waitForTimeout(2500)
  const btn = page.locator('button:has-text("调用智能体生成候选材料")').first()
  if (!(await btn.isVisible().catch(() => false))) {
    return { status: 'button_not_found', note: '未找到生成按钮，可能任务未预选中' }
  }
  await btn.click()
  await page.waitForSelector('.agent-progress-bar, .batch-predicting', { timeout: 5000 }).catch(() => {})
  await waitNoLoading(page, ['Agent 生成中', '批量预测'], 90000)
  await page.waitForTimeout(1500)
  const body = await page.locator('body').innerText().catch(() => '')
  const count = await page.locator('.candidate-list .candidate-item, .candidate-table tbody tr, .candidate-card, [class*="candidate"]').count().catch(() => 0)
  const success = body.includes('Agent 已生成') || count > 0
  return { status: success ? 'success' : 'failed_or_empty', candidateCount: count, hasMessage: body.includes('Agent 已生成') }
}

async function actionPrediction(page) {
  await page.waitForTimeout(2500)
  const btn = page.locator('button:has-text("开始预测")').first()
  if (!(await btn.isEnabled().catch(() => false))) {
    return { status: 'button_disabled', note: '开始预测按钮不可用' }
  }
  await btn.click()
  await page.waitForSelector('.ant-spin-nested-loading, .ant-spin-dot', { timeout: 5000 }).catch(() => {})
  await waitNoLoading(page, ['预测中', '建模中'], 60000)
  await page.waitForTimeout(1500)
  const count = await page.locator('.candidate-table tbody tr, .candidate-list-item').count().catch(() => 0)
  const body = await page.locator('body').innerText().catch(() => '')
  return { status: count > 0 ? 'success' : 'failed_or_empty', candidateCount: count, hasMessage: body.includes('预测完成') }
}

async function actionSynthesis(page) {
  await page.waitForTimeout(2000)
  const btn = page.locator('button:has-text("规划合成路径")').first()
  if (!(await btn.isEnabled().catch(() => false))) {
    return { status: 'button_disabled', note: '规划按钮不可用' }
  }
  await btn.click()
  await page.waitForSelector('.plan-progress', { timeout: 5000 }).catch(() => {})
  await waitNoLoading(page, ['规划中', '搜索候选路线'], 135000)
  await page.waitForTimeout(1500)
  const routes = await page.locator('.route-card').count().catch(() => 0)
  const body = await page.locator('body').innerText().catch(() => '')
  const serviceError = body.match(/服务暂不可用|规划失败|未找到可行|连接逆合成服务失败/)?.[0] || ''
  return { status: routes > 0 ? 'success' : (serviceError ? 'service_error' : 'failed_or_empty'), routeCount: routes, serviceError }
}

async function actionFormulaDesign(page) {
  await page.waitForTimeout(2500)
  const drawer = page.locator('.ant-drawer-open').first()
  if (!(await drawer.isVisible().catch(() => false))) {
    const openBtn = page.locator('button:has-text("生成新配方")').first()
    if (await openBtn.isVisible().catch(() => false)) {
      await openBtn.click({ force: true })
      await page.waitForTimeout(1000)
    }
  }
  const genBtn = page.locator('.ant-drawer-open button:has-text("生成配方")').first()
  if (!(await genBtn.isVisible().catch(() => false))) {
    return { status: 'drawer_not_opened', note: '未打开生成新配方抽屉' }
  }
  // 等待目标材料下拉选项加载（URL 已预填 target=LiCoO2）
  await page.waitForTimeout(800)
  await genBtn.click({ force: true })
  await page.waitForSelector('.ant-spin-nested-loading, .ant-spin-dot', { timeout: 5000 }).catch(() => {})
  await waitNoLoading(page, ['生成中'], 90000)
  await page.waitForTimeout(1500)
  const openDrawer = page.locator('.ant-drawer-open').first()
  const body = await openDrawer.innerText().catch(() => '')
  const bomRows = await openDrawer.locator('.ant-table tbody tr').count().catch(() => 0)
  const success = body.includes('物料清单') && bomRows > 0
  return { status: success ? 'success' : 'failed_or_empty', bomRows, hasError: body.includes('失败') || body.includes('错误') }
}

async function actionEcml(page) {
  await page.waitForTimeout(2000)
  const btn = page.locator('button:has-text("启动循环")').first()
  if (!(await btn.isEnabled().catch(() => false))) {
    const body = await page.locator('body').innerText().catch(() => '')
    const reason = body.includes('暂无实验数据') ? '缺少实验数据前置条件' : '按钮被禁用'
    return { status: 'button_disabled', note: reason }
  }
  await btn.click()
  await page.waitForFunction(() => document.body.innerText.includes('正在轮询') || document.body.innerText.includes('运行中') || document.querySelector('.ant-spin-dot'), { timeout: 10000 }).catch(() => {})
  const start = Date.now()
  let finalStatus = ''
  while (Date.now() - start < 120000) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (body.includes('迭代完成') || body.includes('完成')) {
      finalStatus = 'completed'
      break
    }
    if (body.includes('运行失败') || body.includes('失败')) {
      finalStatus = 'failed'
      break
    }
    if (body.includes('超时')) {
      finalStatus = 'timeout'
      break
    }
    await page.waitForTimeout(2000)
  }
  if (!finalStatus) finalStatus = 'timeout_120s'
  return { status: finalStatus }
}

async function actionExperimentWorkbench(page) {
  await page.waitForTimeout(2500)
  const drawer = page.locator('.ant-drawer-open').first()
  if (!(await drawer.isVisible().catch(() => false))) {
    return { status: 'drawer_not_opened', note: 'create=1 未自动打开新建抽屉' }
  }
  // 项目已通过 URL 预填，等待表单就绪
  await page.waitForTimeout(800)
  try {
    await page.waitForSelector('.ant-drawer-footer button:has-text("创 建")', { timeout: 10000 })
  } catch (e) {
    return { status: 'button_not_found', note: '未找到抽屉底部创建按钮: ' + String(e.message || e).slice(0, 200) }
  }
  const createBtn = page.locator('.ant-drawer-footer button:has-text("创 建")').first()
  await createBtn.click({ force: true })
  let closed = false
  try {
    await page.waitForFunction(() => !document.querySelector('.ant-drawer-open'), { timeout: 30000 })
    closed = true
  } catch {}
  await page.waitForTimeout(1000)
  const body = await page.locator('body').innerText().catch(() => '')
  return { status: closed && body.includes('创建成功') ? 'success' : (closed ? 'success' : 'failed'), message: body.includes('创建成功') ? '创建成功' : '' }
}

// ---------- main runner ----------
async function main() {
  ensureDir(SCREENSHOT_DIR)
  ensureDir(path.dirname(REPORT_MD))
  const report = {
    env: {},
    auth: null,
    projects: [],
    pages: [],
    core: [],
    defects: [],
  }

  // backend health
  const health = await httpGet(`${API}/health`).catch(() => ({ status: 0, data: {} }))
  report.env.backendHealth = health.status
  if (health.status !== 200) {
    report.env.backendRunning = false
    writeReport(report)
    console.log('后端未运行，已生成报告')
    return
  }
  report.env.backendRunning = true

  // login
  const loginRes = await httpPost(`${API}/auth/login`, ADMIN)
  if (loginRes.status !== 200 || !loginRes.data.token) {
    report.env.loginError = loginRes.data
    writeReport(report)
    console.log('登录失败', loginRes.data)
    return
  }
  const { token, user_id, role } = loginRes.data
  report.auth = { user_id, role, tokenPreview: token.slice(0, 20) + '...' }

  // verify projects / tasks
  const projRes = await httpGet(`${API}/projects`, { 'X-Auth-Token': token })
  const projects = Array.isArray(projRes.data) ? projRes.data : (projRes.data.projects || [])
  report.projects = projects.filter((p) => [TEST_PROJECT_ID, TEST_PROJECT2_ID].includes(p.project_id)).map((p) => ({ project_id: p.project_id, name: p.name }))

  const taskRes1 = await httpGet(`${API}/projects/${TEST_PROJECT_ID}/tasks`, { 'X-Auth-Token': token })
  const tasks1 = Array.isArray(taskRes1.data) ? taskRes1.data : (taskRes1.data.tasks || [])
  const task = tasks1.find((t) => t.task_id === TEST_TASK_ID)
  report.env.taskVerified = !!task

  const browser = await chromium.launch({ headless: false })
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
  await context.addInitScript(({ t, uid, role }) => {
    localStorage.setItem('authToken', t)
    localStorage.setItem('userId', uid)
    localStorage.setItem('userRole', role)
  }, { t: token, uid: user_id, role })

  const page = await context.newPage()
  attachListeners(page)

  const pages = [
    { route: '/', name: '首页' },
    { route: '/my-tasks', name: '我的待办' },
    { route: '/projects', name: '项目管理' },
    { route: '/projects/new', name: '项目新建', action: actionProjectNew },
    { route: '/workbench', name: '候选材料设计', query: { project_id: TEST_PROJECT_ID, task_id: TEST_TASK_ID }, action: actionWorkbench },
    { route: '/prediction', name: '性质预测', query: { formula: 'LiCoO2', target_property: 'ionic_conductivity' }, action: actionPrediction },
    { route: '/synthesis', name: '合成路径', query: { smiles: 'CCO' }, action: actionSynthesis },
    { route: '/formula-design', name: '配方与工艺', query: { target: 'LiCoO2' }, action: actionFormulaDesign },
    { route: '/ecml', name: '实验闭环迭代', query: { target: 'LiCoO2', target_property: 'ionic_conductivity' }, action: actionEcml },
    { route: '/ecml/runs', name: '迭代历史' },
    { route: '/battery-life', name: '性能寿命预测' },
    { route: '/experiment-workbench', name: '实验工作台', query: { create: '1', project_id: TEST_PROJECT_ID }, action: actionExperimentWorkbench },
  ]

  for (const cfg of pages) {
    await page.setViewportSize({ width: 1920, height: 1080 })
    flushBuffers()
    let url = BASE + cfg.route
    if (cfg.query) {
      url += '?' + new URLSearchParams(cfg.query).toString()
    }
    console.log(`\n>>> ${cfg.name} ${cfg.route}`)
    const pageRes = {
      name: cfg.name,
      route: cfg.route,
      url,
      finalUrl: '',
      loadStatus: 'ok',
      loadErrors: [],
      loadFailedRequests: [],
      screenshot: '',
      clickCount: 0,
      clicks: [],
      core: null,
    }
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
      await page.waitForTimeout(1500)
      pageRes.finalUrl = page.url()
      const shotName = `${newEv()}_${safeFileName(cfg.route)}_initial`
      pageRes.screenshot = await screenshot(page, shotName)
      const { console: loadErrs, failed: loadFails } = flushBuffers()
      pageRes.loadErrors = loadErrs
      pageRes.loadFailedRequests = loadFails
    } catch (e) {
      pageRes.loadStatus = 'error'
      pageRes.loadError = String(e.message || e).slice(0, 300)
      report.pages.push(pageRes)
      continue
    }

    if (cfg.action) {
      flushBuffers()
      try {
        pageRes.core = await cfg.action(page)
        pageRes.core.screenshot = await screenshot(page, `${newEv()}_${safeFileName(cfg.route)}_core`)
        const { console: coreErrs, failed: coreFails } = flushBuffers()
        pageRes.core.errors = coreErrs
        pageRes.core.failedRequests = coreFails
      } catch (e) {
        pageRes.core = { status: 'exception', error: String(e.message || e).slice(0, 300) }
      }
      flushBuffers()
    }

    await sweepClickables(page, pageRes)
    const afterShot = await screenshot(page, `${newEv()}_${safeFileName(cfg.route)}_final`)
    pageRes.finalScreenshot = afterShot
    report.pages.push(pageRes)
    console.log(`    load=${pageRes.loadStatus} core=${pageRes.core?.status || '-'} clicks=${pageRes.clickCount}`)
  }

  await browser.close()
  deriveDefects(report)
  writeReport(report)
  console.log('\n完成。报告：', REPORT_MD)
}

function deriveDefects(report) {
  const defects = []
  let idx = 1
  function add(mod, sev, title, steps, expected, actual, evidence, suggestion) {
    defects.push({
      id: `BEMCL-${mod}-${sev}-${String(idx).padStart(3, '0')}`,
      module: mod,
      severity: sev,
      title,
      steps,
      expected,
      actual,
      evidence,
      suggestion,
    })
    idx++
  }

  // page load failures
  for (const p of report.pages) {
    if (p.loadStatus !== 'ok') {
      add('NAV', 'P0', `${p.name} 页面加载异常`, `访问 ${p.route}`, '页面正常渲染', `加载失败：${p.loadError || 'unknown'}`, p.screenshot || '', '检查前端构建与路由配置')
    }
    for (const e of p.loadErrors) {
      if (e.includes('pageerror') || e.includes('[error]')) {
        add('FE', 'P1', `${p.name} 初始化报错`, `打开 ${p.route}`, '无 console error', e, p.screenshot || '', '定位异常堆栈并修复')
      }
    }
    for (const f of p.loadFailedRequests) {
      add('API', 'P1', `${p.name} 接口 ${f.status || f.error}`, `打开 ${p.route}`, '接口返回 200', `${f.status ? 'HTTP ' + f.status : f.error} ${f.url}`, p.screenshot || '', '检查后端的对应接口')
    }
  }

  // core action results
  const coreMap = {
    '项目新建': 'PROJ',
    '候选材料设计': 'WORKBENCH',
    '性质预测': 'PRED',
    '合成路径': 'SYNTH',
    '配方与工艺': 'FORMULA',
    '实验闭环迭代': 'ECML',
    '实验工作台': 'EXP',
  }
  for (const p of report.pages) {
    if (!p.core) continue
    const mod = coreMap[p.name] || 'CORE'
    if (p.core.status === 'success' || p.core.status === 'completed') {
      // no defect
    } else if (p.core.status === 'button_disabled' || p.core.status === 'button_not_found' || p.core.status === 'drawer_not_opened' || p.core.status === 'owner_select_failed') {
      add(mod, 'P1', `${p.name} 核心入口不可用`, `访问 ${p.route} 并执行核心操作`, '核心按钮可点击并提交', `${p.core.status}: ${p.core.note || ''}`, p.core.screenshot || p.screenshot, '检查前置条件与页面渲染')
    } else if (p.core.status === 'service_error') {
      add(mod, 'P1', `${p.name} 依赖服务异常`, `执行 ${p.name}`, '成功返回结果', `服务错误：${p.core.serviceError || ''}`, p.core.screenshot, '检查 ASKCOS/Agent/后端服务')
    } else {
      add(mod, 'P0', `${p.name} 核心操作未返回有效结果`, `执行 ${p.name}`, '操作成功并展示结果', `状态=${p.core.status}; ${p.core.error || p.core.note || ''}`, p.core.screenshot || p.screenshot, '修复对应业务链路')
    }
    for (const e of p.core.errors || []) {
      if (e.includes('pageerror') || e.includes('[error]')) {
        add(mod, 'P1', `${p.name} 操作期间报错`, `执行 ${p.name}`, '无 console error', e, p.core.screenshot, '检查前端事件与数据流')
      }
    }
    for (const f of p.core.failedRequests || []) {
      add(mod, 'P0', `${p.name} 操作接口失败`, `执行 ${p.name}`, '接口返回 200', `${f.status ? 'HTTP ' + f.status : f.error} ${f.url}`, p.core.screenshot, '检查后端的业务接口')
    }
  }

  // clickable sweep errors
  for (const p of report.pages) {
    const errs = p.clicks.filter((c) => c.status === 'error')
    if (errs.length > 0) {
      add('FE', 'P2', `${p.name} 部分可点击元素无法交互`, `遍历点击 ${p.route}`, '所有可点击元素正常响应', `${errs.length} 个点击异常：${errs.slice(0, 2).map((e) => e.text).join(', ')}`, p.finalScreenshot || p.screenshot, '检查元素覆盖与事件绑定')
    }
  }

  report.defects = defects
}

function writeReport(report) {
  const counts = { P0: 0, P1: 0, P2: 0, P3: 0 }
  for (const d of report.defects) counts[d.severity]++

  let md = `# BatteryEMCL Lab 前端核心研发链路 Playwright 实操评测报告\n\n`
  md += `> 生成时间：${new Date().toISOString()}\n\n`

  md += `## 1. 环境信息\n\n`
  md += `- 前端地址：${BASE}\n`
  md += `- 后端地址：${API}\n`
  md += `- 后端健康检查：${report.env.backendRunning ? '✅ 200' : `❌ ${report.env.backendHealth}`}\n`
  if (report.auth) {
    md += `- 登录用户：${report.auth.user_id}（角色：${report.auth.role}）\n`
  }
  md += `- 测试项目/任务：\n`
  for (const p of report.projects) md += `  - ${p.project_id} / ${p.name}\n`
  md += `- 任务 ID 验证：${report.env.taskVerified ? '✅' : '❌'}\n\n`

  md += `## 2. 覆盖清单\n\n`
  md += `| 序号 | 页面 | 路由 | 加载状态 | 核心操作 | 可点击元素数 | 初始截图 |\n`
  md += `| --- | --- | --- | --- | --- | --- | --- |\n`
  let i = 1
  for (const p of report.pages) {
    md += `| ${i++} | ${p.name} | ${p.route} | ${p.loadStatus} | ${p.core ? p.core.status : '-'} | ${p.clickCount} | ${path.basename(p.screenshot || '')} |\n`
  }

  md += `\n## 3. 端到端核心链路\n\n`
  for (const p of report.pages) {
    if (!p.core) continue
    md += `### ${p.name}\n\n`
    md += `- 路由：${p.route}\n`
    md += `- 预填参数：${JSON.stringify(p.core)}\n`
    md += `- 操作结果：**${p.core.status}**\n`
    if (p.core.error) md += `- 异常：${p.core.error}\n`
    if (p.core.note) md += `- 备注：${p.core.note}\n`
    if (p.core.candidateCount !== undefined) md += `- 候选数量：${p.core.candidateCount}\n`
    if (p.core.routeCount !== undefined) md += `- 路线数量：${p.core.routeCount}\n`
    if (p.core.bomRows !== undefined) md += `- BOM 行数：${p.core.bomRows}\n`
    if (p.core.serviceError) md += `- 服务错误：${p.core.serviceError}\n`
    if (p.core.errors?.length) md += `- 操作期报错：${p.core.errors.slice(0, 3).join('; ')}\n`
    if (p.core.failedRequests?.length) md += `- 操作期失败请求：${p.core.failedRequests.slice(0, 3).map((f) => f.url).join('; ')}\n`
    if (p.core.screenshot) md += `- 截图：${path.basename(p.core.screenshot)}\n`
    md += `\n`
  }

  md += `## 4. 缺陷清单\n\n`
  if (report.defects.length === 0) {
    md += `未发现缺陷。\n`
  } else {
    md += `| 编号 | 模块 | 级别 | 标题 | 复现步骤 | 期望结果 | 实际结果 | 证据 | 建议 |\n`
    md += `| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n`
    for (const d of report.defects) {
      md += `| ${d.id} | ${d.module} | ${d.severity} | ${d.title} | ${d.steps} | ${d.expected} | ${d.actual} | ${path.basename(d.evidence || '')} | ${d.suggestion} |\n`
    }
  }

  md += `\n## 5. 截图目录\n\n`
  md += `${SCREENSHOT_DIR}\n\n`
  md += `## 6. 统计\n\n`
  md += `- P0：${counts.P0}，P1：${counts.P1}，P2：${counts.P2}，P3：${counts.P3}\n`
  md += `- 总页面数：${report.pages.length}\n`

  fs.writeFileSync(REPORT_MD, md)
  fs.writeFileSync(REPORT_MD.replace('.md', '.json'), JSON.stringify(report, null, 2))
  console.log(`P0=${counts.P0} P1=${counts.P1} P2=${counts.P2} P3=${counts.P3}`)
}

main().catch((e) => {
  console.error('脚本异常退出：', e)
  process.exit(1)
})
