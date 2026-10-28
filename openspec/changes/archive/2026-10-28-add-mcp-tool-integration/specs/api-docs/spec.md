## ADDED Requirements

### Requirement: MCP 管理接口的 OpenAPI 描述

`/openapi.json` SHALL 描述第 6 课新增端点：`GET/POST /api/mcp/servers`、`PUT/DELETE /api/mcp/servers/{id}`、`POST /api/mcp/servers/{id}/connect`、`POST /api/mcp/servers/{id}/disconnect`、`GET /api/mcp/servers/{id}/tools`、`GET /api/mcp/call-logs`，含入参、出参、错误码（401/403/404/409/400/502）与 bearerAuth 安全要求；响应 schema 中 MUST NOT 出现令牌原文字段（只有 `hasToken`）。浏览器 SHALL 能打开 Swagger 页并试调登记/连接/工具/技能保存等主要接口。

#### Scenario: Swagger 可见可试调

- **WHEN** 打开 `/swagger/index.html`
- **THEN** 能看到 MCP 全部端点定义，可 Authorize 后试调 connect 与 tools 接口，登记接口的响应示例只含 hasToken

#### Scenario: 未授权试调被拒

- **WHEN** 不填 Authorize 直接试调 `GET /api/mcp/servers`
- **THEN** 返回 401，与文档标注的错误码一致

#### Scenario: 学生身份被拒

- **WHEN** 以学生 token 试调 `POST /api/mcp/servers`
- **THEN** 返回 403，与文档标注的错误码一致

#### Scenario: 不存在的服务器与同名登记

- **WHEN** 试调 `POST /api/mcp/servers/999/connect` 或登记本班已存在的服务器名
- **THEN** 分别返回 404 与 409，均与文档标注一致

#### Scenario: 服务器不可达时连接失败

- **WHEN** 试调 `POST /api/mcp/servers/{id}/connect` 且目标服务器地址不可达
- **THEN** 返回 502 与可读原因，服务器状态保持未连接，文档标注的错误码与之一致

#### Scenario: 文档不含令牌原文

- **WHEN** 检查 `/openapi.json` 中 MCP 服务器相关 schema 与示例
- **THEN** 只出现布尔 `hasToken`，不出现 token 字段名或令牌值
