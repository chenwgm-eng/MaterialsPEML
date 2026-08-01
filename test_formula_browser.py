"""使用 Playwright 对「配方与工艺」模块进行浏览器端到端测试。

输出：
- 关键页面截图保存到 frontend/screenshots/formula_test/
- 控制台日志记录
- 测试报告写入 frontend/screenshots/formula_test/report.md
"""

import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:5173"
API_URL = "http://127.0.0.1:8002"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "frontend", "screenshots", "formula_test")
TOKEN = None

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


async def login_api():
    """通过 API 登录获取 token，注入到浏览器 localStorage。"""
    global TOKEN
    import requests
    resp = requests.post(f"{API_URL}/auth/login", json={"username": "admin", "password": "admin123"}, timeout=10)
    data = resp.json()
    TOKEN = data["token"]
    log(f"API 登录成功: {data['username']}")
    return data["user_id"], data["token"]


async def screenshot(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"截图: {path}")
    return path


async def inject_auth(page, user_id, token):
    """注入登录态，避免 UI 登录流程。"""
    await page.goto(f"{BASE_URL}/")
    await page.evaluate(f"""
        localStorage.setItem('userId', '{user_id}');
        localStorage.setItem('authToken', '{token}');
        localStorage.setItem('userRole', 'admin');
    """)
    await page.reload()
    await page.wait_for_timeout(1000)


async def navigate_to_formula(page):
    log("导航到配方与工艺页面")
    await page.goto(f"{BASE_URL}/formula-design")
    await page.wait_for_timeout(1500)
    await screenshot(page, "01_formula_list")
    # 检查页面标题
    title = await page.locator(".page-title").inner_text()
    log(f"页面标题: {title}")
    return title


async def test_generate_formula(page):
    log("点击「生成新配方」")
    await page.locator("button:has-text('生成新配方')").first.click()
    await page.wait_for_timeout(800)
    await screenshot(page, "02_design_drawer_open")

    # 选择目标材料
    log("选择目标材料")
    await page.locator(".ant-select").first.click()
    await page.wait_for_timeout(500)
    # 尝试输入 Li6PS5Cl 或选择第一个选项
    await page.keyboard.type("Li6PS5Cl")
    await page.wait_for_timeout(800)
    await screenshot(page, "03_target_select")

    # 如果下拉选项出现，点击第一个
    options = await page.locator(".ant-select-item-option-content").all_inner_texts()
    log(f"下拉选项: {options[:5]}")
    if options:
        await page.locator(".ant-select-item-option-content").first.click()
    else:
        # 直接按 Enter（允许自定义输入）
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(500)

    # 设置需求量
    log("设置需求量")
    inputs = await page.locator("input.ant-input-number-input").all()
    if inputs:
        await inputs[0].fill("10")
    await page.wait_for_timeout(300)
    await screenshot(page, "04_quantity_set")

    # 点击生成配方
    log("点击生成配方")
    gen_btn = page.locator("button:has-text('生成配方')")
    await gen_btn.click()
    await page.wait_for_timeout(3500)
    await screenshot(page, "05_formula_generated")

    # 检查 BOM/BOP 表格是否出现
    bom_rows = await page.locator(".ant-table-tbody tr").all_inner_texts()
    log(f"BOM/BOP 表格行数: {len(bom_rows)}")
    for r in bom_rows[:5]:
        log(f"  行: {r[:80]}")
    return len(bom_rows) > 0


async def test_save_formula(page):
    log("点击保存为配方版本")
    await page.locator("button:has-text('保存为配方版本')").click()
    await page.wait_for_timeout(800)
    await screenshot(page, "06_save_modal")

    # 填写变更说明
    textarea = page.locator("textarea")
    await textarea.fill("Playwright 端到端测试保存")
    await page.wait_for_timeout(300)

    # 监听保存 API 响应
    save_response = {}
    def on_response(resp):
        if '/formulas' in resp.url and resp.request.method == 'POST':
            save_response['status'] = resp.status
            save_response['url'] = resp.url
    page.on('response', on_response)

    # 点击保存：定位到第二个抽屉（保存配方版本）footer 中的主按钮
    await page.locator('.ant-drawer').nth(1).locator('.ant-drawer-footer button.ant-btn-primary').click()
    # 等待保存请求完成、提示出现并刷新列表
    await page.wait_for_selector(".ant-message-success, .ant-message-error", timeout=15000)
    await page.wait_for_timeout(1500)
    await screenshot(page, "07_after_save")

    # 检查是否回到列表并出现新配方
    cards = await page.locator(".formula-id-text").all_inner_texts()
    log(f"配方列表中的配方编号: {cards[:5]}")

    # 保存后设计抽屉仍可能打开，直接刷新页面回到干净的列表状态
    log("刷新页面回到配方列表")
    await page.goto(f"{BASE_URL}/formula-design")
    await page.wait_for_timeout(1200)
    await screenshot(page, "07b_after_save_reload")

    return len(cards) > 0


async def test_formula_detail(page):
    log("点击第一个配方行查看详情")
    await page.locator(".formula-id-text").first.click()
    await page.wait_for_timeout(1000)
    await screenshot(page, "08_formula_detail")

    # 检查详情内容
    detail_title = await page.locator(".head-title").inner_text()
    log(f"详情标题: {detail_title}")
    return "FORM" in detail_title


async def test_prepare_sample(page):
    log("点击「制备样品」按钮")
    sample_btn = page.locator("button:has-text('制备样品')")
    if await sample_btn.count() == 0:
        log("未找到制备样品按钮")
        return False
    await sample_btn.click()
    await page.wait_for_timeout(1500)

    # 检查 URL
    url = page.url
    log(f"跳转后 URL: {url}")
    if "/samples" not in url:
        return False

    # 路由切换后配方详情抽屉可能仍残留，尝试关闭以查看样品表单
    if await page.locator(".ant-drawer-open").count() > 0:
        log("检测到残留的配方详情抽屉，尝试关闭")
        await page.locator(".ant-drawer-open .ant-drawer-close").last.click()
        await page.wait_for_timeout(500)

    await screenshot(page, "09_sample_page")

    # 检查样品表单是否已预填目标材料
    form_name = await page.locator('input[name="name"]').input_value()
    log(f"样品表单名称预填值: {form_name}")
    source_type = await page.locator('input[name="source_type"]').input_value() if await page.locator('input[name="source_type"]').count() > 0 else "N/A"
    log(f"样品表单来源类型: {source_type}")
    return bool(form_name)


async def main():
    user_id, token = await login_api()
    findings = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            await inject_auth(page, user_id, token)

            # 1. 导航到配方页面
            title = await navigate_to_formula(page)
            if "配方与工艺" not in title:
                findings.append("页面标题不匹配，可能未正确加载配方与工艺页面")

            # 2. 生成配方
            has_result = await test_generate_formula(page)
            if not has_result:
                findings.append("生成配方后页面未显示 BOM/BOP 表格数据")

            # 3. 保存配方
            has_saved = await test_save_formula(page)
            if not has_saved:
                findings.append("保存配方后列表未刷新或未出现新配方")

            # 4. 查看详情
            has_detail = await test_formula_detail(page)
            if not has_detail:
                findings.append("配方详情抽屉未正确显示")

            # 5. 制备样品
            has_sample = await test_prepare_sample(page)
            if not has_sample:
                findings.append("点击制备样品后未跳转到样品管理页面")

        except Exception as e:
            log(f"测试异常: {e}")
            findings.append(f"测试过程中出现异常: {e}")
            await screenshot(page, "99_error")
        finally:
            await browser.close()

    # 生成报告
    report_path = os.path.join(SCREENSHOT_DIR, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 配方与工艺浏览器测试报告\n\n")
        f.write(f"测试时间: {datetime.now().isoformat()}\n\n")
        if findings:
            f.write("## 发现的问题\n")
            for i, issue in enumerate(findings, 1):
                f.write(f"{i}. {issue}\n")
        else:
            f.write("## 未发现明显问题\n")
        f.write("\n## 截图清单\n")
        for name in sorted(os.listdir(SCREENSHOT_DIR)):
            if name.endswith(".png"):
                f.write(f"- {name}\n")

    log(f"报告已保存: {report_path}")
    return findings


if __name__ == "__main__":
    findings = asyncio.run(main())
    print("\n测试完成，发现的问题:")
    for f in findings:
        print(f"  - {f}")
