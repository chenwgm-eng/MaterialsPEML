# 开发代理保留 /api 前缀：由后端中间件统一重写并标记 API 请求

开发模式下 vite proxy 将 `/api` 前缀**原样转发**到后端（不做 rewrite），由后端 `rewrite_api_prefix_middleware` 统一重写路径并标记 `is_api_request`；生产模式下后端直接 serve 前端 dist 时同一中间件处理相同的 `/api` 前缀。

## 背景

系统存在与 SPA 前端路由同名的 API 路径（如 `/ecml/runs`、`/agents`、`/tools`）。浏览器直接访问这些路径应返回 SPA 页面，而 API 请求应返回 JSON——后端通过 `is_api_request` scope 标记区分二者。早期 vite proxy 配置了 `rewrite: (p) => p.replace(/^\/api/, '')`，导致开发模式下后端收到的请求已无 `/api` 前缀、标记永远不生效，`/ecml/runs` 等 API 被 `_serve_spa_if_browser` 当作浏览器导航返回 index.html，前端解析失败表现为页面数据恒为空。

## 决策

- vite proxy **不 rewrite**，`/api` 前缀保留转发到 8200。
- 后端 `rewrite_api_prefix_middleware` 为唯一重写点：命中 `/api` 前缀时改写 `request.scope["path"]` 并置 `is_api_request=True`。
- 开发与生产两种访问方式行为一致（均经同一中间件），前端 axios baseURL 固定为 `/api` 无环境差异。

## 考虑过的替代方案

- **vite proxy 剥掉前缀（rewrite）**：被否决。开发模式下后端无法识别 API 请求，与 SPA 同名路由的接口会返回 index.html。
- **后端仅按 Accept 头区分（text/html vs application/json）**：被否决。axios 等客户端 Accept 头不可控，语义弱于显式路径标记。

## 后果

- 任何新增的 `/api` 路由都不需要在前端 proxy 处配置 rewrite 或特殊处理。
- 新增与 SPA 路由同名的 GET 路由时，若需要区分浏览器导航与 API 请求，须沿用 `_serve_spa_if_browser` + `is_api_request` 模式（或确保该路由无需区分）。
- vite.config.js 的 proxy 段不得重新引入 rewrite，否则回归 `/ecml/runs` 返回 HTML 的缺陷。
