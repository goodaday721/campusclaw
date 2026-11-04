# 依赖与运行基线（security-baseline）

- 采集日期：2026-11-04
- 运行时：容器内 Python 3.12.15，MySQL 8.0，Qdrant v1.12.1

## 依赖一致性

```text
$ docker compose exec -T api pip check
No broken requirements found.
```

- 根依赖在 `requirements.txt` 声明上下界；MCP 服务器在 `mcp-server/requirements.txt` 用 `==` 固定版本。
- 容器内不做临时 `pip install`。

## 漏洞扫描（SEC-06）

```text
[RED] SEC-06 依赖漏洞基线: pip-audit 未安装（工具缺失，本课保留的红项）
```

当前无法产出 CVE 清单。已登记的补救项：

1. 在 `Dockerfile` 中固定安装 `pip-audit`（版本写入 `requirements.txt`）。
2. 在 CI 或 `make check-security` 中执行 `pip-audit -r requirements.txt`。
3. 将结果附在本文件下一次迭代中，红项转绿后再关闭。

## 网络与端口基线

- 仅 `web` 映射宿主机端口 `${WEB_PORT:-8080}:80`。
- `api`、`db`、`qdrant`、`mcp-demo`、`worker` 均不映射宿主机端口。
- worker 复用 api 镜像，命令 `python -m app.worker`，仅依赖 `db`。

## 密钥基线

- `JWT_SECRET`、`DB_PASSWORD`、`DB_ROOT_PASSWORD`、`MCP_AUTH_TOKEN`、网关 key 只存在于本地 `.env`。
- 仓库扫描 130 个文件，0 命中（见 `reports/security-precheck.md` SEC-05）。
