import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

const SCREEN_DIR = path.resolve('screenshots', 'capability')
if (!fs.existsSync(SCREEN_DIR)) fs.mkdirSync(SCREEN_DIR, { recursive: true })

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()

page.on('console', msg => console.log('CONSOLE:', msg.type(), msg.text()))
page.on('pageerror', err => console.log('PAGEERROR:', err.message))
page.on('response', resp => {
  if (!resp.ok()) {
    console.log('HTTP ERROR:', resp.status(), resp.url())
  }
})

try {
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: path.join(SCREEN_DIR, 'simple_home.png'), fullPage: true })
  console.log('Home screenshot saved')

  // Login
  const loginBtn = page.locator('button:has-text("登录")').first()
  if (await loginBtn.isVisible().catch(() => false)) {
    await loginBtn.click()
    await page.waitForTimeout(500)
    await page.locator('input[name="username"]').fill('admin')
    await page.locator('input[name="password"]').fill('admin123')
    await page.locator('.ant-modal-footer button:has-text("登录")').click()
    await page.waitForTimeout(2000)
  }
  await page.screenshot({ path: path.join(SCREEN_DIR, 'simple_home_logged_in.png'), fullPage: true })
  console.log('Logged in screenshot saved')

  // Navigate to capability center
  await page.goto('http://localhost:5173/capability-center')
  await page.waitForTimeout(3000)
  await page.screenshot({ path: path.join(SCREEN_DIR, 'simple_capability.png'), fullPage: true })
  console.log('Capability center screenshot saved')

  const title = await page.title().catch(() => '')
  console.log('Page title:', title)
  const rows = await page.locator('.ant-table-tbody tr.ant-table-row').count()
  console.log('Rows:', rows)
} catch (err) {
  console.error('Error:', err)
  await page.screenshot({ path: path.join(SCREEN_DIR, 'simple_error.png'), fullPage: true })
} finally {
  await browser.close()
}
