# api-docs Specification

## Purpose

让外部调用方与浏览器在不读源码的前提下看清每个对外端点的入参、出参、错误码与鉴权要求：`/openapi.json` 提供机器可读的 OpenAPI 3 文档，`/swagger/index.html` 提供可直接试调的浏览器界面。

## Requirements

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

#### Scenario: 未授权试调返回 401

- **WHEN** 不填 Authorize 直接试调 `GET /api/skills`
- **THEN** 返回 401，与文档标注的错误码一致

#### Scenario: 学生越权试调返回 403

- **WHEN** 以学生 token 试调 `POST /api/skills`
- **THEN** 返回 403，与文档标注的错误码一致

#### Scenario: 非法入参返回 400

- **WHEN** 试调 `POST /api/skills` 且 body 缺少 `source` 字段
- **THEN** 返回 400 与可读错误，不产生技能记录

#### Scenario: 不存在的资源返回 404

- **WHEN** 试调 `GET /api/conversations/999999`
- **THEN** 返回 404，与文档标注一致

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

### Requirement: 作业与批改接口的 OpenAPI 描述

`/openapi.json` SHALL 描述第 8 课新增端点：`POST/GET /api/assignments`、`POST /api/assignments/{id}/submissions`、`GET /api/submissions/{id}`，含入参、出参、状态码（201/202/200/400/401/403/404）与 bearerAuth 安全要求；提交端点的响应 MUST 描述 `taskId` 与 `status` 字段。浏览器 SHALL 能在 Swagger 页试调建作业与提交接口。

#### Scenario: 文档含四个新端点

- **WHEN** 请求 `GET /openapi.json`
- **THEN** paths 中包含 `/api/assignments`（POST/GET）、`/api/assignments/{id}/submissions`（POST）、`/api/submissions/{id}`（GET）

#### Scenario: 提交端点描述 202 与任务标识

- **WHEN** 查阅 `POST /api/assignments/{id}/submissions` 定义
- **THEN** 成功响应标注 202 且 schema 含 `taskId` 与 `status`

#### Scenario: 未授权试调返回 401

- **WHEN** 不填 Authorize 直接试调 `GET /api/assignments`
- **THEN** 返回 401，与文档标注的错误码一致

#### Scenario: 学生越权试调返回 403

- **WHEN** 以学生 token 试调 `POST /api/assignments`
- **THEN** 返回 403，与文档标注的错误码一致

#### Scenario: 非法入参与不存在资源

- **WHEN** 试调 `POST /api/assignments` 缺少必填字段，或 `GET /api/submissions/999999`
- **THEN** 分别返回 400 与 404，均与文档标注一致
