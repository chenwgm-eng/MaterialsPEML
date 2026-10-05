/* 全站对比度审计：遍历所有页面，检测文本对比度 < 4.5:1 的元素（排除禁用/占位/装饰） */
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const pages = [
  '/', '/my-tasks', '/projects', '/workbench', '/synthesis', '/formula-design',
  '/ecml', '/ecml/runs', '/experiments', '/experiment-workbench', '/samples',
  '/equipment', '/data-ingest', '/data-quality', '/technology-intelligence',
  '/knowledge-graph', '/materials', '/properties', '/mdm', '/research',
  '/orchestration', '/agents', '/tools', '/mappings', '/capability-center',
  '/eval-center', '/topology', '/dashboard', '/control-plane', '/budgets',
  '/value-report', '/users', '/audit', '/settings', '/nav-visibility',
]

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

// 登录
await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)
const u = page.locator('input[name="username"]')
if (await u.count()) {
  await u.fill('admin')
  await page.locator('input[name="password"]').fill('admin123')
  await page.locator('.ant-modal .ant-btn-primary').first().click()
  await page.waitForTimeout(4000)
}

const audit = `(() => {
  const results = []
  const parse = (c) => {
    const m = c.match(/rgba?\\(([\\d.]+)[,\\s]+([\\d.]+)[,\\s]+([\\d.]+)(?:[,\\s]+([\\d.]+))?\\)/)
    if (!m) return null
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] }
  }
  const lum = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05) }
  const effectiveBg = (el) => {
    let node = el
    while (node && node !== document.body) {
      const cs = getComputedStyle(node)
      // 渐变背景：取最深的色停近似（如侧栏深色渐变）
      if (cs.backgroundImage && cs.backgroundImage.includes('gradient')) {
        return { r: 10, g: 10, b: 10, a: 1 }
      }
      const c = parse(cs.backgroundColor)
      if (c && c.a > 0.5) return c
      node = node.parentElement
    }
    return { r: 247, g: 247, b: 248, a: 1 }
  }
  const walk = (el) => {
    const cs = getComputedStyle(el)
    const txt = (el.textContent || '').trim()
    const isTextNode = el.children.length === 0 || (el.children.length === 0 && txt.length > 0)
    // 直接含文本的叶子/半叶子元素
    const direct = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent || '').trim().length > 0).length > 0
    if (direct && txt.length > 0 && txt.length < 200) {
      const color = parse(cs.color)
      const bg = effectiveBg(el)
      if (color && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0') {
        const r = ratio(color, bg)
        const size = parseFloat(cs.fontSize) || 14
        const bold = parseInt(cs.fontWeight) >= 600
        const min = size >= 18.66 || (size >= 14 && bold) ? 3 : 4.5
        const disabled = el.closest('[disabled], .ant-btn[disabled], .ant-input[disabled], .ant-select-disabled')
        const placeholder = el.closest('.ant-input-placeholder, [placeholder]') && el.matches('.ant-input::placeholder')
        if (r < min && !disabled && cs.color !== 'rgba(0, 0, 0, 0)' && r < 4.2) {
          results.push({
            tag: el.tagName.toLowerCase(),
            cls: (el.className || '').toString().slice(0, 40),
            text: txt.slice(0, 30),
            color: cs.color,
            bg: 'rgb(' + bg.r + ',' + bg.g + ',' + bg.b + ')',
            ratio: Math.round(r * 100) / 100,
            size,
          })
        }
      }
    }
    for (const c of el.children) walk(c)
  }
  walk(document.body)
  // 去重（同 cls+color+bg）
  const seen = new Set()
  return results.filter((r) => {
    const k = r.cls + '|' + r.color + '|' + r.bg
    if (seen.has(k)) return false
    seen.add(k)
    return true
  }).slice(0, 40)
})()`

const report = {}
for (const path of pages) {
  await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
  await page.waitForTimeout(1500)
  const found = await page.evaluate(audit)
  if (found.length) {
    report[path] = found
  }
}
await browser.close()

for (const [path, items] of Object.entries(report)) {
  console.log('\n### ' + path + ' (' + items.length + ' 处)')
  for (const it of items.slice(0, 8)) {
    console.log(`  <${it.tag} .${it.cls}> "${it.text}" ${it.color} on ${it.bg} = ${it.ratio}:1 (${it.size}px)`)
  }
}
console.log('\n总页面数:', pages.length, '有问题的页面:', Object.keys(report).length)
