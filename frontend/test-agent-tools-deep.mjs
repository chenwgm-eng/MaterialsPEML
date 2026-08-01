import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import axios from 'axios'

const BASE_URL = 'http://localhost:8000'
const SCREENSHOT_DIR = path.resolve('test-screenshots-agent-tools-deep')
const REPORT_FILE = path.resolve('test-report-agent-tools-deep.md')

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

const findings = []
let step = 0

function addFinding({ page, feature, severity, description, steps, screenshot }) {
  findings.push({ page: page || '', feature, severity, description, steps: steps || [], screenshot })
}

async function screenshot(page, name) {
  step++
  const file = path.join(SCREENSHOT_DIR, `${String(step).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  return file
}

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function apiLogin() {
  const res = await axios.post(`${BASE_URL}/api/auth/login`, { username: 'admin', password: 'admin123' })
  return res.data
}

async function navigateByMenu(page, menuText) {
  const parentGroup = page.locator('.sidebar-menu .ant-menu-submenu', { hasText: menuText }).first()
  const isInCollapsedGroup = await parentGroup.isVisible().catch(() => false)
  if (isInCollapsedGroup) {
    const child = parentGroup.locator('.ant-menu-item', { hasText: menuText }).first()
    if (!(await child.isVisible().catch(() => false))) {
      await parentGroup.locator('.ant-menu-submenu-title').first().click()
      await wait(400)
    }
  }
  const menuItem = page.locator('.sidebar-menu .menu-text', { hasText: new RegExp(`^${menuText}$`) }).first()
  if (await menuItem.isVisible().catch(() => false)) {
    await menuItem.click()
    return true
  }
  const fallback = page.locator('.sidebar-menu .ant-menu-item', { hasText: menuText }).first()
  if (await fallback.isVisible().catch(() => false)) {
    await fallback.click()
    return true
  }
  return false
}

async function getPageTitle(page) {
  return await page.locator('.page-title').first().innerText({ timeout: 3000 }).catch(() => '')
}

function getToken() {
  // 测试脚本运行在同一进程，可直接复用最近一次 apiLogin 的 token
  return globalThis.__testAuthToken || ''
}

async function apiCall(method, endpoint, data) {
  const token = getToken()
  const cfg = { method, url: `${BASE_URL}/api${endpoint}`, headers: {} }
  if (token) cfg.headers['X-Auth-Token'] = token
  if (data !== undefined) cfg.data = data
  return axios(cfg).then((r) => r.data)
}

async function apiDeleteAgent(id) {
  try {
    await apiCall('delete', `/agents/${encodeURIComponent(id)}`)
  } catch (e) {
    // 忽略不存在
  }
}

async function apiDeleteCapability(id) {
  try {
    await apiCall('delete', `/capabilities/${encodeURIComponent(id)}`)
  } catch (e) {
    // 忽略不存在
  }
}

async function apiApproveCapability(id) {
  try {
    await apiCall('post', `/capabilities/${encodeURIComponent(id)}/approve`)
  } catch (e) {
    // 忽略
  }
}

async function selectAntOption(page, formItemLabel, optionText) {
  const formItem = page.locator('.ant-form-item').filter({ hasText: formItemLabel }).first()
  await formItem.locator('.ant-select').first().click()
  await wait(300)
  const opt = page.locator('.ant-select-dropdown').locator('.ant-select-item', { hasText: optionText }).first()
  if (await opt.isVisible().catch(() => false)) {
    await opt.click()
    await wait(300)
  }
}

function btnByText(container, textRegex) {
  return container.locator('button').filter({ hasText: textRegex }).first()
}

async function getLatestMessage(page) {
  const msg = await page.locator('.ant-message-notice-content').first().innerText({ timeout: 3000 }).catch(() => '')
  if (msg) return msg
  return await page.locator('.ant-notification-notice-message').first().innerText({ timeout: 3000 }).catch(() => '')
}

async function getAllMessages(page) {
  const msgNodes = await page.locator('.ant-message-notice-content').all()
  const notifyNodes = await page.locator('.ant-notification-notice-message').all()
  const texts = []
  for (const n of msgNodes) texts.push(await n.innerText().catch(() => ''))
  for (const n of notifyNodes) texts.push(await n.innerText().catch(() => ''))
  return texts
}

async function clearMessages(page) {
  // 点击消息关闭按钮（不触发 Escape，避免关闭抽屉/弹窗）
  const closers = await page.locator('.ant-message-notice-action, .ant-notification-notice-close').all()
  for (const c of closers) await c.click({ force: true }).catch(() => {})
  // 等待消息自动消失（ant-message 默认 3s）
  for (let i = 0; i < 40; i++) {
    const msgs = await page.locator('.ant-message-notice-content, .ant-notification-notice-message').count().catch(() => 0)
    if (msgs === 0) break
    await wait(100)
  }
}

async function closeAllDrawers(page) {
  const closers = await page.locator('.ant-drawer-close').all()
  for (const c of closers) {
    await c.click({ force: true }).catch(() => {})
    await wait(300)
  }
  await page.keyboard.press('Escape').catch(() => {})
  await wait(300)
}

async function closeAllModals(page) {
  const cancelBtns = await page.locator('.ant-modal-wrap .ant-btn:not(.ant-btn-primary)').all()
  for (const b of cancelBtns.slice(0, 3)) {
    await b.click({ force: true }).catch(() => {})
    await wait(300)
  }
  await page.keyboard.press('Escape').catch(() => {})
  await wait(300)
}

async function safeNavigateByMenu(page, menuText) {
  await closeAllDrawers(page)
  await closeAllModals(page)
  return navigateByMenu(page, menuText)
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      addFinding({ page: page.url(), feature: '浏览器控制台错误', severity: '中', description: msg.text() })
    }
  })
  page.on('pageerror', (err) => {
    addFinding({ page: page.url(), feature: '页面 JS 异常', severity: '高', description: err.message })
  })
  page.on('response', (resp) => {
    const u = resp.url()
    if (resp.status() >= 400 && u.includes('/api/')) {
      addFinding({ page: page.url(), feature: 'API 请求失败', severity: '高', description: `${resp.status()} ${resp.statusText()} ${u}` })
    }
  })

  let loginData
  try {
    loginData = await apiLogin()
    if (loginData?.token) globalThis.__testAuthToken = loginData.token
  } catch (e) {
    addFinding({ page: BASE_URL, feature: '登录接口', severity: '严重', description: `登录接口失败：${e.message}` })
  }

  await page.goto(`${BASE_URL}/`)
  await wait(1000)
  if (loginData?.user_id && loginData?.token) {
    await page.evaluate(
      ({ userId, token, role }) => {
        localStorage.setItem('userId', userId)
        localStorage.setItem('authToken', token)
        localStorage.setItem('userRole', role || 'admin')
      },
      { userId: loginData.user_id, token: loginData.token, role: loginData.role }
    )
  }
  await page.goto(`${BASE_URL}/capability-center`)
  await wait(2000)

  const runId = Date.now()
  const agentName = `测试智能体-${runId}`
  const agentNameEdited = `测试智能体-已编辑-${runId}`
  const capabilityId = `test_capability_${runId}`
  let createdAgentId = null

  // ============================================================
  // 1. 智能体管理 — 完整 CRUD + 测试对话 + 表单校验
  // ============================================================
  try {
    const navOk = await safeNavigateByMenu(page, '智能体管理')
    if (!navOk) {
      addFinding({ page: page.url(), feature: '智能体管理导航', severity: '严重', description: '无法通过左侧菜单找到「智能体管理」入口' })
    }
    await wait(2500)
    const title = await getPageTitle(page)
    if (!title.includes('智能体管理')) {
      addFinding({ page: page.url(), feature: '智能体管理页面', severity: '严重', description: `页面标题异常：期望「智能体管理」，实际「${title || '空'}」`, screenshot: await screenshot(page, 'agents-title') })
    } else {
      await screenshot(page, 'agents-page')

      // 1.1 表单校验：名称为空时保存
      const createBtn = page.locator('.agent-manager-page button:has-text("新建智能体")').first()
      if (await createBtn.isVisible().catch(() => false)) {
        await createBtn.click()
        await wait(800)
        await screenshot(page, 'agent-create-drawer')
        const saveBtn = btnByText(page.locator('.ant-drawer').filter({ hasText: '新建智能体' }).first(), /保\s*存/)
        if (await saveBtn.isVisible().catch(() => false)) {
          // 清空可能存在的默认值
          const nameInput = page.locator('.ant-drawer input[placeholder="Agent 名称"]').first()
          await nameInput.fill('')
          await saveBtn.click()
          await wait(800)
          const notify = await getLatestMessage(page)
          if (!notify.includes('名称')) {
            addFinding({ page: page.url(), feature: '新建智能体校验', severity: '高', description: `名称为空时点击保存未出现必填提示，当前提示：${notify || '无'}`, screenshot: await screenshot(page, 'agent-create-validation') })
          }
          const cancelBtn = btnByText(page.locator('.ant-drawer').filter({ hasText: '新建智能体' }).first(), /取\s*消/)
          if (await cancelBtn.isVisible().catch(() => false)) await cancelBtn.click({ force: true })
          await wait(800)
          await clearMessages(page)
        } else {
          addFinding({ page: page.url(), feature: '新建智能体抽屉', severity: '高', description: '未找到保存按钮' })
        }
      }

      // 1.2 新建智能体并提交
      await createBtn.click()
      await wait(800)
      const createDrawer = page.locator('.ant-drawer').filter({ hasText: '新建智能体' }).first()
      await createDrawer.locator('input[placeholder="Agent 名称"]').first().fill(agentName)
      await selectAntOption(page, '角色', '材料发现')
      const descInput = createDrawer.locator('textarea[placeholder="Agent 职责描述"]').first()
      if (await descInput.isVisible().catch(() => false)) {
        await descInput.fill('由浏览器自动化测试创建的智能体')
      }
      await screenshot(page, 'agent-create-filled')
      const saveBtn = btnByText(createDrawer, /保\s*存/)
      await saveBtn.click()
      // 消息在提交成功后立即出现且很快消失，先轮询捕获
      let notify = ''
      for (let i = 0; i < 15; i++) {
        notify = await getLatestMessage(page)
        if (notify) break
        await wait(100)
      }
      // 等待抽屉关闭或提交完成
      await createDrawer.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {})
      if (!notify.includes('创建') && !notify.includes('成功')) {
        addFinding({ page: page.url(), feature: '新建智能体提交', severity: '严重', description: `提交后未看到创建成功提示，当前提示：${notify || '无'}`, screenshot: await screenshot(page, 'agent-create-submit') })
      }
      await screenshot(page, 'agents-after-create')

      // 1.3 验证列表中出现：新建自定义智能体应自动在「自定义智能体」标签页
      const customTab = page.locator('.agent-manager-page .ant-tabs-tab', { hasText: '自定义智能体' }).first()
      const customTabActive = await customTab.evaluate((el) => el.classList.contains('ant-tabs-tab-active')).catch(() => false)
      if (!customTabActive && await customTab.isVisible().catch(() => false)) {
        await customTab.click()
        await wait(800)
      }
      let newRow = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentName }).first()
      let rowVisible = false
      for (let i = 0; i < 10; i++) {
        rowVisible = await newRow.isVisible().catch(() => false)
        if (rowVisible) break
        await wait(500)
      }
      if (!rowVisible) {
        addFinding({ page: page.url(), feature: '智能体列表刷新', severity: '严重', description: `创建后未在列表中找到「${agentName}」，可能未成功保存或列表未刷新`, screenshot: await screenshot(page, 'agent-not-in-list') })
      } else {
        // 获取 agent id（详情按钮的 click 参数不易读取，用 API 查询）
        try {
          const agentList = await apiCall('get', '/agents')
          const arr = Array.isArray(agentList) ? agentList : (agentList?.agents || [])
          const found = arr.find((a) => a.name === agentName)
          if (found) createdAgentId = found.id
        } catch (e) {
          addFinding({ page: page.url(), feature: '智能体列表 API', severity: '中', description: `创建后查询 API 失败：${e.message}` })
        }
        // 若需要手动切换标签才看到，记录 UX 缺陷
        if (!customTabActive) {
          addFinding({ page: page.url(), feature: '智能体创建后交互', severity: '中', description: '新建自定义智能体成功后，页面仍停留在「内置智能体」标签页，未自动跳转至「自定义智能体」展示新建结果，用户需手动切换标签才能看到' })
        }
      }

      // 1.4 编辑智能体
      if (createdAgentId) {
        const row = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentName }).first()
        const editBtn = btnByText(row, /编\s*辑/)
        if (await editBtn.isVisible().catch(() => false)) {
          await editBtn.click()
          await wait(800)
          const editDrawer = page.locator('.ant-drawer').filter({ hasText: '编辑智能体' }).first()
          const nameInput = editDrawer.locator('input[placeholder="Agent 名称"]').first()
          await nameInput.fill(agentNameEdited)
          await screenshot(page, 'agent-edit-filled')
          const saveEditBtn = btnByText(editDrawer, /保\s*存/)
          await saveEditBtn.click()
          let editNotify = ''
          for (let i = 0; i < 15; i++) {
            editNotify = await getLatestMessage(page)
            if (editNotify) break
            await wait(100)
          }
          await editDrawer.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {})
          if (!editNotify.includes('更新') && !editNotify.includes('成功')) {
            addFinding({ page: page.url(), feature: '编辑智能体提交', severity: '严重', description: `编辑保存后未看到更新成功提示，当前提示：${editNotify || '无'}`, screenshot: await screenshot(page, 'agent-edit-submit') })
          }
          const editedRow = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentNameEdited }).first()
          if (!(await editedRow.isVisible().catch(() => false))) {
            addFinding({ page: page.url(), feature: '智能体编辑结果', severity: '严重', description: `编辑后列表未显示新名称「${agentNameEdited}」`, screenshot: await screenshot(page, 'agent-edit-not-reflected') })
          }
        } else {
          addFinding({ page: page.url(), feature: '智能体编辑按钮', severity: '高', description: `未找到「${agentName}」的编辑按钮` })
        }
      }

      // 1.5 测试对话
      if (createdAgentId) {
        // 用原始名称或编辑后的名称定位均可，因为 row 已更新
        const row = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentNameEdited }).first()
        const testBtn = btnByText(row, /测\s*试/)
        if (await testBtn.isVisible().catch(() => false)) {
          await testBtn.click()
          await wait(1000)
          const chatDrawer = page.locator('.ant-drawer').filter({ hasText: '测试对话' }).first()
          const chatInput = chatDrawer.locator('.chat-input-bar input').first()
          const sendBtn = chatDrawer.locator('.chat-input-bar button').first()
          if (await chatInput.isVisible().catch(() => false)) {
            await chatInput.fill('你好，请简单自我介绍')
            await sendBtn.click()
            await wait(8000)
            await screenshot(page, 'agent-chat-response')
            const assistantMsgs = await chatDrawer.locator('.chat-msg-assistant').count().catch(() => 0)
            const errorNotify = (await getAllMessages(page)).find((t) => t.includes('失败') || t.includes('错误'))
            if (assistantMsgs === 0) {
              addFinding({ page: page.url(), feature: '智能体测试对话', severity: '高', description: `发送消息后 8 秒内未收到助手回复${errorNotify ? `，通知：${errorNotify}` : ''}`, screenshot: await screenshot(page, 'agent-chat-no-reply') })
            }
          } else {
            addFinding({ page: page.url(), feature: '智能体测试对话', severity: '高', description: '测试对话抽屉未正常打开或输入框不可见' })
          }
          await chatDrawer.locator('.ant-drawer-close').first().click({ force: true }).catch(() => {})
          await wait(800)
        } else {
          addFinding({ page: page.url(), feature: '智能体测试按钮', severity: '高', description: `未找到「${agentNameEdited}」的测试按钮` })
        }
      }

      // 1.6 删除智能体
      if (createdAgentId) {
        const row = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentNameEdited }).first()
        const delBtn = btnByText(row, /删\s*除/)
        if (await delBtn.isVisible().catch(() => false)) {
          await delBtn.click()
          await wait(800)
          const confirmBtn = page.locator('.ant-modal-confirm-btns button').filter({ hasText: /删\s*除/ }).first()
          if (await confirmBtn.isVisible().catch(() => false)) {
            await confirmBtn.click()
            await wait(1500)
            const delNotify = await getLatestMessage(page)
            if (!delNotify.includes('删除') && !delNotify.includes('成功')) {
              addFinding({ page: page.url(), feature: '智能体删除', severity: '严重', description: `删除后未看到成功提示，当前提示：${delNotify || '无'}`, screenshot: await screenshot(page, 'agent-delete-submit') })
            }
            const deletedRow = page.locator('.agent-manager-page .ant-table-tbody tr', { hasText: agentNameEdited }).first()
            if (await deletedRow.isVisible().catch(() => false)) {
              addFinding({ page: page.url(), feature: '智能体删除结果', severity: '严重', description: `删除后列表仍显示「${agentNameEdited}」`, screenshot: await screenshot(page, 'agent-delete-not-reflected') })
            }
          } else {
            addFinding({ page: page.url(), feature: '智能体删除确认', severity: '高', description: '点击删除后未弹出确认对话框' })
          }
        } else {
          addFinding({ page: page.url(), feature: '智能体删除按钮', severity: '高', description: `未找到「${agentNameEdited}」的删除按钮` })
        }
      }
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '智能体管理深入测试', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'agents-deep-exception') })
  }

  // ============================================================
  // 2. 能力中心 — 登记能力契约 + 列表刷新 + 审批
  // ============================================================
  try {
    await safeNavigateByMenu(page, '能力契约')
    await wait(2500)
    await screenshot(page, 'capability-page')

    const registerBtn = page.locator('button:has-text("登记能力")').first()
    if (await registerBtn.isVisible().catch(() => false)) {
      await registerBtn.click()
      await wait(1000)
      const drawer = page.locator('.ant-drawer').filter({ hasText: '登记能力契约' }).first()
      await screenshot(page, 'capability-register-drawer')

      // 2.1 校验空 capability_id
      const saveBtn = btnByText(drawer, /保\s*存/)
      await saveBtn.click()
      await wait(800)
      const emptyNotify = await getLatestMessage(page)
      // 浏览器 required 会拦截，抽屉应保持打开
      const stillOpen = await drawer.isVisible().catch(() => false)
      if (!stillOpen && !emptyNotify.includes('失败') && !emptyNotify.includes('错误')) {
        addFinding({ page: page.url(), feature: '能力登记校验', severity: '高', description: `未填写能力 ID 时点击保存，抽屉意外关闭且无错误提示`, screenshot: await screenshot(page, 'capability-empty-id') })
      }
      await clearMessages(page)

      // 2.2 正常填写并提交
      await drawer.locator('input').first().fill(capabilityId)
      await drawer.locator('.ant-form-item').filter({ hasText: '名称' }).first().locator('input').first().fill('测试能力')
      await drawer.locator('.ant-form-item').filter({ hasText: '提供方' }).first().locator('input').first().fill('browser-test')
      await drawer.locator('.ant-form-item').filter({ hasText: '版本' }).first().locator('input').first().fill('v0.1')
      await selectAntOption(page, '风险等级', '低')
      await screenshot(page, 'capability-register-filled')
      await saveBtn.click()
      // 消息在提交成功后立即出现且很快消失，先轮询捕获
      let capNotify = ''
      for (let i = 0; i < 15; i++) {
        capNotify = await getLatestMessage(page)
        if (capNotify) break
        await wait(100)
      }
      await drawer.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {})
      if (!capNotify.includes('成功') && !capNotify.includes('登记')) {
        addFinding({ page: page.url(), feature: '能力登记提交', severity: '严重', description: `提交后未看到成功提示，当前提示：${capNotify || '无'}`, screenshot: await screenshot(page, 'capability-register-submit') })
      }
      await screenshot(page, 'capability-after-register')

      // 2.3 列表中应出现待审批状态（轮询最多 10 秒）
      let capRow = page.locator('.capability-center .ant-table-tbody tr', { hasText: capabilityId }).first()
      let capVisible = false
      for (let i = 0; i < 20; i++) {
        capVisible = await capRow.isVisible().catch(() => false)
        if (capVisible) break
        await wait(500)
      }
      if (capVisible) {
        // 状态列为表格第 5 列（索引 4），避免误读到提供方 tag
        const statusText = await capRow.locator('td').nth(4).locator('.ant-tag').first().innerText().catch(() => '')
        if (!statusText.includes('待审批')) {
          addFinding({ page: page.url(), feature: '能力登记状态', severity: '中', description: `新登记能力状态不是「待审批」，实际：${statusText}`, screenshot: await screenshot(page, 'capability-status') })
        }
      } else {
        // 补充检查：页面源码是否包含 capability_id，以区分「未渲染」与「分页/过滤导致不可见」
        const pageHtml = await page.content().catch(() => '')
        const inHtml = pageHtml.includes(capabilityId)
        addFinding({ page: page.url(), feature: '能力登记列表刷新', severity: '严重', description: `登记后列表未找到「${capabilityId}」${inHtml ? '（页面源码中存在该 ID，可能被分页或过滤隐藏）' : '（页面源码中也不存在，可能未成功保存或列表未刷新）'}`, screenshot: await screenshot(page, 'capability-not-in-list') })
      }
    } else {
      addFinding({ page: page.url(), feature: '登记能力按钮', severity: '高', description: '未找到「登记能力」按钮' })
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '能力中心深入测试', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'capability-deep-exception') })
  }

  // ============================================================
  // 3. 工具与连接器 — SCP 开关持久化 + 自检 + 本地工具自检
  // ============================================================
  try {
    await safeNavigateByMenu(page, '工具与连接器')
    await wait(2500)
    const title = await getPageTitle(page)
    if (!title.includes('工具与连接器')) {
      addFinding({ page: page.url(), feature: '工具与连接器页面', severity: '严重', description: `页面标题异常：期望「工具与连接器」，实际「${title || '空'}」`, screenshot: await screenshot(page, 'tools-title') })
    } else {
      await screenshot(page, 'tools-page')

      // 3.1 SCP 开关切换并验证持久化
      const firstSwitch = page.locator('.tools-hub .scp-card .ant-switch').first()
      if (await firstSwitch.isVisible().catch(() => false)) {
        const before = await firstSwitch.isChecked().catch(() => false)
        await firstSwitch.click()
        await wait(2000)
        const after = await firstSwitch.isChecked().catch(() => false)
        if (before === after) {
          addFinding({ page: page.url(), feature: 'SCP 启用开关', severity: '高', description: '点击开关后状态未变化，可能未响应或权限校验失败', screenshot: await screenshot(page, 'tools-switch-nochange') })
        } else {
          // 刷新页面验证持久化
          await page.reload()
          await wait(2500)
          const reloadedSwitch = page.locator('.tools-hub .scp-card .ant-switch').first()
          const persisted = await reloadedSwitch.isChecked().catch(() => false)
          if (persisted !== after) {
            addFinding({ page: page.url(), feature: 'SCP 开关持久化', severity: '高', description: `刷新后开关状态未持久化：刷新前=${after}，刷新后=${persisted}`, screenshot: await screenshot(page, 'tools-switch-persist') })
          }
          // 恢复原始状态
          if (persisted !== before) {
            await reloadedSwitch.click()
            await wait(2000)
          }
        }
      }

      // 3.2 SCP 服务器自检
      const scpTestBtn = page.locator('.tools-hub .scp-card-actions button').filter({ hasText: /自\s*检/ }).first()
      if (await scpTestBtn.isVisible().catch(() => false)) {
        await scpTestBtn.click()
        await wait(5000)
        await screenshot(page, 'tools-scp-selftest')
        const notify = await getLatestMessage(page)
        if (notify.includes('失败') || notify.includes('错误')) {
          addFinding({ page: page.url(), feature: 'SCP 自检结果', severity: '中', description: `SCP 服务器自检未通过：${notify}（若环境未配置真实 SCP 则为预期现象）`, screenshot: await screenshot(page, 'tools-scp-selftest-fail') })
        }
      }

      // 3.3 本地兜底工具自检
      const localTestBtn = page.locator('.tools-hub .ant-table-tbody tr').filter({ hasText: /生\s*成\s*晶\s*体\s*候\s*选|predict_crystal_properties|generate_crystal_candidates/ }).first()
        .locator('button').filter({ hasText: /自\s*检/ }).first()
      if (await localTestBtn.isVisible().catch(() => false)) {
        await localTestBtn.click()
        await wait(5000)
        await screenshot(page, 'tools-local-selftest')
        const notify = await getLatestMessage(page)
        if (notify.includes('失败') || notify.includes('错误')) {
          addFinding({ page: page.url(), feature: '本地工具自检结果', severity: '中', description: `本地工具自检未通过：${notify}`, screenshot: await screenshot(page, 'tools-local-selftest-fail') })
        }
      }
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '工具与连接器深入测试', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'tools-deep-exception') })
  }

  // ============================================================
  // 4. 边界与错误场景：直接访问 SPA 路径、API 异常提示
  // ============================================================
  try {
    for (const path of ['/agents', '/tools', '/capability-center']) {
      const resp = await axios.get(`${BASE_URL}${path}`, { headers: { Accept: 'text/html' }, maxRedirects: 0 })
      const contentType = resp.headers['content-type'] || ''
      const body = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data)
      if (contentType.includes('application/json') || body.trim().startsWith('[') || body.trim().startsWith('{')) {
        addFinding({ page: `${BASE_URL}${path}`, feature: '前后端路由冲突', severity: '严重', description: `直接访问 ${path} 被后端 API 截获，返回 JSON 而非 SPA 页面` })
      }
    }
  } catch (e) {
    addFinding({ page: BASE_URL, feature: '路由冲突检测', severity: '中', description: `检测请求异常：${e.message}` })
  }

  await browser.close()

  // 清理测试数据
  if (createdAgentId) await apiDeleteAgent(createdAgentId)
  await apiDeleteCapability(capabilityId)

  // 生成报告
  const lines = []
  lines.push('# 智能体管理、工具与连接器深入测试报告')
  lines.push('')
  lines.push(`- 测试时间：${new Date().toLocaleString('zh-CN')}`)
  lines.push(`- 测试地址：${BASE_URL}`)
  lines.push(`- 发现问题数：${findings.length}`)
  lines.push('')
  lines.push('## 测试范围')
  lines.push('')
  lines.push('本次测试在基础页面可用性之上，进一步覆盖以下场景：')
  lines.push('')
  lines.push('1. 智能体管理：表单校验、新建并提交、编辑、测试对话、删除、列表刷新。')
  lines.push('2. 能力中心：登记能力契约、必填校验、列表刷新、状态验证。')
  lines.push('3. 工具与连接器：SCP 启用开关切换及持久化、SCP 服务器自检、本地工具自检。')
  lines.push('4. 边界与错误：直接访问 SPA 路径的前后端路由冲突、API 失败与前端错误提示。')
  lines.push('')
  lines.push('## 问题汇总')
  lines.push('')
  if (findings.length === 0) {
    lines.push('未发现问题。')
  } else {
    lines.push('| 严重级别 | 功能模块 | 问题描述 | 页面 URL | 复现步骤 | 截图 |')
    lines.push('| --- | --- | --- | --- | --- | --- |')
    for (const f of findings) {
      lines.push(`| ${f.severity} | ${f.feature} | ${f.description.replace(/\|/g, '\\|')} | ${f.page} | ${(f.steps || []).join(' → ') || '-'} | ${f.screenshot ? path.basename(f.screenshot) : '-'} |`)
    }
  }
  lines.push('')
  lines.push('## 截图目录')
  lines.push('')
  lines.push(SCREENSHOT_DIR)
  lines.push('')

  fs.writeFileSync(REPORT_FILE, lines.join('\n'), 'utf-8')
  console.log(`报告已生成：${REPORT_FILE}`)
  console.log(`发现问题：${findings.length}`)
})()
