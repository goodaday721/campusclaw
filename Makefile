# 交付与自检入口（宿主机执行，需 Docker Desktop 已启动）。
#
#   make up       一条命令构建启动六服务，缺 .env 时自动生成随机密钥，
#                 最后轮询 /health/ready 直到依赖就绪
#   make verify   提交前门禁：pytest + e2e + apitest 三条全绿
#
# Windows 未安装 make 时用等价入口：
#   powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1

.PHONY: up verify check-security

up:
	sh scripts/bootstrap.sh

verify:
	docker compose exec -T api python -m pytest -q
	docker compose exec -T api python e2e_test.py
	docker compose exec -T api python apitest/run_all.py

check-security:
	docker compose exec -T api python scripts/check_security.py
