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

  await page.waitForTimeout(2000);
  await page.waitForFunction(() => {
    const spin = document.querySelector('.graph-card .ant-spin');
    return !spin || spin.classList.contains('ant-spin-hidden') || getComputedStyle(spin).display === 'none';
  }, { timeout: 30000 });
  await page.waitForTimeout(2000);

  // Programmatically trigger node detail via exposed helper
  const nodeInfo = await page.evaluate(() => {
    const targetId = 'Li7La3Zr2O12';
    if (window.__kgClickNode) window.__kgClickNode(targetId);
    return { clickedId: targetId, helperExists: typeof window.__kgClickNode === 'function' };
  });
  console.log('clicked node:', nodeInfo);

  await page.waitForTimeout(800);

  const modal = await page.$('.ant-modal');
  const title = modal ? await modal.$eval('.ant-modal-title', (el) => el.textContent).catch(() => null) : null;
  const body = modal ? await modal.$eval('.node-detail', (el) => el.innerText).catch(() => null) : null;
  console.log('modal visible:', !!modal);
  console.log('modal title:', title);
  console.log('modal body:', body);

  await browser.close();
})();
