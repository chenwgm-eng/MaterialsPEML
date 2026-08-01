# BatteryEMCL Lab 数据 / 知识 / AI / 管理模块 Playwright 实操评测报告

- 测评时间：2026/7/29 18:46:49
- 前端地址：http://localhost:5173
- 后端地址：http://localhost:8000/api
- 浏览器：Chromium headless，viewport 1920×1080
- 登录角色：admin

## 1. 执行摘要

| 指标 | 数值 |
|---|---|
| 覆盖页面数 | 25 |
| 成功加载页面 | 25 |
| 加载失败页面 | 0 |
| 截图证据数 | 297 |
| 缺陷总数 | 8 |
| **P0** | 1 |
| **P1** | 3 |
| **P2** | 1 |
| **P3** | 3 |

## 2. 缺陷清单

| 编号 | 严重度 | 模块 | 页面 | 标题 | 描述 | 证据 |
|---|---|---|---|---|---|---|
| BEMCL-EXP-P1-001 | P1 | EXP | /experiments | 实验数据 自定义操作异常 | locator.click: Timeout 2000ms exceeded.
Call log:
[2m  - waiting for locator('.ant-layout-content button:has-text("编辑"):visible').first()[22m
[2m    - locator resolved to <button type="button" data-v-d041dd15="" aria-label="编辑实验记录" class="css-dev-only-do-not-override-fh4l2d ant-btn ant-btn-link ant-btn-sm">…</button>[22m
[2m  - attempting click action[22m
[2m    2 × waiting for element to be visible, enabled and stable[22m
[2m      - element is visible, enabled and stable[22m
[2m      - scrolling into view if needed[22m
[2m      - done scrolling[22m
[2m      - <td colspan="1" class="ant-descriptions-item-content">…</td> from <div>…</div> subtree intercepts pointer events[22m
[2m    - retrying click action[22m
[2m    - waiting 20ms[22m
[2m    2 × waiting for element to be visible, enabled and stable[22m
[2m      - element is visible, enabled and stable[22m
[2m      - scrolling into view if needed[22m
[2m      - done scrolling[22m
[2m      - <td colspan="1" class="ant-descriptions-item-content">…</td> from <div>…</div> subtree intercepts pointer events[22m
[2m    - retrying click action[22m
[2m      - waiting 100ms[22m
[2m    4 × waiting for element to be visible, enabled and stable[22m
[2m      - element is visible, enabled and stable[22m
[2m      - scrolling into view if needed[22m
[2m      - done scrolling[22m
[2m      - <td colspan="1" class="ant-descriptions-item-content">…</td> from <div>…</div> subtree intercepts pointer events[22m
[2m    - retrying click action[22m
[2m      - waiting 500ms[22m
 | [EV-20260729-219] |
| BEMCL-EXP-P1-002 | P1 | EXP | /experiments | 实验数据 控制台出现严重错误 | [pageerror] TypeError: Cannot read properties of null (reading 'project_id')；[pageerror] TypeError: Cannot read properties of null (reading 'emitsOptions') | [EV-20260729-226] |
| BEMCL-MDM-P1-001 | P1 | MDM | /mdm | 主数据治理 自定义操作异常 | locator.click: Timeout 3000ms exceeded.
Call log:
[2m  - waiting for locator('.ant-modal-content:visible, .ant-drawer-content:visible button:has-text("保存"), .ant-modal-content:visible, .ant-drawer-content:visible button:has-text("提交"), .ant-modal-content:visible, .ant-drawer-content:visible button:has-text("确认"), .ant-modal-content:visible, .ant-drawer-content:visible button:has-text("确定")').first()[22m
[2m    - locator resolved to <div class="ant-modal-content">…</div>[22m
[2m  - attempting click action[22m
[2m    2 × waiting for element to be visible, enabled and stable[22m
[2m      - element is not stable[22m
[2m    - retrying click action[22m
[2m    - waiting 20ms[22m
[2m    - waiting for element to be visible, enabled and stable[22m
[2m    - element is not stable[22m
[2m  2 × retrying click action[22m
[2m      - waiting 100ms[22m
[2m      - waiting for element to be visible, enabled and stable[22m
[2m      - element is not visible[22m
[2m  5 × retrying click action[22m
[2m      - waiting 500ms[22m
[2m      - waiting for element to be visible, enabled and stable[22m
[2m      - element is not visible[22m
[2m  - retrying click action[22m
[2m    - waiting 500ms[22m
 | [EV-20260729-327] |
| BEMCL-RES-P3-001 | P3 | RES | /research | 研发工作台 控制台出现警告 | [error] Warning: [ant-design-vue: Descriptions] Sum of column `span` in a line not match `column` of Descriptions. | [EV-20260729-347] |
| BEMCL-ORCH-P3-001 | P3 | ORCH | /orchestration | 智能编排 控制台出现警告 | [error] Warning: [ant-design-vue: Descriptions] Sum of column `span` in a line not match `column` of Descriptions. | [EV-20260729-357] |
| BEMCL-AGT-P2-001 | P2 | AGT | /agents | Agent 工具映射 / SCP 风险策略未呈现 | 未检测到关键内容：工具路由策略 / 风险 / SCP | [EV-20260729-358] |
| BEMCL-TOPO-P0-001 | P0 | TOPO | /topology | 调用关系 路由返回 404 | 页面内容包含 404 或无权限提示 | [EV-20260729-388] |
| BEMCL-MAP-P3-001 | P3 | MAP | /mappings | 映射控制台 控制台出现警告 | [warning] [Vue warn]: Property "expandedRowRender" was accessed during render but is not defined on instance. 
  at <MappingConsole onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< undefined > > 
  at <BaseTransition mode="out-in" appear=false persisted=false  ... > 
  at <Transition name="fade" mode="out-in" > 
  at <RouterView> 
  at <Anonymous hasSider=undefined prefixCls="ant-layout-content" tag；[warning] [Vue warn]: Property "expandedRowRender" was accessed during render but is not defined on instance. 
  at <MappingConsole onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > 
  at <BaseTransition mode="out-in" appear=false persisted=false  ... > 
  at <Transition name="fade" mode="out-in" > 
  at <RouterView> 
  at <Anonymous hasSider=undefined prefixCls="ant-layout-content" | [EV-20260729-403] |

## 3. 页面执行明细

### /experiment-workbench — 实验工作台

- 状态：已加载并交互
- 模块缩写：EXPW
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-201 | 实验工作台 页面全貌 | frontend/screenshots/pw_data_ai/EXPW_full.png |
| EV-20260729-202 | 分页 1 | frontend/screenshots/pw_data_ai/EXPW_page_0.png |
| EV-20260729-203 | 分页 2 | frontend/screenshots/pw_data_ai/EXPW_page_1.png |
| EV-20260729-204 | 分页 3 | frontend/screenshots/pw_data_ai/EXPW_page_2.png |
| EV-20260729-205 | 表格行 2 | frontend/screenshots/pw_data_ai/EXPW_row_1.png |
| EV-20260729-206 | 表格行 3 | frontend/screenshots/pw_data_ai/EXPW_row_2.png |
| EV-20260729-207 | 表格行 4 | frontend/screenshots/pw_data_ai/EXPW_row_3.png |
| EV-20260729-208 | 表格行 5 | frontend/screenshots/pw_data_ai/EXPW_row_4.png |
| EV-20260729-209 | 下拉选择 2 | frontend/screenshots/pw_data_ai/EXPW_select_1.png |
| EV-20260729-210 | 卡片 1 | frontend/screenshots/pw_data_ai/EXPW_card_0.png |
| EV-20260729-211 | 按钮: 批量导入 | frontend/screenshots/pw_data_ai/EXPW_btn_0.png |
| EV-20260729-212 | 按钮: 新建任务 | frontend/screenshots/pw_data_ai/EXPW_btn_1.png |
| EV-20260729-213 | 按钮: 查看结果 | frontend/screenshots/pw_data_ai/EXPW_btn_2.png |
| EV-20260729-214 | 按钮: 查看结果 | frontend/screenshots/pw_data_ai/EXPW_btn_3.png |
| EV-20260729-215 | 按钮: 查看结果 | frontend/screenshots/pw_data_ai/EXPW_btn_4.png |
| EV-20260729-216 | 按钮: 查看结果 | frontend/screenshots/pw_data_ai/EXPW_btn_5.png |

### /experiments — 实验数据

- 状态：已加载并交互
- 模块缩写：EXP
- 本页缺陷：2 个
  - BEMCL-EXP-P1-001（P1）、BEMCL-EXP-P1-002（P1）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-217 | 实验数据 页面全貌 | frontend/screenshots/pw_data_ai/EXP_full.png |
| EV-20260729-218 | 实验记录详情 | frontend/screenshots/pw_data_ai/EXP_detail.png |
| EV-20260729-219 | 实验数据 自定义操作异常 | frontend/screenshots/pw_data_ai/EXP_custom_error.png |
| EV-20260729-220 | Tab: 实验记录 | frontend/screenshots/pw_data_ai/EXP_tab_0.png |
| EV-20260729-221 | Tab: 测量值分布 | frontend/screenshots/pw_data_ai/EXP_tab_1.png |
| EV-20260729-222 | 下拉选择 1 | frontend/screenshots/pw_data_ai/EXP_select_0.png |
| EV-20260729-223 | 搜索 test | frontend/screenshots/pw_data_ai/EXP_search.png |
| EV-20260729-224 | 卡片 1 | frontend/screenshots/pw_data_ai/EXP_card_0.png |
| EV-20260729-225 | 卡片 2 | frontend/screenshots/pw_data_ai/EXP_card_1.png |
| EV-20260729-226 | 实验数据 控制台严重错误 | frontend/screenshots/pw_data_ai/EXP_console_error.png |

### /samples — 样品管理

- 状态：已加载并交互
- 模块缩写：SAM
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-227 | 样品管理 页面全貌 | frontend/screenshots/pw_data_ai/SAM_full.png |
| EV-20260729-228 | 分页 1 | frontend/screenshots/pw_data_ai/SAM_page_0.png |
| EV-20260729-229 | 分页 2 | frontend/screenshots/pw_data_ai/SAM_page_1.png |
| EV-20260729-230 | 分页 3 | frontend/screenshots/pw_data_ai/SAM_page_2.png |
| EV-20260729-231 | 表格行 2 | frontend/screenshots/pw_data_ai/SAM_row_1.png |
| EV-20260729-232 | 表格行 3 | frontend/screenshots/pw_data_ai/SAM_row_2.png |
| EV-20260729-233 | 表格行 4 | frontend/screenshots/pw_data_ai/SAM_row_3.png |
| EV-20260729-234 | 表格行 5 | frontend/screenshots/pw_data_ai/SAM_row_4.png |
| EV-20260729-235 | 下拉选择 3 | frontend/screenshots/pw_data_ai/SAM_select_2.png |
| EV-20260729-236 | 搜索 test | frontend/screenshots/pw_data_ai/SAM_search.png |
| EV-20260729-237 | 卡片 1 | frontend/screenshots/pw_data_ai/SAM_card_0.png |
| EV-20260729-238 | 按钮: 新建样品 | frontend/screenshots/pw_data_ai/SAM_btn_0.png |
| EV-20260729-239 | 按钮: 详情 | frontend/screenshots/pw_data_ai/SAM_btn_1.png |
| EV-20260729-240 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/SAM_btn_2.png |
| EV-20260729-241 | 按钮: 流转 | frontend/screenshots/pw_data_ai/SAM_btn_3.png |
| EV-20260729-242 | 按钮: 详情 | frontend/screenshots/pw_data_ai/SAM_btn_4.png |
| EV-20260729-243 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/SAM_btn_5.png |

### /equipment — 设备台账

- 状态：已加载并交互
- 模块缩写：EQP
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-244 | 设备台账 页面全貌 | frontend/screenshots/pw_data_ai/EQP_full.png |
| EV-20260729-245 | 表格行 2 | frontend/screenshots/pw_data_ai/EQP_row_1.png |
| EV-20260729-246 | 表格行 3 | frontend/screenshots/pw_data_ai/EQP_row_2.png |
| EV-20260729-247 | 表格行 4 | frontend/screenshots/pw_data_ai/EQP_row_3.png |
| EV-20260729-248 | 表格行 5 | frontend/screenshots/pw_data_ai/EQP_row_4.png |
| EV-20260729-249 | 下拉选择 3 | frontend/screenshots/pw_data_ai/EQP_select_2.png |
| EV-20260729-250 | 卡片 1 | frontend/screenshots/pw_data_ai/EQP_card_0.png |
| EV-20260729-251 | 按钮: 查询 | frontend/screenshots/pw_data_ai/EQP_btn_0.png |
| EV-20260729-252 | 按钮: 新增设备 | frontend/screenshots/pw_data_ai/EQP_btn_1.png |
| EV-20260729-253 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/EQP_btn_2.png |
| EV-20260729-254 | 按钮: 操作 | frontend/screenshots/pw_data_ai/EQP_btn_3.png |
| EV-20260729-255 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/EQP_btn_4.png |
| EV-20260729-256 | 按钮: 操作 | frontend/screenshots/pw_data_ai/EQP_btn_5.png |

### /data-ingest — 数据接入

- 状态：已加载并交互
- 模块缩写：ING
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-257 | 数据接入 页面全貌 | frontend/screenshots/pw_data_ai/ING_full.png |
| EV-20260729-258 | 表格行 1 | frontend/screenshots/pw_data_ai/ING_row_0.png |
| EV-20260729-259 | 表格行 2 | frontend/screenshots/pw_data_ai/ING_row_1.png |
| EV-20260729-260 | 表格行 3 | frontend/screenshots/pw_data_ai/ING_row_2.png |
| EV-20260729-261 | 表格行 4 | frontend/screenshots/pw_data_ai/ING_row_3.png |
| EV-20260729-262 | 表格行 5 | frontend/screenshots/pw_data_ai/ING_row_4.png |
| EV-20260729-263 | 卡片 1 | frontend/screenshots/pw_data_ai/ING_card_0.png |
| EV-20260729-264 | 卡片 2 | frontend/screenshots/pw_data_ai/ING_card_1.png |
| EV-20260729-265 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/ING_btn_0.png |
| EV-20260729-266 | 按钮: 查看明细 | frontend/screenshots/pw_data_ai/ING_btn_1.png |
| EV-20260729-267 | 按钮: 查看明细 | frontend/screenshots/pw_data_ai/ING_btn_2.png |
| EV-20260729-268 | 按钮: 查看明细 | frontend/screenshots/pw_data_ai/ING_btn_3.png |
| EV-20260729-269 | 按钮: 查看明细 | frontend/screenshots/pw_data_ai/ING_btn_4.png |
| EV-20260729-270 | 按钮: 查看明细 | frontend/screenshots/pw_data_ai/ING_btn_5.png |

### /data-quality — 数据质量

- 状态：已加载并交互
- 模块缩写：DQ
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-271 | 数据质量 页面全貌 | frontend/screenshots/pw_data_ai/DQ_full.png |
| EV-20260729-272 | 下拉选择 1 | frontend/screenshots/pw_data_ai/DQ_select_0.png |
| EV-20260729-273 | 卡片 1 | frontend/screenshots/pw_data_ai/DQ_card_0.png |
| EV-20260729-274 | 卡片 2 | frontend/screenshots/pw_data_ai/DQ_card_1.png |
| EV-20260729-275 | 卡片 3 | frontend/screenshots/pw_data_ai/DQ_card_2.png |
| EV-20260729-276 | 卡片 4 | frontend/screenshots/pw_data_ai/DQ_card_3.png |
| EV-20260729-277 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/DQ_btn_0.png |

### /technology-intelligence — 技术情报

- 状态：已加载并交互
- 模块缩写：TI
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-278 | 技术情报 页面全貌 | frontend/screenshots/pw_data_ai/TI_full.png |
| EV-20260729-279 | 技术情报搜索 | frontend/screenshots/pw_data_ai/TI_search.png |
| EV-20260729-280 | Tab:  技术情报  | frontend/screenshots/pw_data_ai/TI_tab_0.png |
| EV-20260729-281 | Tab:  已保存图谱  | frontend/screenshots/pw_data_ai/TI_tab_1.png |
| EV-20260729-282 | 卡片 1 | frontend/screenshots/pw_data_ai/TI_card_0.png |
| EV-20260729-283 | 按钮: 刷 新 | frontend/screenshots/pw_data_ai/TI_btn_0.png |

### /knowledge-graph — 知识图谱

- 状态：已加载并交互
- 模块缩写：KG
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-284 | 知识图谱 页面全貌 | frontend/screenshots/pw_data_ai/KG_full.png |
| EV-20260729-285 | 知识图谱可视化 | frontend/screenshots/pw_data_ai/KG_graph.png |
| EV-20260729-286 | 卡片 1 | frontend/screenshots/pw_data_ai/KG_card_0.png |
| EV-20260729-287 | 卡片 2 | frontend/screenshots/pw_data_ai/KG_card_1.png |
| EV-20260729-288 | 按钮: 刷 新 | frontend/screenshots/pw_data_ai/KG_btn_0.png |
| EV-20260729-289 | 按钮: Li6PS5Cl 知识图谱 | frontend/screenshots/pw_data_ai/KG_btn_1.png |
| EV-20260729-290 | 按钮: 查看 | frontend/screenshots/pw_data_ai/KG_btn_2.png |
| EV-20260729-291 | 按钮: solid electrolyte 知识图谱 | frontend/screenshots/pw_data_ai/KG_btn_3.png |
| EV-20260729-292 | 按钮: 查看 | frontend/screenshots/pw_data_ai/KG_btn_4.png |

### /materials — 物料规格库

- 状态：已加载并交互
- 模块缩写：MAT
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-293 | 物料规格库 页面全貌 | frontend/screenshots/pw_data_ai/MAT_full.png |
| EV-20260729-294 | 分页 1 | frontend/screenshots/pw_data_ai/MAT_page_0.png |
| EV-20260729-295 | 表格行 2 | frontend/screenshots/pw_data_ai/MAT_row_1.png |
| EV-20260729-296 | 表格行 3 | frontend/screenshots/pw_data_ai/MAT_row_2.png |
| EV-20260729-297 | 表格行 4 | frontend/screenshots/pw_data_ai/MAT_row_3.png |
| EV-20260729-298 | 表格行 5 | frontend/screenshots/pw_data_ai/MAT_row_4.png |
| EV-20260729-299 | 下拉选择 2 | frontend/screenshots/pw_data_ai/MAT_select_1.png |
| EV-20260729-300 | 卡片 1 | frontend/screenshots/pw_data_ai/MAT_card_0.png |
| EV-20260729-301 | 卡片 2 | frontend/screenshots/pw_data_ai/MAT_card_1.png |
| EV-20260729-302 | 按钮: 查询 | frontend/screenshots/pw_data_ai/MAT_btn_0.png |
| EV-20260729-303 | 按钮: 新增物料 | frontend/screenshots/pw_data_ai/MAT_btn_1.png |
| EV-20260729-304 | 按钮: 详情 | frontend/screenshots/pw_data_ai/MAT_btn_2.png |
| EV-20260729-305 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/MAT_btn_3.png |
| EV-20260729-306 | 按钮: 详情 | frontend/screenshots/pw_data_ai/MAT_btn_4.png |
| EV-20260729-307 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/MAT_btn_5.png |

### /properties — 属性字典

- 状态：已加载并交互
- 模块缩写：PROP
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-308 | 属性字典 页面全貌 | frontend/screenshots/pw_data_ai/PROP_full.png |
| EV-20260729-309 | 属性字典列表 | frontend/screenshots/pw_data_ai/PROP_list.png |
| EV-20260729-310 | Tab:  化合物标识 13 | frontend/screenshots/pw_data_ai/PROP_tab_0.png |
| EV-20260729-311 | Tab:  物化性质 0 | frontend/screenshots/pw_data_ai/PROP_tab_1.png |
| EV-20260729-312 | Tab:  安全信息 0 | frontend/screenshots/pw_data_ai/PROP_tab_2.png |
| EV-20260729-313 | Tab:  化合物分类 0 | frontend/screenshots/pw_data_ai/PROP_tab_3.png |
| EV-20260729-314 | Tab:  电池材料属性 0 | frontend/screenshots/pw_data_ai/PROP_tab_4.png |
| EV-20260729-315 | Tab:  催化材料属性 0 | frontend/screenshots/pw_data_ai/PROP_tab_5.png |
| EV-20260729-316 | Tab:  高分子材料属性 0 | frontend/screenshots/pw_data_ai/PROP_tab_6.png |
| EV-20260729-317 | 表格行 2 | frontend/screenshots/pw_data_ai/PROP_row_1.png |
| EV-20260729-318 | 表格行 4 | frontend/screenshots/pw_data_ai/PROP_row_3.png |
| EV-20260729-319 | 表格行 5 | frontend/screenshots/pw_data_ai/PROP_row_4.png |
| EV-20260729-320 | 下拉选择 1 | frontend/screenshots/pw_data_ai/PROP_select_0.png |
| EV-20260729-321 | 搜索 test | frontend/screenshots/pw_data_ai/PROP_search.png |
| EV-20260729-322 | 按钮: 添 加 | frontend/screenshots/pw_data_ai/PROP_btn_0.png |

### /mdm — 主数据治理

- 状态：已加载并交互
- 模块缩写：MDM
- 本页缺陷：1 个
  - BEMCL-MDM-P1-001（P1）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-323 | 主数据治理 页面全貌 | frontend/screenshots/pw_data_ai/MDM_full.png |
| EV-20260729-324 | MDM 标准单位 | frontend/screenshots/pw_data_ai/MDM_____.png |
| EV-20260729-325 | MDM 测试方法 | frontend/screenshots/pw_data_ai/MDM_____.png |
| EV-20260729-326 | MDM 特性 | frontend/screenshots/pw_data_ai/MDM___.png |
| EV-20260729-327 | 主数据治理 自定义操作异常 | frontend/screenshots/pw_data_ai/MDM_custom_error.png |
| EV-20260729-328 | 分页 1 | frontend/screenshots/pw_data_ai/MDM_page_0.png |
| EV-20260729-329 | 分页 2 | frontend/screenshots/pw_data_ai/MDM_page_1.png |
| EV-20260729-330 | 分页 3 | frontend/screenshots/pw_data_ai/MDM_page_2.png |
| EV-20260729-331 | 表格行 2 | frontend/screenshots/pw_data_ai/MDM_row_1.png |
| EV-20260729-332 | 表格行 3 | frontend/screenshots/pw_data_ai/MDM_row_2.png |
| EV-20260729-333 | 表格行 4 | frontend/screenshots/pw_data_ai/MDM_row_3.png |
| EV-20260729-334 | 表格行 5 | frontend/screenshots/pw_data_ai/MDM_row_4.png |
| EV-20260729-335 | 搜索 test | frontend/screenshots/pw_data_ai/MDM_search.png |
| EV-20260729-336 | 卡片 1 | frontend/screenshots/pw_data_ai/MDM_card_0.png |
| EV-20260729-337 | 卡片 2 | frontend/screenshots/pw_data_ai/MDM_card_1.png |
| EV-20260729-338 | 按钮: 新增 | frontend/screenshots/pw_data_ai/MDM_btn_0.png |

### /research — 研发工作台

- 状态：已加载并交互
- 模块缩写：RES
- 本页缺陷：1 个
  - BEMCL-RES-P3-001（P3）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-339 | 研发工作台 页面全貌 | frontend/screenshots/pw_data_ai/RES_full.png |
| EV-20260729-340 | 下拉选择 1 | frontend/screenshots/pw_data_ai/RES_select_0.png |
| EV-20260729-341 | 按钮: 智能编排模式 | frontend/screenshots/pw_data_ai/RES_btn_0.png |
| EV-20260729-342 | 按钮: 前往 Agent 管理查看角色库 | frontend/screenshots/pw_data_ai/RES_btn_1.png |
| EV-20260729-343 | 按钮: 测试 | frontend/screenshots/pw_data_ai/RES_btn_2.png |
| EV-20260729-344 | 按钮: 详情 | frontend/screenshots/pw_data_ai/RES_btn_3.png |
| EV-20260729-345 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/RES_btn_4.png |
| EV-20260729-346 | 按钮: 测试 | frontend/screenshots/pw_data_ai/RES_btn_5.png |
| EV-20260729-347 | 研发工作台 控制台警告 | frontend/screenshots/pw_data_ai/RES_console_warn.png |

### /orchestration — 智能编排

- 状态：已加载并交互
- 模块缩写：ORCH
- 本页缺陷：1 个
  - BEMCL-ORCH-P3-001（P3）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-341 | 按钮: 智能编排模式 | frontend/screenshots/pw_data_ai/RES_btn_0.png |
| EV-20260729-348 | 智能编排 页面全貌 | frontend/screenshots/pw_data_ai/ORCH_full.png |
| EV-20260729-349 | 卡片 1 | frontend/screenshots/pw_data_ai/ORCH_card_0.png |
| EV-20260729-350 | 卡片 2 | frontend/screenshots/pw_data_ai/ORCH_card_1.png |
| EV-20260729-351 | 按钮: 前往 Agent 管理查看角色库 | frontend/screenshots/pw_data_ai/ORCH_btn_0.png |
| EV-20260729-352 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/ORCH_btn_1.png |
| EV-20260729-353 | 按钮: 测试 | frontend/screenshots/pw_data_ai/ORCH_btn_2.png |
| EV-20260729-354 | 按钮: 详情 | frontend/screenshots/pw_data_ai/ORCH_btn_3.png |
| EV-20260729-355 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/ORCH_btn_4.png |
| EV-20260729-356 | 按钮: 测试 | frontend/screenshots/pw_data_ai/ORCH_btn_5.png |
| EV-20260729-357 | 智能编排 控制台警告 | frontend/screenshots/pw_data_ai/ORCH_console_warn.png |

### /agents — 智能体管理

- 状态：已加载并交互
- 模块缩写：AGT
- 本页缺陷：1 个
  - BEMCL-AGT-P2-001（P2）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-358 | 智能体管理 页面全貌 | frontend/screenshots/pw_data_ai/AGT_full.png |
| EV-20260729-359 | 智能体 内置智能体 | frontend/screenshots/pw_data_ai/AGT______.png |
| EV-20260729-360 | 智能体 自定义智能体 | frontend/screenshots/pw_data_ai/AGT_______.png |
| EV-20260729-361 | 智能体 模型路由 | frontend/screenshots/pw_data_ai/AGT_____.png |
| EV-20260729-362 | 智能体详情 | frontend/screenshots/pw_data_ai/AGT_detail.png |
| EV-20260729-363 | Tab:  内置智能体 13 | frontend/screenshots/pw_data_ai/AGT_tab_0.png |
| EV-20260729-364 | Tab:  自定义智能体 1 | frontend/screenshots/pw_data_ai/AGT_tab_1.png |
| EV-20260729-365 | Tab:  模型路由 14规划中 | frontend/screenshots/pw_data_ai/AGT_tab_2.png |
| EV-20260729-366 | 表格行 2 | frontend/screenshots/pw_data_ai/AGT_row_1.png |
| EV-20260729-367 | 表格行 3 | frontend/screenshots/pw_data_ai/AGT_row_2.png |
| EV-20260729-368 | 表格行 4 | frontend/screenshots/pw_data_ai/AGT_row_3.png |
| EV-20260729-369 | 表格行 5 | frontend/screenshots/pw_data_ai/AGT_row_4.png |
| EV-20260729-370 | 卡片 1 | frontend/screenshots/pw_data_ai/AGT_card_0.png |
| EV-20260729-371 | 按钮: 新建智能体 | frontend/screenshots/pw_data_ai/AGT_btn_0.png |
| EV-20260729-372 | 按钮: 详情 | frontend/screenshots/pw_data_ai/AGT_btn_1.png |
| EV-20260729-373 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/AGT_btn_2.png |
| EV-20260729-374 | 按钮: 详情 | frontend/screenshots/pw_data_ai/AGT_btn_3.png |
| EV-20260729-375 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/AGT_btn_4.png |
| EV-20260729-376 | 按钮: 详情 | frontend/screenshots/pw_data_ai/AGT_btn_5.png |

### /tools — 工具与连接器

- 状态：已加载并交互
- 模块缩写：TOOL
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-377 | 工具与连接器 页面全貌 | frontend/screenshots/pw_data_ai/TOOL_full.png |
| EV-20260729-378 | 表格行 2 | frontend/screenshots/pw_data_ai/TOOL_row_1.png |
| EV-20260729-379 | 表格行 3 | frontend/screenshots/pw_data_ai/TOOL_row_2.png |
| EV-20260729-380 | 表格行 4 | frontend/screenshots/pw_data_ai/TOOL_row_3.png |
| EV-20260729-381 | 表格行 5 | frontend/screenshots/pw_data_ai/TOOL_row_4.png |
| EV-20260729-382 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/TOOL_btn_0.png |
| EV-20260729-383 | 按钮: 详情 | frontend/screenshots/pw_data_ai/TOOL_btn_1.png |
| EV-20260729-384 | 按钮: 自检 | frontend/screenshots/pw_data_ai/TOOL_btn_2.png |
| EV-20260729-385 | 按钮: 详情 | frontend/screenshots/pw_data_ai/TOOL_btn_3.png |
| EV-20260729-386 | 按钮: 自检 | frontend/screenshots/pw_data_ai/TOOL_btn_4.png |
| EV-20260729-387 | 按钮: 详情 | frontend/screenshots/pw_data_ai/TOOL_btn_5.png |

### /topology — 调用关系

- 状态：已加载并交互
- 模块缩写：TOPO
- 本页缺陷：1 个
  - BEMCL-TOPO-P0-001（P0）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-388 | 调用关系 页面全貌 | frontend/screenshots/pw_data_ai/TOPO_full.png |
| EV-20260729-389 | 下拉选择 1 | frontend/screenshots/pw_data_ai/TOPO_select_0.png |
| EV-20260729-390 | 搜索 test | frontend/screenshots/pw_data_ai/TOPO_search.png |
| EV-20260729-391 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/TOPO_btn_0.png |

### /mappings — 映射控制台

- 状态：已加载并交互
- 模块缩写：MAP
- 本页缺陷：1 个
  - BEMCL-MAP-P3-001（P3）

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-392 | 映射控制台 页面全貌 | frontend/screenshots/pw_data_ai/MAP_full.png |
| EV-20260729-393 | 分页 1 | frontend/screenshots/pw_data_ai/MAP_page_0.png |
| EV-20260729-394 | 表格行 1 | frontend/screenshots/pw_data_ai/MAP_row_0.png |
| EV-20260729-395 | 表格行 2 | frontend/screenshots/pw_data_ai/MAP_row_1.png |
| EV-20260729-396 | 表格行 3 | frontend/screenshots/pw_data_ai/MAP_row_2.png |
| EV-20260729-397 | 下拉选择 1 | frontend/screenshots/pw_data_ai/MAP_select_0.png |
| EV-20260729-398 | 按钮: 刷 新 | frontend/screenshots/pw_data_ai/MAP_btn_0.png |
| EV-20260729-399 | 按钮: 详情 | frontend/screenshots/pw_data_ai/MAP_btn_1.png |
| EV-20260729-400 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/MAP_btn_2.png |
| EV-20260729-401 | 按钮: 详情 | frontend/screenshots/pw_data_ai/MAP_btn_3.png |
| EV-20260729-402 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/MAP_btn_4.png |
| EV-20260729-403 | 映射控制台 控制台警告 | frontend/screenshots/pw_data_ai/MAP_console_warn.png |

### /capability-center — 能力契约

- 状态：已加载并交互
- 模块缩写：CAP
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-404 | 能力契约 页面全貌 | frontend/screenshots/pw_data_ai/CAP_full.png |
| EV-20260729-405 | 能力契约详情抽屉 | frontend/screenshots/pw_data_ai/CAP_detail.png |
| EV-20260729-406 | 登记能力契约 表单提交 | frontend/screenshots/pw_data_ai/CAP_form_submit_1785321831687.png |

### /eval-center — 评估中心

- 状态：已加载并交互
- 模块缩写：EVAL
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-407 | 评估中心 页面全貌 | frontend/screenshots/pw_data_ai/EVAL_full.png |
| EV-20260729-408 | 表格行 1 | frontend/screenshots/pw_data_ai/EVAL_row_0.png |
| EV-20260729-409 | 下拉选择 1 | frontend/screenshots/pw_data_ai/EVAL_select_0.png |
| EV-20260729-410 | 卡片 1 | frontend/screenshots/pw_data_ai/EVAL_card_0.png |
| EV-20260729-411 | 卡片 2 | frontend/screenshots/pw_data_ai/EVAL_card_1.png |
| EV-20260729-412 | 卡片 3 | frontend/screenshots/pw_data_ai/EVAL_card_2.png |
| EV-20260729-413 | 按钮: 开始评估 | frontend/screenshots/pw_data_ai/EVAL_btn_0.png |
| EV-20260729-414 | 按钮: 刷新当前 | frontend/screenshots/pw_data_ai/EVAL_btn_1.png |
| EV-20260729-415 | 按钮: 发起评估 | frontend/screenshots/pw_data_ai/EVAL_btn_2.png |
| EV-20260729-416 | 按钮: 查 看 | frontend/screenshots/pw_data_ai/EVAL_btn_3.png |

### /dashboard — 管理看板

- 状态：已加载并交互
- 模块缩写：DASH
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-417 | 管理看板 页面全貌 | frontend/screenshots/pw_data_ai/DASH_full.png |
| EV-20260729-418 | 卡片 1 | frontend/screenshots/pw_data_ai/DASH_card_0.png |
| EV-20260729-419 | 卡片 2 | frontend/screenshots/pw_data_ai/DASH_card_1.png |
| EV-20260729-420 | 卡片 3 | frontend/screenshots/pw_data_ai/DASH_card_2.png |
| EV-20260729-421 | 卡片 4 | frontend/screenshots/pw_data_ai/DASH_card_3.png |
| EV-20260729-422 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/DASH_btn_0.png |
| EV-20260729-423 | 按钮: 今 日 | frontend/screenshots/pw_data_ai/DASH_btn_1.png |
| EV-20260729-424 | 按钮: 本 周 | frontend/screenshots/pw_data_ai/DASH_btn_2.png |
| EV-20260729-425 | 按钮: 本 月 | frontend/screenshots/pw_data_ai/DASH_btn_3.png |
| EV-20260729-426 | 按钮: 近30天 | frontend/screenshots/pw_data_ai/DASH_btn_4.png |
| EV-20260729-427 | 按钮: 近90天 | frontend/screenshots/pw_data_ai/DASH_btn_5.png |

### /control-plane — 控制平面

- 状态：已加载并交互
- 模块缩写：CTRL
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-428 | 控制平面 页面全貌 | frontend/screenshots/pw_data_ai/CTRL_full.png |
| EV-20260729-429 | 控制平面运行详情 | frontend/screenshots/pw_data_ai/CTRL_run_detail.png |
| EV-20260729-430 | 分页 1 | frontend/screenshots/pw_data_ai/CTRL_page_0.png |
| EV-20260729-431 | 分页 2 | frontend/screenshots/pw_data_ai/CTRL_page_1.png |
| EV-20260729-432 | 分页 3 | frontend/screenshots/pw_data_ai/CTRL_page_2.png |
| EV-20260729-433 | 表格行 1 | frontend/screenshots/pw_data_ai/CTRL_row_0.png |
| EV-20260729-434 | 表格行 2 | frontend/screenshots/pw_data_ai/CTRL_row_1.png |
| EV-20260729-435 | 表格行 3 | frontend/screenshots/pw_data_ai/CTRL_row_2.png |
| EV-20260729-436 | 表格行 4 | frontend/screenshots/pw_data_ai/CTRL_row_3.png |
| EV-20260729-437 | 表格行 5 | frontend/screenshots/pw_data_ai/CTRL_row_4.png |
| EV-20260729-438 | 下拉选择 1 | frontend/screenshots/pw_data_ai/CTRL_select_0.png |
| EV-20260729-439 | 卡片 1 | frontend/screenshots/pw_data_ai/CTRL_card_0.png |
| EV-20260729-440 | 卡片 2 | frontend/screenshots/pw_data_ai/CTRL_card_1.png |
| EV-20260729-441 | 卡片 3 | frontend/screenshots/pw_data_ai/CTRL_card_2.png |
| EV-20260729-442 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/CTRL_btn_0.png |
| EV-20260729-443 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/CTRL_btn_1.png |
| EV-20260729-444 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/CTRL_btn_2.png |

### /budgets — 预算看板

- 状态：已加载并交互
- 模块缩写：BUD
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-445 | 预算看板 页面全貌 | frontend/screenshots/pw_data_ai/BUD_full.png |
| EV-20260729-446 | 表格行 1 | frontend/screenshots/pw_data_ai/BUD_row_0.png |
| EV-20260729-447 | 下拉选择 1 | frontend/screenshots/pw_data_ai/BUD_select_0.png |
| EV-20260729-448 | 卡片 1 | frontend/screenshots/pw_data_ai/BUD_card_0.png |
| EV-20260729-449 | 按钮: 查询 | frontend/screenshots/pw_data_ai/BUD_btn_0.png |
| EV-20260729-450 | 按钮: 重置 | frontend/screenshots/pw_data_ai/BUD_btn_1.png |
| EV-20260729-451 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/BUD_btn_2.png |
| EV-20260729-452 | 按钮: 设置预算 | frontend/screenshots/pw_data_ai/BUD_btn_3.png |
| EV-20260729-453 | 按钮: 设置预算 | frontend/screenshots/pw_data_ai/BUD_btn_4.png |

### /value-report — 收益账单

- 状态：已加载并交互
- 模块缩写：VAL
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-454 | 收益账单 页面全貌 | frontend/screenshots/pw_data_ai/VAL_full.png |
| EV-20260729-455 | 收益账单选择项目 | frontend/screenshots/pw_data_ai/VAL_project.png |
| EV-20260729-456 | 表格行 1 | frontend/screenshots/pw_data_ai/VAL_row_0.png |
| EV-20260729-457 | 表格行 2 | frontend/screenshots/pw_data_ai/VAL_row_1.png |
| EV-20260729-458 | 表格行 3 | frontend/screenshots/pw_data_ai/VAL_row_2.png |
| EV-20260729-459 | 表格行 4 | frontend/screenshots/pw_data_ai/VAL_row_3.png |
| EV-20260729-460 | 下拉选择 1 | frontend/screenshots/pw_data_ai/VAL_select_0.png |
| EV-20260729-461 | 搜索 test | frontend/screenshots/pw_data_ai/VAL_search.png |
| EV-20260729-462 | 卡片 1 | frontend/screenshots/pw_data_ai/VAL_card_0.png |
| EV-20260729-463 | 卡片 2 | frontend/screenshots/pw_data_ai/VAL_card_1.png |
| EV-20260729-464 | 卡片 3 | frontend/screenshots/pw_data_ai/VAL_card_2.png |
| EV-20260729-465 | 卡片 4 | frontend/screenshots/pw_data_ai/VAL_card_3.png |
| EV-20260729-466 | 按钮: 基线设置 | frontend/screenshots/pw_data_ai/VAL_btn_0.png |
| EV-20260729-467 | 按钮: 导出 Markdown | frontend/screenshots/pw_data_ai/VAL_btn_1.png |
| EV-20260729-468 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/VAL_btn_2.png |
| EV-20260729-469 | 按钮: 新增规则 | frontend/screenshots/pw_data_ai/VAL_btn_3.png |
| EV-20260729-470 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/VAL_btn_4.png |
| EV-20260729-471 | 按钮: 编辑 | frontend/screenshots/pw_data_ai/VAL_btn_5.png |

### /users — 用户管理

- 状态：已加载并交互
- 模块缩写：USR
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-472 | 用户管理 页面全貌 | frontend/screenshots/pw_data_ai/USR_full.png |
| EV-20260729-473 | 用户新增弹窗（未提交） | frontend/screenshots/pw_data_ai/USR_add_modal.png |
| EV-20260729-474 | 表格行 2 | frontend/screenshots/pw_data_ai/USR_row_1.png |
| EV-20260729-475 | 表格行 3 | frontend/screenshots/pw_data_ai/USR_row_2.png |
| EV-20260729-476 | 下拉选择 1 | frontend/screenshots/pw_data_ai/USR_select_0.png |
| EV-20260729-477 | 下拉选择 2 | frontend/screenshots/pw_data_ai/USR_select_1.png |
| EV-20260729-478 | 搜索 test | frontend/screenshots/pw_data_ai/USR_search.png |
| EV-20260729-479 | 卡片 1 | frontend/screenshots/pw_data_ai/USR_card_0.png |
| EV-20260729-480 | 按钮: 新增用户 | frontend/screenshots/pw_data_ai/USR_btn_0.png |
| EV-20260729-481 | 按钮: 刷新 | frontend/screenshots/pw_data_ai/USR_btn_1.png |
| EV-20260729-482 | 按钮: 详情 | frontend/screenshots/pw_data_ai/USR_btn_2.png |
| EV-20260729-483 | 按钮: 修改 | frontend/screenshots/pw_data_ai/USR_btn_3.png |

### /settings — 系统设置

- 状态：已加载并交互
- 模块缩写：SET
- 本页缺陷：0 个

| 证据编号 | 说明 | 截图 |
|---|---|---|
| EV-20260729-484 | 系统设置 页面全貌 | frontend/screenshots/pw_data_ai/SET_full.png |
| EV-20260729-485 | 系统设置保存按钮点击（只读验证） | frontend/screenshots/pw_data_ai/SET_save_click.png |
| EV-20260729-486 | 下拉选择 3 | frontend/screenshots/pw_data_ai/SET_select_2.png |
| EV-20260729-487 | 卡片 1 | frontend/screenshots/pw_data_ai/SET_card_0.png |
| EV-20260729-488 | 卡片 2 | frontend/screenshots/pw_data_ai/SET_card_1.png |
| EV-20260729-489 | 卡片 3 | frontend/screenshots/pw_data_ai/SET_card_2.png |
| EV-20260729-490 | 卡片 4 | frontend/screenshots/pw_data_ai/SET_card_3.png |
| EV-20260729-491 | 按钮: 更 新 | frontend/screenshots/pw_data_ai/SET_btn_0.png |
| EV-20260729-492 | 按钮: 更 新 | frontend/screenshots/pw_data_ai/SET_btn_1.png |
| EV-20260729-493 | 按钮: 保存 LLM 配置 | frontend/screenshots/pw_data_ai/SET_btn_2.png |
| EV-20260729-494 | 按钮: 更 新 | frontend/screenshots/pw_data_ai/SET_btn_3.png |
| EV-20260729-495 | 按钮: 更 新 | frontend/screenshots/pw_data_ai/SET_btn_4.png |
| EV-20260729-496 | 按钮: 保存 AI4S 引擎配置 | frontend/screenshots/pw_data_ai/SET_btn_5.png |

## 4. 待确认项

- 本次脚本实际覆盖 25 个页面；需求清单中列出的 28 个页面有 3 个未在脚本中注册（请核对是否在其它测试脚本中覆盖）。
- 技术情报 / 知识图谱的 Paper-Material-Claim 关系依赖图谱节点标签，若节点类型未在 DOM 文本中展示，则标记为[待确认]。
- Agent SCP 风险策略若未在“工具路由策略”中显式出现，则标记为[待确认]。
- 部分表单的创建结果以服务端校验为准，前端未提示成功不代表接口失败。

## 5. 交付物

- Playwright 脚本：frontend/scripts/pw_data_ai_review.js
- 运行结果报告：doc/review_data_ai_playwright.md
- 截图目录：frontend/screenshots/pw_data_ai/
