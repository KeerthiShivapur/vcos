"""Slice 4F.1 acceptance — Universal People Intelligence Foundation (live API).

Checks against the running stack (http://localhost:8999). 4F.1 is the
foundation of the People Intelligence family: canonical person profiles with
always-on temporal windows (membership / role / reporting), identity resolution
that never silently merges, the living org chart + people graph, the /brain/
people + /brain/org surfaces, governed brain-question intents, exact-once
event journaling for the canonical employee lifecycle, governance (downward-
only visibility, never reveals invisible subordinates), and tenant isolation.
NOT another isolated silver — everything is read from the SAME canonical
people model already in the schema.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
KNOW = f"{API}/brain/knowledge"
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
        "user": data["user"],
        "organization": data["organization"],
    }


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 400) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=30
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:
        pass
    return -1


async def poll(
    client: httpx.AsyncClient,
    headers: dict,
    method: str,
    url: str,
    predicate,
    params: dict | None = None,
    json: dict | None = None,
    timeout: float = 300,
    tick=None,
) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = await client.request(method, url, headers=headers, params=params, json=json)
        if r.status_code in (200, 201):
            last = r.json()
            if predicate(last):
                return last
        if tick:
            try:
                await tick()
            except Exception:
                pass
        await asyncio.sleep(2)
    return last


async def hire(client: httpx.AsyncClient, headers: dict, email: str, first: str, last: str, **extra) -> dict:
    r = await client.post(
        f"{API}/employees",
        json={"first_name": first, "last_name": last, "email": email, **extra},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "People Co", f"peopleco-{t}", f"people{t}@peopleco.test.co", "People Founder")
        auth = org["headers"]
        oid = org["organization"]["id"]
        me = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]

        # -------- 1. canonical directory + temporal membership windows
        team = (await c.post(f"{API}/teams", json={"name": "Comet", "code": "comet"}, headers=auth)).json()
        dept = (await c.post(f"{API}/departments", json={"name": "Product", "code": "prod"}, headers=auth)).json()
        ada = await hire(c, auth, f"a{t}@peopleco.test.co", "Ada", "Alvarez",
                         team_id=team["id"], department_id=dept["id"])
        await dispatch(c, auth)
        profile = (await c.get(f"{BRAIN}/people/{ada['id']}", headers=auth)).json()
        check("1. every hire materializes a canonical person with a membership window",
              profile["id"] == ada["id"]
              and (profile.get("current_membership") or {}).get("employment_status") == "active",
              str(profile)[:250])
        check("2. the hire is journaled as a durable person.created",
              any(i.get("kind") == "person.created" and i.get("event_id")
                  for i in (await c.get(f"{BRAIN}/people/{ada['id']}/history", headers=auth)).json()
                  .get("history", {}).get("timeline", [])),
              str((await c.get(f"{BRAIN}/people/{ada['id']}/history", headers=auth)).json().get("history"))[:250])

        base = time.time()
        t0 = time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime(base + 120))
        t1 = time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime(base + 3720))
        susp = await c.put(f"{BRAIN}/people/{ada['id']}/membership",
                           json={"employment_status": "suspended", "valid_from": t0},
                           headers=auth)
        reopen = await c.put(f"{BRAIN}/people/{ada['id']}/membership",
                             json={"employment_status": "active", "valid_from": t1},
                             headers=auth)
        hist = (await c.get(f"{BRAIN}/people/{ada['id']}/history", headers=auth)).json()
        statuses = [m["employment_status"] for m in hist["history"]["memberships"]]
        midpoint = time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime(base + 360 + 60))
        at = (await c.get(f"{BRAIN}/people/{ada['id']}/at", params={"at": midpoint}, headers=auth)).json()
        check("3. membership windows are temporal: history keeps every window",
              susp.status_code == 200 and reopen.status_code == 200
              and statuses == ["active", "suspended", "active"], f"{susp.status_code} {statuses}")
        check("4. the past is reconstructable at any moment (suspended then)",
              (at.get("membership") or {}).get("employment_status") == "suspended",
              str(at)[:250])

        # -------- 5. identity resolution: never silently merges
        linked = await c.post(f"{BRAIN}/people/{ada['id']}/identities",
                              json={"source": "github", "source_key": "ada-dev", "verified": True},
                              headers=auth)
        resolved = (await c.post(f"{BRAIN}/people/identities/resolve",
                                 json={"source": "github", "source_key": "ada-dev"}, headers=auth)).json()
        brand = await hire(c, auth, f"b{t}@peopleco.test.co", "Brand", "Ngo")
        refused = await c.post(f"{BRAIN}/people/{brand['id']}/identities",
                               json={"source": "github", "source_key": "ada-dev", "verified": True},
                               headers=auth)
        check("5. a strong identity key resolves to exactly one person",
              linked.status_code == 200 and resolved.get("person_id") == ada["id"]
              and resolved.get("ambiguous") is False, str(resolved))
        check("6. a conflicting key is refused, never merged",
              refused.status_code == 409,
              f"status={refused.status_code} {refused.text[:200]}")

        # -------- 7. roles are primary-demoting temporal windows
        r1 = await c.post(f"{BRAIN}/people/{ada['id']}/roles",
                          json={"role_title": "Backend Engineer", "role_type": "functional", "is_primary": True},
                          headers=auth)
        r2 = await c.post(f"{BRAIN}/people/{ada['id']}/roles",
                          json={"role_title": "Tech Lead", "role_type": "functional", "is_primary": True},
                          headers=auth)
        roles = (await c.get(f"{BRAIN}/people/{ada['id']}/history", headers=auth)).json()
        open_roles = [r for r in roles["history"]["roles"] if r["valid_to"] is None]
        check("7. assigning a new primary role demotes the previous (one open primary)",
              r1.status_code == 200 and r2.status_code == 200
              and [r["role_title"] for r in open_roles] == ["Tech Lead"],
              str(open_roles)[:200])
        emp_ada = (await c.get(f"{API}/employees/{ada['id']}", headers=auth)).json()
        check("8. the employee record mirrors the open primary designation",
              emp_ada.get("designation") == "Tech Lead", str(emp_ada)[:150])

        # -------- 9. reporting windows drive the org chart + reporting line
        boss = await hire(c, auth, f"c{t}@peopleco.test.co", "Cin", "Oo")
        rep = await c.post(f"{BRAIN}/people/{ada['id']}/reporting",
                           json={"relationship_type": "reports_to", "manager_person_id": boss["id"]},
                           headers=auth)
        line = (await c.get(f"{BRAIN}/people/{ada['id']}/reporting-line", headers=auth)).json()
        chain_names = [m["name"] for m in line["manager_chain"]]
        check("9. reporting windows reconstruct the reporting line above a person",
              rep.status_code == 200 and "Cin Oo" in chain_names, f"{chain_names}")
        chart = (await c.get(f"{BRAIN}/org/chart", headers=auth)).json()
        flat = []
        for root in chart.get("roots") or []:
            flat.append(root["id"])
            flat.extend(ch["id"] for ch in root.get("children") or [])
        check("10. the living org chart is built from open windows",
              boss["id"] in flat and ada["id"] in flat, f"sorted={sorted(flat)}")

        # -------- 11. related people are deterministic + explained
        buddy = await hire(c, auth, f"d{t}@peopleco.test.co", "Dev", "Pak",
                           team_id=team["id"], department_id=dept["id"])
        related = (await c.get(f"{BRAIN}/people/{ada['id']}/related", headers=auth)).json()
        rel_map = {r["person_id"]: r["relation"] for r in related.get("relations") or []}
        check("11. relation strengths are deterministic (team > department)",
              rel_map.get(buddy["id"]) == "same_team"
              and rel_map.get(boss["id"]) == "manager"
              and related.get("count", 0) >= 2, str(rel_map))

        # -------- 12. people graph + units
        graph = (await c.get(f"{BRAIN}/org/graph", headers=auth)).json()
        units = (await c.get(f"{BRAIN}/org/units/summary", headers=auth)).json()
        members = (await c.get(f"{BRAIN}/org/units", params={"unit_kind": "team", "unit_id": team["id"]}, headers=auth)).json()
        check("12. the people graph materializes nodes + edges",
              len(graph.get("nodes") or []) >= 3 and len(graph.get("edges") or []) >= 1,
              str(graph)[:250])
        check("13. unit surfaces enumerate members from the canonical model",
              members.get("members_count", 0) >= 2 and members.get("unit_name") == "Comet", str(members)[:250])

        # -------- 14. governed brain questions
        q1 = (await c.post(f"{KNOW}/query", json={"question": "who works in the Comet team?"}, headers=auth)).json()
        names = {p["name"] for p in q1.get("answers") or []}
        check("14. 'who works in X' binds the unit and names its members",
              q1.get("intent") == "people" and q1.get("kind") == "unit_members"
              and "Ada Alvarez" in names, str(q1)[:250])
        q2 = (await c.post(f"{KNOW}/query", json={"question": "who reports to Cin Oo?"}, headers=auth)).json()
        q3 = (await c.post(f"{KNOW}/query", json={"question": "show the org chart"}, headers=auth)).json()
        check("15. 'who reports to X' resolves the direct reports",
              q2.get("intent") == "people" and q2.get("kind") == "direct_reports"
              and any(a.get("name") == "Ada Alvarez" for a in q2.get("answers") or []), str(q2)[:250])
        check("16. the org chart brain question materializes the chart",
              q3.get("intent") == "people" and q3.get("kind") == "org_chart", str(q3)[:250])

        # -------- 17. exact-once under event replay (promotion + offboarding)
        prom_resp = await c.patch(f"{API}/employees/{ada['id']}",
                                  json={"designation": "Principal Engineer"}, headers=auth)
        assert prom_resp.status_code == 200, prom_resp.text
        await dispatch(c, auth)
        timeline = (await c.get(f"{BRAIN}/people/{ada['id']}/history", headers=auth)).json()
        promoted_kinds = [m["kind"] for m in timeline["history"]["timeline"]
                          if m["kind"] == "role.assigned" and m.get("event_id")]
        roles_now = [r["role_title"] for r in timeline["history"]["roles"] if r["valid_to"] is None]
        check("17. a promotion opens exactly one primary role window",
              len(promoted_kinds) == 1 and roles_now == ["Principal Engineer"],
              f"kinds={promoted_kinds} roles={roles_now}")

        off = await c.post(f"{API}/offboarding",
                           json={"employee_id": brand["id"], "reason": "resigned"}, headers=auth)
        assert off.status_code == 200, off.text
        off_id = off.json()["id"]
        tasks = (await c.get(f"{API}/offboarding/{off_id}", headers=auth)).json().get("tasks", [])
        for task in tasks:
            await c.post(f"{API}/offboarding/{off_id}/tasks/{task['id']}/complete",
                         json={}, headers=auth)
        done = await c.post(f"{API}/offboarding/{off_id}/complete", headers=auth)
        assert done.status_code == 200, done.text
        await dispatch(c, auth)
        brand_hist = (await c.get(f"{BRAIN}/people/{brand['id']}/history", headers=auth)).json()
        brand_statuses = [m["employment_status"] for m in brand_hist["history"]["memberships"]]
        check("18. offboarding closes the membership window once (departed retained)",
              brand_statuses.count("departed") == 1
              and brand_statuses[0] == "active"
              and brand_statuses[-1] == "departed", f"{brand_statuses}")

        # -------- 19. governance: scoped readers see only their scope
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Comet scope", "scope_type": "team", "entity_id": team["id"]},
                              headers=auth)).json()
        emp = (await c.post(f"{API}/users/invite", json={
            "email": f"sco{t}@peopleco.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite",
                               json={"token": emp["token"], "email": f"sco{t}@peopleco.test.co",
                                     "full_name": "Scoped Mgr", "password": "StrongPass123!"},
                               headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        await c.post(f"{API}/governance/assignments",
                     json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
                     headers=auth)
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)
        await c.post(f"{API}/governance/delegations",
                     json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4f.1"},
                     headers=auth)
        outsider = await hire(c, auth, f"e{t}@peopleco.test.co", "Ezra", "Ray")
        scoped_dir = (await c.get(f"{BRAIN}/people", headers=scoped)).json()
        scoped_ids = {p["id"] for p in scoped_dir.get("people") or []}
        hidden_unit = (await c.get(f"{BRAIN}/org/units",
                                   params={"unit_kind": "team", "unit_id": team["id"]}, headers=scoped)).json()
        denied = await c.post(f"{BRAIN}/people/{outsider['id']}/roles",
                              json={"role_title": "Ghost", "role_type": "functional"},
                              headers=scoped)
        allow_owner = await c.post(f"{BRAIN}/people/{outsider['id']}/roles",
                                   json={"role_title": "Backend Engineer", "role_type": "functional"},
                                   headers=auth)
        check("19. scoped readers see exactly their team on every surface",
              scoped_dir.get("scope") == "scoped"
              and ada["id"] in scoped_ids and outsider["id"] not in scoped_ids
              and hidden_unit.get("members_count", -1) >= 2,
              f"dir={sorted(scoped_ids)} unit={hidden_unit.get('members_count')}")
        check("20. writes need employees:manage (403 scoped, 200 admin)",
              denied.status_code == 403 and allow_owner.status_code == 200,
              f"denied={denied.status_code} owner={allow_owner.status_code}")

        # -------- 21. tenant isolation
        rival = await register(c, "Rival People Co", f"rivpeople-{t}", f"r{t}@rivpeople.test.co", "Riv Founder")
        await dispatch(c, rival["headers"])
        r_dir = (await c.get(f"{BRAIN}/people", headers=rival["headers"])).json()
        r_profile = await c.get(f"{BRAIN}/people/{ada['id']}", headers=rival["headers"])
        r_write = await c.post(f"{BRAIN}/people/{ada['id']}/roles",
                               json={"role_title": "Ghost", "role_type": "functional"},
                               headers=rival["headers"])
        check("21. tenant isolation: a rival sees only their own org and mutates nothing",
              r_dir.get("total_visible") == 1
              and ada["id"] not in {p["id"] for p in r_dir.get("people") or []}
              and r_profile.status_code == 404
              and r_write.status_code == 404,
              f"dir={r_dir.get('total_visible')} profile={r_profile.status_code} write={r_write.status_code}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))