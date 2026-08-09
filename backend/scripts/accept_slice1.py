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
    print("=== VCOS Slice 1 acceptance: auth, organization setup, roles, RBAC (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org_a = await register(c, "Alpha Inc", f"alpha-{t}", f"alice{t}@alpha.test.co", "Alice Founder")
        print("1. Founder registered Alpha Inc")

        # --- auth basics -----------------------------------------------------
        r = await c.post(f"{API}/auth/login", json={"email": f"alice{t}@alpha.test.co", "password": "wrong-password"})
        check("login with wrong password rejected", r.status_code == 401)
        r = await c.post(f"{API}/auth/login", json={"email": f"alice{t}@alpha.test.co", "password": "StrongPass123!"})
        check("login with correct password", r.status_code == 200)
        r = await c.get(f"{API}/auth/me")
        check("unauthenticated request rejected", r.status_code == 401)
        r = await c.get(f"{API}/auth/me", headers=org_a["headers"])
        check("GET /auth/me returns the founder", r.status_code == 200 and r.json()["email"] == f"alice{t}@alpha.test.co")
        check("founder role is ceo", r.json()["role"] == "ceo")
        print("2. Auth basics: 401/200, role ceo")

        # --- invite + accept -------------------------------------------------
        bob = await invite_and_accept(c, org_a["headers"], f"bob{t}@alpha.test.co", "Bob Worker", "employee")
        bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
        r = await c.get(f"{API}/auth/me", headers=bob_headers)
        check("invite->accept gives Bob an active account", r.status_code == 200)
        check("Bob role is employee", r.json()["role"] == "employee")

        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"bob{t}@alpha.test.co", "role": "employee", "full_name": "Bob Again"},
            headers=org_a["headers"],
        )
        check("re-inviting an existing member rejected with 409", r.status_code == 409)
        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"dup{t}@alpha.test.co", "role": "employee", "full_name": "Dup"},
            headers=org_a["headers"],
        )
        check("first invite for a new email succeeds", r.status_code == 201)
        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"dup{t}@alpha.test.co", "role": "employee", "full_name": "Dup"},
            headers=org_a["headers"],
        )
        check("duplicate pending invite rejected with 409", r.status_code == 409)
        print("3. Invitation lifecycle: accept, duplicates guarded")

        # --- RBAC: employee --------------------------------------------------
        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"x{t}@alpha.test.co", "role": "employee", "full_name": "X"},
            headers=bob_headers,
        )
        check("employee cannot invite users (403)", r.status_code == 403)
        r = await c.get(f"{API}/roles", headers=bob_headers)
        check("employee cannot read roles (403)", r.status_code == 403)
        r = await c.get(f"{API}/users", headers=bob_headers)
        check("employee can read the user directory (200)", r.status_code == 200)
        r = await c.get(f"{API}/users/invitations", headers=bob_headers)
        check("employee cannot list invitations (403)", r.status_code == 403)
        r = await c.get(f"{API}/audit", headers=bob_headers)
        check("employee cannot read the audit log (403)", r.status_code == 403)
        print("4. RBAC: employee surface locked down")

        # --- RBAC: HR --------------------------------------------------------
        dana = await invite_and_accept(c, org_a["headers"], f"dana{t}@alpha.test.co", "Dana Hr", "hr")
        dana_headers = {"Authorization": f"Bearer {dana['access_token']}"}
        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"emp{t}@alpha.test.co", "role": "employee", "full_name": "Emp"},
            headers=dana_headers,
        )
        check("HR can invite an employee (201)", r.status_code == 201)
        r = await c.post(
            f"{API}/users/invite",
            json={"email": f"adminx{t}@alpha.test.co", "role": "admin", "full_name": "Admin X"},
            headers=dana_headers,
        )
        check("HR cannot invite an admin (role escalation guard)", r.status_code == 403)
        r = await c.get(f"{API}/users/invitations", headers=dana_headers)
        check("HR can read invitations", r.status_code == 200)
        r = await c.get(f"{API}/roles", headers=dana_headers)
        check("HR can read roles (roles:read granted)", r.status_code == 200)
        print("5. RBAC: HR can manage people but cannot escalate")

        # --- RBAC: admin -----------------------------------------------------
        admin = await invite_and_accept(c, org_a["headers"], f"admin{t}@alpha.test.co", "Ava Admin", "admin")
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        r = await c.get(f"{API}/auth/me", headers=admin_headers)
        check("invited admin accepts with role admin", r.json()["role"] == "admin")
        r = await c.get(f"{API}/users", headers=admin_headers)
        check("admin can list users (200)", r.status_code == 200)
        r = await c.get(f"{API}/roles", headers=admin_headers)
        check("admin can read roles (200)", r.status_code == 200)
        roles = {role["code"]: role["id"] for role in r.json()}
        r = await c.patch(f"{API}/users/{bob['user']['id']}/status", json={"status": "active"}, headers=admin_headers)
        check("admin can manage member status", r.status_code == 200)
        r = await c.post(f"{API}/users/{bob['user']['id']}/roles", json={"role_id": roles["employee"]}, headers=admin_headers)
        check("admin can assign an existing role", r.status_code == 200)
        r = await c.post(
            f"{API}/users/{bob['user']['id']}/roles",
            json={"role_id": roles["admin"], "replace_all": False},
            headers=dana_headers,
        )
        check("HR cannot assign the admin role (escalation guard)", r.status_code == 403, r.text[:160])
        print("6. RBAC: admin can read + manage users and roles")

        # --- role model ------------------------------------------------------
        r = await c.get(f"{API}/roles", headers=org_a["headers"])
        roles = {role["code"]: role for role in r.json()}
        for code in ("ceo", "admin", "hr", "employee"):
            check(f"system role present: {code}", code in roles)
        r = await c.get(f"{API}/roles/permissions", headers=org_a["headers"])
        perms = {p["code"] for p in r.json()}
        check("permission catalog includes users:invite", "users:invite" in perms)
        check("permission catalog includes users:manage", "users:manage" in perms)
        check("permission catalog includes roles:read", "roles:read" in perms)
        print("7. Role + permission model exposed")

        # --- sessions --------------------------------------------------------
        r = await c.post(
            f"{API}/auth/logout",
            json={"refresh_token": bob["refresh_token"], "all_devices": False},
            headers=bob_headers,
        )
        check("logout succeeds", r.status_code == 200)
        r = await c.post(f"{API}/auth/refresh", json={"refresh_token": bob["refresh_token"]})
        check("refresh after logout rejected (401)", r.status_code == 401)

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
