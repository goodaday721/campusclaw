## ADDED Requirements

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
