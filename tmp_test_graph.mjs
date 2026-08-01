import { chromium } from 'playwright';

const base = 'http://localhost:5173/technology-intelligence';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  page.on('console', (msg) => console.log('PAGE CONSOLE:', msg.type(), msg.text()));
  page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));

  console.log('navigating to', base);
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForSelector('input[placeholder*="关键词"]', { timeout: 10000 });

  console.log('searching LLZO');
  await page.fill('input[placeholder*="关键词"]', 'LLZO');
  await page.press('input[placeholder*="关键词"]', 'Enter');

  // wait for search loading to finish
  await page.waitForTimeout(2000);
  await page.waitForFunction(() => {
    const spin = document.querySelector('.graph-card .ant-spin');
    return !spin || spin.classList.contains('ant-spin-hidden') || getComputedStyle(spin).display === 'none';
  }, { timeout: 30000 });

  // ensure chart container has size
  const rect = await page.evaluate(() => {
    const el = document.querySelector('.kg-chart');
    return el ? el.getBoundingClientRect() : null;
  });
  console.log('chart rect:', rect);

  // Wait a bit for echarts force layout
  await page.waitForTimeout(3000);

  // Try to find a rendered node element (canvas or svg)
  const hasNode = await page.evaluate(() => {
    const chart = document.querySelector('.kg-chart');
    if (!chart) return false;
    const canvas = chart.querySelector('canvas');
    const svg = chart.querySelector('svg');
    return { canvas: !!canvas, svg: !!svg, children: chart.childElementCount };
  });
  console.log('chart children:', hasNode);

  // Click near center of chart to hit a node
  if (rect && rect.width > 0 && rect.height > 0) {
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    console.log('clicking chart center', x, y);
    await page.mouse.click(x, y);
    await page.waitForTimeout(1000);
  }

  // Check for modal
  const modal = await page.$('.ant-modal');
  const modalTitle = modal ? await modal.$eval('.ant-modal-title', (el) => el.textContent).catch(() => null) : null;
  const modalBody = modal ? await modal.$eval('.node-detail', (el) => el.innerText).catch(() => null) : null;
  console.log('modal visible:', !!modal);
  console.log('modal title:', modalTitle);
  console.log('modal body:', modalBody);

  await browser.close();
})();
