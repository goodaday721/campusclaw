## ADDED Requirements

### Requirement: MCP 管理接口的 OpenAPI 描述

`/openapi.json` SHALL 描述第 6 课新增端点：`GET/POST /api/mcp/servers`、`PUT/DELETE /api/mcp/servers/{id}`、`POST /api/mcp/servers/{id}/connect`、`POST /api/mcp/servers/{id}/disconnect`、`GET /api/mcp/servers/{id}/tools`、`GET /api/mcp/call-logs`，含入参、出参、错误码（401/403/404/409/400/502）与 bearerAuth 安全要求；响应 schema 中 MUST NOT 出现令牌原文字段（只有 `hasToken`）。浏览器 SHALL 能打开 Swagger 页并试调登记/连接/工具/技能保存等主要接口。

#### Scenario: Swagger 可见可试调

- **WHEN** 打开 `/swagger/index.html`
- **THEN** 能看到 MCP 全部端点定义，可 Authorize 后试调 connect 与 tools 接口，登记接口的响应示例只含 hasToken
