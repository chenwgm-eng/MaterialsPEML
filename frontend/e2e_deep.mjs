// 深度功能实测：AI 预测链路、详情抽屉、404页核实、关键交互
import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://localhost:5173'
const OUT = path.join(__dirname, '..', 'doc', 'e2e_evidence')
const results = []

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errs = []
page.on('pageerror', (e) => errs.push(`[pageerror] ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error') errs.push(`[console] ${m.text()}`) })

await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 }).catch(()=>{})
// 登录
await page.locator('.ant-layout-header button').filter({ hasText: '登录' }).first().click().catch(()=>{})
await page.waitForTimeout(500)
await page.locator('input[name="username"]').fill('admin')
await page.locator('input[name="password"]').fill('admin123')
await page.locator('.ant-modal .ant-btn-primary').click()
await page.waitForTimeout(1500)

// 1) 404 页渲染核实
await page.goto(BASE + '/nonexistent-zzz', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(800)
const nf = await page.evaluate(() => {
  const mc = document.querySelector('.main-content')
  return { mainText: mc ? mc.innerText.slice(0,200) : '(no main-content)', bodyText: document.body.innerText.slice(0,200) }
}).catch(()=>({mainText:'ERR',bodyText:'ERR'}))
results.push({ test: '404_render', nf })

// 2) 电池寿命预测（AI 三智能体链路）
await page.goto(BASE + '/battery-life', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(800)
const cycleData = JSON.stringify([
  {"cycle":1,"capacity":100},{"cycle":2,"capacity":99},{"cycle":3,"capacity":98.2},
  {"cycle":4,"capacity":97.1},{"cycle":5,"capacity":95.8},{"cycle":6,"capacity":94.2},
  {"cycle":7,"capacity":92.5},{"cycle":8,"capacity":90.6},{"cycle":9,"capacity":88.5},
  {"cycle":10,"capacity":86.2}
])
await page.locator('textarea').first().fill(cycleData).catch(()=>{})
await page.locator('input').first().fill('LiFePO4').catch(()=>{})
await page.locator('button').filter({ hasText: '开始预测' }).first().click().catch(()=>{})
results.push({ test: 'battery_life_clicked', errs: [...errs] })
errs.length = 0
// 轮询结果（最长 60s）
let blResult = null
for (let i=0;i<30;i++){
  await page.waitForTimeout(2000)
  blResult = await page.evaluate(() => {
    const mc = document.querySelector('.main-content')
    return mc ? mc.innerText.slice(-1500) : ''
  }).catch(()=> '')
  if (blResult.includes('预测') && !blResult.includes('开始预测') && blResult.length>600) break
}
results.push({ test: 'battery_life_result', tail: blResult.trim().slice(-1200), errs: [...errs] })
errs.length = 0

// 3) 物料详情抽屉（3D 结构查看）
await page.goto(BASE + '/materials', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
await page.locator('button').filter({ hasText: '详情' }).first().click().catch(()=>{})
await page.waitForTimeout(1500)
const matDetail = await page.evaluate(() => {
  const d = document.querySelector('.ant-drawer, .ant-modal')
  return d ? d.innerText.slice(0,600) : '(no drawer)'
}).catch(()=> '(no drawer)')
results.push({ test: 'material_detail_drawer', matDetail, errs: [...errs] })
errs.length = 0
await page.keyboard.press('Escape').catch(()=>{})
await page.waitForTimeout(500)

// 4) 配方详情抽屉
await page.goto(BASE + '/formula-design', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
await page.locator('button').filter({ hasText: '详情' }).first().click().catch(()=>{})
await page.waitForTimeout(1500)
const formDetail = await page.evaluate(() => {
  const d = document.querySelector('.ant-drawer, .ant-modal')
  return d ? d.innerText.slice(0,800) : '(no drawer)'
}).catch(()=> '(no drawer)')
results.push({ test: 'formula_detail_drawer', formDetail, errs: [...errs] })
errs.length = 0
await page.keyboard.press('Escape').catch(()=>{})
await page.waitForTimeout(500)

// 5) 知识图谱查看
await page.goto(BASE + '/knowledge-graph', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
await page.locator('button').filter({ hasText: '查看' }).first().click().catch(()=>{})
await page.waitForTimeout(2500)
const kg = await page.evaluate(() => ({
  canvas: document.querySelectorAll('canvas').length,
  text: document.querySelector('.main-content')?.innerText.slice(0,400) || ''
})).catch(()=>({canvas:0,text:'ERR'}))
results.push({ test: 'knowledge_graph_view', kg, errs: [...errs] })
errs.length = 0

// 6) 属性字典字段展开
await page.goto(BASE + '/properties', { waitUntil: 'networkidle' }).catch(()=>{})
await page.waitForTimeout(1000)
const propErr = [...errs]; errs.length=0
results.push({ test: 'properties_page', errs: propErr })

await browser.close()
fs.writeFileSync(path.join(OUT, 'deep_evidence.json'), JSON.stringify(results, null, 2))
console.log('DEEP DONE')