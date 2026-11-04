"""Student polls their submission; status flows pending → … → terminal.

A short poll (up to ~15s) tries to catch the worker finishing; if the model
gateway is unconfigured the case still passes as long as the status is one of
the four legal values and matches the database row.
"""
import time


def path(ctx):
    return f"/api/submissions/{ctx['grading_submission_id']}"


def skip_if(ctx):
    return None if ctx.get("grading_submission_id") else "no submission from previous case"


def check(resp, ctx):
    import requests

    from helpers import db_query_one

    legal = {"pending", "running", "succeeded", "failed"}
    data = resp.json()
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"

    deadline = time.time() + 15
    while data["status"] in ("pending", "running") and time.time() < deadline:
        time.sleep(1)
        again = requests.get(
            f"{ctx['base_url']}{path(ctx)}",
            headers={"Authorization": f"Bearer {ctx['tokens']['student']}"},
            timeout=60,
        )
        assert again.status_code == 200, again.text[:200]
        data = again.json()

    assert data["status"] in legal, f"illegal status {data['status']}"
    row = db_query_one(
        "SELECT status, score, feedback FROM submissions WHERE id = %s",
        (data["id"],),
    )
    assert row and row["status"] == data["status"], "API/DB status mismatch"
    if data["status"] == "succeeded":
        assert row["score"] is not None or row["feedback"], "no readable result"
    if data["status"] == "failed":
        assert data["score"] is None


CASE = {
    "name": "学生轮询批改结果（状态合法且与库一致，短轮询到终态）",
    "method": "GET",
    "path": path,
    "role": "student",
    "skip_if": skip_if,
    "check": check,
}
