// BatteryEMCL Lab 数据 / 知识资产 / AI 与编排 / 管理模块 Playwright 深度实操测评
// 输出：截图 -> frontend/screenshots/pw_data_ai/，报告 -> doc/review_data_ai_playwright.md
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..', '..')
const BASE = 'http://localhost:5173'
const API_BASE = 'http://localhost:8000/api'
const SCREEN_DIR = path.join(ROOT, 'frontend', 'screenshots', 'pw_data_ai')
const REPORT_PATH = path.join(ROOT, 'doc', 'review_data_ai_playwright.md')
const CREDENTIALS = { username: 'admin', password: 'admin123' }

fs.mkdirSync(SCREEN_DIR, { recursive: true })

let evCounter = 200
function nextEv() {
  const id = `EV-20260729-${evCounter.toString().padStart(3, '0')}`
  evCounter++
  return id
}

const evidenceList = []
function recordEvidence(label, relPath) {
  const id = nextEv()
  evidenceList.push({ id, label, screenshot: relPath })
  return id
}

const findings = []
const findingCounters = {}
function addFinding(moduleAbbr, severity, title, description, route, evIds = []) {
  if (!findingCounters[moduleAbbr]) findingCounters[moduleAbbr] = {}
  findingCounters[moduleAbbr][severity] = (findingCounters[moduleAbbr][severity] || 0) + 1
  const n = findingCounters[moduleAbbr][severity]
  findings.push({
    id: `BEMCL-${moduleAbbr}-${severity}-${String(n).padStart(3, '0')}`,
    module: moduleAbbr,
    severity,
    title,
    description,
    route,
    evidence: evIds,
    time: new Date().toISOString(),
  })
}

async function screenshot(page, slug) {
  const safeSlug = String(slug).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80)
  const fileName = `${safeSlug}.png`
  const abs = path.join(SCREEN_DIR, fileName)
  await page.screenshot({ path: abs, fullPage: false })
  return `frontend/screenshots/pw_data_ai/${fileName}`
}

async function pageText(page) {
  return await page.locator('body').innerText({ timeout: 5000 }).catch(() => '')
}

async function authenticate() {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(CREDENTIALS),
  })
  if (!resp.ok) {
    const body = await resp.text().catch(() => '')
    throw new Error(`登录接口 ${resp.status}: ${body.slice(0, 200)}`)
  }
  const data = await resp.json()
  return { userId: data.user_id, token: data.token, role: data.role || 'admin' }
}

async function waitLoaded(page, baseMs = 2500) {
  await page.waitForTimeout(baseMs)
  try {
    await page.waitForSelector('.ant-spin-dot', { state: 'hidden', timeout: 12000 })
  } catch {}
  try {
    await page.waitForSelector('.ant-skeleton', { state: 'hidden', timeout: 6000 })
  } catch {}
}

async function closeOverlays(page) {
  try {
    const modalClose = page.locator('.ant-modal-close:visible').first()
    if (await modalClose.isVisible().catch(() => false)) await modalClose.click({ timeout: 2000 })
  } catch {}
  try {
    const drawerClose = page.locator('.ant-drawer-close:visible').first()
    if (await drawerClose.isVisible().catch(() => false)) await drawerClose.click({ timeout: 2000 })
  } catch {}
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
}

async function getScope(page) {
  const has = await page.locator('.ant-layout-content').count()
  return has ? '.ant-layout-content' : 'body'
}

async function fillVisibleForm(page) {
  const container = '.ant-modal-content:visible, .ant-drawer-content:visible'
  const textInputs = await page.locator(`${container} input:visible`).all()
  let idx = 0
  for (const input of textInputs) {
    try {
      const type = await input.getAttribute('type').catch(() => 'text')
      if (['file', 'hidden', 'checkbox', 'radio'].includes(type)) continue
      if (await input.isDisabled().catch(() => true)) continue
      const ph = (await input.getAttribute('placeholder').catch(() => '')).toLowerCase()
      let value = `auto-${idx}`
      if (type === 'number') value = String(Math.floor(Math.random() * 100) + 1)
      else if (ph.includes('邮箱') || ph.includes('email')) value = `auto${idx}@test.com`
      else if (ph.includes('手机') || ph.includes('phone')) value = '13800000000'
      await input.fill(value, { timeout: 2000 })
      idx++
    } catch {}
  }
  const selects = await page.locator(`${container} .ant-select:visible`).all()
  for (const sel of selects) {
    try {
      await sel.click({ timeout: 2000 })
      await page.waitForTimeout(500)
      const opt = page.locator('.ant-select-item-option-content').first()
      if (await opt.isVisible().catch(() => false)) {
        await opt.click({ timeout: 2000 })
        await page.waitForTimeout(300)
      } else {
        await page.keyboard.press('Escape')
      }
    } catch {}
  }
  const textareas = await page.locator(`${container} textarea:visible`).all()
  for (const ta of textareas) {
    try {
      await ta.fill(`auto description ${Date.now()}`, { timeout: 2000 })
    } catch {}
  }
}

async function submitVisibleForm(page, abbr, labelPrefix, evidenceList) {
  const container = '.ant-modal-content:visible, .ant-drawer-content:visible'
  const saveBtn = page
    .locator(
      `${container} button:has-text("保存"), ${container} button:has-text("提交"), ${container} button:has-text("确认"), ${container} button:has-text("确定")`,
    )
    .first()
  if (await saveBtn.isVisible().catch(() => false)) {
    await saveBtn.click({ timeout: 3000 })
    await page.waitForTimeout(1500)
    const shot = await screenshot(page, `${abbr}_form_submit_${Date.now()}`)
    evidenceList.push(recordEvidence(`${labelPrefix} 表单提交`, shot))
    const txt = await pageText(page)
    return txt.includes('成功') || txt.includes('新增成功') || txt.includes('保存成功') || txt.includes('导入完成')
  }
  return false
}

async function openAndFillCreate(page, triggerText, abbr, label, evidenceList) {
  const scope = await getScope(page)
  const btn = page.locator(`${scope} button:has-text("${triggerText}"):visible`).first()
  if (await btn.isVisible().catch(() => false)) {
    await btn.click({ timeout: 3000 })
    await page.waitForTimeout(800)
    await fillVisibleForm(page)
    const ok = await submitVisibleForm(page, abbr, label, evidenceList)
    await closeOverlays(page)
    return ok
  }
  return null
}

async function clickTabs(page, abbr, evidenceList, max = 8) {
  const scope = await getScope(page)
  const summary = []
  for (let i = 0; i < max; i++) {
    const loc = page.locator(`${scope} .ant-tabs-tab:visible`).nth(i)
    const visible = await loc.isVisible().catch(() => false)
    if (!visible) break
    const text = (await loc.textContent().catch(() => '')).slice(0, 40).replace(/\s+/g, ' ')
    try {
      await loc.click({ timeout: 2000 })
      await page.waitForTimeout(600)
      const shot = await screenshot(page, `${abbr}_tab_${i}`)
      summary.push(recordEvidence(`Tab: ${text}`, shot))
    } catch {}
  }
  return summary
}

async function clickPagination(page, abbr, evidenceList, max = 3) {
  const scope = await getScope(page)
  const summary = []
  for (let i = 0; i < max; i++) {
    const loc = page.locator(`${scope} .ant-pagination-item:not(.ant-pagination-item-active):visible`).nth(i)
    const visible = await loc.isVisible().catch(() => false)
    if (!visible) break
    try {
      await loc.click({ timeout: 2000 })
      await page.waitForTimeout(800)
      const shot = await screenshot(page, `${abbr}_page_${i}`)
      summary.push(recordEvidence(`分页 ${i + 1}`, shot))
    } catch {}
  }
  return summary
}

async function clickTableRows(page, abbr, evidenceList, max = 5) {
  const scope = await getScope(page)
  const summary = []
  for (let i = 0; i < max; i++) {
    const loc = page.locator(`${scope} .ant-table-tbody tr:visible`).nth(i)
    const visible = await loc.isVisible().catch(() => false)
    if (!visible) break
    try {
      await loc.click({ timeout: 2000 })
      await page.waitForTimeout(800)
      const shot = await screenshot(page, `${abbr}_row_${i}`)
      summary.push(recordEvidence(`表格行 ${i + 1}`, shot))
      await closeOverlays(page)
    } catch {}
  }
  return summary
}

async function interactSelects(page, abbr, evidenceList, max = 4) {
  const scope = await getScope(page)
  const summary = []
  for (let i = 0; i < max; i++) {
    const loc = page.locator(`${scope} .ant-select:visible`).nth(i)
    const visible = await loc.isVisible().catch(() => false)
    if (!visible) break
    try {
      await loc.click({ timeout: 2000 })
      await page.waitForTimeout(500)
      const opt = page.locator('.ant-select-item-option-content').first()
      if (await opt.isVisible().catch(() => false)) {
        await opt.click({ timeout: 2000 })
        await page.waitForTimeout(600)
        const shot = await screenshot(page, `${abbr}_select_${i}`)
        summary.push(recordEvidence(`下拉选择 ${i + 1}`, shot))
      } else {
        await page.keyboard.press('Escape')
      }
    } catch {}
  }
  return summary
}

async function performSearch(page, abbr, evidenceList) {
  const scope = await getScope(page)
  const loc = page
    .locator(
      `${scope} input[type="search"]:visible, ${scope} .ant-input-search input:visible, ${scope} input[placeholder*="搜索"]:visible`,
    )
    .first()
  if (await loc.isVisible().catch(() => false)) {
    try {
      await loc.fill('test', { timeout: 2000 })
      await loc.press('Enter')
      await page.waitForTimeout(1200)
      const shot = await screenshot(page, `${abbr}_search`)
      return [recordEvidence('搜索 test', shot)]
    } catch {}
  }
  return []
}

async function clickCards(page, abbr, evidenceList, max = 4) {
  const scope = await getScope(page)
  const summary = []
  for (let i = 0; i < max; i++) {
    const loc = page.locator(`${scope} .ant-card:visible`).nth(i)
    const visible = await loc.isVisible().catch(() => false)
    if (!visible) break
    try {
      await loc.click({ timeout: 2000 })
      await page.waitForTimeout(500)
      const shot = await screenshot(page, `${abbr}_card_${i}`)
      summary.push(recordEvidence(`卡片 ${i + 1}`, shot))
      await closeOverlays(page)
    } catch {}
  }
  return summary
}

async function clickButtons(page, abbr, evidenceList, max = 6) {
  const scope = await getScope(page)
  let clicked = 0
  let index = 0
  const summary = []
  const maxInspect = Math.max(max * 6, 24)
  while (clicked < max && index < maxInspect) {
    const btn = page.locator(`${scope} button:visible`).nth(index)
    const visible = await btn.isVisible().catch(() => false)
    if (!visible) break
    const info = await btn
      .evaluate((el) => {
        const text = (el.textContent || '').trim().slice(0, 40)
        const cls = el.className || ''
        const disabled = el.disabled
        const inTab = !!el.closest('.ant-tabs-tab, .ant-pagination, .ant-select-dropdown, .ant-modal-confirm, .ant-popover, .ant-dropdown')
        return { text, cls, disabled, inTab }
      })
      .catch(() => null)
    index++
    if (!info) continue
    if (info.disabled || info.inTab) continue
    if (info.text.includes('删除') || info.text.includes('退出登录') || info.text.includes('登出')) continue
    if (info.cls.includes('ant-btn-dangerous')) continue
    // 跳过纯图标按钮，避免在表格行操作列上无限遍历
    if (!info.text) continue
    console.log(`      [${abbr}] button click: ${info.text}`)
    try {
      await btn.scrollIntoViewIfNeeded({ timeout: 1500 })
      await btn.click({ timeout: 3000 })
      await page.waitForTimeout(700)
      const shot = await screenshot(page, `${abbr}_btn_${clicked}`)
      summary.push(recordEvidence(`按钮: ${info.text}`, shot))
      clicked++
      await closeOverlays(page)
    } catch {}
  }
  return summary
}

async function sweepInteractions(page, abbr, evidenceList) {
  const results = []
  console.log(`    [${abbr}] sweep: tabs`)
  results.push(...(await clickTabs(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: pagination`)
  results.push(...(await clickPagination(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: rows`)
  results.push(...(await clickTableRows(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: selects`)
  results.push(...(await interactSelects(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: search`)
  results.push(...(await performSearch(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: cards`)
  results.push(...(await clickCards(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: buttons`)
  results.push(...(await clickButtons(page, abbr, evidenceList)))
  console.log(`    [${abbr}] sweep: done`)
  return results
}

function classifyErrors(errors) {
  const critical = []
  const warnings = []
  for (const e of errors) {
    const s = String(e)
    if (/TypeError|ReferenceError|SyntaxError|Cannot read|undefined is not|NetworkError|failed to fetch|ERR_/.test(s)) {
      critical.push(s.slice(0, 400))
    } else if (s.toLowerCase().includes('warning') || s.includes('warn')) {
      warnings.push(s.slice(0, 400))
    }
  }
  return { critical: [...new Set(critical)], warnings: [...new Set(warnings)] }
}

async function reviewPage(page, route, name, abbr, checks = {}, custom) {
  const routeErrors = []
  const onConsole = (msg) => {
    if (['error', 'warning'].includes(msg.type())) routeErrors.push(`[${msg.type()}] ${msg.text()}`)
  }
  const onPageError = (err) => routeErrors.push(`[pageerror] ${String(err)}`)
  page.on('console', onConsole)
  page.on('pageerror', onPageError)

  const pageEvidence = []
  console.log(`  [${abbr}] 开始加载...`)
  let loaded = false
  try {
    await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 25000 })
    await page.waitForTimeout(2000)
    await waitLoaded(page, 2000)
    loaded = true
    console.log(`  [${abbr}] 加载完成`)
  } catch (e) {
    const shot = await screenshot(page, `${abbr}_load_fail`)
    const ev = recordEvidence(`${name} 加载失败`, shot)
    addFinding(abbr, 'P0', `${name} 页面加载失败`, e.message, route, [ev])
    page.off('console', onConsole)
    page.off('pageerror', onPageError)
    return { route, name, abbr, status: 'load_failed', evidence: pageEvidence }
  }

  const fullShot = await screenshot(page, `${abbr}_full`)
  pageEvidence.push(recordEvidence(`${name} 页面全貌`, fullShot))
  const bodyText = await pageText(page)

  if (bodyText.includes('页面不存在') || bodyText.includes('404') || bodyText.includes('您访问的页面')) {
    addFinding(abbr, 'P0', `${name} 路由返回 404`, '页面内容包含 404 或无权限提示', route, pageEvidence)
  }

  // 关键内容校验
  if (checks.mustInclude) {
    for (const item of checks.mustInclude) {
      const found = item.keywords.some((k) => bodyText.includes(k))
      if (!found) {
        addFinding(abbr, item.severity || 'P2', item.title, `未检测到关键内容：${item.keywords.join(' / ')}`, route, pageEvidence)
      }
    }
  }

  // 自定义深度操作
  if (custom) {
    console.log(`  [${abbr}] 执行自定义操作...`)
    try {
      await custom(page, { recordEvidence, screenshot, pageText, addFinding, closeOverlays, fillVisibleForm, submitVisibleForm, openAndFillCreate })
      console.log(`  [${abbr}] 自定义操作完成`)
    } catch (e) {
      const shot = await screenshot(page, `${abbr}_custom_error`)
      const ev = recordEvidence(`${name} 自定义操作异常`, shot)
      addFinding(abbr, 'P1', `${name} 自定义操作异常`, e.message, route, [ev])
    }
  }

  // 通用交互巡扫
  console.log(`  [${abbr}] 开始交互巡扫...`)
  await sweepInteractions(page, abbr, pageEvidence)
  console.log(`  [${abbr}] 交互巡扫完成`)

  // 错误分级落库
  const { critical, warnings } = classifyErrors(routeErrors)
  if (critical.length) {
    const shot = await screenshot(page, `${abbr}_console_error`)
    const ev = recordEvidence(`${name} 控制台严重错误`, shot)
    addFinding(abbr, 'P1', `${name} 控制台出现严重错误`, critical.slice(0, 3).join('；'), route, [ev])
  }
  if (warnings.length && !critical.length) {
    const shot = await screenshot(page, `${abbr}_console_warn`)
    const ev = recordEvidence(`${name} 控制台警告`, shot)
    addFinding(abbr, 'P3', `${name} 控制台出现警告`, warnings.slice(0, 3).join('；'), route, [ev])
  }

  page.off('console', onConsole)
  page.off('pageerror', onPageError)
  return { route, name, abbr, status: 'ok', evidence: pageEvidence, errors: routeErrors }
}

// ─────────────────────────────────────────────────────────────────────────────
// 页面定义
// ─────────────────────────────────────────────────────────────────────────────
const PAGES = [
  // 实验与数据
  {
    route: '/experiment-workbench',
    name: '实验工作台',
    abbr: 'EXPW',
    checks: {
      mustInclude: [
        { keywords: ['实验工作台', '创建任务', '项目'], title: '实验工作台核心文案缺失', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const scope = await getScope(page)
      const createBtn = page.locator(`${scope} button:has-text("创建任务"):visible, ${scope} button:has-text("新建任务"):visible`).first()
      if (await createBtn.isVisible().catch(() => false)) {
        await createBtn.click({ timeout: 3000 })
        await page.waitForTimeout(800)
        await h.fillVisibleForm(page)
        await h.submitVisibleForm(page, 'EXPW', '创建任务', this.evidenceRef || [])
        await h.closeOverlays(page)
      }
    },
  },
  {
    route: '/experiments',
    name: '实验数据',
    abbr: 'EXP',
    checks: {
      mustInclude: [
        { keywords: ['实验数据', '样品编号', '实验类型'], title: '实验数据页核心元素缺失', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const scope = await getScope(page)
      const detailBtn = page.locator(`${scope} button:has-text("详情"):visible`).first()
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click({ timeout: 2000 })
        await page.waitForTimeout(800)
        const shot = await screenshot(page, 'EXP_detail')
        recordEvidence('实验记录详情', shot)
        await h.closeOverlays(page)
      }
      const editBtn = page.locator(`${scope} button:has-text("编辑"):visible`).first()
      if (await editBtn.isVisible().catch(() => false)) {
        await editBtn.click({ timeout: 2000 })
        await page.waitForTimeout(800)
        const shot = await screenshot(page, 'EXP_edit')
        recordEvidence('实验记录编辑（只读验证）', shot)
        await h.closeOverlays(page)
      }
    },
  },
  {
    route: '/samples',
    name: '样品管理',
    abbr: 'SAM',
    checks: { mustInclude: [{ keywords: ['样品管理', '样品清单'], title: '样品管理页核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      await h.openAndFillCreate(page, '新建样品', 'SAM', '新建样品', this.evidenceRef || [])
    },
  },
  {
    route: '/equipment',
    name: '设备台账',
    abbr: 'EQP',
    checks: { mustInclude: [{ keywords: ['设备台账', '设备清单'], title: '设备台账页核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      await h.openAndFillCreate(page, '新增设备', 'EQP', '新增设备', this.evidenceRef || [])
    },
  },
  {
    route: '/data-ingest',
    name: '数据接入',
    abbr: 'ING',
    checks: {
      mustInclude: [
        { keywords: ['数据接入', '上传文件', '字段映射'], title: '数据接入核心步骤缺失', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const csvPath = path.join(SCREEN_DIR, 'ev-ingest-test.csv')
      fs.writeFileSync(
        csvPath,
        `sample_id,batch_number,experiment_type,temperature,ionic_conductivity,unit\nSMP-EV-001,BAT-EV-20260728-01,EIS,25,1.35e-3,S/cm\nSMP-EV-002,BAT-EV-20260728-02,EIS,25,1.20e-3,S/cm`,
      )
      const fileInput = page.locator('input[type="file"]').first()
      if (await fileInput.isVisible().catch(() => false)) {
        await fileInput.setInputFiles(csvPath)
        await page.waitForTimeout(2000)
        let shot = await screenshot(page, 'ING_upload_preview')
        recordEvidence('数据接入上传预览', shot)
        const nextBtn = page.locator('button:has-text("下一步"):visible').first()
        if (await nextBtn.isVisible().catch(() => false)) {
          await nextBtn.click({ timeout: 3000 })
          await page.waitForTimeout(1500)
          shot = await screenshot(page, 'ING_mapping')
          recordEvidence('数据接入字段映射', shot)
        }
        const qualityNext = page.locator('.step-actions button:has-text("下一步"):visible').first()
        if (await qualityNext.isVisible().catch(() => false)) {
          await qualityNext.click({ timeout: 3000 })
          await page.waitForTimeout(1500)
          shot = await screenshot(page, 'ING_quality')
          recordEvidence('数据接入质量报告', shot)
        }
        const operatorInput = page.locator('.step-body input[placeholder*="操作人"]:visible').first()
        if (await operatorInput.isVisible().catch(() => false)) {
          await operatorInput.fill('自动化测试', { timeout: 2000 })
          const commitBtn = page.locator('button:has-text("开始导入"):visible').first()
          if (await commitBtn.isVisible().catch(() => false)) {
            await commitBtn.click({ timeout: 3000 })
            await page.waitForTimeout(2000)
            shot = await screenshot(page, 'ING_commit')
            recordEvidence('数据接入确认导入', shot)
          }
        }
      }
    },
  },
  {
    route: '/data-quality',
    name: '数据质量',
    abbr: 'DQ',
    checks: { mustInclude: [{ keywords: ['数据质量', '规则', '检查'], title: '数据质量核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      const scope = await getScope(page)
      const runBtn = page.locator(`${scope} button:has-text("运行"):visible, ${scope} button:has-text("检查"):visible`).first()
      if (await runBtn.isVisible().catch(() => false)) {
        await runBtn.click({ timeout: 2000 })
        await page.waitForTimeout(1200)
        const shot = await screenshot(page, 'DQ_run')
        recordEvidence('数据质量运行检查', shot)
      }
    },
  },
  // 知识资产
  {
    route: '/technology-intelligence',
    name: '技术情报',
    abbr: 'TI',
    checks: {
      mustInclude: [
        { keywords: ['技术情报', '文献列表', '知识图谱'], title: '技术情报核心板块缺失', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const search = page.locator('input[placeholder*="搜索电池材料文献"]:visible').first()
      if (await search.isVisible().catch(() => false)) {
        await search.fill('固态电解质', { timeout: 2000 })
        await search.press('Enter')
        await page.waitForTimeout(2500)
        const shot = await screenshot(page, 'TI_search')
        recordEvidence('技术情报搜索', shot)
      }
    },
  },
  {
    route: '/knowledge-graph',
    name: '知识图谱',
    abbr: 'KG',
    checks: {
      mustInclude: [
        { keywords: ['知识图谱', '节点', '关系'], title: '知识图谱核心元素缺失', severity: 'P1' },
        { keywords: ['Paper', 'Material', 'Claim'], title: '知识图谱 Paper-Material-Claim 关系未呈现', severity: 'P2' },
      ],
    },
    async custom(page, h) {
      await page.waitForTimeout(2000)
      const shot = await screenshot(page, 'KG_graph')
      recordEvidence('知识图谱可视化', shot)
    },
  },
  {
    route: '/materials',
    name: '物料规格库',
    abbr: 'MAT',
    checks: { mustInclude: [{ keywords: ['物料', '物料清单'], title: '物料规格库核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      await h.openAndFillCreate(page, '新增物料', 'MAT', '新增物料', this.evidenceRef || [])
    },
  },
  {
    route: '/properties',
    name: '属性字典',
    abbr: 'PROP',
    checks: { mustInclude: [{ keywords: ['属性', '属性字典'], title: '属性字典核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      await page.waitForTimeout(500)
      const shot = await screenshot(page, 'PROP_list')
      recordEvidence('属性字典列表', shot)
    },
  },
  {
    route: '/mdm',
    name: '主数据治理',
    abbr: 'MDM',
    checks: {
      mustInclude: [
        { keywords: ['主数据治理', '标准单位', '测试方法'], title: 'MDM 字典/单位/检测方法未呈现', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const nodes = ['标准单位', '测试方法', '特性']
      for (const title of nodes) {
        const node = page.locator(`.ant-tree-title:has-text("${title}"):visible`).first()
        if (await node.isVisible().catch(() => false)) {
          await node.click({ timeout: 2000 })
          await page.waitForTimeout(1200)
          const shot = await screenshot(page, `MDM_${title}`)
          recordEvidence(`MDM ${title}`, shot)
        }
      }
      const unitNode = page.locator('.ant-tree-title:has-text("标准单位"):visible').first()
      if (await unitNode.isVisible().catch(() => false)) {
        await unitNode.click({ timeout: 2000 })
        await page.waitForTimeout(800)
        await h.openAndFillCreate(page, '新增', 'MDM', '新增标准单位', this.evidenceRef || [])
      }
    },
  },
  // AI 与编排
  {
    route: '/research',
    name: '研发工作台',
    abbr: 'RES',
    checks: { mustInclude: [{ keywords: ['研发工作台', '研究'], title: '研发工作台核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/orchestration',
    name: '智能编排',
    abbr: 'ORCH',
    checks: {
      mustInclude: [
        { keywords: ['编排', '工作流', '任务'], title: '智能编排核心元素缺失', severity: 'P1' },
      ],
    },
  },
  {
    route: '/agents',
    name: '智能体管理',
    abbr: 'AGT',
    checks: {
      mustInclude: [
        { keywords: ['智能体', '内置智能体', '工具'], title: '智能体管理核心板块缺失', severity: 'P1' },
        { keywords: ['工具路由策略', '风险', 'SCP'], title: 'Agent 工具映射 / SCP 风险策略未呈现', severity: 'P2' },
      ],
    },
    async custom(page, h) {
      // 切换三个 tab
      for (const tabText of ['内置智能体', '自定义智能体', '模型路由']) {
        const tab = page.locator(`.ant-tabs-tab:has-text("${tabText}"):visible`).first()
        if (await tab.isVisible().catch(() => false)) {
          await tab.click({ timeout: 2000 })
          await page.waitForTimeout(800)
          const shot = await screenshot(page, `AGT_${tabText}`)
          recordEvidence(`智能体 ${tabText}`, shot)
        }
      }
      const detailBtn = page.locator('.ant-tabs-tabpane-active button:has-text("详情"):visible').first()
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click({ timeout: 2000 })
        await page.waitForTimeout(1000)
        const shot = await screenshot(page, 'AGT_detail')
        recordEvidence('智能体详情', shot)
        // 展开工具路由策略
        const collapse = page.locator('.ant-collapse-header:visible').first()
        if (await collapse.isVisible().catch(() => false)) {
          await collapse.click({ timeout: 2000 })
          await page.waitForTimeout(600)
          const shot2 = await screenshot(page, 'AGT_eligibility')
          recordEvidence('智能体工具路由策略展开', shot2)
        }
        await h.closeOverlays(page)
      }
    },
  },
  {
    route: '/tools',
    name: '工具与连接器',
    abbr: 'TOOL',
    checks: { mustInclude: [{ keywords: ['工具', '连接器'], title: '工具与连接器核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/topology',
    name: '调用关系',
    abbr: 'TOPO',
    checks: { mustInclude: [{ keywords: ['调用关系', '拓扑'], title: '调用关系核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/mappings',
    name: '映射控制台',
    abbr: 'MAP',
    checks: { mustInclude: [{ keywords: ['映射', 'Mapping'], title: '映射控制台核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/capability-center',
    name: '能力契约',
    abbr: 'CAP',
    checks: {
      mustInclude: [
        { keywords: ['能力契约', '契约总数'], title: '能力契约中心未加载', severity: 'P1' },
        { keywords: ['适用域', '回退链', '风险等级'], title: 'Capability Center 适用域/回退链/风险等级未呈现', severity: 'P1' },
      ],
    },
    async custom(page, h) {
      const detailIcon = page.locator('.ant-table-row button[aria-label="详情"]:visible').first()
      if (await detailIcon.isVisible().catch(() => false)) {
        await detailIcon.click({ timeout: 2000 })
        await page.waitForTimeout(1000)
        const shot = await screenshot(page, 'CAP_detail')
        recordEvidence('能力契约详情抽屉', shot)
        await h.closeOverlays(page)
      }
      await h.openAndFillCreate(page, '登记能力', 'CAP', '登记能力契约', this.evidenceRef || [])
    },
  },
  {
    route: '/eval-center',
    name: '评估中心',
    abbr: 'EVAL',
    checks: { mustInclude: [{ keywords: ['评估', 'Eval'], title: '评估中心核心元素缺失', severity: 'P1' }] },
  },
  // 管理
  {
    route: '/dashboard',
    name: '管理看板',
    abbr: 'DASH',
    checks: { mustInclude: [{ keywords: ['管理看板', '总览'], title: '管理看板核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/control-plane',
    name: '控制平面',
    abbr: 'CTRL',
    checks: {
      mustInclude: [
        { keywords: ['控制平面', '运行队列'], title: '控制平面核心板块缺失', severity: 'P1' },
        { keywords: ['预算', '模型连接健康'], title: '控制平面预算 / 工具网关 / 健康未呈现', severity: 'P2' },
      ],
    },
    async custom(page, h) {
      const detailBtn = page.locator('button[aria-label="查看详情"]:visible').first()
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click({ timeout: 2000 })
        await page.waitForTimeout(1000)
        const shot = await screenshot(page, 'CTRL_run_detail')
        recordEvidence('控制平面运行详情', shot)
        await h.closeOverlays(page)
      }
    },
  },
  {
    route: '/budgets',
    name: '预算看板',
    abbr: 'BUD',
    checks: { mustInclude: [{ keywords: ['预算', 'Budget'], title: '预算看板核心元素缺失', severity: 'P1' }] },
  },
  {
    route: '/value-report',
    name: '收益账单',
    abbr: 'VAL',
    checks: { mustInclude: [{ keywords: ['收益', '账单', '成本'], title: '收益账单核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      const select = page.locator('.ant-select:visible').first()
      if (await select.isVisible().catch(() => false)) {
        await select.click({ timeout: 2000 })
        await page.waitForTimeout(500)
        const opt = page.locator('.ant-select-item-option-content').first()
        if (await opt.isVisible().catch(() => false)) {
          await opt.click({ timeout: 2000 })
          await page.waitForTimeout(1500)
          const shot = await screenshot(page, 'VAL_project')
          recordEvidence('收益账单选择项目', shot)
        }
      }
    },
  },
  {
    route: '/users',
    name: '用户管理',
    abbr: 'USR',
    checks: { mustInclude: [{ keywords: ['用户', '角色'], title: '用户管理核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      // 仅验证新增入口存在，不实际创建用户，避免污染账号体系
      const scope = await getScope(page)
      const addBtn = page.locator(`${scope} button:has-text("新增"):visible, ${scope} button:has-text("新建"):visible`).first()
      if (await addBtn.isVisible().catch(() => false)) {
        await addBtn.click({ timeout: 2000 })
        await page.waitForTimeout(600)
        const shot = await screenshot(page, 'USR_add_modal')
        recordEvidence('用户新增弹窗（未提交）', shot)
        await h.closeOverlays(page)
      }
    },
  },
  {
    route: '/settings',
    name: '系统设置',
    abbr: 'SET',
    checks: { mustInclude: [{ keywords: ['设置', '系统'], title: '系统设置核心元素缺失', severity: 'P1' }] },
    async custom(page, h) {
      const scope = await getScope(page)
      const saveBtn = page.locator(`${scope} button:has-text("保存"):visible`).first()
      if (await saveBtn.isVisible().catch(() => false)) {
        // 仅点击保存做只读验证，不修改配置
        await saveBtn.click({ timeout: 2000 })
        await page.waitForTimeout(800)
        const shot = await screenshot(page, 'SET_save_click')
        recordEvidence('系统设置保存按钮点击（只读验证）', shot)
      }
    },
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────────────────────────────────
async function main() {
  console.log('正在认证...')
  let auth
  try {
    auth = await authenticate()
    console.log(`认证成功: ${auth.userId} / ${auth.role}`)
  } catch (e) {
    console.error('认证失败，尝试使用本地 token 继续:', e.message)
    auth = { userId: 'admin', token: 'admin-token-placeholder', role: 'admin' }
  }

  console.log('启动 Chromium...')
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  })
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
  const page = await ctx.newPage()

  // 全局阻止确认删除类弹窗
  page.on('dialog', async (dialog) => {
    await dialog.dismiss()
  })

  // 写入登录态
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 20000 })
  await page.evaluate(
    ({ userId, token, role }) => {
      localStorage.setItem('userId', userId)
      localStorage.setItem('authToken', token)
      localStorage.setItem('userRole', role)
    },
    auth,
  )
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 20000 })
  await waitLoaded(page, 2000)

  const homeShot = await screenshot(page, 'home_auth')
  recordEvidence('登录后首页', homeShot)

  const summaries = []
  for (const p of PAGES) {
    console.log(`正在测评: ${p.route} (${p.name})`)
    const summary = await reviewPage(page, p.route, p.name, p.abbr, p.checks, p.custom ? p.custom.bind(p) : undefined)
    summaries.push(summary)
    // 每个页面之间稍微停顿，减少后端压力
    await page.waitForTimeout(500)
  }

  await browser.close()

  // 生成报告
  generateReport(summaries)
  console.log(`\n完成。报告: ${REPORT_PATH}`)
  console.log(`截图目录: ${SCREEN_DIR}`)
  console.log(`缺陷统计 -> P0:${countSeverity('P0')} P1:${countSeverity('P1')} P2:${countSeverity('P2')} P3:${countSeverity('P3')}`)
}

function countSeverity(sev) {
  return findings.filter((f) => f.severity === sev).length
}

function generateReport(summaries) {
  const now = new Date().toLocaleString('zh-CN', { hour12: false })
  const totalPages = PAGES.length
  const successPages = summaries.filter((s) => s.status !== 'load_failed').length
  const lines = []
  lines.push('# BatteryEMCL Lab 数据 / 知识 / AI / 管理模块 Playwright 实操评测报告')
  lines.push('')
  lines.push(`- 测评时间：${now}`)
  lines.push(`- 前端地址：${BASE}`)
  lines.push(`- 后端地址：${API_BASE}`)
  lines.push(`- 浏览器：Chromium headless，viewport 1920×1080`)
  lines.push(`- 登录角色：admin`)
  lines.push('')
  lines.push('## 1. 执行摘要')
  lines.push('')
  lines.push(`| 指标 | 数值 |`)
  lines.push(`|---|---|`)
  lines.push(`| 覆盖页面数 | ${totalPages} |`)
  lines.push(`| 成功加载页面 | ${successPages} |`)
  lines.push(`| 加载失败页面 | ${totalPages - successPages} |`)
  lines.push(`| 截图证据数 | ${evidenceList.length} |`)
  lines.push(`| 缺陷总数 | ${findings.length} |`)
  lines.push(`| **P0** | ${countSeverity('P0')} |`)
  lines.push(`| **P1** | ${countSeverity('P1')} |`)
  lines.push(`| **P2** | ${countSeverity('P2')} |`)
  lines.push(`| **P3** | ${countSeverity('P3')} |`)
  lines.push('')
  lines.push('## 2. 缺陷清单')
  lines.push('')
  if (findings.length === 0) {
    lines.push('本次自动化遍历未检测到缺陷。')
    lines.push('')
  } else {
    lines.push(`| 编号 | 严重度 | 模块 | 页面 | 标题 | 描述 | 证据 |`)
    lines.push(`|---|---|---|---|---|---|---|`)
    for (const f of findings) {
      const evLinks = f.evidence.map((id) => `[${id}]`).join(' ')
      lines.push(`| ${f.id} | ${f.severity} | ${f.module} | ${f.route} | ${f.title} | ${f.description.replace(/\|/g, '\\|')} | ${evLinks} |`)
    }
    lines.push('')
  }
  lines.push('## 3. 页面执行明细')
  lines.push('')
  for (const s of summaries) {
    lines.push(`### ${s.route} — ${s.name}`)
    lines.push('')
    lines.push(`- 状态：${s.status === 'load_failed' ? '加载失败' : '已加载并交互'}`)
    lines.push(`- 模块缩写：${s.abbr}`)
    const pageFindings = findings.filter((f) => f.route === s.route)
    lines.push(`- 本页缺陷：${pageFindings.length} 个`)
    if (pageFindings.length) {
      lines.push(`  - ${pageFindings.map((f) => `${f.id}（${f.severity}）`).join('、')}`)
    }
    lines.push('')
    const pageEvidence = evidenceList.filter((e) => e.screenshot.includes(`/${s.abbr}_`) || e.label.includes(s.name))
    lines.push(`| 证据编号 | 说明 | 截图 |`)
    lines.push(`|---|---|---|`)
    for (const e of pageEvidence.slice(0, 80)) {
      lines.push(`| ${e.id} | ${e.label} | ${e.screenshot} |`)
    }
    lines.push('')
  }
  lines.push('## 4. 待确认项')
  lines.push('')
  lines.push('- 技术情报 / 知识图谱的 Paper-Material-Claim 关系依赖图谱节点标签，若节点类型未在 DOM 文本中展示，则标记为[待确认]。')
  lines.push('- Agent SCP 风险策略若未在“工具路由策略”中显式出现，则标记为[待确认]。')
  lines.push('- 部分表单的创建结果以服务端校验为准，前端未提示成功不代表接口失败。')
  lines.push('')
  lines.push('## 5. 交付物')
  lines.push('')
  lines.push(`- Playwright 脚本：frontend/scripts/pw_data_ai_review.js`)
  lines.push(`- 运行结果报告：doc/review_data_ai_playwright.md`)
  lines.push(`- 截图目录：frontend/screenshots/pw_data_ai/`)
  lines.push('')

  fs.writeFileSync(REPORT_PATH, lines.join('\n'), 'utf-8')
}

main().catch((e) => {
  console.error('脚本执行失败:', e)
  process.exit(1)
})
