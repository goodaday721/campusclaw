"""One-shot API test runner (lesson-5 deliverable).

Discovers cases under apitest/cases — one script per endpoint, the directory
tree mirrors the URL path (``{id}`` segments become ``item``, the file name is
the HTTP method, e.g. ``cases/api/skills/item/PUT.py``). Each module exposes a
``CASE`` dict: name / method / path / role / body / check(resp, ctx), where
check asserts three layers: HTTP status code, response content, and database
consistency (PyMySQL direct to the db service).

Run inside the compose network:
    docker compose exec -T api python apitest/run_all.py

Requests go through Nginx (http://web:80) so the full proxy path is exercised.
The HTML report is written to apitest/report.html (git-ignored).
"""
import html
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

import requests

APITEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APITEST_DIR))

BASE_URL = os.environ.get("APITEST_BASE_URL", "http://web:80")
CASES_DIR = APITEST_DIR / "cases"
REPORT_PATH = APITEST_DIR / "report.html"

USERS = {
    "teacher": {"username": "teacher_a", "password": "teacher_a_pass"},
    "student": {"username": "student_a", "password": "student_a_pass"},
}

# Within one URL directory, run GET -> POST -> PUT -> DELETE.
METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "DELETE": 3}


class Resp:
    """Minimal response wrapper so stream and normal cases share one shape."""

    def __init__(self, status_code: int, content_type: str, text: str):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = text

    def json(self):
        return json.loads(self.text)


def discover_cases() -> list[tuple[str, dict]]:
    """Import every cases/**/[A-Z]*.py module and collect its CASE dict."""
    entries = []
    for path in sorted(CASES_DIR.rglob("*.py")):
        if not path.stem[:1].isupper():
            continue
        rel = path.relative_to(CASES_DIR).as_posix()
        spec = importlib.util.spec_from_file_location(
            f"apicase_{rel.replace('/', '_').replace('.', '_')}", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case = getattr(module, "CASE", None)
        if case:
            entries.append((rel, case))
    entries.sort(
        key=lambda item: (
            str(Path(item[0]).parent).lower(),
            METHOD_ORDER.get(item[1].get("method", "GET"), 9),
        )
    )
    return entries


def login(role: str) -> str:
    resp = requests.post(f"{BASE_URL}/auth/login", json=USERS[role], timeout=30)
    resp.raise_for_status()
    return resp.json()["token"]


def execute(case: dict, ctx: dict) -> Resp:
    headers = {}
    role = case.get("role")
    if role:
        headers["Authorization"] = f"Bearer {ctx['tokens'][role]}"
    path = case["path"](ctx) if callable(case["path"]) else case["path"]
    body = case.get("body")
    body = body(ctx) if callable(body) else body
    url = f"{BASE_URL}{path}"
    if case.get("sse"):
        # Consume the whole SSE body so the server-side generator finishes
        # (and persists) before check() inspects the database.
        resp = requests.post(url, json=body, headers=headers, stream=True, timeout=300)
        text = resp.text  # triggers the full read
        wrapped = Resp(resp.status_code, resp.headers.get("Content-Type", ""), text)
        resp.close()
        return wrapped
    raw = requests.request(case["method"], url, json=body, headers=headers, timeout=120)
    return Resp(raw.status_code, raw.headers.get("Content-Type", ""), raw.text)


def render_report(results: list[dict], total_seconds: float) -> None:
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    rows = []
    for idx, r in enumerate(results, start=1):
        badge = {
            "PASS": '<span class="pass">PASS</span>',
            "FAIL": '<span class="fail">FAIL</span>',
            "SKIP": '<span class="skip">SKIP</span>',
        }[r["status"]]
        detail = (
            f'<pre class="detail">{html.escape(r["detail"])}</pre>'
            if r["detail"]
            else ""
        )
        rows.append(
            f"<tr><td>{idx}</td>"
            f"<td>{html.escape(r['name'])}</td>"
            f"<td><code>{html.escape(r['method'])} {html.escape(r['path'])}</code></td>"
            f"<td>{badge}</td>"
            f"<td>{r['seconds']:.2f}s</td>"
            f"<td>{detail}</td></tr>"
        )
    report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>apitest 报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 24px auto; max-width: 1100px; color: #222; }}
  h1 {{ font-size: 20px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 16px; }}
  .summary span {{ display: inline-block; margin-right: 16px; font-size: 14px; }}
  .pass {{ color: #1e8e4a; font-weight: bold; }}
  .fail {{ color: #c62828; font-weight: bold; }}
  .skip {{ color: #b8860b; font-weight: bold; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #e0e0e0; padding: 8px 10px; text-align: left;
            vertical-align: top; }}
  th {{ background: #94070a; color: #fff; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  pre.detail {{ margin: 0; white-space: pre-wrap; word-break: break-all;
                color: #c62828; font-size: 12px; }}
</style>
</head>
<body>
<h1>campusclaw 接口自动化测试报告</h1>
<div class="meta">
  基址 {html.escape(BASE_URL)} ·
  {time.strftime('%Y-%m-%d %H:%M:%S')} · 总耗时 {total_seconds:.1f}s
</div>
<div class="summary">
  <span>总计 {len(results)}</span>
  <span class="pass">通过 {passed}</span>
  <span class="fail">失败 {failed}</span>
  <span class="skip">跳过 {skipped}</span>
</div>
<table>
<tr><th>#</th><th>用例</th><th>接口</th><th>结果</th><th>耗时</th><th>详情</th></tr>
{''.join(rows)}
</table>
</body>
</html>
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> int:
    cases = discover_cases()
    ctx: dict = {"tokens": {}, "base_url": BASE_URL}
    for role in USERS:
        try:
            ctx["tokens"][role] = login(role)
        except Exception as exc:  # noqa: BLE001 — report per-case skips instead
            print(f"[warn] login failed for {role}: {exc}")

    print(f"apitest: {len(cases)} cases against {BASE_URL}\n")
    results = []
    started_all = time.time()
    for rel, case in cases:
        name = case.get("name", rel)
        method = case.get("method", "GET")
        entry = {
            "name": name,
            "method": method,
            "path": case["path"](ctx) if callable(case["path"]) else case["path"],
            "status": "PASS",
            "detail": "",
            "seconds": 0.0,
        }
        started = time.time()
        try:
            skip = None
            if case.get("role") and not ctx["tokens"].get(case["role"]):
                skip = f"no token for role {case['role']}"
            if skip is None and "skip_if" in case:
                skip = case["skip_if"](ctx)
            if skip:
                entry["status"] = "SKIP"
                entry["detail"] = skip
            else:
                resp = execute(case, ctx)
                case["check"](resp, ctx)
        except Exception as exc:  # noqa: BLE001 — any failure marks the case red
            entry["status"] = "FAIL"
            entry["detail"] = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip() or str(exc)
        entry["seconds"] = time.time() - started
        results.append(entry)
        mark = {"PASS": ".", "FAIL": "F", "SKIP": "s"}[entry["status"]]
        print(
            f"[{mark}] {entry['status']:<4} {method:<6} {entry['path']:<48} "
            f"{name} ({entry['seconds']:.2f}s)"
        )
        if entry["status"] == "FAIL":
            print(f"       {entry['detail']}")

    total_seconds = time.time() - started_all
    render_report(results, total_seconds)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    print(
        f"\nreport: {REPORT_PATH}\n"
        f"summary: {passed} passed, {failed} failed, {skipped} skipped "
        f"in {total_seconds:.1f}s"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
