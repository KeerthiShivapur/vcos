import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def datetime_utcnow():
    return datetime.now(timezone.utc)


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


async def make_scope(client, headers, name, scope_type, parent_id=None):
    payload = {"name": name, "scope_type": scope_type}
    if parent_id:
        payload["parent_id"] = parent_id
    r = await client.post(f"{API}/governance/scopes", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def effective(client, headers, user_id, scope_id=None):
    params = {"user_id": user_id}
    if scope_id:
        params["scope_id"] = scope_id
    r = await client.get(f"{API}/governance/effective-permissions", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def role_id(client, headers, code: str) -> str:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    return next(r["id"] for r in roles if r["code"] == code)


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4C acceptance: governance, RBAC & enterprise control (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org = await register(c, "Govern Corp", f"gc-{t}", f"ada{t}@gc.test.co", "Ada Founder")
        auth = org["headers"]
        invited = await invite_and_accept(c, auth, f"emp{t}@gc.test.co", "Emp Worker", "employee")
        emp_auth = {"Authorization": f"Bearer {invited['access_token']}"}
        emp_user_id = invited["user"]["id"]
        manager_role = await role_id(c, auth, "manager")
        employees = (await c.get(f"{API}/employees", headers=auth)).json()
        emp_employee_id = next(e["id"] for e in employees if e["email"] == f"emp{t}@gc.test.co")
        print("1. Founder (ceo) + employee set up")

        # --- RBAC: employee has no governance surface -------------------------
        r403 = await c.get(f"{API}/governance/scopes", headers=emp_auth)
        check("employee cannot read scopes (403)", r403.status_code == 403, r403.text[:160])
        r403b = await c.post(
            f"{API}/governance/scopes",
            json={"name": "Sneaky", "scope_type": "department"},
            headers=emp_auth,
        )
        check("employee cannot create scopes (403)", r403b.status_code == 403, r403b.text[:160])
        print("2. Governance surface gated to governance:read/manage holders")

        # --- scope tree ---------------------------------------------------------
        eng = await make_scope(c, auth, "Engineering", "department")
        backend = await make_scope(c, auth, "Backend", "team", parent_id=eng["id"])
        finance = await make_scope(c, auth, "Finance", "department")
        scopes = (await c.get(f"{API}/governance/scopes", headers=auth)).json()
        check("scope tree created (dept -> team) with depth",
              {s["name"]: s["depth"] for s in scopes} == {"Engineering": 0, "Backend": 1, "Finance": 0},
              str(scopes)[:240])
        deep_parent = backend
        for i in range(31):
            deep_parent = await make_scope(c, auth, f"L{i}", "team", parent_id=deep_parent["id"])
        r400 = await c.post(
            f"{API}/governance/scopes",
            json={"name": "Too deep", "scope_type": "team", "parent_id": deep_parent["id"]},
            headers=auth,
        )
        check("scope depth capped at 32 (400)", r400.status_code == 400, r400.text[:160])
        print("3. Scope tree + depth cap (bounded ancestry)")

        # --- scoped role assignment + effective permissions --------------------
        a = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": emp_user_id, "role_id": manager_role, "scope_id": backend["id"]},
            headers=auth,
        )
        check("manager role assigned at Backend scope (201)", a.status_code == 201, a.text[:160])
        at_backend = await effective(c, auth, emp_user_id, scope_id=backend["id"])
        check("effective: projects:manage at Backend", "projects:manage" in at_backend["permissions"], str(at_backend)[:240])
        at_finance = await effective(c, auth, emp_user_id, scope_id=finance["id"])
        check("no leakage to sibling Finance scope",
              "projects:manage" not in at_finance["permissions"], str(at_finance)[:240])
        org_wide = await effective(c, auth, emp_user_id)
        check("org-wide authority unchanged by scoped assignment",
              "projects:manage" not in org_wide["permissions"], str(org_wide)[:240])
        print("4. Scoped authority flows downward only (bounded, no sibling leakage)")

        # --- escalation guard ---------------------------------------------------
        employee_role = await role_id(c, auth, "employee")
        denied = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": invited["user"]["id"], "role_id": manager_role},
            headers=emp_auth,
        )
        check("employee cannot assign a role at all (403)", denied.status_code == 403, denied.text[:160])
        print("5. No privilege escalation: assignment requires governance:manage")

        # --- delegations ---------------------------------------------------------
        grant = (
            await c.post(
                f"{API}/governance/delegations",
                json={
                    "granted_to_user": emp_user_id,
                    "permission_code": "projects:manage",
                    "reason": "Temporary ownership",
                    "expires_at": (datetime_utcnow() + timedelta(hours=1)).isoformat(),
                },
                headers=auth,
            )
        ).json()
        check("delegation created org-wide (active)", grant["status"] == "active", str(grant)[:200])
        created = await c.post(
            f"{API}/projects", json={"name": "Delegated project"}, headers=emp_auth
        )
        check("delegate can create projects (201)", created.status_code == 201, created.text[:160])
        revoke = await c.post(
            f"{API}/governance/delegations/{grant['id']}/revoke", headers=auth
        )
        check("delegation revoked (200)", revoke.status_code == 200 and revoke.json()["status"] == "revoked", revoke.text[:160])
        too_late = await c.post(
            f"{API}/projects", json={"name": "Too late"}, headers=emp_auth
        )
        check("revocation is immediate (403)", too_late.status_code == 403, too_late.text[:160])

        expired_grant = (
            await c.post(
                f"{API}/governance/delegations",
                json={
                    "granted_to_user": emp_user_id,
                    "permission_code": "projects:manage",
                    "expires_at": (datetime_utcnow() - timedelta(minutes=5)).isoformat(),
                },
                headers=auth,
            )
        ).json()
        expired_use = await c.post(
            f"{API}/projects", json={"name": "Expired"}, headers=emp_auth
        )
        check("expired delegation denied lazily (403)", expired_use.status_code == 403, expired_use.text[:160])
        print("6. Delegation create -> use -> revoke (403) -> expiry (lazy deny)")

        # --- approval policy gate -----------------------------------------------
        policy = (
            await c.post(
                f"{API}/governance/policies",
                json={
                    "name": "Release gate",
                    "approval_type": "release",
                    "required_permission": "approvals:manage",
                    "self_approval_allowed": True,
                },
                headers=auth,
            )
        ).json()
        check("approval policy created (201)", bool(policy.get("id")), str(policy)[:200])
        approval = (
            await c.post(
                f"{API}/approvals",
                json={"approval_type": "release", "title": "Ship 4C", "policy_id": policy["id"]},
                headers=auth,
            )
        ).json()
        denied_decide = await c.post(
            f"{API}/approvals/{approval['id']}/decide",
            json={"decision": "approved"},
            headers=emp_auth,
        )
        check("employee without the policy permission refused (403)",
              denied_decide.status_code == 403, denied_decide.text[:160])
        decided = await c.post(
            f"{API}/approvals/{approval['id']}/decide",
            json={"decision": "approved", "note": "Go"},
            headers=auth,
        )
        check("policy holder decides the approval (200/approved)",
              decided.status_code == 200 and decided.json()["status"] == "approved", decided.text[:160])
        print("7. Approval policies gate who may decide what")

        # --- tenant isolation -----------------------------------------------------
        org_b = await register(c, "Sneaky Gov", f"sg-{t}", f"eve{t}@sg.test.co", "Eve Sneaky")
        headers_b = org_b["headers"]
        r404 = await c.get(f"{API}/governance/scopes", headers=headers_b)
        org_b_scopes = r404.json() if r404.status_code == 200 else []
        leaked = [s["name"] for s in org_b_scopes if s["name"] in {"Engineering", "Backend", "Finance"}]
        check("outsider org sees only its own scopes (no leak)",
              r404.status_code == 200 and not leaked, f"status={r404.status_code} leaked={leaked}")
        r404b = await c.get(f"{API}/governance/effective-permissions", params={"user_id": emp_user_id}, headers=headers_b)
        check("outsider org cannot evaluate members (404)", r404b.status_code == 404, r404b.text[:160])
        print("8. Tenant isolation on governance data")

        # --- events + audit -------------------------------------------------------
        events = (await c.get(f"{API}/events", headers=auth)).json()["items"]
        names = {e["name"] for e in events}
        for expected in (
            "governance.scope.created",
            "governance.assignment.created",
            "governance.delegation.created",
            "governance.delegation.revoked",
            "governance.policy.created",
        ):
            check(f"event trail contains {expected}", expected in names, f"have: {sorted(names)[:14]}")
        audit = (await c.get(f"{API}/audit", params={"action": "governance.delegation.created"}, headers=auth)).json()
        check("audit: delegation creation recorded", audit.get("total", 0) >= 1, str(audit)[:200])
        print("9. Governance loop fully audited + evented")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
