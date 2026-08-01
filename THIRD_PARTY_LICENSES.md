# 第三方开源组件许可证清单

> BatteryEMCL Lab — 第三方依赖合规文档
>
> 本文档列出版本 v0.1.0 中随产品分发的所有第三方开源组件及其许可证信息。
>
> **部署模式说明**：ASKCOS 逆合成引擎为外部服务，由客户自行部署，
> BatteryEMCL Lab 仅通过 HTTP API 调用，不随产品分发 ASKCOS 代码或数据。
> 因此 ASKCOS 相关组件的许可证义务由部署方（客户）承担。

---

## 一、主项目前端依赖（frontend/package.json）

### 运行时依赖

| 组件 | 版本 | 许可证 | 上游地址 |
|------|------|--------|----------|
| Vue | ^3.5.13 | MIT | https://github.com/vuejs/core |
| Vue Router | ^4.4.5 | MIT | https://github.com/vuejs/router |
| Pinia | ^2.2.4 | MIT | https://github.com/vuejs/pinia |
| Ant Design Vue | ^4.2.3 | MIT | https://github.com/vueComponent/ant-design-vue |
| Axios | ^1.7.7 | MIT | https://github.com/axios/axios |
| ECharts | ^5.5.1 | Apache-2.0 | https://github.com/apache/echarts |
| Playwright | ^1.62.0 | Apache-2.0 | https://github.com/microsoft/playwright |
| SheetJS (xlsx) | ^0.18.5 | Apache-2.0 | https://github.com/SheetJS/sheetjs |

### 开发依赖

| 组件 | 版本 | 许可证 | 上游地址 |
|------|------|--------|----------|
| Vite | ^5.4.11 | MIT | https://github.com/vitejs/vite |
| @vitejs/plugin-vue | ^5.2.1 | MIT | https://github.com/vitejs/vite-plugin-vue |

---

## 二、主项目后端依赖（pyproject.toml）

### 核心依赖

| 组件 | 版本 | 许可证 | 商业化风险 |
|------|------|--------|------------|
| FastAPI | >=0.100 | MIT | 无 |
| uvicorn | >=0.23 | BSD-3-Clause | 无 |
| Pydantic | >=2.0 | MIT | 无 |
| SQLAlchemy | >=2.0 | MIT | 无 |
| Alembic | >=1.13 | MIT | 无 |
| httpx | >=0.24 | BSD-3-Clause | 无 |
| requests | >=2.31 | Apache-2.0 | 无 |
| python-dotenv | >=1.0 | BSD-3-Clause | 无 |
| openpyxl | >=3.1 | MIT | 无 |
| numpy | >=1.24 | BSD-3-Clause | 无 |
| pandas | >=2.0 | BSD-3-Clause | 无 |
| RDKit | >=2023.3 | BSD-3-Clause | 无（注意算法专利） |
| PyMatGen | >=2023.10 | MIT | 无 |
| PySCF | >=2.4 | Apache-2.0 | 无 |
| watchdog | >=3.0 | Apache-2.0 | 无 |
| **ASE** | **>=3.22** | **LGPL-2.1+** | ⚠️ 分发时需提供源码 |
| **psycopg** | **>=3.1** | **LGPL-3.0** | 低（含 libpq 链接例外） |

### 可选依赖（ML）

| 组件 | 版本 | 许可证 | 商业化风险 |
|------|------|--------|------------|
| PyTorch | >=2.0 | BSD-3-Clause | 无 |
| scikit-learn | >=1.3 | BSD-3-Clause | 无 |

### 开发工具

| 组件 | 版本 | 许可证 |
|------|------|--------|
| pytest | >=7.4 | MIT |
| pytest-cov | >=4.1 | MIT |
| pytest-asyncio | >=0.21 | Apache-2.0 |
| ruff | >=0.1 | MIT |

### 构建工具

| 组件 | 版本 | 许可证 |
|------|------|--------|
| setuptools | >=68.0 | MIT |
| wheel | — | MIT |

---

## 三、外部服务：ASKCOS 逆合成引擎（客户自行部署）

> ASKCOS 为独立的外部 HTTP 服务，由客户自行部署和运维。
> BatteryEMCL Lab 仅通过 `httpx` 调用其 HTTP API（`GET /api/treebuilder/`），
> 不包含 ASKCOS 的任何代码或数据，不参与 ASKCOS 的编译、链接或分发。
>
> **许可证义务归属**：ASKCOS 及其所有子依赖的许可证合规责任由部署方（客户）承担。

### ASKCOS 核心组件（供客户参考）

| 组件 | 许可证 | 备注 |
|------|--------|------|
| ASKCOS 引擎 (askcos-tmp) | MPL-2.0 | 文件级 copyleft，商业可用 |
| ASKCOS 反应数据 (askcos-data) | **CC BY-NC-SA 4.0** | 禁止商业使用，客户需自行获取商业授权 |

### ASKCOS 内部依赖（供客户参考，与本产品无关）

| 关键风险组件 | 许可证 | 风险 |
|-------------|--------|------|
| uWSGI | GPL-2.0（含链接例外） | 客户需评估 |
| mysqlclient | GPL-2.0 | 客户需评估 |
| CairoSVG | LGPL-3.0 | 客户需评估 |
| pycairo | LGPL-2.1 / MPL-1.1 | 客户需评估 |

其余 22 个子依赖（Django, Celery, TensorFlow, Redis 等）均为 BSD/MIT/Apache-2.0，商业友好。

---

## 四、Docker 基础设施（随产品分发）

| 镜像/组件 | 版本 | 许可证 | 风险 |
|-----------|------|--------|------|
| postgres | 16-alpine | PostgreSQL License | 无 |

---

## 五、外部 API 服务

以下为通过网络调用的外部服务，不受开源许可证约束，但需确认其服务条款：

| 服务 | 默认地址 | 用途 | 部署方 |
|------|----------|------|--------|
| InternLM | https://chat.intern-ai.org.cn/api/v1 | LLM 推理 / 逆合成分析 | 第三方 |
| LongCat | https://api.longcat.chat/openai | LLM 推理 | 第三方 |
| Materials Project | https://api.materialsproject.org | 材料数据查询 | 第三方 |
| SCP Hub | https://scp.intern-ai.org.cn/api/v1/mcp | 科学计算工具调用 | 第三方 |
| ASKCOS | http://localhost:5000 | 逆合成规划（可选） | **客户** |

---

## 六、商业化风险汇总

### 产品自身风险（BatteryEMCL Lab 需承担）

| 等级 | 组件 | 许可证 | 条件 | 满足方式 |
|------|------|--------|------|----------|
| 🟡 | ASE | LGPL-2.1+ | 分发时提供源码 | SaaS 模式无需分发；本地部署提供源码链接 |
| 🟡 | psycopg | LGPL-3.0 | 分发时提供源码 | 含 libpq 链接例外，实际风险低 |
| 🟢 | 其余 26 个组件 | MIT/BSD/Apache-2.0 | 保留版权声明 | 已满足（见 NOTICE 文件） |

### 客户侧风险（由客户承担，供参考）

| 等级 | 组件 | 许可证 | 说明 |
|------|------|--------|------|
| 🔴 | ASKCOS Data | CC BY-NC-SA 4.0 | 客户商业使用需获取授权 |
| 🟡 | uWSGI | GPL-2.0 | ASKCOS 内部依赖，客户需评估 |
| 🟡 | mysqlclient | GPL-2.0 | ASKCOS 内部依赖，客户需评估 |

---

## 七、合规检查清单

### BatteryEMCL Lab 侧（产品交付前）

- [x] **LICENSE** 文件已放置于项目根目录
- [x] **NOTICE** 文件已包含所有 Apache-2.0 组件的版权声明
- [x] **THIRD_PARTY_LICENSES.md**（本文档）已随产品分发
- [ ] 外部 API 服务（InternLM, Materials Project, LongCat, SCP Hub）的商业使用条款已确认
- [ ] 产品界面中提供第三方许可证查看入口（如 "关于 → 开源许可"）
- [ ] 如以二进制形式分发，需附带 ASE 的 LGPL 源码获取方式说明
- [ ] 算法专利 FTO 分析已完成（RDKit, PySCF, PyMatGen 相关算法）

### 客户侧（交付时告知）

- [ ] 客户已知悉 ASKCOS 需自行部署，不在本产品交付范围内
- [ ] 客户已知悉 ASKCOS Data 为 CC BY-NC-SA 4.0，商业使用需获取授权
- [ ] 如客户不部署 ASKCOS，系统可切换 `ENGINE_MODE=internlm` 使用 InternLM 替代
- [ ] 建议客户在部署 ASKCOS 前自行评估 uWSGI (GPL-2.0) 和 mysqlclient (GPL-2.0) 的合规性

---

*文档生成日期：2026-07-26*
*基于项目 v0.1.0 依赖快照生成，依赖版本更新后需同步更新本文档*