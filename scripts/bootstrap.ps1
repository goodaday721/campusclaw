# 一条命令起全栈（Windows 入口，无需 make）：缺 .env 时按 .env.example 生成随机
# 密钥，构建并启动六个服务，然后轮询 /health/ready 直到依赖就绪。
# 已有的 .env 一律原样保留，绝不覆盖真实密钥。
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Write-Log([string]$Message) {
    Write-Host "[up] $Message"
}

function New-Hex([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    return (($buffer | ForEach-Object { $_.ToString('x2') }) -join '')
}

if (-not (Test-Path '.env')) {
    Write-Log '未发现 .env，从 .env.example 生成随机密钥'
    Copy-Item '.env.example' '.env'

    $content = Get-Content '.env' -Raw
    $content = $content -replace '(?m)^DB_PASSWORD=.*$', "DB_PASSWORD=$(New-Hex 16)"
    $content = $content -replace '(?m)^DB_ROOT_PASSWORD=.*$', "DB_ROOT_PASSWORD=$(New-Hex 16)"
    $content = $content -replace '(?m)^JWT_SECRET=.*$', "JWT_SECRET=$(New-Hex 32)"
    $content = $content -replace '(?m)^MCP_AUTH_TOKEN=.*$', "MCP_AUTH_TOKEN=$(New-Hex 16)"
    # 必须写无 BOM 的 UTF-8：带 BOM 会让 compose 把首个键读成 "\ufeffDB_HOST"
    [System.IO.File]::WriteAllText(
        (Join-Path $root '.env'),
        $content,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Log '已生成 .env（EMBED_API_KEY / CHAT_API_KEY 需手工填写，留空时 AI 功能降级为 503）'
}
else {
    Write-Log '沿用已有的 .env'
}

Write-Log '构建并启动六个服务（首次构建需要几分钟）'
docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Log 'docker compose 启动失败，请确认 Docker Desktop 已运行'
    exit 1
}

$port = 8080
$portLine = Select-String -Path '.env' -Pattern '^WEB_PORT=' | Select-Object -Last 1
if ($portLine) {
    $value = ($portLine.Line -split '=', 2)[1].Trim()
    if ($value) { $port = $value }
}
$url = "http://localhost:$port/health/ready"

Write-Log "等待就绪检查 $url"
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    }
    catch {
        # 503/连接失败都继续等：容器还在启动或依赖未就绪
    }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Log '就绪检查超时（240 秒），api 最近日志：'
    docker compose logs --tail=40 api
    exit 1
}

docker compose ps
Write-Host ''
Write-Host "登录页: http://localhost:$port/login"
Write-Host '演示账号: teacher_a / student_a / teacher_b / student_b'
