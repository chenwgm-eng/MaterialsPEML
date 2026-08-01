import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

const BASE_URL = 'http://localhost:5173'
const API_URL = 'http://localhost:8000'
const SCREEN_DIR = path.resolve('screenshots', 'capability')
if (!fs.existsSync(SCREEN_DIR)) fs.mkdirSync(SCREEN_DIR, { recursive: true })

const issues = []
let screenshotIndex = 0
let registeredCapabilityId = null

function addIssue(category, title, steps, expected, actual, severity = '中') {
  const issue = {
    id: issues.length + 1,
    category,
    title,
    steps,
    expected,
    actual,
    severity,
    screenshot: null,
  }
  issues.push(issue)
  console.log(`  [问题] #${issue.id} [${severity}] [${category}] ${title}`)
  console.log(`    预期：${expected}`)
  console.log(`    实际：${actual}`)
  return issue
}

function attachScreenshot(issue, screenshotPath) {
  if (issue && screenshotPath) {
    issue.screenshot = screenshotPath
    console.log(`  [截图] 已关联到问题 #${issue.id}: ${screenshotPath}`)
  }
}

async function screenshot(page, name) {
  screenshotIndex++
  const file = path.join(SCREEN_DIR, `${String(screenshotIndex).padStart(2, '0')}_${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  console.log(`  [截图] ${file}`)
  return file
}

async function waitForNoSpin(page, timeout = 5000) {
  try { await page.waitForSelector('.ant-spin-dot', { state: 'hidden', timeout }) } catch {}
}

async function closeNotifications(page) {
  const closeBtns = await page.locator('.ant-notification-notice-close').all()
  for (const btn of closeBtns) { try { await btn.click() } catch {} }
  await page.waitForTimeout(300)
}

async function dismissModals(page) {
  // 关闭可见的确认弹窗（例如「确认放弃未保存的修改？」），优先点击主按钮（"放弃"/"确定"）
  try {
    const primaryBtn = page.locator('.ant-modal-confirm-btns button.ant-btn-primary').first()
    if (await primaryBtn.isVisible().catch(() => false)) {
      await primaryBtn.click().catch(() => {})
      await page.waitForTimeout(300)
      return true
    }
  } catch {}
  // 兜底：按 Escape 关闭任意弹窗
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(200)
  return false
}

async function apiLogin() {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  if (!res.ok) throw new Error(`Login failed: ${res.status}`)
  return await res.json()
}

async function initBrowser() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  page.on('pageerror', err => console.log('PAGEERROR:', err.message))
  page.on('request', req => {
    if (req.url().includes('/capabilities') && req.method() === 'POST') {
      console.log('API REQUEST:', req.method(), req.url())
    }
  })
  page.on('response', resp => {
    if (resp.url().includes('/capabilities') && resp.request().method() === 'POST') {
      console.log('API RESPONSE:', resp.status(), resp.url())
    }
    if (!resp.ok() && resp.url().includes('/api')) {
      console.log('API ERROR:', resp.status(), resp.url())
    }
  })
  page.on('crash', () => console.log('PAGE CRASH'))
  return { browser, page }
}

async function setAuth(page, auth) {
  await page.goto(`${BASE_URL}/`)
  await page.waitForTimeout(1000)
  await page.evaluate((data) => {
    localStorage.setItem('authToken', data.token)
    localStorage.setItem('userId', data.user_id)
    localStorage.setItem('userRole', data.role)
  }, auth)
}

async function setRole(page, auth, role) {
  await page.evaluate((data) => {
    localStorage.setItem('authToken', data.token)
    localStorage.setItem('userId', data.user_id)
    localStorage.setItem('userRole', data.role)
  }, { ...auth, role })
}

async function clearAuth(page) {
  await page.evaluate(() => {
    localStorage.removeItem('authToken')
    localStorage.removeItem('userId')
    localStorage.removeItem('userRole')
  })
}

async function runStep(name, fn) {
  console.log(`\n[步骤开始] ${name}`)
  try {
    await fn()
    console.log(`[步骤完成] ${name}`)
  } catch (err) {
    console.log(`[步骤失败] ${name}: ${err.message}`)
    throw err
  }
}

async function testPageLoad(page) {
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(2000)
  await closeNotifications(page)
  await waitForNoSpin(page)
  await screenshot(page, 'capability_center_initial')

  const title = await page.title().catch(() => '')
  if (!title.includes('能力契约')) {
    addIssue('UI/UX 问题', '页面标题未正确显示', '访问能力契约页面', '标题包含能力契约', `标题：${title}`, '低')
  }

  const statLabels = await page.locator('.stat-label').allTextContents()
  const expectedLabels = ['契约总数', '活跃', '待审批', '高风险']
  for (const label of expectedLabels) {
    if (!statLabels.includes(label)) {
      addIssue('UI/UX 问题', `统计条缺少「${label}」`, '进入能力契约中心页面', `显示${expectedLabels.join('、')}`, `实际显示：${statLabels.join('、')}`, '中')
    }
  }

  const columns = await page.locator('.ant-table-thead th').allTextContents()
  const expectedColumns = ['名称', '提供方', '版本', '风险等级', '状态', '不确定性方法', '负责人', '操作']
  for (const col of expectedColumns) {
    if (!columns.some(c => c.includes(col))) {
      addIssue('UI/UX 问题', `表格缺少「${col}」列`, '进入能力契约中心页面', `显示${expectedColumns.join('、')}`, `实际列：${columns.join('、')}`, '中')
    }
  }

  const totalText = await page.locator('.stat-row .stat-item:first-child .stat-value').textContent().catch(() => '0')
  const totalCount = parseInt(totalText, 10) || 0
  const paginationTotalText = await page.locator('.ant-pagination-total-text').textContent().catch(() => '')
  const paginationMatch = paginationTotalText.match(/共\s*(\d+)\s*条/)
  const paginationTotal = paginationMatch ? parseInt(paginationMatch[1], 10) : -1
  if (paginationTotal >= 0 && totalCount !== paginationTotal) {
    addIssue('数据一致性问题', '统计条「契约总数」与分页总数不一致', '对比统计条数字与分页总数', `总数=${totalCount}，分页=${paginationTotal}`, `总数=${totalCount}，分页=${paginationTotal}`, '中')
  }
}

async function testFilters(page) {
  const rowsBefore = await page.locator('.ant-table-tbody tr.ant-table-row').count()

  // risk level filter
  await page.locator('.filter-bar .ant-select').nth(1).click()
  await page.waitForTimeout(300)
  await page.locator('.ant-select-item-option:has-text("高")').first().click()
  await page.waitForTimeout(300)
  await page.locator('button:has-text("查询")').first().click()
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await screenshot(page, 'filter_risk_high')
  const riskTags = await page.locator('.ant-table-tbody tr.ant-table-row td:nth-child(4) .ant-tag').allTextContents()
  for (const tag of riskTags) {
    if (!tag.includes('高')) {
      addIssue('功能缺陷', '风险等级过滤未生效', '选择风险等级「高」并查询', '仅显示高风险记录', `出现非高风险标签：${tag}`, '高')
      break
    }
  }

  // reset
  await page.locator('button:has-text("重置")').first().click()
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await screenshot(page, 'filter_reset')
  const rowsAfterReset = await page.locator('.ant-table-tbody tr.ant-table-row').count()
  if (rowsAfterReset !== rowsBefore) {
    addIssue('功能缺陷', '重置过滤后数据未恢复', '先过滤再点击重置', `恢复${rowsBefore}行`, `实际${rowsAfterReset}行`, '中')
  }

  // keyword search: 后端 q 参数在 capability_id / name / provider / owner 多字段上检索
  const firstName = await page.locator('.ant-table-tbody tr.ant-table-row:first-child td:nth-child(1) .name-text').textContent().catch(() => '')
  const keyword = firstName && firstName !== '-' ? firstName.slice(0, 3) : ''
  if (keyword) {
    const kwInput = page.locator('.filter-bar .ant-input').first()
    await kwInput.fill(keyword)
    await kwInput.press('Enter')
    await page.waitForTimeout(1000)
    await waitForNoSpin(page)
    await screenshot(page, 'keyword_search')
    // 后端 q 在 capability_id/name/provider/owner 上匹配；校验每条返回记录至少在一个字段上包含关键词
    const searchedRows = page.locator('.ant-table-tbody tr.ant-table-row')
    const searchedCount = await searchedRows.count()
    if (searchedCount === 0) {
      addIssue('功能缺陷', '关键词搜索无结果', `搜索「${keyword}」`, '至少返回 1 条匹配记录', '无结果', '中')
    } else {
      for (let i = 0; i < searchedCount; i++) {
        const row = searchedRows.nth(i)
        // capability_id 渲染在第一列作为副标题（.id-text），所以同时取整格文本
        const nameCellText = await row.locator('td:nth-child(1)').textContent().catch(() => '')
        const name = await row.locator('td:nth-child(1) .name-text').textContent().catch(() => '')
        const provider = await row.locator('td:nth-child(2)').textContent().catch(() => '')
        const owner = await row.locator('td:nth-child(7)').textContent().catch(() => '')
        const matched = [name, nameCellText, provider, owner].some(t => (t || '').includes(keyword))
        if (!matched) {
          addIssue('功能缺陷', '关键词搜索结果存在不匹配记录', `搜索「${keyword}」`, '每条记录的 capability_id/name/provider/owner 至少有一个包含关键词', `记录不匹配：name=${name}, provider=${provider}, owner=${owner}`, '中')
          break
        }
      }
    }
  }

  await page.locator('button:has-text("重置")').first().click()
  await page.waitForTimeout(500)
}

async function testDetailDrawer(page) {
  // 关键词搜索可能过滤了列表，进入详情抽屉前先重置过滤并等待表格行加载
  await page.locator('button:has-text("重置")').first().click().catch(() => {})
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await page.locator('.ant-table-tbody tr.ant-table-row').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})

  const firstRow = page.locator('.ant-table-tbody tr.ant-table-row').first()
  if (!(await firstRow.isVisible().catch(() => false))) {
    addIssue('其他', '能力契约列表为空，无法测试详情抽屉', '进入能力契约中心', '有数据', '无数据', '中')
    return
  }
  await firstRow.click()
  await page.waitForTimeout(1000)
  await screenshot(page, 'detail_drawer')

  const title = await page.locator('.ant-drawer-title').textContent().catch(() => '')
  if (!title.includes('模型卡')) {
    addIssue('UI/UX 问题', '详情抽屉标题不符合预期', '点击表格行', '标题包含「模型卡」', `标题：${title}`, '低')
  }

  const labels = ['能力 ID', '名称', '提供方', '版本', '风险等级', '状态', '时延 SLA', '不确定性方法', 'OOD 方法', '验证数据集', '负责人', '许可证', '登记来源', '更新时间']
  const drawerText = await page.locator('.ant-drawer-body').textContent().catch(() => '')
  for (const label of labels) {
    if (!drawerText.includes(label)) {
      addIssue('UI/UX 问题', `详情抽屉缺少「${label}」字段`, '打开详情抽屉', `显示${label}`, '未显示', '中')
    }
  }

  // fallback chain jump
  const chainNodes = await page.locator('.fallback-node.clickable').all()
  if (chainNodes.length) {
    const nodeText = await chainNodes[0].textContent()
    await chainNodes[0].click()
    await page.waitForTimeout(800)
    await screenshot(page, 'detail_drawer_jump')
    const newTitle = await page.locator('.ant-drawer-title').textContent().catch(() => '')
    if (!newTitle || newTitle === title) {
      addIssue('功能缺陷', '回退链节点点击无法跳转', '在详情抽屉点击回退链节点', '跳转到该能力详情', '标题未变化', '中')
    }
  }

  await page.locator('.ant-drawer-close').click().catch(() => {})
  await page.waitForTimeout(300)
}

async function testRegister(page) {
  await page.locator('button:has-text("登记能力")').first().click()
  // 等待登记抽屉标题文本出现（之前步骤的详情抽屉可能仍在 DOM 中，
  // 用 :has-text 精确匹配，避免取到旧 drawer 的空标题）
  await page.waitForSelector('.ant-drawer-title:has-text("登记能力契约")', { state: 'visible', timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(300)
  await screenshot(page, 'register_drawer_open')

  // 使用 .last() 取最新打开的抽屉标题，避免匹配到已关闭但仍在 DOM 中的旧 drawer
  const drawerTitle = await page.locator('.ant-drawer-title').last().textContent().catch(() => '')
  if (!drawerTitle.includes('登记能力契约')) {
    addIssue('UI/UX 问题', '登记抽屉标题不符合预期', '点击「登记能力」按钮打开抽屉', '标题包含「登记能力契约」', `标题：${drawerTitle}`, '低')
  }

  const saveBtn = page.locator('.ant-drawer-footer button.ant-btn-primary, .ant-drawer-footer button:has-text("保存")').first()
  // empty id validation
  await saveBtn.click()
  await page.waitForTimeout(300)
  await screenshot(page, 'register_empty_id')
  const warningCount = await page.locator('.ant-message-notice:has-text("请填写能力 ID")').count()
  if (warningCount === 0) {
    addIssue('功能缺陷', '能力 ID 为空时未提示必填', '打开登记抽屉并直接点击保存', '提示「请填写能力 ID」', '无提示或提示错误', '高')
  }

  const testId = `test_cap_${Date.now()}`
  registeredCapabilityId = testId
  const inputs = await page.locator('.ant-drawer-body .ant-input').all()
  if (inputs.length >= 8) {
    await inputs[0].fill(testId)
    await inputs[1].fill('测试能力')
    await inputs[2].fill('test-provider')
    await inputs[3].fill('v1.0')
    await inputs[4].fill('P95 < 60s')
    // inputs[5] validation_dataset, inputs[6] owner, inputs[7] license
    await inputs[5].fill('test-validation-set')
    await inputs[6].fill('test-owner')
    await inputs[7].fill('MIT')
  }

  // tags inputs for supported_domains and limitations
  try {
    const domainSelect = page.locator('.ant-form-item:has-text("适用域") .ant-select').first()
    await domainSelect.locator('input').fill('battery')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(200)
  } catch {}

  // invalid JSON
  const textareas = await page.locator('.ant-drawer-body textarea').all()
  if (textareas.length >= 3) {
    await textareas[0].fill('{invalid json}')
    await saveBtn.click()
    await page.waitForTimeout(800)
    await screenshot(page, 'register_invalid_json')
    const jsonErrorCount = await page.locator('.ant-message-notice:has-text("不是合法 JSON")').count()
    if (jsonErrorCount === 0) {
      addIssue('功能缺陷', '输入非法 JSON 时未给出明确提示', '在输入 Schema 输入 {invalid json} 并保存', '提示「输入 Schema 不是合法 JSON」', '无明确 JSON 错误提示', '中')
    }

    await textareas[0].fill('{"smiles": "SMILES 字符串"}')
    await textareas[1].fill('{"score": "预测分数"}')
    await textareas[2].fill('{"unit": "次", "price": 0.1}')
  }
  await screenshot(page, 'register_filled')

  // 捕获登记请求的 API 响应，便于在失败时记录错误信息
  const registerResponsePromise = page.waitForResponse(
    resp => resp.url().includes('/capabilities') && resp.request().method() === 'POST',
    { timeout: 8000 }
  ).catch(() => null)
  await saveBtn.click()
  const registerResponse = await registerResponsePromise
  let registerApiError = null
  if (registerResponse) {
    const status = registerResponse.status()
    if (status >= 400) {
      registerApiError = `HTTP ${status}`
      try {
        const body = await registerResponse.json()
        if (body && body.detail) registerApiError += `: ${JSON.stringify(body.detail)}`
      } catch {}
    }
  }
  await page.waitForTimeout(2000)
  await screenshot(page, 'register_submit')
  await closeNotifications(page)

  const successCount = await page.locator('.ant-message-notice:has-text("登记成功")').count()
  // refresh table and verify
  await page.locator('button:has-text("刷新")').first().click()
  await page.waitForTimeout(1500)
  await waitForNoSpin(page)
  await screenshot(page, 'register_refresh')
  const rowVisible = await page.locator(`.ant-table-tbody tr:has-text("${testId}")`).count()
  if (successCount === 0 && rowVisible === 0) {
    addIssue('功能缺陷', '登记能力契约后未成功新增记录', '填写完整表单并提交', '提示成功并在表格新增待审批记录', `未看到成功提示或新增记录${registerApiError ? `；API 错误：${registerApiError}` : ''}`, '高')
  }

  // duplicate id
  await page.locator('button:has-text("登记能力")').first().click()
  await page.waitForTimeout(800)
  const inputs2 = await page.locator('.ant-drawer-body .ant-input').all()
  if (inputs2.length) await inputs2[0].fill(testId)
  const saveBtn2 = page.locator('.ant-drawer-footer button.ant-btn-primary, .ant-drawer-footer button:has-text("保存")').first()
  await saveBtn2.click()
  await page.waitForTimeout(800)
  await closeNotifications(page)
  await screenshot(page, 'register_duplicate')
  // 直接刷新页面关闭所有抽屉和弹窗，避免 dirty 表单确认弹窗阻塞后续步骤
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)
}

async function testApproveAndDeprecate(page, auth) {
  await setRole(page, auth, 'admin')
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)

  await page.locator('button:has-text("重置")').first().click()
  await page.waitForTimeout(500)

  if (!registeredCapabilityId) {
    addIssue('其他', '未记录新登记的能力 ID，无法定向测试审批/废止', '登记能力后', '已保存 capability_id', '未保存', '中')
    return
  }

  // filter by newly registered capability id to find the pending row
  const kwInput = page.locator('.filter-bar .ant-input').first()
  await kwInput.fill(registeredCapabilityId)
  await kwInput.press('Enter')
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await screenshot(page, 'filter_new_capability')

  const targetRow = page.locator(`.ant-table-tbody tr.ant-table-row:has-text("${registeredCapabilityId}")`)
  const targetCount = await targetRow.count()
  if (targetCount === 0) {
    addIssue('功能缺陷', '新登记的能力未在表格中显示', `搜索能力 ID ${registeredCapabilityId}`, '能找到新记录', '未找到', '高')
    return
  }

  const approveBtn = targetRow.locator('button[aria-label="审批"]').first()
  if (!(await approveBtn.isVisible().catch(() => false))) {
    const issue = addIssue('UI/UX 问题', '新记录行未显示审批按钮', `查找能力 ${registeredCapabilityId}`, '显示审批按钮', '未显示审批按钮', '高')
    const file = await screenshot(page, 'new_row_no_approve')
    attachScreenshot(issue, file)
  } else {
    await approveBtn.click()
    await page.waitForTimeout(1000)
    await closeNotifications(page)
    await screenshot(page, 'after_approve')

    const statusTag = targetRow.locator('td:nth-child(5) .ant-tag').first()
    const status = await statusTag.textContent().catch(() => '')
    if (!status.includes('活跃')) {
      const issue = addIssue('功能缺陷', '审批后状态未变为活跃', '点击新记录的审批按钮', '状态变为活跃', `状态为：${status}`, '高')
      const file = await screenshot(page, 'approve_status_not_active')
      attachScreenshot(issue, file)
    }
  }

  // deprecate the same active record
  await page.locator('button:has-text("重置")').first().click()
  await page.waitForTimeout(500)
  await kwInput.fill(registeredCapabilityId)
  await kwInput.press('Enter')
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await screenshot(page, 'filter_new_capability_active')

  const activeRow = page.locator(`.ant-table-tbody tr.ant-table-row:has-text("${registeredCapabilityId}")`)
  if (await activeRow.count() === 0) {
    addIssue('功能缺陷', '审批后无法找到该能力记录以测试废止', `搜索能力 ${registeredCapabilityId}`, '能找到记录', '未找到', '高')
    return
  }

  const deprecateBtn = activeRow.locator('button[aria-label="废止"]').first()
  if (!(await deprecateBtn.isVisible().catch(() => false))) {
    const issue = addIssue('UI/UX 问题', '活跃记录行未显示废止按钮', `查找能力 ${registeredCapabilityId}`, '显示废止按钮', '未显示废止按钮', '高')
    const file = await screenshot(page, 'active_row_no_deprecate')
    attachScreenshot(issue, file)
  } else {
    await deprecateBtn.click()
    await page.waitForTimeout(500)
    await page.locator('.ant-modal-confirm-btns button:has-text("确认废止")').click()
    await page.waitForTimeout(1000)
    await closeNotifications(page)
    await screenshot(page, 'after_deprecate')

    const statusTag = activeRow.locator('td:nth-child(5) .ant-tag').first()
    const status = await statusTag.textContent().catch(() => '')
    if (!status.includes('已废止')) {
      const issue = addIssue('功能缺陷', '废止后状态未变为已废止', '点击活跃记录的废止按钮并确认', '状态变为已废止', `状态为：${status}`, '高')
      const file = await screenshot(page, 'deprecate_status_not_deprecated')
      attachScreenshot(issue, file)
    }
  }
}

async function testEdit(page) {
  // 重新加载页面以确保抽屉/弹窗全部关闭，避免上一个步骤残留的 drawer 拦截点击
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)

  // 等待表格首行可见且稳定
  await page.locator('.ant-table-tbody tr.ant-table-row').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})

  const firstRow = page.locator('.ant-table-tbody tr.ant-table-row').first()
  if (!(await firstRow.isVisible().catch(() => false))) {
    addIssue('其他', '能力契约列表为空，无法测试编辑', '进入能力契约中心', '有数据', '无数据', '中')
    return
  }

  const editBtn = firstRow.locator('button[aria-label="编辑"]').first()
  if (!(await editBtn.isVisible().catch(() => false))) {
    const issue = addIssue('UI/UX 问题', '表格行未显示编辑按钮', '查看表格行操作列', '显示编辑按钮', '未显示编辑按钮', '中')
    const file = await screenshot(page, 'no_edit_button')
    attachScreenshot(issue, file)
    return
  }

  // 关闭可能残留的确认弹窗，并将目标行滚动到视口中部，避免被顶部过滤栏遮挡
  await dismissModals(page)
  await firstRow.scrollIntoViewIfNeeded().catch(() => {})
  await page.waitForTimeout(200)
  // 使用 force: true 绕过 pointer-events 拦截检查（按钮已确认可见）
  await editBtn.click({ force: true })
  // 等待编辑抽屉标题文本出现
  await page.waitForSelector('.ant-drawer-title:has-text("编辑能力契约")', { state: 'visible', timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(300)
  await screenshot(page, 'edit_drawer_open')

  const drawerTitle = await page.locator('.ant-drawer-title').last().textContent().catch(() => '')
  if (!drawerTitle.includes('编辑能力契约')) {
    addIssue('UI/UX 问题', '编辑抽屉标题不符合预期', '点击编辑按钮打开抽屉', '标题包含「编辑能力契约」', `标题：${drawerTitle}`, '中')
  }

  // verify form is pre-filled: name and provider inputs should have values
  const inputs = await page.locator('.ant-drawer-body .ant-input').all()
  let prefillOk = false
  if (inputs.length >= 3) {
    const nameValue = await inputs[1].inputValue().catch(() => '')
    const providerValue = await inputs[2].inputValue().catch(() => '')
    if (nameValue && providerValue) {
      prefillOk = true
    }
  }
  if (!prefillOk) {
    addIssue('功能缺陷', '编辑抽屉表单未预填充', '点击编辑按钮打开抽屉', '名称和提供方字段已填充', '关键字段为空', '中')
  }

  // verify submit button text is "保存修改" in edit mode
  const saveBtnText = await page.locator('.ant-drawer-footer button.ant-btn-primary').first().textContent().catch(() => '')
  if (saveBtnText && !saveBtnText.includes('保存修改')) {
    addIssue('UI/UX 问题', '编辑模式保存按钮文案不符合预期', '打开编辑抽屉查看底部按钮', '按钮文案包含「保存修改」', `文案：${saveBtnText}`, '低')
  }

  await page.locator('.ant-drawer-close').click().catch(() => {})
  await page.waitForTimeout(300)
}

async function testDelete(page) {
  if (!registeredCapabilityId) {
    addIssue('其他', '未记录新登记的能力 ID，无法测试删除', '登记能力后', '已保存 capability_id', '未保存', '中')
    return
  }

  // ensure admin role so delete is available
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)

  // filter to find the test row
  const kwInput = page.locator('.filter-bar .ant-input').first()
  await kwInput.fill(registeredCapabilityId)
  await kwInput.press('Enter')
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)
  await screenshot(page, 'delete_filter_target')

  const targetRow = page.locator(`.ant-table-tbody tr.ant-table-row:has-text("${registeredCapabilityId}")`)
  if (await targetRow.count() === 0) {
    addIssue('功能缺陷', '无法找到测试记录以测试删除', `搜索能力 ID ${registeredCapabilityId}`, '能找到记录', '未找到', '高')
    return
  }

  const deleteBtn = targetRow.locator('button[aria-label="删除"]').first()
  if (!(await deleteBtn.isVisible().catch(() => false))) {
    const issue = addIssue('UI/UX 问题', '行未显示删除按钮', `查找能力 ${registeredCapabilityId}`, '显示删除按钮', '未显示删除按钮', '高')
    const file = await screenshot(page, 'no_delete_button')
    attachScreenshot(issue, file)
    return
  }

  await deleteBtn.click()
  await page.waitForTimeout(500)
  await screenshot(page, 'delete_confirm_modal')

  // confirm the modal: try common confirm button patterns
  const confirmBtn = page.locator(
    '.ant-modal-confirm-btns button:has-text("确认删除"), ' +
    '.ant-popconfirm button:has-text("确认删除"), ' +
    '.ant-modal-confirm-btns button:has-text("确定"), ' +
    '.ant-popconfirm-buttons button.ant-popover-buttons-confirm, ' +
    '.ant-modal-confirm-btns button.ant-btn-primary'
  ).first()
  await confirmBtn.click().catch(() => {})
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await screenshot(page, 'after_delete')

  // verify the row disappears
  await kwInput.fill(registeredCapabilityId)
  await kwInput.press('Enter')
  await page.waitForTimeout(1000)
  await waitForNoSpin(page)

  const rowCount = await page.locator(`.ant-table-tbody tr.ant-table-row:has-text("${registeredCapabilityId}")`).count()
  if (rowCount > 0) {
    const issue = addIssue('功能缺陷', '删除后记录仍在列表中', `删除能力 ${registeredCapabilityId}`, '记录消失', `仍有 ${rowCount} 条记录`, '高')
    const file = await screenshot(page, 'delete_failed')
    attachScreenshot(issue, file)
  }

  // reset filter
  await page.locator('button:has-text("重置")').first().click()
  await page.waitForTimeout(500)

  // mark cleanup done so later steps know the test row is gone
  registeredCapabilityId = null
}

async function testPermission(page, auth) {
  // ensure admin role and check the page is accessible
  await setRole(page, auth, 'admin')
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)
  await screenshot(page, 'capability_admin')

  const adminPath = new URL(page.url()).pathname
  if (adminPath !== '/capability-center') {
    addIssue('权限安全问题', 'admin 角色无法访问能力契约页面', '设置 userRole=admin 后访问 /capability-center', '可正常访问', `被重定向到 ${adminPath}`, '高')
    return
  }

  const registerBtnVisible = await page.locator('button:has-text("登记能力")').first().isVisible().catch(() => false)
  if (!registerBtnVisible) {
    addIssue('UI/UX 问题', 'admin 角色未显示「登记能力」按钮', 'admin 登录后查看能力契约中心', '显示登记能力按钮', '未显示', '高')
  }

  // test unauthenticated access: router should redirect to '/'
  await clearAuth(page)
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await screenshot(page, 'capability_without_login')

  const unauthPath = new URL(page.url()).pathname
  if (unauthPath !== '/') {
    addIssue('权限安全问题', '未登录用户未重定向到首页', '退出登录后访问 /capability-center', '重定向到 /', `被重定向到 ${unauthPath}`, '高')
  }

  // viewer role: viewer < admin, should also be redirected to '/'
  await setRole(page, auth, 'viewer')
  await page.goto(`${BASE_URL}/capability-center`)
  await page.waitForTimeout(1500)
  await closeNotifications(page)
  await waitForNoSpin(page)
  await screenshot(page, 'capability_viewer')

  const viewerPath = new URL(page.url()).pathname
  if (viewerPath !== '/') {
    addIssue('权限安全问题', 'viewer 角色未重定向到首页', '设置 userRole=viewer 后访问 /capability-center', '重定向到 /', `被重定向到 ${viewerPath}`, '高')
  }
}

async function main() {
  const auth = await apiLogin()
  console.log('API login ok, user:', auth.user_id, 'role:', auth.role)

  const { browser, page } = await initBrowser()
  await setAuth(page, auth)

  function stepTestPageLoad() { return testPageLoad(page) }
  function stepTestFilters() { return testFilters(page) }
  function stepTestDetailDrawer() { return testDetailDrawer(page) }
  function stepTestRegister() { return testRegister(page) }
  function stepTestEdit() { return testEdit(page) }
  function stepTestApproveAndDeprecate() { return testApproveAndDeprecate(page, auth) }
  function stepTestDelete() { return testDelete(page) }
  function stepTestPermission() { return testPermission(page, auth) }

  const steps = [
    stepTestPageLoad,
    stepTestFilters,
    stepTestDetailDrawer,
    stepTestRegister,
    stepTestEdit,
    stepTestApproveAndDeprecate,
    stepTestDelete,
    stepTestPermission,
  ]

  for (const step of steps) {
    try {
      await runStep(step.name, step)
    } catch (err) {
      const issue = addIssue('其他', `测试步骤异常：${step.name}`, '自动化测试过程中', '正常完成', `异常：${err.message}`, '高')
      const file = await screenshot(page, `exception_${step.name}`)
      attachScreenshot(issue, file)
      console.error(err)
      // close any open drawer to unblock following steps
      await page.locator('.ant-drawer-close').click().catch(() => {})
      await page.keyboard.press('Escape').catch(() => {})
      await page.waitForTimeout(300)
    }
  }

  const reportPath = path.join(SCREEN_DIR, 'report.json')
  fs.writeFileSync(reportPath, JSON.stringify({ issues, screenshotDir: SCREEN_DIR }, null, 2))
  console.log(`\n测试完成。发现 ${issues.length} 个问题。`)
  console.log(`截图目录：${SCREEN_DIR}`)
  console.log(`报告文件：${reportPath}`)
  if (issues.length) {
    console.log('\n问题列表：')
    for (const issue of issues) {
      console.log(`[${issue.severity}] ${issue.id}. [${issue.category}] ${issue.title}`)
      if (issue.screenshot) {
        console.log(`  截图：${issue.screenshot}`)
      }
    }
  }

  await browser.close()
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
