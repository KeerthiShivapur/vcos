import asyncio
import sys
import time
import uuid

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    label = "PASS" if ok else "FAIL"
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{label}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


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


async def invite_and_accept(client: httpx.AsyncClient, headers: dict, email: str, full_name: str):
    r = await client.post(f"{API}/users/invite", json={"email": email, "role": "employee", "full_name": full_name}, headers=headers)
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{API}/auth/register/invite",
        json={"token": r.json()["token"], "email": email, "full_name": full_name, "password": "StrongPass123!"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 2 acceptance (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org_a = await register(c, "Acme Inc", f"acme-{t}", f"alice{t}@acme.test.co", "Alice Founder")
        org_b = await register(c, "Other Corp", f"other-{t}", f"zoe{t}@other.test.co", "Zoe Founder")
        print("1. Founder registered Acme Inc; second tenant Other Corp registered")

        bob = await invite_and_accept(c, org_a["headers"], f"bob{t}@acme.test.co", "Bob Worker")
        charlie = (await c.post(
            f"{API}/employees",
            json={"first_name": "Charlie", "email": f"charlie{t}@acme.test.co", "designation": "Engineer"},
            headers=org_a["headers"],
        )).json()
        bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
        print("2. Bob accepted the invite; Charlie was added as an employee")

        employees = (await c.get(f"{API}/employees", headers=org_a["headers"])).json()
        alice_emp = next(e for e in employees if e["email"] == org_a["user"]["email"])
        bob_emp = next(e for e in employees if e["email"] == bob["user"]["email"])
        charlie_emp = next(e for e in employees if e["email"] == f"charlie{t}@acme.test.co")

        dept = (await c.post(f"{API}/departments", json={"name": "Engineering", "code": "eng"}, headers=org_a["headers"])).json()
        team = (
            await c.post(
                f"{API}/teams",
                json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": bob_emp["id"]},
                headers=org_a["headers"],
            )
        ).json()
        print("3. Engineering department + Backend team created")

        check("invite-accept auto-creates Bob's employee record", bob_emp["id"] is not None)
        check("Charlie created via POST /employees", charlie_emp["id"] is not None)
        check("set manager: Charlie -> Bob", (await _patch(c, f"{API}/employees/{charlie_emp['id']}", {"manager_id": bob_emp["id"]}, org_a["headers"])).status_code == 200)
        check("set manager: Bob -> Alice", (await _patch(c, f"{API}/employees/{bob_emp['id']}", {"manager_id": alice_emp["id"]}, org_a["headers"])).status_code == 200)
        r = await _patch(c, f"{API}/employees/{alice_emp['id']}", {"manager_id": charlie_emp["id"]}, org_a["headers"])
        check("manager cycle Alice -> Charlie rejected with 400", r.status_code == 400 and "cycle" in r.json().get("detail", ""), r.text[:160])
        r = await _patch(c, f"{API}/employees/{alice_emp['id']}", {"manager_id": alice_emp["id"]}, org_a["headers"])
        check("self-manager rejected with 400", r.status_code == 400, r.text[:160])

        check("promote Charlie (designation change)", (await _patch(c, f"{API}/employees/{charlie_emp['id']}", {"designation": "Staff Engineer"}, org_a["headers"])).status_code == 200)
        check("transfer Charlie to Engineering", (await _patch(c, f"{API}/employees/{charlie_emp['id']}", {"department_id": dept["id"]}, org_a["headers"])).status_code == 200)
        print("4. Hierarchy, cycle guard, promotion, transfer done")

        events = (await c.get(f"{API}/events", headers=org_a["headers"])).json()["items"]
        names = {e["name"] for e in events}
        for expected in ("department.created", "team.created", "employee.created", "manager.changed", "employee.promoted", "employee.transferred"):
            check(f"event emitted: {expected}", expected in names)

        chart = (await c.get(f"{API}/organization/chart", headers=org_a["headers"])).json()
        ids = {n["id"] for n in chart["roots"]}
        check("org chart roots contain Alice", alice_emp["id"] in ids)
        graph = (await c.get(f"{API}/organization/graph", headers=org_a["headers"])).json()
        edges = {(e["relation"], e["source"], e["target"]) for e in graph.get("edges", [])}
        check("graph edge: Alice manages Bob", ("manages", alice_emp["id"], bob_emp["id"]) in edges)
        check("graph edge: Bob manages Charlie", ("manages", bob_emp["id"], charlie_emp["id"]) in edges)
        print("5. Org chart + graph show hierarchy")

        reports = (await c.get(f"{API}/employees/{bob_emp['id']}/reports", headers=org_a["headers"])).json()
        check("Bob's direct reports include Charlie", any(e["id"] == charlie_emp["id"] for e in reports))

        print("6. Waiting for live event worker to deliver notifications (max 120s)...")
        bob_titles: set[str] = set()
        alice_titles: set[str] = set()
        deadline = time.time() + 120
        while time.time() < deadline:
            bob_titles = {n["title"] for n in (await c.get(f"{API}/notifications", headers=bob_headers)).json()["items"]}
            alice_titles = {n["title"] for n in (await c.get(f"{API}/notifications", headers=org_a["headers"])).json()["items"]}
            if "Manager changed" in bob_titles and "New direct report" in bob_titles:
                break
            await asyncio.sleep(10)
        check("notification delivered: Bob 'Manager changed'", "Manager changed" in bob_titles)
        check("notification delivered: Bob 'New direct report' (Charlie joined his team)", "New direct report" in bob_titles)
        check("notification delivered: Alice 'New direct report'", "New direct report" in alice_titles)

        r = await c.get(f"{API}/employees", headers=bob_headers)
        check("employee role can read the directory", r.status_code == 200 and r.json())
        r = await c.post(f"{API}/users/invite", json={"email": f"nobody{t}@acme.test.co", "role": "employee", "full_name": "Nobody"}, headers=bob_headers)
        check("employee role cannot invite users", r.status_code == 403)
        r = await _patch(c, f"{API}/employees/{charlie_emp['id']}", {"manager_id": alice_emp["id"]}, bob_headers)
        check("employee role cannot change managers", r.status_code in (403, 400), r.text[:120])
        print("7. Permissions enforced for employee role")

        r = await c.get(f"{API}/departments/{dept['id']}", headers=org_b["headers"])
        check("tenant isolation: cross-org department is 404", r.status_code == 404)
        r = await c.get(f"{API}/employees/{alice_emp['id']}", headers=org_b["headers"])
        check("tenant isolation: cross-org employee is 404", r.status_code == 404)

        audit = (await c.get(f"{API}/audit", headers=org_a["headers"])).json()["items"]
        actions = {e["action"] for e in audit}
        for expected in ("department.created", "team.created", "employee.created", "manager.changed", "employee.transferred", "employee.promoted"):
            check(f"audit trail: {expected}", expected in actions)
        print("8. Audit trail complete")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


async def _patch(client: httpx.AsyncClient, url: str, json: dict, headers: dict):
    return await client.patch(url, json=json, headers=headers)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
