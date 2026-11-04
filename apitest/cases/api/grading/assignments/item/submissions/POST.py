"""Student submits an answer → 202 + taskId; the jobs row is pending.

The submission id and task id land in ctx for the polling case.
"""


def path(ctx):
    return f"/api/assignments/{ctx['grading_assignment_id']}/submissions"


def skip_if(ctx):
    return None if ctx.get("grading_assignment_id") else "no assignment from a-setup"


def check(resp, ctx):
    assert resp.status_code == 202, f"status {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["status"] == "pending", f"initial status {body['status']}"
    assert body["taskId"] > 0

    from helpers import db_query_one

    job = db_query_one("SELECT * FROM jobs WHERE id = %s", (body["taskId"],))
    assert job, "jobs row missing"
    assert job["status"] == "pending"
    assert job["dedupe_key"] == f"grade:{body['submissionId']}"

    # Resubmitting the same answer reuses the same submission + task.
    import requests

    again = requests.post(
        f"{ctx['base_url']}{path(ctx)}",
        json={"answer": "x = 4"},
        headers={"Authorization": f"Bearer {ctx['tokens']['student']}"},
        timeout=60,
    )
    assert again.status_code == 202, again.text[:200]
    repeat = again.json()
    assert repeat["submissionId"] == body["submissionId"], "resubmit must reuse submission"
    assert repeat["taskId"] == body["taskId"], "resubmit must reuse the task"
    assert db_query_one(
        "SELECT count(*) AS n FROM submissions"
    )["n"] >= 1

    ctx["grading_submission_id"] = body["submissionId"]
    ctx["grading_task_id"] = body["taskId"]


CASE = {
    "name": "学生提交作业（202 + taskId、任务落库、重复提交幂等）",
    "method": "POST",
    "path": path,
    "role": "student",
    "body": {"answer": "x = 4"},
    "skip_if": skip_if,
    "check": check,
}
