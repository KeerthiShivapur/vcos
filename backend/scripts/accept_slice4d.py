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


async def answer(client: httpx.AsyncClient, headers: dict, question: str):
    r = await client.post(f"{API}/brain/answer", json={"question": question}, headers=headers)
    return r


async def cited_evidence_ids(claims) -> set[str]:
    return {e["id"] for c in claims for e in c.get("evidence", [])}


async def search(client: httpx.AsyncClient, headers: dict, query: str):
    r = await client.get(f"{API}/search", params={"q": query}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["results"]


async def make_scoped_only(client: httpx.AsyncClient, headers: dict, user_id: str) -> None:
    """Remove the user's org-wide role so only a scoped assignment remains."""
    assignments = (
        await client.get(f"{API}/governance/assignments", params={"user_id": user_id}, headers=headers)
    ).json()
    org_wide = next(a for a in assignments if a["scope_id"] is None)
    removed = await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)
    assert removed.status_code == 200, removed.text


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.1 acceptance: canonical company intelligence & evidence layer (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Brain Corp", f"bc-{t}", f"ada{t}@bc.test.co", "Ada Founder")
        auth = org["headers"]
        emp = await invite_and_accept(c, auth, f"emp{t}@bc.test.co", "Emp Member")
        emp_auth = {"Authorization": f"Bearer {emp['access_token']}"}
        print("1. Founder (ceo) + employee set up")

        # --- seed evidence: project, task, conversation + message --------------
        proj = (
            await c.post(
                f"{API}/projects",
                json={"name": "Cloud Migration", "description": "Slice 4D evidence", "status": "active"},
                headers=auth,
            )
        ).json()
        task = (
            await c.post(
                f"{API}/tasks",
                json={"project_id": proj["id"], "title": "Cutover to the new platform", "status": "in_progress"},
                headers=auth,
            )
        ).json()
        me = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]
        convo = (
            await c.post(
                f"{API}/conversations",
                json={"type": "channel", "title": "aurora-launch", "member_ids": [me]},
                headers=auth,
            )
        ).json()
        sent = await c.post(
            f"{API}/conversations/{convo['id']}/messages",
            json={"content": "Aurora goes live with the Cloud Migration platform next week"},
            headers=auth,
        )
        assert sent.status_code == 201, sent.text
        msg_id = sent.json()["id"]
        print("2. Evidence seeded: project + task + conversation + message")

        # --- canonical answer contract -----------------------------------------
        r = await answer(c, auth, "What is the status of the Cloud Migration project and its tasks?")
        claims = r.json().get("claims", [])
        cited = await cited_evidence_ids(claims)
        check("brain/answer: 200 with non-empty claims", r.status_code == 200 and len(claims) > 0,
              f"status={r.status_code} claims={len(claims)}")
        check("answer evidence cites the real project (no fabrication)",
              proj["id"] in cited and all(
                  e.get("type") in {"project", "task", "message", "conversation", "scope", "decision", "goal", "budget"}
                  for c in claims for e in c.get("evidence", [])
              ),
              f"cited={sorted(cited)[:6]}")

        # --- tenant isolation ---------------------------------------------------
        org_b = await register(c, "Sneaky Brain", f"sb-{t}", f"eve{t}@sb.test.co", "Eve Sneaky")
        r_b = await answer(c, org_b["headers"], "What is the status of the Cloud Migration project and its tasks?")
        leaked = (await cited_evidence_ids(r_b.json().get("claims", []))) & {proj["id"], task["id"], convo["id"], msg_id}
        check("outsider org gets no cross-tenant evidence", not leaked,
              f"status={r_b.status_code} leaked={leaked}")
        # --- messaging membership gating ---------------------------------------
        r_msg = await answer(c, auth, "What was decided and discussed about the Aurora platform?")
        has_message = any(
            e.get("type") == "message" and e.get("id") == msg_id
            for c in r_msg.json().get("claims", []) for e in c.get("evidence", [])
        )
        check("owner sees membership-gated message evidence", has_message, r_msg.text[:200])

        # --- permission-filtered search ----------------------------------------
        owner_hits = await search(c, auth, "Aurora")
        emp_hits = await search(c, emp_auth, "Aurora")
        check(
            "search: member sees message, non-member does not",
            any(rr["type"] == "message" and rr["id"] == msg_id for rr in owner_hits)
            and not any(rr["type"] == "message" and rr["id"] == msg_id for rr in emp_hits),
            f"owner={[r['type'] for r in owner_hits]} emp={[r['type'] for r in emp_hits]}",
        )
        outs_hits = await search(c, org_b["headers"], "Cloud Migration")
        check("search: no cross-tenant leakage",
              not any(rr["id"] == proj["id"] for rr in outs_hits),
              f"outsider={[r['title'] for r in outs_hits][:4]}")
        print("3. Authorization differences: answer gating, membership filter, tenant isolation")

        # --- scoped-only caller (org-wide role removed) -------------------------
        await make_scoped_only(c, auth, emp["user"]["id"])
        r_scoped = await answer(c, emp_auth, "What is the status of the Cloud Migration project?")
        check("scoped-only caller denied brain (403)", r_scoped.status_code == 403, r_scoped.text[:160])
        print("4. Scoped-only authority cannot use the org-wide brain")

        # --- relationship graph --------------------------------------------------
        sync = await c.post(f"{API}/brain/graph/relationships/sync", json={"mode": "entity"}, headers=auth)
        sync_body = sync.json() if sync.status_code == 200 else {}
        check("graph sync returns synced count", sync.status_code == 200 and sync_body.get("synced", 0) >= 1
              and sync_body.get("mode") in {"entity", "recent"}, f"status={sync.status_code} body={sync.text[:160]}")
        tr = (
            await c.get(
                f"{API}/brain/graph/relationships/traverse",
                params={"node_type": "task", "node_id": task["id"], "max_depth": 3},
                headers=auth,
            )
        ).json()
        keys = {f"{n['type']}:{n['id']}" for n in tr.get("nodes", [])}
        check("traversal connects task -> project with bounded limits",
              f"project:{proj['id']}" in keys and tr.get("limits", {}).get("max_nodes") == 64,
              f"keys={sorted(keys)[:6]} limits={tr.get('limits')}")
        r_sync_emp = await c.post(f"{API}/brain/graph/relationships/sync", json={"mode": "entity"}, headers=emp_auth)
        r_tr_emp = await c.get(
            f"{API}/brain/graph/relationships/traverse",
            params={"node_type": "task", "node_id": task["id"]},
            headers=emp_auth,
        )
        check("graph RBAC: sync needs manage (403), traverse needs read (403)",
              r_sync_emp.status_code == 403 and r_tr_emp.status_code == 403,
              f"sync={r_sync_emp.status_code} traverse={r_tr_emp.status_code}")
        print("5. Relationship sync + bounded traversal + RBAC")

        # --- change-driven consumers --------------------------------------------
        processed = False
        edge_seen = False
        for _ in range(40):
            ev = (await c.get(f"{API}/intelligence/events", params={"limit": 100}, headers=auth)).json()
            msg_ev = [e for e in ev if e["name"] == "messaging.message_sent"]
            processed = bool(msg_ev) and msg_ev[0].get("processed_at") is not None
            tr = (
                await c.get(
                    f"{API}/brain/graph/relationships/traverse",
                    params={"node_type": "conversation", "node_id": convo["id"], "max_depth": 2},
                    headers=auth,
                )
            ).json()
            nodes = tr.get("nodes", [])
            edge_seen = any(n["type"] == "message" and n["id"] == msg_id for n in nodes)
            if processed and edge_seen:
                break
            await asyncio.sleep(3)
        check("message_sent change-driven: event processed, message edge reachable",
              processed and edge_seen, f"processed={processed} edge={edge_seen}")

        tr = (
            await c.get(
                f"{API}/brain/graph/relationships/traverse",
                params={"node_type": "conversation", "node_id": convo["id"], "max_depth": 2},
                headers=auth,
            )
        ).json()
        msg_nodes = [n for n in tr.get("nodes", []) if n["type"] == "message" and n["id"] == msg_id]
        await c.post(f"{API}/brain/graph/relationships/sync", json={"mode": "entity"}, headers=auth)
        tr2 = (
            await c.get(
                f"{API}/brain/graph/relationships/traverse",
                params={"node_type": "conversation", "node_id": convo["id"], "max_depth": 2},
                headers=auth,
            )
        ).json()
        msg_nodes2 = [n for n in tr2.get("nodes", []) if n["type"] == "message" and n["id"] == msg_id]
        check("idempotent: single message node, re-sync does not duplicate",
              len(msg_nodes) == 1 and len(msg_nodes2) == 1,
              f"before={len(msg_nodes)} after={len(msg_nodes2)}")
        print("6. Change-driven consumers + idempotent sync")

        # --- worker + scheduler ---------------------------------------------------
        run1 = await c.post(f"{API}/intelligence/workers/company_intel/run", headers=auth)
        run2 = await c.post(f"{API}/intelligence/workers/company_intel/run", headers=auth)
        b1 = run1.json() if run1.status_code == 200 else {}
        check("company_intel worker runs on demand (idempotent)",
              run1.status_code == 200 and b1.get("worker") == "company_intel"
              and isinstance(b1.get("processed"), int) and b1["processed"] >= 0
              and run2.status_code == 200,
              f"r1={run1.status_code} {run1.text[:120]} r2={run2.status_code}")
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        reg = next((w for w in workers if w["name"] == "company_intel"), None)
        check("scheduler registry exposes company_intel @ 900s",
              reg is not None and reg.get("interval_seconds") == 900,
              f"registry={[w['name'] for w in workers]}")
        print("7. Worker sweep + scheduler registry")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
