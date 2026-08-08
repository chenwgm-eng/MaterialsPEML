import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://localhost:5173'
const OUT = path.join(__dirname, '..', 'doc', 'e2e_evidence')

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errs = []
const api = []
page.on('pageerror', (e) => errs.push(`[pageerror] ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error') errs.push(`[console] ${m.text()}`) })
page.on('response', async (r) => {
  if (r.url().includes('/api/') && r.request().method() === 'POST') {
    let body = ''
    try { body = await r.text() } catch {}
    api.push({ url: r.url(), status: r.status(), body: body.slice(0, 2000) })
  }
})

await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 }).catch(()=>{})
await page.locator('.ant-layout-header button').filter({ hasText: '登录' }).first().click().catch(()=>{})
await page.waitForTimeout(500)
await page.locator('input[name="username"]').fill('admin')
await page.locator('input[name="password"]').fill('admin123')
await page.locator('.ant-modal .ant-btn-primary').click()
await page.waitForTimeout(1500)

// 晶体性质预测
await page.goto(BASE + '/prediction', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
// 选择晶体材料 tab（默认可能是标准预测-晶体）
await page.locator('input[name="formula"]').fill('Li6PS5Cl').catch(()=>{})
await page.locator('button').filter({ hasText: '开始预测' }).first().click().catch(()=>{})
errs.length = 0
let result = ''
for (let i=0;i<45;i++){
  await page.waitForTimeout(2000)
  result = await page.evaluate(() => {
    const mc = document.querySelector('.main-content')
    return mc ? mc.innerText.slice(-2000) : ''
  }).catch(()=>'')
  if ((result.includes('结果') || result.includes('预测')) && result.length > 400 && !result.includes('请先输入化学式')) break
}
await page.screenshot({ path: path.join(OUT, 'page__prediction_result.png'), fullPage: false }).catch(()=>{})

// 临时逆合成规划
await page.goto(BASE + '/synthesis', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
await page.locator('button').filter({ hasText: '临时逆合成规划' }).first().click().catch(()=>{})
await page.waitForTimeout(800)
const inputs = await page.locator('input').all()
if (inputs.length >= 2) {
  await inputs[0].fill('Li6PS5Cl').catch(()=>{})
  await inputs[1].fill('LiCl').catch(()=>{})
}
await page.locator('button').filter({ hasText: '开始规划' }).first().click().catch(()=>{})
let synResult = ''
for (let i=0;i<30;i++){
  await page.waitForTimeout(2000)
  synResult = await page.evaluate(() => {
    const mc = document.querySelector('.main-content')
    return mc ? mc.innerText.slice(-2000) : ''
  }).catch(()=>'')
  if (synResult.includes('路线') || synResult.includes('结果') || synResult.includes('失败')) break
}
await page.screenshot({ path: path.join(OUT, 'page__synthesis_temp.png'), fullPage: false }).catch(()=>{})

await browser.close()
fs.writeFileSync(path.join(OUT, 'prediction_test.json'), JSON.stringify({ predictionResult: result, synthesisResult: synResult, api, errs }, null, 2))
console.log('PREDICTION TEST DONE')
