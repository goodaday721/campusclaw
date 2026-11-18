#!/bin/sh
# 一条命令起全栈（make up 的实现）：缺 .env 时按 .env.example 生成随机密钥，
# 构建并启动六个服务，然后轮询 /health/ready 直到依赖就绪。
#
# 只依赖 POSIX sh + docker compose；随机数优先用 openssl，缺失时读 /dev/urandom。
# 已有的 .env 一律原样保留，绝不覆盖真实密钥。
set -eu

cd "$(dirname "$0")/.."

log() { printf '[up] %s\n' "$1"; }

rand_hex() {
    bytes="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$bytes"
    else
        od -An -N"$bytes" -tx1 /dev/urandom | tr -d ' \n'
    fi
}

if [ ! -f .env ]; then
    log "未发现 .env，从 .env.example 生成随机密钥"
    db_pass=$(rand_hex 16)
    db_root=$(rand_hex 16)
    jwt_secret=$(rand_hex 32)
    mcp_token=$(rand_hex 16)
    # 逐行重写，避开 awk/sed -i 在不同发行版与 Git Bash 上的差异
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            DB_PASSWORD=*)      printf 'DB_PASSWORD=%s\n' "$db_pass" ;;
            DB_ROOT_PASSWORD=*) printf 'DB_ROOT_PASSWORD=%s\n' "$db_root" ;;
            JWT_SECRET=*)       printf 'JWT_SECRET=%s\n' "$jwt_secret" ;;
            MCP_AUTH_TOKEN=*)   printf 'MCP_AUTH_TOKEN=%s\n' "$mcp_token" ;;
            *)                  printf '%s\n' "$line" ;;
        esac
    done < .env.example > .env.tmp
    mv .env.tmp .env
    chmod 600 .env 2>/dev/null || true
    log "已生成 .env（EMBED_API_KEY / CHAT_API_KEY 需手工填写，留空时 AI 功能降级为 503）"
else
    log "沿用已有的 .env"
fi

log "构建并启动六个服务（首次构建需要几分钟）"
if ! docker compose up --build -d; then
    log "docker compose 启动失败，请确认 Docker Desktop 已运行"
    exit 1
fi

port=$(grep -E '^WEB_PORT=' .env | tail -1 | cut -d= -f2 || true)
[ -n "${port:-}" ] || port=8080
url="http://localhost:${port}/health/ready"

probe() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS "$url" >/dev/null 2>&1
    else
        docker compose exec -T api python -c \
            "import urllib.request; urllib.request.urlopen('http://localhost:5000/health/ready', timeout=2)" \
            >/dev/null 2>&1
    fi
}

log "等待就绪检查 ${url}"
i=0
while [ "$i" -lt 120 ]; do
    if probe; then
        docker compose ps
        printf '\n登录页: http://localhost:%s/login\n演示账号: teacher_a / student_a / teacher_b / student_b\n' "$port"
        exit 0
    fi
    i=$((i + 1))
    sleep 2
done

log "就绪检查超时（240 秒），api 最近日志："
docker compose logs --tail=40 api
exit 1
