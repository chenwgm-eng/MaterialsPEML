# MaterialsPEML Lab

**MaterialsPEML Lab 是面向高分子改性塑料（kingfa 领域）的 AI 研发平台。**

> 英文版见 [README.en.md](README.en.md)

---

## 简介

从"一句话研发目标"出发，自动完成候选识别 → 配方设计 → 工艺规划 → 业务审批 → 实验验证 → 反哺策略的研发闭环。

核心定位：

- 数据可信度四档（实测 measured / 模拟 simulated / 模型预测 predicted / 工程估算 estimated），每个值都回答"这是哪来的、靠不靠谱"
- 实验闭环与 ECML：验证精度标尺（预测 vs 实际 MAPE）
- 领域包机制：默认材料体系、配方模板、参考范围
- 企业级能力：多租户权限 + 细粒度审批 + 全链路日志

## 技术栈

- **后端**：FastAPI + SQLAlchemy + PostgreSQL（`postgresql+psycopg://...`），数据库迁移用 Alembic
- **前端**：Vue 3 + Vite + Ant Design Vue 4
- **智能能力**：LLM（InternLM 等）+ MCP 科学工具（SCP）+ 本地生成/预测器
- **测试**：pytest（后端）+ Playwright（前端 E2E 巡检）

## 快速开始

```bash
# 后端（端口 8200）
python -m uvicorn battery_materials_agent.api:app --host 0.0.0.0 --port 8200

# 前端（Vite，端口 5173）
cd frontend && npm install && npm run dev

# 生产构建
cd frontend && npm run build
```

数据库：

```
postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl
```

## 运行测试

```bash
# 后端单测
python -m pytest tests/unit/test_two_layer_workflow.py tests/unit/test_process_deepening_service.py -q

# 前端 E2E 巡检（需 5173 + 8200 双活）
cd frontend && node tests/deep-audit.mjs
```

## 目录结构

```
battery_materials_agent/     # 后端 FastAPI 服务
  agent.py                   #   BatteryMaterialsAgent 门面 + MCP 工具注册
  api.py                     #   REST API（单体应用入口）
  experiment/               #   候选/工艺/设备/实验控制存储
  generation/               #   候选生成器（晶体/高分子）
  ecml/                      #   ECML 闭环引擎
  hybrid/                    #   研发流水线编排
  domain_packs/              #   领域包（battery / kingfa）
frontend/                    # Vue 3 前端
alembic/versions/            # 数据库迁移
docs/                        # 产品说明书、用户手册、ADR 设计决策
tests/unit/                  # pytest 单元测试
```

## 联系我们

对本项目感兴趣、希望合作或获取商业授权，欢迎联系：

**wangmiao.chen@cheeryell.com**

## 许可证

[PolyForm Noncommercial License 1.0.0](LICENSE) — 仅允许非商业用途；商业用途需另行授权。
