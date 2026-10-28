# 第 7 课 · 验证记录

记录时间：2026-10-28。以下每条命令均在项目根目录执行，输出为当次真实结果。

## 一、规约校验

```bash
openspec validate --all --strict
```

结果：`Totals: 11 passed, 0 failed`（11 个能力主 spec）。能力与 Scenario 的对应关系见 [ability-scenarios.md](ability-scenarios.md)。

## 二、门禁三条命令（同一镜像，容器内执行）

```bash
docker compose exec -T api python -m pytest -q
docker compose exec -T api python e2e_test.py
docker compose exec -T api python apitest/run_all.py
```

| 命令 | 结果 |
| --- | --- |
| pytest | **134 passed**，0 failed（582.01s） |
| e2e_test.py（test-client 模式，含第 3–6 课场景） | **71 passed, 0 failed** |
| apitest/run_all.py（经 Nginx `http://web:80`） | **25 passed, 0 failed, 0 skipped**（21.5s） |

## 三、骨架基线（主环境实测）

```bash
curl http://localhost:8080/health
curl http://localhost:8080/health/ready
```

```
/health       -> 200 {"status":"ok"}
/health/ready -> 200 {"checks":{"db":{"ms":22.2,"status":"ok"},"qdrant":{"ms":21.6,"status":"ok"}},"status":"ok"}
```

访问日志（`docker compose logs api --tail`），每行一条 JSON，且 Werkzeug 默认访问日志已压制，不再出现非 JSON 行：

```
{"ts": "2026-10-28T03:10:20+0000", "level": "INFO", "request_id": "63161bd7ae4f43aa87c021079f3101cc", "method": "GET", "path": "/materials", "status": 200, "ms": 26.6, "class_id": 1, "user_id": 1}
{"ts": "2026-10-28T03:10:20+0000", "level": "INFO", "request_id": "8fe7aaad9dda41ce97742021152b02b8", "method": "POST", "path": "/search", "status": 200, "ms": 27.7, "class_id": 1, "user_id": 3}
```

## 四、交叉评审：独立目录从零启动（替代「组内另一人在自己机器上跑通」）

因 1 人独立完成，改为用**独立目录 + 独立 Compose 项目名 + 独立数据卷 + 不同端口**做一次等效的交叉验证，确保不存在「只在某人机器上能跑」的问题：

```powershell
git clone <本仓库> $env:TEMP\cc-verify2
copy .env $env:TEMP\cc-verify2\.env        # 只改 WEB_PORT=8090，其余保持
cd $env:TEMP\cc-verify2
docker compose -p ccverify up -d --build
```

结果：

| 检查项 | 结果 |
| --- | --- |
| 五个服务启动（web/api/db/qdrant/mcp-demo） | 全部 Started |
| `GET http://localhost:8090/health` | 200 `{"status":"ok"}` |
| `GET http://localhost:8090/health/ready` | 200 `{"checks":{"db":{"ms":12.2,"status":"ok"},"qdrant":{"ms":2.9,"status":"ok"}},"status":"ok"}` |
| `POST http://localhost:8090/auth/login`（teacher_a） | 200 |
| 访问日志 | 纯 JSON，三条依次为 /health、/health/ready、/auth/login |
| 验证后清理 | `docker compose -p ccverify down -v` 已删除验证用数据卷与网络 |

说明：该次启动**只有** `README.md` 的步骤（clone → 填 `.env` → 一条命令 → 查健康检查），未做任何口头补充，符合骨架完成现象。

## 五、密钥边界核查

```bash
git log --all --oneline -- .env          # 无输出
```

对 `.env` 中 `MCP_AUTH_TOKEN`、`AI_GATEWAY_KEY`、`DB_PASSWORD`、`DB_ROOT_PASSWORD` 四个真实值分别做 `git log -S <值>` 全历史检索，均为 clean（0 命中）。仓库只保留只写键名的 `.env.example`。

## 六、核查清单对照

| 维度 | 条目 | 状态 | 证据 |
| --- | --- | --- | --- |
| 仓库 | 地址可访问、教师有权限 | 通过 | GitHub public 仓库 |
| 仓库 | 按 README 从零跑起来 | 通过 | 第四节 |
| 仓库 | 历史无密钥明文 | 通过 | 第五节 |
| 规约 | 四份文件齐、`--strict` 通过 | 通过 | 第一节、`openspec/changes/archive/` |
| 规约 | 每能力 ≥1 组 Scenario，失败路径 ≥4 条 | 通过 | `ability-scenarios.md` |
| 规约 | 能力与 Scenario 一一对应 | 通过 | 同上 |
| 规范 | 五类 + 三类补充写成文件 | 通过 | `AGENTS.md`、`docs/standards/` |
| 规范 | 每条写明检查方式 | 通过 | 各文件「检查：」行 |
| 骨架 | 分层无反向依赖 | 通过 | `docs/standards/backend.md` 检查项 |
| 骨架 | 配置外置、缺失即启动失败 | 通过 | `app/config.py` |
| 骨架 | `/health` 免认证；`/health/ready` 返回依赖连通 | 通过 | 第三节 |
| 骨架 | 日志一行一条 JSON 且带请求标识 | 通过 | 第三节 |
| 交付 | 骨架标签 | 通过 | `v0.0.1-skeleton` |
| 交付 | 验证记录归档 | 通过 | 本文件 |
| 交付 | 交叉评审 | 通过 | 第四节（本人独立复现） |

## 七、已知偏差与取舍

- `/health` 只做存活判定，依赖探活放在 `/health/ready`：避免 DB 抖动导致存活探针重启正常进程；课件要求的「返回依赖连通状态」由后者满足。
- 单人完成，第三节交叉评审以「独立目录 + 独立项目名复现」替代组内他人复现，已在 `roles-and-contribution.md` 说明。
- 群组内既有历史提交未按 `YYYY-MM-DD-短横小写英文名` 命名（该规范自第 7 课起生效，仅约束新变更）；三个存量变更已在归档时补日期前缀。
