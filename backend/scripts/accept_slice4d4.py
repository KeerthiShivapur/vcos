"""Slice 4D.4 acceptance — universal organizational pattern intelligence (live API).

12 checks against the running stack (http://localhost:8999):

  1. change-driven formation: three blocked tasks form one repeated_delay
     pattern (execution family, project scope, lifecycle candidate/emerging)
  2. evidence lineage: every supporting event is a task.transitioned; evidence
     refs resolve; occurrence history matches the count
  3. one occurrence is never a pattern: a single blocked task stays invisible
  4. exactly-once replay: re-draining + re-running never duplicates occurrences
  5. legacy surface: phase 9 /intelligence/patterns?status=open still lists it
  6. governance: scoped brain:read-only reader sees the project pattern; a
     hidden project's pattern is 404 (never 403/leak); PATCH is 403 for them
  7. tenant isolation: rival org sees nothing
  8. brain integration: /brain/answer cites pattern claims with evidence urls
  9. worker + scheduler: pattern worker registered @ 120s, on-demand run ok
 10. lifecycle: PATCH acknowledge persists and lists under status=acknowledged
 11. endpoint contract: anonymous 401/403, invalid legacy status 422,
     missing pattern 404
 12. related links: bounded and governance-filtered

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


async def run_pattern_worker(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.post(f"{API}/intelligence/workers/pattern/run", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def patterns(client: httpx.AsyncClient, headers: dict, **params) -> list[dict]:
    q: dict = {"limit": 200}
    q.update(params)
    r = await client.get(f"{API}/brain/patterns", params=q, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("patterns", [])


async def block_tasks(client: httpx.AsyncClient, headers: dict, project_id: str, titles: list[str]) -> None:
    for title in titles:
        task = (await client.post(
            f"{API}/tasks",
            json={"title": title, "project_id": project_id, "status": "todo"},
            headers=headers,
        )).json()
        tr = await client.post(f"{API}/tasks/{task['id']}/transition", json={"status": "blocked"}, headers=headers)
        assert tr.status_code == 200, tr.text


async def wait_for_pattern(
    client: httpx.AsyncClient,
    headers: dict,
    predicate,
) -> dict:
    for _ in range(12):
        await dispatch(client, headers)
        await run_pattern_worker(client, headers)
        for pattern in await patterns(client, headers):
            if predicate(pattern):
                return pattern
        await asyncio.sleep(3)
    raise AssertionError("pattern never became observable")


async def form_scoped_pattern(client: httpx.AsyncClient, headers: dict, name: str, titles: list[str]) -> tuple[dict, dict]:
    """Project + governance scope + blocked tasks -> project-scoped pattern."""
    proj = (
        await client.post(
            f"{API}/projects",
            json={"name": name, "description": "Slice 4D.4 anchor", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            f"{API}/governance/scopes",
            json={"name": f"{name} scope", "scope_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
    ).json()
    await block_tasks(client, headers, proj["id"], titles)
    pattern = await wait_for_pattern(
        client, headers,
        lambda p: p.get("auth_project_id") == proj["id"] and p.get("pattern_type") == "repeated_delay",
    )
    return proj, scope, pattern


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.4 acceptance: universal pattern intelligence (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Pattern Corp", f"pc-{t}", f"ada{t}@pc.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")
        await drain(c, auth)

        proj, scope, pattern = await form_scoped_pattern(c, auth, "Helios Delivery", ["Checkout API", "Billing export", "Mobile push"])
        print("2. Three blocked tasks seeded; pattern formed")

        # ---- 1: change-driven formation -----------------------------------------
        check(
            "1. change-driven formation: repeated_delay, execution, project scope, lifecycle",
            pattern["pattern_type"] == "repeated_delay"
            and pattern["family"] == "execution"
            and "Repeated delays" in pattern["title"]
            and pattern["count"] == 3
            and pattern["occurrence_count"] == 3
            and pattern["status"] in ("candidate", "emerging")
            and pattern["confidence"] >= 0.4
            and pattern["scope_type"] == "project"
            and pattern["auth_project_id"] == proj["id"]
            and len(pattern.get("supporting_event_ids", [])) == 3,
            f"status={pattern.get('status')} family={pattern.get('family')} count={pattern.get('count')}",
        )

        # ---- 2: evidence lineage + occurrence history ---------------------------
        ev = await c.get(f"{API}/brain/patterns/{pattern['id']}/evidence", headers=auth)
        assert ev.status_code == 200, ev.text
        evidence = ev.json()
        hist = (await c.get(f"{API}/brain/patterns/{pattern['id']}/history", headers=auth)).json()
        check(
            "2. evidence lineage: all events task.transitioned, history matches count",
            len(evidence["source_events"]) == 3
            and len(evidence["evidence"]) >= 1
            and all(item.get("title") == "task.transitioned" and item.get("relationship") == "occurrence"
                    for item in evidence["evidence"])
            and len(hist["history"]) == 3
            and hist["occurrence_count"] == 3
            and all(item["event_name"] == "task.transitioned" for item in hist["history"]),
            f"source_events={len(evidence['source_events'])} history={len(hist['history'])}",
        )
        print("3. Formation + lineage verified")

        # ---- 3: one occurrence is never a pattern -------------------------------
        solo_proj = (
            await c.post(
                f"{API}/projects",
                json={"name": "Solo Effort", "description": "single blocked task", "status": "active"},
                headers=auth,
            )
        ).json()
        solo_scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Solo scope", "scope_type": "project", "entity_id": solo_proj["id"]},
                headers=auth,
            )
        ).json()
        await block_tasks(c, auth, solo_proj["id"], ["Lone delivery"])
        await dispatch(c, auth)
        await run_pattern_worker(c, auth)
        check(
            "3. one occurrence is never a pattern",
            not any(p.get("auth_project_id") == solo_proj["id"] for p in await patterns(c, auth)),
            f"solo_scope={solo_scope['id']}",
        )

        # ---- 4: exactly-once replay ----------------------------------------------
        before = {p["id"]: p["count"] for p in await patterns(c, auth)}
        hist_before = len((await c.get(f"{API}/brain/patterns/{pattern['id']}/history", headers=auth)).json()["history"])
        for _ in range(3):
            await dispatch(c, auth)
            await run_pattern_worker(c, auth)
        after = {p["id"]: p["count"] for p in await patterns(c, auth)}
        hist_after = len((await c.get(f"{API}/brain/patterns/{pattern['id']}/history", headers=auth)).json()["history"])
        check(
            "4. exactly-once replay: occurrences and history unchanged",
            after.get(pattern["id"]) == before.get(pattern["id"]) and hist_after == hist_before,
            f"count={before.get(pattern['id'])}->{after.get(pattern['id'])} history={hist_before}->{hist_after}",
        )
        print("4-5. Invisibility + exactly-once verified")

        # ---- 5: legacy surface -----------------------------------------------------
        legacy = await c.get(f"{API}/intelligence/patterns", params={"status": "open", "limit": 200}, headers=auth)
        assert legacy.status_code == 200, legacy.text
        legacy_ids = {p["id"] for p in legacy.json()}
        check(
            "5. legacy surface: /intelligence/patterns?status=open lists the lifecycle pattern",
            pattern["id"] in legacy_ids,
            f"legacy_count={len(legacy_ids)}",
        )

        # ---- 6: governance -----------------------------------------------------------
        hidden_proj, hidden_scope, hidden_pattern = await form_scoped_pattern(
            c, auth, "Hidden Ops", ["Hidden A", "Hidden B", "Hidden C"]
        )
        assert hidden_scope  # referenced
        emp = (await c.post(
            f"{API}/users/invite",
            json={"email": f"emp{t}@pc.test.co", "role": "manager", "full_name": "Scoped Mgr"},
            headers=auth,
        )).json()
        joined = (await c.post(
            f"{API}/auth/register/invite",
            json={"token": emp["token"], "email": f"emp{t}@pc.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"},
        )).json()
        emp_auth = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
            headers=auth,
        )
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x["scope_id"] is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(
            f"{API}/governance/delegations",
            json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.4"},
            headers=auth,
        )
        assert dg.status_code == 201, dg.text

        scoped_ids = {p["id"] for p in await patterns(c, emp_auth)}
        hidden_get = await c.get(f"{API}/brain/patterns/{hidden_pattern['id']}", headers=emp_auth)
        hidden_ev = await c.get(f"{API}/brain/patterns/{hidden_pattern['id']}/evidence", headers=emp_auth)
        hidden_rel = await c.get(f"{API}/brain/patterns/{hidden_pattern['id']}/related", headers=emp_auth)
        patch_denied = await c.patch(
            f"{API}/brain/patterns/{pattern['id']}", json={"status": "dismissed"}, headers=emp_auth
        )
        check(
            "6. governance: scoped reader sees own pattern; hidden is 404; PATCH is 403",
            pattern["id"] in scoped_ids
            and hidden_pattern["id"] not in scoped_ids
            and hidden_get.status_code == 404
            and hidden_ev.status_code == 404
            and hidden_rel.status_code == 404
            and patch_denied.status_code == 403,
            f"visible={pattern['id'] in scoped_ids} hidden_get={hidden_get.status_code} patch={patch_denied.status_code}",
        )
        print("6. Governance verified")

        # ---- 7: tenant isolation ----------------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc-{t}", f"eve{t}@rc.test.co", "Eve Rival")
        rival_ids = {p["id"] for p in await patterns(c, org_b["headers"])}
        check(
            "7. tenant isolation: outsider org sees nothing",
            pattern["id"] not in rival_ids,
            f"rival_count={len(rival_ids)}",
        )

        # ---- 8: brain integration ----------------------------------------------------
        rb = await c.post(
            f"{API}/brain/answer",
            json={"question": "our delivery tasks keep getting blocked repeatedly — is that a recurring pattern?"},
            headers=auth,
        )
        claims = rb.json().get("claims", []) if rb.status_code == 200 else []
        pattern_cited = any(
            cl.get("kind") == "pattern"
            and any(e.get("type") == "pattern" and e.get("url", "").startswith("/brain/patterns/")
                    for e in cl.get("evidence", []))
            for cl in claims
        )
        check(
            "8. brain integration: /brain/answer cites pattern claims",
            rb.status_code == 200 and pattern_cited,
            f"status={rb.status_code} claims={len(claims)}",
        )

        # ---- 9: worker + scheduler ---------------------------------------------------
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        reg = next((w for w in workers if w["name"] == "pattern"), None)
        run = await run_pattern_worker(c, auth)
        check(
            "9. pattern worker registered @ 120s and runs on demand",
            reg is not None and reg.get("interval_seconds") == 120 and reg.get("run_on_demand") is True
            and run.get("worker") == "pattern" and isinstance(run.get("processed"), int),
            f"reg={reg} run={run}",
        )

        # ---- 10: lifecycle --------------------------------------------------------------
        ack = await c.patch(f"{API}/brain/patterns/{pattern['id']}", json={"status": "acknowledged"}, headers=auth)
        acked = (await c.get(f"{API}/brain/patterns", params={"status": "acknowledged"}, headers=auth)).json()
        check(
            "10. lifecycle: acknowledge persists and lists under status=acknowledged",
            ack.status_code == 200 and ack.json().get("status") == "acknowledged"
            and pattern["id"] in {p["id"] for p in acked.get("patterns", [])},
            f"ack={ack.status_code}:{ack.text[:100]}",
        )
        print("8-10. Brain, worker, lifecycle verified")

        # ---- 11: endpoint contract --------------------------------------------------------
        anon_list = await c.get(f"{API}/brain/patterns")
        anon_get = await c.get(f"{API}/brain/patterns/{pattern['id']}")
        missing = await c.get(f"{API}/brain/patterns/does-not-exist", headers=auth)
        bad_status = await c.patch(
            f"{API}/intelligence/patterns/{pattern['id']}", json={"status": "banana"}, headers=auth
        )
        check(
            "11. endpoint contract: anonymous 401, missing 404, invalid status 422",
            anon_list.status_code in (401, 403) and anon_get.status_code in (401, 403)
            and missing.status_code == 404
            and bad_status.status_code == 422,
            f"anon={anon_list.status_code}/{anon_get.status_code} missing={missing.status_code} bad={bad_status.status_code}",
        )

        # ---- 12: related links --------------------------------------------------------------
        rel = (await c.get(f"{API}/brain/patterns/{pattern['id']}/related", headers=auth)).json()
        check(
            "12. related links: bounded",
            isinstance(rel.get("related"), list) and len(rel.get("related", [])) <= 10,
            f"count={len(rel.get('related', []))}",
        )
        print("11-12. Contracts verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
