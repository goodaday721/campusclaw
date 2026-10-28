# 评审与完成定义

适用范围：每次 openspec 变更的评审与收尾。一人独立完成时本文件同时充当自评清单。

## 完成定义

- 一句话：当该变更的 tasks 全部勾选、三条门禁命令全绿、且 AGENTS.md 与 `docs/standards/` 已同步更新时，变更才算完成。
  检查：`git status --short` 无未提交改动；三条门禁命令退出码均为 0；`git diff --stat AGENTS.md docs/standards/` 非空（行为变更时）。
- 完成不是"代码能跑"：未写用例、未更新规范、未更新 README 验证路径，一律视为未完成。
  检查：`git diff --stat tests/ README.md` 与改动范围对应。

## 变更规模

- 一次变更只做一件事；净增超过 12 个文件或 600 行（含测试与文档）先拆成多个 change。
  检查：`git diff --stat HEAD` 的文件数与增删行数；`ls openspec/changes` 只出现 `archive` 与一个进行中的变更目录。
- 不夹带无关重构：同一提交里不出现与 proposal 无关的格式化、改名、依赖升级。
  检查：`git diff --stat` 逐文件对照 proposal 的 What Changes 列表。
- 一个变更不跨越两课：第 7 课的规范文档不修改 app/、migrations/、tests/ 的行为代码。
  检查：`git status --short app migrations tests` 本次为空。

## 评审检查表

| 栏目 | 必查项 | 证据落点 |
|---|---|---|
| 功能 | proposal 的每条 What Changes 都有实现与用例 | `git diff`、`tests/` 对应用例名 |
| 失败路径 | 400/401/403/404/409/413/415/502/503 各有至少一条用例，且断言无副作用 | `tests/test_*` 的失败用例；`tests/test_materials.py::TestUploadConstraints` |
| 权限 | 学生写接口 403、跨班 404、伪造 `class_id` 与 `system` 消息被忽略 | `tests/test_role.py`、`tests/test_isolation.py`、`tests/test_retrieval.py::TestSearchClassIsolation` |
| 证据 | 门禁三条命令的输出、/health 与 /health/ready 的返回、关键日志行 | 提交说明或评审记录里粘贴的终端输出 |

- 四栏齐全才可归档 change；缺栏视为评审未通过。
  检查：`ls openspec/changes/archive/<日期>-<变更名>/` 存在且 tasks 全 `[x]`。
- 权限栏必须含"绕过前端直调"的证据，不能只测界面按钮。
  检查：`tests/test_role.py::TestBypassFrontend::test_student_bypass_frontend_still_403`、`tests/test_isolation.py::TestDirectURLBypass`。

## 门禁必跑命令

- 门禁命令固定五条，缺一条视为未完成：pytest、e2e、apitest、运行态核对、openspec 校验。
  检查：依次运行 `docker compose exec -T api python -m pytest -q`、`docker compose exec -T api python e2e_test.py`（或宿主机 `python e2e_test.py --http`）、`docker compose exec -T api python apitest/run_all.py`、`docker compose ps` 五服务 running 且 `curl http://localhost:8080/health` 返回 `{"status":"ok"}`、`openspec validate --all --strict --no-interactive` 末行 `Totals: 11 passed, 0 failed` 且 `openspec list` 输出 `No active changes found.`；任一非 0 即阻断。

## 例外书面化

- 任何偏离 AGENTS.md 或 `docs/standards/` 的做法必须在本次 change 的 `design.md`「例外」小节写清四项：违反的条目、原因、影响面、补救时点。
  检查：`grep -n "## 例外" openspec/changes/*/design.md` 有对应小节（未归档时）。
- 例外不得长期存在：同一例外只允许一个变更周期，到期未修则在 tasks 里留一条未完成项。
  检查：`grep -rn "TODO\|例外" openspec/changes/*/tasks.md`。
- 不得用"课程要求时间紧"作为例外理由；没有可验证的补救计划等于未通过评审。
  检查：评审记录里例外四项齐全（人工核对）。

## 个人贡献记录模板

一人独立完成时，三角色由同一人兼任，按下面三段各写一行事实 + 一行证据，附在提交说明或 change 的 tasks 末尾。

```
角色一 产品与设计：负责 <本变更范围> 的页面文案、四态、术语与验收口径。
  证据：docs/standards/product.md 对应条目；README 验证路径第 <n> 条。
角色二 后端与安全：负责 <分层/接口/权限> 的实现与越权防护。
  证据：app/ 下 <文件>；tests/test_<模块>.py 的 <用例名>。
角色三 测试与部署：负责门禁命令执行、数据隔离与回滚演练。
  证据：pytest / e2e_test.py / apitest.run_all 输出；docker compose ps 与 /health 返回。
```

- 每段证据必须能直接打开，不写"已完成测试"这类不可核对的措辞。
  检查：把证据路径逐条粘贴进终端可复现（`docker compose exec -T api python -m pytest -q tests/test_<模块>.py`）。
- 三角色都写，不允许只写"开发"一栏；一人兼任不是省略角色分工的理由。
  检查：记录中 `角色一/角色二/角色三` 三段齐全。
