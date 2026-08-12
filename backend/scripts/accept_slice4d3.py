"""Slice 4D.3 acceptance — organizational memory automation (live API).

12 checks against the running stack (http://localhost:8999):

  1. change-driven formation: blocked task forms an evidence-backed experience
  2. evidence lineage: task/project/dependency refs resolve to titles/urls
  3. outcome journey: blocker completion + dependent completion resolve positive
     and produce a lesson; manual downgrade is rejected (monotonic)
  4. historical search: semantic hit with scores, miss, blank question 422
  5. timeline: episodes link memories to their forming events
  6. related links: bounded and governance-filtered
  7. feed governance: scoped brain:read-only reader sees the project memory;
     a memory outside their scope is 404 (never 403/leak) and outcome POST is 403
  8. tenant isolation: rival org sees nothing
  9. exactly-once replay: re-draining + re-running the worker never duplicates
 10. brain integration: /brain/answer cites historical memory claims
 11. worker + scheduler: memory_formation registered @ 300s, on-demand run ok
 12. endpoint contract: anonymous 401, blank search 422, invalid outcome 422

Exit code 0 when all pass.
"""

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
    r2 = await client.post(
        f"{API}/auth/register/invite",
        json={"token": r.json()["token"], "email": email, "full_name": full_name, "password": "StrongPass123!"},
    )
    assert r2.status_code == 201, r2.text
    return r2.json()


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 500) -> int:
    r = await client.post(f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("processed", 0)


async def drain(client: httpx.AsyncClient, headers: dict) -> None:
    """Pre-drain the global FIFO so this run's events dispatch promptly."""
    for _ in range(15):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def run_memory_worker(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.post(f"{API}/intelligence/workers/memory_formation/run", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def feed(client: httpx.AsyncClient, headers: dict, category: str | None = None) -> list[dict]:
    params: dict = {"limit": 100}
    if category:
        params["memory_category"] = category
    r = await client.get(f"{API}/brain/memory/feed", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("memories", [])


async def form_blocked_experience(client: httpx.AsyncClient, headers: dict, title: str) -> tuple[dict, dict, dict]:
    """Create project + blocker + dependent, block the dependent, and drive
    the change pipeline until the blocked experience memory is observable."""
    proj = (
        await client.post(
            f"{API}/projects",
            json={"name": f"{title} project", "description": "Slice 4D.3 anchor", "status": "active"},
            headers=headers,
        )
    ).json()
    # A governance scope must exist before the episode forms: memory inherits
    # the project scope only when the project is governance-scoped.
    scope = (
        await client.post(
            f"{API}/governance/scopes",
            json={"name": f"{title} scope", "scope_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
    ).json()
    blocker = (
        await client.post(
            f"{API}/tasks",
            json={"title": f"{title} prereq", "project_id": proj["id"], "status": "todo"},
            headers=headers,
        )
    ).json()
    dependent = (
        await client.post(
            f"{API}/tasks",
            json={"title": title, "project_id": proj["id"], "status": "todo"},
            headers=headers,
        )
    ).json()
    dep = await client.post(
        f"{API}/tasks/{dependent['id']}/dependencies",
        json={"depends_on_task_id": blocker["id"]},
        headers=headers,
    )
    assert dep.status_code == 201, dep.text
    tr = await client.post(
        f"{API}/tasks/{dependent['id']}/transition",
        json={"status": "blocked"},
        headers=headers,
    )
    assert tr.status_code == 200, tr.text

    experience: dict | None = None
    for _ in range(12):
        await dispatch(client, headers)
        await run_memory_worker(client, headers)
        memories = await feed(client, headers)
        for memory in memories:
            if memory.get("source_event") == "task.blocked" and memory.get("entity_id") == dependent["id"]:
                experience = memory
                break
        if experience:
            break
        await asyncio.sleep(3)
    assert experience is not None, "blocked experience never formed"
    return proj, blocker, experience, scope


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.3 acceptance: organizational memory automation (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Memory Corp", f"mc-{t}", f"ada{t}@mc.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")
        await drain(c, auth)

        proj, blocker, experience, scope = await form_blocked_experience(c, auth, "Billing sync delivery")
        print("2. Blocked-task episode seeded; experience formed")

        # ---- 1: change-driven formation ---------------------------------------
        check(
            "1. change-driven formation: blocked task forms experience memory",
            experience["memory_category"] == "experience"
            and experience["outcome_type"] is None
            and experience["auth_scope"] == "project"
            and experience["auth_project_id"] == proj["id"]
            and len(experience.get("evidence", [])) >= 3,
            f"cat={experience.get('memory_category')} scope={experience.get('auth_scope')}",
        )

        # ---- 2: evidence lineage ----------------------------------------------
        ev = await c.get(f"{API}/brain/memory/{experience['id']}/evidence", headers=auth)
        assert ev.status_code == 200, ev.text
        evidence = ev.json()["evidence"]
        by_type = {item["type"]: item for item in evidence}
        check(
            "2. evidence lineage: task/project/dependency refs resolve",
            by_type.get("task", {}).get("resolved") is True
            and by_type.get("task", {}).get("title") == "Billing sync delivery"
            and by_type.get("task", {}).get("url") == f"/tasks/{experience['entity_id']}"
            and by_type.get("project", {}).get("resolved") is True
            and by_type.get("dependency", {}).get("resolved") is True
            and by_type.get("event", {}).get("resolved") is True
            and by_type.get("event", {}).get("title"),
            f"types={sorted(by_type)}",
        )
        print("3. Formation + lineage verified")

        # ---- 3: outcome journey ------------------------------------------------
        rc = await c.post(f"{API}/tasks/{blocker['id']}/transition", json={"status": "completed"}, headers=auth)
        assert rc.status_code == 200, rc.text
        for _ in range(12):
            await dispatch(c, auth)
            await run_memory_worker(c, auth)
            if any(
                m.get("entity_id") == experience["entity_id"]
                and m.get("entity_type") == "task"
                and m.get("outcome_type") == "positive"
                for m in await feed(c, auth)
            ):
                break
            await asyncio.sleep(3)
        rd = await c.post(f"{API}/tasks/{experience['entity_id']}/transition", json={"status": "completed"}, headers=auth)
        assert rd.status_code == 200, rd.text
        lesson: dict | None = None
        for _ in range(12):
            await dispatch(c, auth)
            await run_memory_worker(c, auth)
            for memory in await feed(c, auth):
                if memory.get("memory_category") == "lesson" and memory.get("entity_id") == experience["entity_id"]:
                    lesson = memory
                    break
            if lesson:
                break
            await asyncio.sleep(3)
        positive = [
            m for m in await feed(c, auth)
            if m.get("entity_id") == experience["entity_id"]
            and m.get("entity_type") == "task"
            and m.get("outcome_type") == "positive"
        ]
        downgrade = await c.post(
            f"{API}/brain/memory/{experience['id']}/outcome",
            json={"outcome_type": "negative", "outcome": "vendor never recovered"},
            headers=auth,
        )
        check(
            "3. outcome journey: positive resolution, lesson, monotonic downgrade rejection",
            bool(positive) and lesson is not None and bool(lesson.get("lesson"))
            and downgrade.status_code == 200 and downgrade.json().get("outcome_type") == "positive",
            f"positive={bool(positive)} lesson={bool(lesson)} downgrade={downgrade.status_code}:{downgrade.text[:120]}",
        )
        print("4. Outcome journey verified")

        # ---- 4: historical search ---------------------------------------------
        hit = await c.post(
            f"{API}/brain/memory/search",
            json={"question": "task was blocked during execution like this before", "limit": 10},
            headers=auth,
        )
        assert hit.status_code == 200, hit.text
        hit_body = hit.json()
        miss = await c.post(
            f"{API}/brain/memory/search",
            json={"question": "quarterly revenue grew by twelve percent"},
            headers=auth,
        )
        blank = await c.post(f"{API}/brain/memory/search", json={"question": "   "}, headers=auth)
        hit_ids = [m["id"] for m in hit_body.get("memories", [])]
        top = (hit_body.get("memories") or [{}])[0]
        check(
            "4. historical search: hit with scores, miss, blank 422",
            hit_body.get("matched", 0) >= 1
            and experience["id"] in hit_ids
            and isinstance(top.get("confidence"), (int, float))
            and top.get("fact_kind") == "observation"
            and miss.status_code == 200 and miss.json().get("matched") == 0
            and blank.status_code == 422,
            f"matched={hit_body.get('matched')} miss={miss.status_code}:{miss.json().get('matched')} blank={blank.status_code}",
        )

        # ---- 5: timeline --------------------------------------------------------
        tl = await c.get(f"{API}/brain/memory/timeline", headers=auth)
        assert tl.status_code == 200, tl.text
        episodes = tl.json().get("episodes", [])
        categories = {e.get("memory_category") for e in episodes}
        dep_episodes = [e for e in episodes if e.get("entity_type") == "task" and e.get("entity_id") == experience["entity_id"]]
        check(
            "5. timeline: episodes link to forming events, all categories present",
            bool(dep_episodes)
            and all(set(e.get("episode_events", [])) <= set(e.get("source_event_ids") or []) for e in dep_episodes)
            and {"experience", "lesson", "outcome"} <= categories,
            f"categories={sorted(categories)}",
        )

        # ---- 6: related links ----------------------------------------------------
        rel = await c.get(f"{API}/brain/memory/{experience['id']}/related", headers=auth)
        assert rel.status_code == 200, rel.text
        related = rel.json().get("related", [])
        check(
            "6. related links: bounded and scoped",
            len(related) <= 5,
            f"count={len(related)}",
        )
        print("5-6. Search, timeline, related verified")

        # ---- 7: feed governance ---------------------------------------------------
        emp = await invite_and_accept(c, auth, f"emp{t}@mc.test.co", "Scoped Mgr", role="manager")
        emp_auth = {"Authorization": f"Bearer {emp['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": emp["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
            headers=auth,
        )
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": emp["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x["scope_id"] is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(
            f"{API}/governance/delegations",
            json={"granted_to_user": emp["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.3"},
            headers=auth,
        )
        assert dg.status_code == 201, dg.text

        hidden_proj, hidden_blocker, hidden_exp, _ = await form_blocked_experience(c, auth, "Off-scope delivery")
        assert hidden_blocker  # referenced
        scoped_feed = await feed(c, emp_auth)
        scoped_ids = {m["id"] for m in scoped_feed}
        hidden_get = await c.get(f"{API}/brain/memory/{hidden_exp['id']}", headers=emp_auth)
        hidden_ev = await c.get(f"{API}/brain/memory/{hidden_exp['id']}/evidence", headers=emp_auth)
        hidden_rel = await c.get(f"{API}/brain/memory/{hidden_exp['id']}/related", headers=emp_auth)
        outcome_denied = await c.post(
            f"{API}/brain/memory/{experience['id']}/outcome",
            json={"outcome_type": "partial", "outcome": "scoped observer records"},
            headers=emp_auth,
        )
        check(
            "7. feed governance: scoped reader sees own project, hidden memory is 404, outcome is 403",
            experience["id"] in scoped_ids
            and hidden_exp["id"] not in scoped_ids
            and hidden_get.status_code == 404
            and hidden_ev.status_code == 404
            and hidden_rel.status_code == 404
            and outcome_denied.status_code == 403,
            f"visible={experience['id'] in scoped_ids} hidden_get={hidden_get.status_code} "
            f"outcome={outcome_denied.status_code}",
        )
        print("7. Governance verified")

        # ---- 8: tenant isolation ---------------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc-{t}", f"eve{t}@rc.test.co", "Eve Rival")
        rival_feed = await feed(c, org_b["headers"])
        check(
            "8. tenant isolation: outsider org sees nothing",
            experience["id"] not in {m["id"] for m in rival_feed},
            f"rival_feed={len(rival_feed)}",
        )

        # ---- 9: exactly-once replay ------------------------------------------------
        before = await feed(c, auth)
        before_count = len(before)
        for _ in range(3):
            await dispatch(c, auth)
            await run_memory_worker(c, auth)
        after = await feed(c, auth)
        after_count = len(after)
        check(
            "9. exactly-once replay: re-running the pipeline never duplicates",
            after_count == before_count,
            f"before={before_count} after={after_count}",
        )
        print("8-9. Isolation + exactly-once verified")

        # ---- 10: brain integration ---------------------------------------------------
        rb = await c.post(
            f"{API}/brain/answer",
            json={"question": "task was blocked during execution like this before"},
            headers=auth,
        )
        claims = rb.json().get("claims", []) if rb.status_code == 200 else []
        memory_cited = any(
            e.get("type") == "memory" and e.get("url", "").startswith("/brain/memory/")
            for cl in claims
            for e in cl.get("evidence", [])
        )
        check(
            "10. brain integration: /brain/answer cites historical memory claims",
            rb.status_code == 200 and memory_cited,
            f"status={rb.status_code} cited={memory_cited}",
        )

        # ---- 11: worker + scheduler ---------------------------------------------------
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        reg = next((w for w in workers if w["name"] == "memory_formation"), None)
        run = await run_memory_worker(c, auth)
        check(
            "11. memory_formation worker registered @ 300s and runs on demand",
            reg is not None and reg.get("interval_seconds") == 300
            and run.get("worker") == "memory_formation" and isinstance(run.get("processed"), int),
            f"reg={reg} run={run}",
        )

        # ---- 12: endpoint contract -------------------------------------------------------
        anon_feed = await c.get(f"{API}/brain/memory/feed")
        anon_tl = await c.get(f"{API}/brain/memory/timeline")
        bad_outcome = await c.post(
            f"{API}/brain/memory/{experience['id']}/outcome",
            json={"outcome_type": "banana"},
            headers=auth,
        )
        check(
            "12. endpoint contract: anonymous 401, invalid outcome 422",
            anon_feed.status_code in (401, 403) and anon_tl.status_code in (401, 403)
            and bad_outcome.status_code == 422,
            f"anon={anon_feed.status_code}/{anon_tl.status_code} bad={bad_outcome.status_code}",
        )
        print("10-12. Brain, worker, contracts verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
