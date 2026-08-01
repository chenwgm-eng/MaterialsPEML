import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import axios from 'axios'

const BASE_URL = 'http://localhost:8000'
const SCREENSHOT_DIR = path.resolve('test-screenshots-agent-tools')
const REPORT_FILE = path.resolve('test-report-agent-tools.md')

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
  // 1. 如果目标在折叠的父菜单下，先展开父菜单
  const parentGroup = page.locator('.sidebar-menu .ant-menu-submenu', { hasText: menuText }).first()
  const isInCollapsedGroup = await parentGroup.isVisible().catch(() => false)
  if (isInCollapsedGroup) {
    // 检查是否已展开（通过判断子菜单是否可见）
    const child = parentGroup.locator('.ant-menu-item', { hasText: menuText }).first()
    if (!(await child.isVisible().catch(() => false))) {
      await parentGroup.locator('.ant-menu-submenu-title').first().click()
      await wait(400)
    }
  }

  // 2. 点击目标菜单文本
  const menuItem = page.locator('.sidebar-menu .menu-text', { hasText: new RegExp(`^${menuText}$`) }).first()
  if (await menuItem.isVisible().catch(() => false)) {
    await menuItem.click()
    return true
  }
  // 3. 兼容折叠或只有图标的情况
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

  // 0. 登录
  let loginData
  try {
    loginData = await apiLogin()
  } catch (e) {
    addFinding({ page: BASE_URL, feature: '登录接口', severity: '严重', description: `登录接口失败：${e.message}` })
  }

  // 先设置登录态，再进入能力中心（避免未登录被重定向到首页）
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
  await screenshot(page, 'start-capability')

  // 1. 智能体管理（通过菜单导航）
  try {
    const navOk = await navigateByMenu(page, '智能体管理')
    if (!navOk) {
      addFinding({ page: page.url(), feature: '智能体管理导航', severity: '严重', description: '无法通过左侧菜单找到「智能体管理」入口' })
    }
    await wait(2500)
    const title = await getPageTitle(page)
    if (!title.includes('智能体管理')) {
      addFinding({ page: page.url(), feature: '智能体管理页面', severity: '严重', description: `页面标题异常：期望「智能体管理」，实际「${title || '空'}」`, screenshot: await screenshot(page, 'agents-title') })
    } else {
      await screenshot(page, 'agents-page')

      // 1.1 检查列表
      const rows = await page.locator('.agent-manager-page .ant-table-tbody tr').count().catch(() => 0)
      if (rows === 0) {
        addFinding({ page: page.url(), feature: '智能体列表', severity: '中', description: '内置/自定义智能体列表为空' })
      }

      // 1.2 新建智能体
      const createBtn = page.locator('.agent-manager-page button:has-text("新建智能体")').first()
      if (await createBtn.isVisible().catch(() => false)) {
        await createBtn.click()
        await wait(800)
        await screenshot(page, 'agent-create-drawer')
        const drawerTitle = await page.locator('.ant-drawer-title').first().innerText().catch(() => '')
        if (!drawerTitle.includes('新建智能体')) {
          addFinding({ page: page.url(), feature: '新建智能体抽屉', severity: '高', description: `抽屉标题异常：${drawerTitle || '未打开'}` })
        } else {
          await page.locator('.ant-drawer input[placeholder="Agent 名称"]').first().fill('测试智能体-' + Date.now())
          await wait(500)
          // 不实际提交，避免抽屉关闭异常阻塞后续测试；点击取消关闭
          const cancelBtn = page.locator('.ant-drawer-footer button').filter({ hasText: /取\s*消/ }).first()
          if (await cancelBtn.isVisible().catch(() => false)) {
            await cancelBtn.click({ force: true })
          } else {
            await page.locator('.ant-drawer-close').first().click({ force: true }).catch(() => {})
          }
          await wait(800)
          await screenshot(page, 'agent-create-closed')
        }
      } else {
        addFinding({ page: page.url(), feature: '新建智能体按钮', severity: '高', description: '未找到「新建智能体」按钮' })
      }

      // 1.3 测试详情/编辑/测试按钮是否存在
      const detailVisible = await page.locator('.agent-manager-page >> text=详情').first().isVisible().catch(() => false)
      const editVisible = await page.locator('.agent-manager-page >> text=编辑').first().isVisible().catch(() => false)
      const testVisible = await page.locator('.agent-manager-page >> text=测试').first().isVisible().catch(() => false)
      if (!detailVisible) {
        addFinding({ page: page.url(), feature: '智能体操作按钮', severity: '中', description: '未找到「详情」按钮' })
      }
      if (!editVisible) {
        addFinding({ page: page.url(), feature: '智能体操作按钮', severity: '中', description: '未找到「编辑」按钮' })
      }
      if (!testVisible) {
        addFinding({ page: page.url(), feature: '智能体操作按钮', severity: '中', description: '未找到「测试」按钮' })
      }
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '智能体管理', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'agents-exception') })
  }

  // 2. 工具与连接器（通过菜单导航）
  try {
    const navOk = await navigateByMenu(page, '工具与连接器')
    if (!navOk) {
      addFinding({ page: page.url(), feature: '工具与连接器导航', severity: '严重', description: '无法通过左侧菜单找到「工具与连接器」入口' })
    }
    await wait(2500)
    const title = await getPageTitle(page)
    if (!title.includes('工具与连接器')) {
      addFinding({ page: page.url(), feature: '工具与连接器页面', severity: '严重', description: `页面标题异常：期望「工具与连接器」，实际「${title || '空'}」`, screenshot: await screenshot(page, 'tools-title') })
    } else {
      await screenshot(page, 'tools-page')

      // 2.1 SCP 服务器卡片
      const scpCards = await page.locator('.tools-hub .scp-card').count().catch(() => 0)
      if (scpCards === 0) {
        addFinding({ page: page.url(), feature: 'SCP 服务器列表', severity: '高', description: '未渲染 SCP 服务器卡片' })
      }

      // 2.2 能力绑定表格
      const capRows = await page.locator('.tools-hub .ant-table-tbody tr').count().catch(() => 0)
      if (capRows === 0) {
        addFinding({ page: page.url(), feature: '能力绑定表格', severity: '中', description: '能力绑定列表为空或未加载' })
      }

      // 2.3 开关与自检
      const firstSwitch = page.locator('.tools-hub .scp-card .ant-switch').first()
      if (await firstSwitch.isVisible().catch(() => false)) {
        const before = await firstSwitch.isChecked().catch(() => false)
        await firstSwitch.click()
        await wait(1500)
        const after = await firstSwitch.isChecked().catch(() => false)
        if (before === after) {
          addFinding({ page: page.url(), feature: 'SCP 启用开关', severity: '高', description: '点击开关后状态未变化，可能未响应或权限校验失败' })
        }
        await screenshot(page, 'tools-switch')
      }

      const testBtn = page.locator('.tools-hub .scp-card-actions button:has-text("自检")').first()
      if (await testBtn.isVisible().catch(() => false)) {
        await testBtn.click()
        await wait(4000)
        const notify = await page.locator('.ant-notification-notice-message').first().innerText().catch(() => '')
        if (notify.includes('失败') || notify.includes('错误')) {
          addFinding({ page: page.url(), feature: 'SCP 自检', severity: '高', description: `自检失败：${notify}`, screenshot: await screenshot(page, 'tools-self-test-error') })
        } else {
          await screenshot(page, 'tools-self-test')
        }
      }
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '工具与连接器', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'tools-exception') })
  }

  // 3. 能力中心（已在当前页，直接测试登记能力）
  try {
    const navOk = await navigateByMenu(page, '能力契约')
    if (!navOk) {
      addFinding({ page: page.url(), feature: '能力契约导航', severity: '严重', description: '无法通过左侧菜单找到「能力契约」入口' })
    }
    await wait(2500)
    await screenshot(page, 'capability-page')

    const rows = await page.locator('.capability-center .ant-table-tbody tr').count().catch(() => 0)
    if (rows === 0) {
      addFinding({ page: page.url(), feature: '能力列表', severity: '中', description: '能力列表为空' })
    }

    const registerBtn = page.locator('button:has-text("登记能力")').first()
      if (await registerBtn.isVisible().catch(() => false)) {
        await registerBtn.click()
        await wait(1000)
        await screenshot(page, 'capability-register-drawer')
        const drawerTitle = await page.locator('.ant-drawer-title').first().innerText().catch(() => '')
        if (!drawerTitle.includes('登记')) {
          addFinding({ page: page.url(), feature: '登记能力抽屉', severity: '中', description: `抽屉未正常打开：${drawerTitle || '空'}` })
        } else {
          const drawer = page.locator('.ant-drawer').filter({ hasText: '登记能力契约' }).first()
          const closeBtn = drawer.locator('.ant-drawer-close').first()
          const saveBtn = drawer.locator('.ant-drawer-footer button').filter({ hasText: /保\s*存/ }).first()
          const closeVisible = await closeBtn.isVisible().catch(() => false)
          const saveVisible = await saveBtn.isVisible().catch(() => false)
          if (!closeVisible) addFinding({ page: page.url(), feature: '登记能力抽屉关闭按钮', severity: '中', description: '关闭按钮不可见' })
          if (!saveVisible) addFinding({ page: page.url(), feature: '登记能力抽屉保存按钮', severity: '高', description: '保存按钮不可见，无法提交' })
          if (closeVisible) await closeBtn.click({ force: true })
        }
      } else {
        addFinding({ page: page.url(), feature: '登记能力按钮', severity: '高', description: '未找到「登记能力」按钮' })
      }
    // 等待抽屉关闭动画完成，避免遮罩拦截后续菜单点击
    await wait(1000)
  } catch (e) {
    addFinding({ page: page.url(), feature: '能力中心', severity: '严重', description: `测试异常：${e.message}`, screenshot: await screenshot(page, 'capability-exception') })
  }

  // 4. 控制平面
  try {
    const navOk = await navigateByMenu(page, '控制平面')
    if (!navOk) {
      addFinding({ page: page.url(), feature: '控制平面导航', severity: '中', description: '未在菜单中找到「控制平面」入口（可能非 admin 隐藏）' })
    } else {
      await wait(2500)
      const title = await getPageTitle(page)
      if (!title.includes('控制平面')) {
        addFinding({ page: page.url(), feature: '控制平面页面', severity: '高', description: `页面标题异常：期望「控制平面」，实际「${title || '空'}」`, screenshot: await screenshot(page, 'control-plane-title') })
      } else {
        await screenshot(page, 'control-plane-page')
      }
    }
  } catch (e) {
    addFinding({ page: page.url(), feature: '控制平面', severity: '严重', description: `测试异常：${e.message}` })
  }

  // 5. 路由冲突检测：直接访问前端路径不应被后端 API 截获返回 JSON
  try {
    for (const path of ['/agents', '/tools']) {
      const resp = await axios.get(`${BASE_URL}${path}`, { headers: { Accept: 'text/html' }, maxRedirects: 0 })
      const contentType = resp.headers['content-type'] || ''
      const body = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data)
      if (contentType.includes('application/json') || body.trim().startsWith('[') || body.trim().startsWith('{')) {
        addFinding({ page: `${BASE_URL}${path}`, feature: '前后端路由冲突', severity: '严重', description: `直接访问 ${path} 被后端 API 截获，返回 JSON 而非 SPA 页面，导致刷新/书签/外链无法进入该页面` })
      }
    }
  } catch (e) {
    addFinding({ page: BASE_URL, feature: '路由冲突检测', severity: '中', description: `检测请求异常：${e.message}` })
  }

  await browser.close()

  // 生成报告
  const lines = []
  lines.push('# 智能体管理、工具与连接器浏览器测试报告')
  lines.push('')
  lines.push(`- 测试时间：${new Date().toLocaleString('zh-CN')}`)
  lines.push(`- 测试地址：${BASE_URL}`)
  lines.push(`- 发现问题数：${findings.length}`)
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
