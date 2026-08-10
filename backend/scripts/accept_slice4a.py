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
    print("=== VCOS Slice 4A acceptance: decision -> execution loop (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org = await register(c, "Decision Corp", f"dc-{t}", f"ada{t}@dc.test.co", "Ada Founder")
        auth = org["headers"]
        ada_id = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]
        bob = await invite_and_accept(c, auth, f"bob{t}@dc.test.co", "Bob Worker", "employee")
        bob_auth = {"Authorization": f"Bearer {bob['access_token']}"}
        employees = (await c.get(f"{API}/employees", headers=auth)).json()
        bob_id = next(e["id"] for e in employees if e["email"] == f"bob{t}@dc.test.co")
        print("1. Founder + Bob (employee, action owner) set up")

        project = (
            await c.post(
                f"{API}/projects",
                json={"name": "Portal 4A", "code": f"p4a{t % 10**4}", "status": "active", "description": "Customer portal"},
                headers=auth,
            )
        ).json()
        goal = (
            await c.post(
                f"{API}/goals",
                json={"name": "Improve activation", "scope": "project", "project_id": project["id"], "status": "planned"},
                headers=auth,
            )
        ).json()
        print("2. Project + goal ready")

        # --- decision with structured follow-up actions ----------------------
        decision = (
            await c.post(
                f"{API}/decisions",
                json={
                    "title": "Launch the enterprise portal",
                    "description": "Adopt a dedicated customer portal.",
                    "context": "Reduce onboarding time for enterprise customers.",
                    "status": "made",
                    "decision_maker_id": ada_id,
                    "participants": [{"employee_id": ada_id, "role": "maker"}],
                    "project_id": project["id"],
                    "goal_id": goal["id"],
                    "follow_up_actions": [
                        {
                            "text": "Build the onboarding flow",
                            "owner_id": bob_id,
                            "project_id": project["id"],
                            "goal_id": goal["id"],
                            "due_date": "2026-09-01",
                            "status": "pending",
                        },
                        {"text": "Contact five pilot customers", "owner_id": bob_id, "status": "pending"},
                    ],
                },
                headers=auth,
            )
        ).json()
        decision_id = decision["id"]
        actions = decision["follow_up_actions"]
        check("decision created with 2 structured follow-up actions", len(actions) == 2)
        check("action carries owner + project + goal + due date",
              actions[0]["owner_id"] == bob_id and actions[0]["project_id"] == project["id"] and actions[0]["goal_id"] == goal["id"] and actions[0]["due_date"] == "2026-09-01",
              str(actions[0])[:200])
        check("decision surface carries the goal name", decision.get("goal_name") == "Improve activation", str(decision.get("goal_name")))
        print("3. Decision recorded with structured follow-up actions")

        # --- execute -> task with full lineage ---------------------------------
        r = await c.post(f"{API}/decisions/{decision_id}/actions/0/execute", headers=auth)
        check("founder executes action 0 -> task (200)", r.status_code == 200, r.text[:200])
        task = r.json()["task"]
        check("task linked to the decision", task["decision_id"] == decision_id)
        check("task carries project + goal", task["project_id"] == project["id"] and task["goal_id"] == goal["id"])
        check("task assigned to the action owner", task["assignee_id"] == bob_id)
        check("task description cites the decision context", "Reduce onboarding time" in (task["description"] or ""))
        check("task tagged 'decision'", "decision" in (task["tags"] or []))
        check("task payload carries the decision citation", (task.get("decision") or {}).get("title") == "Launch the enterprise portal")

        notifications = (await c.get(f"{API}/notifications", headers=bob_auth)).json()["items"]
        check("Bob notified: assigned from decision (title cites the decision)",
              any(n["type"] == "task.assigned" and "from decision 'Launch the enterprise portal'" in n["title"] for n in notifications),
              str([n["title"] for n in notifications[:3]]))
        print("4. Execution converted the action into a lineage-carrying task")

        decision_after = (await c.get(f"{API}/decisions/{decision_id}", headers=auth)).json()
        action0 = decision_after["follow_up_actions"][0]
        check("action now linked to the task", action0.get("task_id") == task["id"] and action0["status"] == "in_progress")
        duplicate = await c.post(f"{API}/decisions/{decision_id}/actions/0/execute", headers=auth)
        check("duplicate execution rejected (400)", duplicate.status_code == 400, duplicate.text[:160])
        print("5. Action linkage + duplicate execution guard")

        tasks = (await c.get(f"{API}/decisions/{decision_id}/tasks", headers=auth)).json()
        check("GET /decisions/{id}/tasks returns the produced task (hydrated)", len(tasks) == 1 and tasks[0]["id"] == task["id"] and tasks[0]["decision_id"] == decision_id, str(tasks)[:200])
        detail = (await c.get(f"{API}/tasks/{task['id']}", headers=auth)).json()
        check("task detail carries decision.reason (why)", bool((detail.get("decision") or {}).get("reason")), str((detail.get("decision") or {}).get("reason"))[:160])
        print("6. Task lineage visible via decision and task endpoints")

        # --- search + graph ---------------------------------------------------
        search = (await c.get(f"{API}/knowledge/search", params={"q": "onboarding", "kind": "decision"}, headers=auth)).json()
        check("follow-up text is searchable", any(r["id"] == decision_id for r in search["results"]), str(search)[:200])
        relations = (await c.get(f"{API}/knowledge/decision/{decision_id}/relations", headers=auth)).json()
        produced = [r for r in relations if r.get("relation_type") == "produces" and r.get("target_type") == "task"]
        check("knowledge graph carries the decision -> task edge", len(produced) == 1, str(relations)[:200])
        print("7. Decision searchable + graph edge present")

        # --- my-work renders the produced task (due-date safe) -------------------
        my_work = await c.get(f"{API}/my-work", headers=bob_auth)
        check("Bob's /my-work returns 200 with the open produced task",
              my_work.status_code == 200 and my_work.json()["tasks"]["total"] == 1,
              my_work.text[:200])
        print("8. My-work surfaces the task (overdue + sort paths exercised)")

        # --- tenant isolation ----------------------------------------------------
        org_b = await register(c, "Sneaky Corp", f"sn-{t}", f"eve{t}@sn.test.co", "Eve Sneaky")
        headers_b = org_b["headers"]
        me_b = (await c.get(f"{API}/employees/me", headers=headers_b)).json()["id"]
        foreign = await c.post(
            f"{API}/tasks",
            json={"title": "Sneaky task", "decision_id": decision_id, "assignee_id": me_b},
            headers=headers_b,
        )
        check("task in org B cannot cite org A's decision (400)", foreign.status_code == 400, foreign.text[:160])
        hijack = await c.patch(
            f"{API}/decisions/{decision_id}",
            json={"follow_up_actions": [{"text": "Hijacked", "owner_id": me_b}]},
            headers=auth,
        )
        check("decision update with foreign owner rejected (400)", hijack.status_code == 400, hijack.text[:160])
        leaked = await c.get(f"{API}/decisions/{decision_id}/tasks", headers=headers_b)
        check("cross-org read of decision tasks denied (404)", leaked.status_code == 404, leaked.text[:160])
        print("9. Tenant isolation on decision <-> task links")

        # --- completing the task implements the decision ------------------------
        r = await c.post(f"{API}/tasks/{task['id']}/transition", json={"status": "in_progress"}, headers=auth)
        check("partial progress does not implement the decision", r.status_code == 200)
        still = (await c.get(f"{API}/decisions/{decision_id}", headers=auth)).json()
        check("decision still 'made' after partial progress", still["status"] == "made", still["status"])
        r = await c.post(f"{API}/tasks/{task['id']}/transition", json={"status": "completed"}, headers=auth)
        check("task transition to completed (200)", r.status_code == 200, r.text[:160])
        done = (await c.get(f"{API}/decisions/{decision_id}", headers=auth)).json()
        check("decision auto-implemented once its task is completed", done["status"] == "implemented", done["status"])
        executed = next(a for a in done["follow_up_actions"] if a.get("task_id"))
        pending = next(a for a in done["follow_up_actions"] if not a.get("task_id"))
        check("executed action marked completed", executed["status"] == "completed")
        check("unexecuted action stays pending", pending["status"] == "pending")
        print("10. Completion closes the loop: decision implemented")

        # --- the loop is audited, notified and evented --------------------------
        events = (await c.get(f"{API}/events", params={"name": "decision.implemented"}, headers=auth)).json()
        check("event: decision.implemented recorded", events.get("total", 0) >= 1)
        audit = (await c.get(f"{API}/audit", params={"action": "decision.implemented", "resource_type": "decision"}, headers=auth)).json()
        check("audit: decision.implemented recorded", audit.get("total", 0) >= 1 and audit["items"][0]["action"] == "decision.implemented")
        notif = (await c.get(f"{API}/notifications", headers=auth)).json()["items"]
        check("notification: decision.implemented delivered", any(n["type"] == "decision.implemented" for n in notif))
        all_events = (await c.get(f"{API}/events", headers=auth)).json()["items"]
        names = {e["name"] for e in all_events}
        check("event trail contains decision.executed", "decision.executed" in names)
        check("event trail contains decision.created", "decision.created" in names)
        print("11. Audit, notifications and event trail complete")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
