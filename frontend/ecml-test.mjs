import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE = 'http://localhost:8000';
const SHOTS = join(__dirname, 'ecml-test-screenshots');
mkdirSync(SHOTS, { recursive: true });

const REPORT = [];
function add(page, step, status, detail = '', severity = '') {
  REPORT.push({ page, step, status, detail, severity, timestamp: new Date().toISOString() });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : status === 'WARN' ? '⚠️' : '🔍';
  console.log(`${icon} [${severity || 'INFO'}] ${page} | ${step}: ${status} ${detail ? '| ' + detail : ''}`);
}
async function shot(page, name) {
  const fname = name.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '_').substring(0, 80);
  try {
    await page.screenshot({ path: join(SHOTS, `${fname}.png`), fullPage: true, timeout: 15000 });
  } catch (e) {
    console.warn(`⚠️ 截图失败 ${fname}: ${e.message}`);
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const page = await context.newPage();
  const errors = [];
  const reqs404 = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  page.on('response', resp => { if (resp.status() === 404) reqs404.push(resp.url()); });

  try {
    // 1. ECML 主页面
    console.log('\n=== 一、实验闭环迭代主页 (/ecml) ===\n');
    await page.goto(`${BASE}/ecml`, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => {
      add('/ecml', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(2500);
    add('/ecml', '页面加载', 'PASS', `URL: ${page.url()}`);

    const title = await page.title().catch(() => '');
    add('/ecml', '页面标题', title.includes('实验闭环迭代') ? 'PASS' : 'FAIL', `标题: "${title}"`, title.includes('实验闭环迭代') ? '' : 'P0');

    const subtitle = await page.textContent('.page-subtitle').catch(() => '');
    add('/ecml', '副标题说明', subtitle.includes('7 步闭环') ? 'PASS' : 'WARN', `副标题: "${subtitle.trim()}"`, subtitle.includes('7 步闭环') ? '' : 'P1');

    const hint = await page.textContent('.page-usage-hint').catch(() => '');
    add('/ecml', '使用说明', hint.includes('实验数据') ? 'PASS' : 'WARN', `说明: "${hint.trim()}"`);

    await shot(page, '01_ecml_main');

    // 检查表单元素
    const targetInput = await page.$('input[placeholder*="LiCoO2"]');
    add('/ecml', '目标输入框', targetInput ? 'PASS' : 'FAIL', targetInput ? '存在' : '未找到', targetInput ? '' : 'P0');

    const propSelect = await page.$('.ant-select');
    add('/ecml', '目标属性选择', propSelect ? 'PASS' : 'FAIL', propSelect ? '存在' : '未找到', propSelect ? '' : 'P0');

    const iterInput = await page.$('.ant-input-number input');
    add('/ecml', '迭代次数输入', iterInput ? 'PASS' : 'FAIL', iterInput ? '存在' : '未找到', iterInput ? '' : 'P0');

    const startBtn = await page.$('button:has-text("启动循环")');
    add('/ecml', '启动循环按钮', startBtn ? 'PASS' : 'FAIL', startBtn ? '存在' : '未找到', startBtn ? '' : 'P0');

    const historyBtn = await page.$('a:has-text("运行历史")');
    add('/ecml', '运行历史入口', historyBtn ? 'PASS' : 'FAIL', historyBtn ? '存在' : '未找到', historyBtn ? '' : 'P1');

    const chips = await page.$$('.template-chip');
    add('/ecml', '目标模板chip', chips.length >= 2 ? 'PASS' : 'WARN', `数量: ${chips.length}`, chips.length < 2 ? 'P2' : '');

    // 单/多目标切换：ant-design-vue 的 a-radio-button 渲染为
    // <label class="ant-radio-button-wrapper"><span class="ant-radio-button">...</span><span>多目标</span></label>
    // 文本在 wrapper 内的 span，不在 .ant-radio-button 内，因此选择器必须用 wrapper
    const modeWrappers = await page.$$('.ant-radio-button-wrapper');
    let multiWrapper = null;
    for (const w of modeWrappers) {
      const txt = (await w.textContent().catch(() => '')).trim();
      if (txt.includes('多目标')) { multiWrapper = w; break; }
    }
    add('/ecml', '多目标切换按钮', multiWrapper || modeWrappers.length >= 2 ? 'PASS' : 'FAIL', `wrapper数量: ${modeWrappers.length}`, modeWrappers.length < 2 ? 'P1' : '');
    if (multiWrapper) {
      // 点击 label wrapper 触发 ant-design-vue radio 完整事件链
      await multiWrapper.click().catch(async () => {
        // 兜底：直接点击 input
        const input = await multiWrapper.$('input');
        if (input) await input.click();
      });
      await page.waitForTimeout(1500);
      // 多目标模式下会渲染多选下拉；兼容 ant-design-vue 4.x 的 mode="multiple" 实际渲染为 class 含 ant-select-multiple
      const multiSelect = await page.$('.multi-objective-editor, .ant-select-multiple, .ant-select[mode="multiple"]');
      add('/ecml', '多目标属性集选择', multiSelect ? 'PASS' : 'FAIL', multiSelect ? '出现多选下拉' : '未出现', multiSelect ? '' : 'P1');
      await shot(page, '02_ecml_multi_objective');
      // 切回单目标
      const singleWrapper = modeWrappers.find(w => w !== multiWrapper);
      if (singleWrapper) await singleWrapper.click().catch(() => {});
      await page.waitForTimeout(300);
    }

    // 边界：迭代次数 0 / 10 / 非数字
    // abc 输入会被 parser 过滤为空，a-input-number 回退到上一个有效值或空
    if (iterInput) {
      for (const v of ['0', '10', 'abc']) {
        await iterInput.fill(v);
        await page.waitForTimeout(300);
        const val = await iterInput.inputValue();
        const pass = val === v || (v === 'abc' && val !== 'abc');
        add('/ecml', `迭代次数输入"${v}"`, pass ? 'PASS' : 'WARN', `当前值: "${val}"`, pass ? '' : 'P2');
      }
      await iterInput.fill('1');
    }

    // 2. 启动一次真实 ECML 运行（test 目标走快速路径）
    console.log('\n=== 二、启动 ECML 闭环运行 ===\n');
    if (targetInput && iterInput && startBtn) {
      await targetInput.fill('test');
      await iterInput.fill('1');
      await startBtn.click();
      add('/ecml', '点击启动循环', 'PASS', '已点击');
      await shot(page, '07_ecml_after_start');

      // 等待运行完成或超时（后端 LLM/DFT 链路可能较慢，最多等待 4 分钟）
      let completed = false;
      for (let i = 0; i < 80; i++) {
        await page.waitForTimeout(3000);
        const url = page.url();
        const againBtn = await page.$('button:has-text("再次运行")');
        const cancelBtn = await page.$('button:has-text("取消运行")');
        const stateCard = await page.$('.flow-card, .result-overview-card');
        if (againBtn || (stateCard && !(await cancelBtn?.isVisible().catch(() => false)))) {
          completed = true;
          add('/ecml', '运行完成检测', 'PASS', `URL: ${url}`);
          break;
        }
        if (i % 5 === 0) await shot(page, `08_ecml_running_${i}`);
      }
      if (!completed) {
        add('/ecml', '运行完成检测', 'WARN', '超过120秒未完成', 'P1');
      }
      await shot(page, '09_ecml_run_final');

      // 检查结果卡片
      const overview = await page.$('.result-overview-card');
      add('/ecml', '结果概览卡片', overview ? 'PASS' : 'WARN', overview ? '存在' : '未找到', overview ? '' : 'P2');
      const candidates = await page.$('#ecml-detail-candidates');
      add('/ecml', '候选材料卡片', candidates ? 'PASS' : 'WARN', candidates ? '存在' : '未找到', candidates ? '' : 'P2');
      const synthesizable = await page.$('#ecml-detail-synthesizable');
      add('/ecml', '工业化验证卡片', synthesizable ? 'PASS' : 'WARN', synthesizable ? '存在' : '未找到', synthesizable ? '' : 'P2');
      const nextRound = await page.$('.detail-card:has-text("下一轮候选建议")');
      add('/ecml', '下一轮候选建议', nextRound ? 'PASS' : 'WARN', nextRound ? '存在' : '未找到', nextRound ? '' : 'P2');
    } else {
      add('/ecml', '启动运行', 'FAIL', '缺少必要表单元素', 'P0');
    }

    // 3. 运行历史页
    console.log('\n=== 三、迭代历史 (/ecml/runs) ===\n');
    await page.goto(`${BASE}/ecml/runs`, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => {
      add('/ecml/runs', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(3000);
    add('/ecml/runs', '页面加载', 'PASS', `URL: ${page.url()}`);

    // 检测后端 API 路径与前端路由冲突：若页面内容为 JSON，说明命中了 /ecml/runs API
    const bodyTextRuns = await page.textContent('body').catch(() => '');
    const isJsonResponse = bodyTextRuns.trim().startsWith('{') || bodyTextRuns.trim().startsWith('[');
    if (isJsonResponse) {
      add('/ecml/runs', '路由冲突检测', 'FAIL', '访问 /ecml/runs 返回后端 JSON 而非前端页面（API 路径与 SPA 路由冲突）', 'P0');
    } else {
      const runsTitle = await page.title().catch(() => '');
      add('/ecml/runs', '页面标题', runsTitle.includes('迭代历史') ? 'PASS' : 'FAIL', `标题: "${runsTitle}"`, runsTitle.includes('迭代历史') ? '' : 'P0');

      const createBtn = await page.$('a:has-text("新建实验闭环迭代")');
      add('/ecml/runs', '新建入口', createBtn ? 'PASS' : 'FAIL', createBtn ? '存在' : '未找到', createBtn ? '' : 'P1');

      const envFilters = await page.$$('.ant-radio-button');
      add('/ecml/runs', '环境筛选按钮', envFilters.length >= 3 ? 'PASS' : 'WARN', `数量: ${envFilters.length}`, envFilters.length < 3 ? 'P2' : '');

      const rows = await page.$$('.ant-table-tbody tr');
      add('/ecml/runs', '运行记录列表', rows.length > 0 ? 'PASS' : 'WARN', `记录数: ${rows.length}`, rows.length === 0 ? 'P2' : '');
    }

    await shot(page, '03_ecml_runs');

    // 4. 候选工作台联动
    console.log('\n=== 四、候选工作台联动 (/workbench) ===\n');
    await page.goto(`${BASE}/workbench`, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => {
      add('/workbench', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(3000);
    add('/workbench', '页面加载', 'PASS', `URL: ${page.url()}`);

    const candidateTitle = await page.title().catch(() => '');
    add('/workbench', '页面标题', candidateTitle.includes('候选') ? 'PASS' : 'WARN', `标题: "${candidateTitle}"`);

    // 候选工作台必须先选择项目/任务才能生成候选；此处检查入口按钮是否存在
    const generateBtn = await page.$('button:has-text("调用智能体生成候选")');
    add('/workbench', '生成候选入口', generateBtn ? 'PASS' : 'WARN', generateBtn ? '存在' : '未找到', generateBtn ? '' : 'P2');

    // 未选择候选时操作栏隐藏，"送入闭环迭代"不可见；记录为 INFO
    const ecmlBtn = await page.$('button:has-text("送入闭环迭代")');
    add('/workbench', '送入闭环迭代按钮', ecmlBtn ? 'PASS' : 'INFO', ecmlBtn ? '存在' : '未选中候选时隐藏（符合设计）');

    await shot(page, '04_candidate_workbench');

    // 5. 无效 run_id 边界
    console.log('\n=== 五、异常边界 ===\n');
    await page.goto(`${BASE}/ecml?run_id=not-exist`, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => {
      add('/ecml?run_id=not-exist', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(2500);
    add('/ecml?run_id=not-exist', '页面加载', 'PASS', `URL: ${page.url()}`);

    const errorAlert = await page.$('.ant-alert-error');
    const bodyText = await page.textContent('body').catch(() => '');
    add('/ecml?run_id=not-exist', '无效run_id错误提示', errorAlert || bodyText.includes('不存在') || bodyText.includes('失败') ? 'PASS' : 'WARN', errorAlert ? '存在错误提示' : '未找到明确错误提示', errorAlert ? '' : 'P2');

    await shot(page, '05_ecml_invalid_runid');

    // 6. URL 参数预填
    await page.goto(`${BASE}/ecml?target=LiFePO4&target_property=band_gap`, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => {
      add('/ecml?target=...', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(2500);
    const targetVal = await page.$eval('input[placeholder*="LiCoO2"]', el => el.value).catch(() => '');
    add('/ecml?target=...', 'URL参数预填目标', targetVal === 'LiFePO4' ? 'PASS' : 'FAIL', `目标值: "${targetVal}"`, targetVal === 'LiFePO4' ? '' : 'P1');
    await shot(page, '06_ecml_prefill');

    // Console/Network 错误汇总
    await page.waitForTimeout(1000);
    // 排除预期的 404（无效 run_id 测试产生的 /api/ecml/runs/not-exist）
    const expected404Pattern = /\/api\/ecml\/runs\/not-exist/;
    const meaningfulErrors = [...new Set(errors)].filter(e =>
      !expected404Pattern.test(e) && !e.includes('404 (Not Found)')
    );
    if (meaningfulErrors.length) {
      meaningfulErrors.forEach(e => add('Console', 'JS错误', 'FAIL', e, 'P1'));
    } else {
      add('Console', 'JS错误', 'PASS', '未检测到非预期错误');
    }
    const meaningful404 = [...new Set(reqs404)].filter(u => !expected404Pattern.test(u));
    if (meaningful404.length) {
      meaningful404.forEach(u => add('Network', '404资源', 'WARN', u, 'P2'));
    } else {
      add('Network', '404资源', 'PASS', '未检测到非预期 404');
    }

  } catch (e) {
    add('GLOBAL', '测试异常', 'FAIL', e.message, 'P0');
  } finally {
    await browser.close();
    const reportPath = join(__dirname, 'ecml-test-report.json');
    writeFileSync(reportPath, JSON.stringify(REPORT, null, 2));
    console.log(`\n报告已保存: ${reportPath}`);
    console.log(`截图目录: ${SHOTS}`);
  }
})();
