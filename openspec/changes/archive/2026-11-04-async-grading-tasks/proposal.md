# 变更：add-async-grading-tasks

## Why

第 8 课要求把一次长耗时写操作从同步请求里拆出去：提交后立刻返回可轮询的任务标识，由独立消费者完成重活。小组项目此前把「作业提交与批改」和「异步任务队列」列为不做项；本课任务清单明确要求演示链路「登录取令牌 → 提交作业返回 202 与任务标识 → 轮询 pending → running → succeeded」，并要为第 9 课的并发与事务判据留下可复现证据，因此本次推翻这两条非目标。

## What Changes

- 新增作业与提交：教师建作业（标题、题目、参考答案），学生按班级提交文本答案；重复提交不产生第二份结果。
- 新增任务表 `jobs` 与独立 `worker` 容器：以数据库作为队列，消费者用 `FOR UPDATE SKIP LOCKED` 领取，进程重启时重新入队超时的 running 任务，保证至少一次投递 + 幂等写结果。
- 新增批改服务：worker 调课程网关对提交答案给出分数与评语；网关不可用或解析失败按重试上限置 failed，并把原因写回提交记录。
- 提交接口返回 `202 Accepted` 与 `taskId`；新增轮询接口，学生只能看自己的提交，跨班与越权一律 404。
- 开放接口：`POST/GET /api/assignments`、`POST /api/assignments/<id>/submissions`、`GET /api/submissions/<id>`，全部进入 `/openapi.json`。
- 容器数由五变六（新增 `worker`，仍只有 web 映射宿主机端口）。
- 同步更新 `AGENTS.md`、`docs/standards/{backend,data,ops,testing}.md` 与 `README.md` 中的服务数、异步语义与验证路径。

## Non-Goals

- 不做多人协作批改、不做按班级排名与统计报表。
- 不做消息中间件（不引入 Redis / RabbitMQ / Celery），队列就是数据库表。
- 不做作业附件上传，提交内容只有文本。
- 不做批改结果的人工复核流程。
- 不做多消费者横向扩展与优先级队列。

## Capabilities

- `async-jobs`（新增）：任务表、领取语义、重试与重新入队、恰好一次效果。
- `grading-tasks`（新增）：作业创建、学生提交、202 + 轮询、班级隔离、幂等提交、批改落库。
- `api-docs`（修改）：四个新端点进入 OpenAPI 文档。
