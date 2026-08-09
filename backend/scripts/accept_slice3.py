import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


async def register(client: httpx.AsyncClient, name: str, slug: str, email: str, full_name: str):
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": name,
            "organization_slug": slug,
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": full_name,
            "email": email,
            "username": email.split("@")[0],
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "access": data["access_token"],
        "user": data["user"],
        "organization": data["organization"],
    }


async def invite_and_accept(client: httpx.AsyncClient, headers: dict, email: str, full_name: str, role: str = "employee"):
    r = await client.post(f"{API}/users/invite", json={"email": email, "role": role, "full_name": full_name}, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    r2 = await client.post(
        f"{API}/auth/register/invite",
        json={"token": body["token"], "email": email, "full_name": full_name, "password": "StrongPass123!"},
    )
    assert r2.status_code == 201, r2.text
    return r2.json()


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 3 acceptance: task execution engine (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org = await register(c, "Task Corp", f"tk-{t}", f"ada{t}@tk.test.co", "Ada Founder")
        auth = org["headers"]
        bob = await invite_and_accept(c, auth, f"bob{t}@tk.test.co", "Bob Worker", "employee")
        bob_auth = {"Authorization": f"Bearer {bob['access_token']}"}
        employees = (await c.get(f"{API}/employees", headers=auth)).json()
        bob_emp = next(e for e in employees if e["email"] == f"bob{t}@tk.test.co")
        print("1. Founder + Bob (employee, assignee) set up")

        project = (
            await c.post(
                f"{API}/projects",
                json={"name": "TaskOps", "code": f"to{t % 10**4}", "status": "active", "description": "Work execution demo"},
                headers=auth,
            )
        ).json()
        main_task = (
            await c.post(
                f"{API}/tasks",
                json={
                    "project_id": project["id"],
                    "title": "Build checkout flow",
                    "description": "Design and ship the payment flow.",
                    "priority": "high",
                    "tags": ["urgent"],
                    "assignee_id": bob_emp["id"],
                    "status": "backlog",
                },
                headers=auth,
            )
        ).json()
        gate_task = (
            await c.post(
                f"{API}/tasks",
                json={"project_id": project["id"], "title": "Approve payment provider", "priority": "medium", "status": "backlog"},
                headers=auth,
            )
        ).json()
        dep = await c.post(
            f"{API}/tasks/{main_task['id']}/dependencies",
            json={"depends_on_task_id": gate_task["id"], "kind": "finish_to_start"},
            headers=auth,
        )
        check("dependency edge (finish_to_start) created", dep.status_code == 201)
        print("2. Project + tasks + dependency graph ready")

        # --- dependency guard ------------------------------------------------
        r = await c.get(f"{API}/tasks/{main_task['id']}", headers=bob_auth)
        blocked = r.json().get("blocked_by", [])
        check("Bob's task surfaces blocked_by with the gate", any(b["task_id"] == gate_task["id"] for b in blocked), str(blocked)[:200])

        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "in_progress"}, headers=bob_auth)
        check("start work allowed under finish_to_start (hard links only)", r.status_code == 200, r.text[:160])
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "completed"}, headers=bob_auth)
        check("transition to completed blocked by finish_to_start dependency", r.status_code == 400, r.text[:160])
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "blocked"}, headers=bob_auth)
        check("transition to blocked allowed", r.status_code == 200)
        print("3. Dependency guard: complete gated, start allowed under finish_to_start, blocked status reachable")

        # --- assignee-only editing -------------------------------------------
        r = await c.patch(f"{API}/tasks/{gate_task['id']}", json={"title": "hijacked"}, headers=bob_auth)
        check("Bob cannot edit the unassigned task (403)", r.status_code == 403)
        r = await c.patch(
            f"{API}/tasks/{main_task['id']}",
            json={"title": "Build checkout flow (v2)", "priority": "critical", "due_date": "2026-12-31", "tags": ["urgent", "sales"]},
            headers=bob_auth,
        )
        check("Bob can edit his own task", r.status_code == 200)
        check("edit persisted (title)", r.json()["title"] == "Build checkout flow (v2)")
        check("edit persisted (tags)", set(r.json().get("tags", [])) == {"urgent", "sales"})
        print("4. Assignee-only edit enforced + persisted")

        # --- subtasks + parent progress --------------------------------------
        r = await c.post(
            f"{API}/tasks",
            json={"project_id": project["id"], "parent_task_id": main_task["id"], "title": "Design the API contract", "status": "todo", "assignee_id": bob_emp["id"]},
            headers=bob_auth,
        )
        check("assignee can create a subtask", r.status_code == 201)
        sub = r.json()
        r = await c.post(
            f"{API}/tasks",
            json={"project_id": project["id"], "parent_task_id": main_task["id"], "title": "Sneaky subtask", "status": "todo", "assignee_id": bob_emp["id"]},
            headers=auth,
        )
        check("founder (manager) can also add subtasks", r.status_code == 201)
        sub2 = r.json()
        r = await c.post(
            f"{API}/tasks",
            json={"project_id": project["id"], "parent_task_id": gate_task["id"], "title": "Sub on someone else's task", "status": "todo"},
            headers=bob_auth,
        )
        check("Bob cannot add a subtask to an unassigned parent (403)", r.status_code == 403, r.text[:160])
        r = await c.post(f"{API}/tasks/{sub['id']}/transition", json={"status": "completed"}, headers=bob_auth)
        check("subtask completed", r.status_code == 200)
        r = await c.get(f"{API}/tasks/{main_task['id']}", headers=bob_auth)
        check("parent progress follows subtasks (1/2)", r.json()["subtasks_completed"] == 1 and r.json()["subtasks_count"] == 2, str({k: r.json().get(k) for k in ("subtasks_count", "subtasks_completed")}))
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "completed"}, headers=bob_auth)
        check("parent cannot complete while a subtask is open (400)", r.status_code == 400, r.text[:160])
        r = await c.post(f"{API}/tasks/{sub2['id']}/transition", json={"status": "completed"}, headers=auth)
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "completed"}, headers=bob_auth)
        check("parent still cannot complete while the gate is open (400)", r.status_code == 400, r.text[:160])
        print("5. Subtasks: progress rollup, completion guards")

        # --- founder completes the gate; worker unblocks ----------------------
        r = await c.post(f"{API}/tasks/{gate_task['id']}/transition", json={"status": "completed"}, headers=auth)
        check("founder completes the gate task", r.status_code == 200)
        print("6. Gate completed; waiting for the dependency worker (max 120s)...")
        deadline = time.time() + 120
        titles: set[str] = set()
        parent_status = None
        while time.time() < deadline:
            titles = {n["title"] for n in (await c.get(f"{API}/notifications", headers=bob_auth)).json()["items"]}
            parent_status = (await c.get(f"{API}/tasks/{main_task['id']}", headers=bob_auth)).json().get("status")
            if parent_status == "todo" and any("Task unblocked" in x for x in titles):
                break
            await asyncio.sleep(10)
        check("notification: 'Task unblocked' delivered to the assignee", any("Task unblocked" in x for x in titles))
        check("dependency worker reset the task to todo", parent_status == "todo", str(parent_status))

        # --- full status ladder ------------------------------------------------
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "in_progress"}, headers=bob_auth)
        check("task starts once unblocked", r.status_code == 200)
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "review"}, headers=bob_auth)
        check("review transition allowed", r.status_code == 200)
        r = await c.post(f"{API}/tasks/{main_task['id']}/transition", json={"status": "completed"}, headers=bob_auth)
        check("completed transition allowed", r.status_code == 200)
        print("7. Worker notification + full status ladder")

        # --- comments + mention notification ----------------------------------
        r = await c.post(
            f"{API}/tasks/{main_task['id']}/comments",
            json={"body": f"@{org['user']['email']} please review the API design"},
            headers=bob_auth,
        )
        check("Bob comments on his task", r.status_code == 201)
        comments = (await c.get(f"{API}/tasks/{main_task['id']}/comments", headers=bob_auth)).json()
        check("comment list contains the mention", any("please review the API design" in cm["body"] for cm in comments))
        print("8. Mention delivered on the task")

        # --- attachments ------------------------------------------------------
        r = await c.post(
            f"{API}/tasks/{main_task['id']}/attachments",
            json={"filename": "checkout-spec.pdf", "url": "https://example.com/checkout-spec.pdf", "size_bytes": 1024, "kind": "document"},
            headers=bob_auth,
        )
        check("attachment added", r.status_code == 201)
        atts = (await c.get(f"{API}/tasks/{main_task['id']}/attachments", headers=bob_auth)).json()
        check("attachment listed with url", any(a["url"] == "https://example.com/checkout-spec.pdf" for a in atts))
        print("9. Attachments stored and listed")

        # --- activity trail -----------------------------------------------------
        activity = (await c.get(f"{API}/tasks/{main_task['id']}/activity", headers=bob_auth)).json()
        kinds = {a.get("kind") or a.get("action") for a in activity}
        for expected in ("task.created", "task.updated", "task.commented", "task.attachment_added", "task.transitioned", "task.unblocked", "dependency.added"):
            check(f"activity trail contains {expected}", expected in kinds, f"kinds={sorted(kinds)}")
        blocked_entries = [a for a in activity if (a.get("action")) == "task.transitioned" and (a.get("details") or {}).get("status") == "blocked"]
        check("activity trail records the blocked transition", bool(blocked_entries), f"kinds={sorted(kinds)}")
        check("activity trail records the completed kind", "task.completed" in kinds, f"kinds={sorted(kinds)}")
        print("10. Full activity trail preserved")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
