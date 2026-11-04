"""Lesson-8 minimal security pre-check (SEC-05 / SEC-06).

Run inside the api container (the image carries the repo):
    docker compose exec -T api python scripts/check_security.py
or via `make check-security`.

SEC-05 scans tracked-ish source/text files for high-risk credential literals
and for env assignments in non-example files. SEC-06 attempts a dependency
vulnerability audit; when the audit tool is absent it reports RED instead of
silently passing (lesson-8 requires keeping at least one red finding).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git", "uploads", "data", "node_modules", "__pycache__", ".pytest_cache",
    ".venv", "venv", "reports",
}
TEXT_SUFFIXES = {
    ".py", ".yml", ".yaml", ".json", ".md", ".txt", ".conf", ".sql", ".js",
    ".html", ".css", ".cfg", ".ini", ".example",
}

# Literal-value patterns that should never reach the repo.
SECRET_PATTERNS = [
    re.compile(r"(?:^|[^A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?:^|[^A-Za-z0-9])AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
]
# Env assignments in non-example files (values must stay in .env only).
ENV_ASSIGNMENT = re.compile(
    r"^(JWT_SECRET|DB_PASSWORD|DB_ROOT_PASSWORD|MCP_AUTH_TOKEN|"
    r"CHAT_API_KEY|EMBED_API_KEY)\s*=\s*(\S+)\s*$"
)
ALLOWED_FILENAMES = {".env.example"}


def _iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in ALLOWED_FILENAMES:
            continue
        if path.name == ".env":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def sec05_secret_scan() -> tuple[str, str]:
    hits = []
    scanned = 0
    for path in _iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(p.search(line) for p in SECRET_PATTERNS):
                hits.append(f"{path.relative_to(ROOT)}:{lineno} 疑似密钥字面量")
                continue
            match = ENV_ASSIGNMENT.match(line.strip())
            if match:
                hits.append(f"{path.relative_to(ROOT)}:{lineno} 密钥赋给了 {match.group(1)}")
    if hits:
        return "RED", f"扫描 {scanned} 个文件，命中 {len(hits)} 处：" + "；".join(hits[:5])
    return "PASS", f"扫描 {scanned} 个文件，未发现密钥字面量或非示例文件的密钥赋值"


def sec06_dependency_audit() -> tuple[str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", str(ROOT / "requirements.txt")],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        return "RED", "pip-audit 不可用（工具缺失，本课保留的红项）"
    if proc.returncode == 0:
        return "PASS", (proc.stdout or "no known vulnerabilities").strip().splitlines()[-1]
    if "No module named" in (proc.stderr or "") or "No module named" in (proc.stdout or ""):
        return "RED", "pip-audit 未安装（工具缺失，本课保留的红项）"
    return "RED", (proc.stderr or proc.stdout or "audit failed").strip()[:400]


def main() -> int:
    rows = [
        ("SEC-05 密钥扫描", *sec05_secret_scan()),
        ("SEC-06 依赖漏洞基线", *sec06_dependency_audit()),
    ]
    red = 0
    for name, status, detail in rows:
        if status == "RED":
            red += 1
        print(f"[{status}] {name}: {detail}")
    print(f"\n汇总：{len(rows) - red} PASS / {red} RED（完整七项见 reports/security-precheck.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
