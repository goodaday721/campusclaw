## ADDED Requirements

### Requirement: OpenAPI 接口描述

系统 SHALL 在 `GET /openapi.json` 提供 OpenAPI 3 文档，覆盖全部对外端点（含既有登录/材料/检索/问答与新提示词/技能/智能体/会话端点）；每个操作 MUST 描述路径与方法、入参（请求体 schema 与查询参数）、出参（响应 schema）、错误码（401/400/403/404/503）以及是否需要登录（需要登录的操作标注 `bearerAuth` security，并在 `components.securitySchemes` 声明 Bearer 认证方案）。

#### Scenario: 文档可被机器读取

- **WHEN** 客户端请求 `GET /openapi.json`
- **THEN** 响应为 200 且 body 是可解析的合法 OpenAPI 3 JSON，包含全部对外端点与 bearerAuth 安全方案

#### Scenario: 需登录端点在文档中标注

- **WHEN** 查阅 `POST /api/conversations` 等受保护操作的定义
- **THEN** 其 security 标注为 bearerAuth，而 `/health` 等公开端点无此标注

### Requirement: 浏览器可用的 Swagger UI

系统 SHALL 在 `GET /swagger/index.html` 提供 Swagger UI 页面（静态引用 CDN 的 swagger-ui-dist，`url` 指向本服务 `/openapi.json`），浏览器可直接打开查看文档并试调接口（含粘贴 Bearer token 的 Authorize 入口）。

#### Scenario: 打开 Swagger UI 并试调

- **WHEN** 浏览器打开 `/swagger/index.html`，通过 Authorize 填入登录返回的 token 后试调 `GET /api/prompt`
- **THEN** 页面正常渲染文档，试调请求携带 `Authorization: Bearer <token>` 并返回 200 与真实数据
