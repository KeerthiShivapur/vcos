"""Slice 4D.2 acceptance — semantic company knowledge intelligence (live API).

14 checks against the running stack (http://localhost:8999):

  1. offline provider: deterministic, scores present, no embedding/confidence
  2. hybrid ranking: matching document ranks first (semantic + lexical)
  3. evidence lineage: source row, url, freshness, provider on every result
  4. multi-kind: policy surfaces under kinds=["policy"]
  5. multi-kind: wiki surfaces under kinds=["wiki"]
  6. change-driven create: new published doc becomes searchable
  7. change-driven update: edited content replaces the old content
  8. change-driven delete: removed doc stops surfacing
  9. tenant isolation: separate org sees nothing
 10. governance scoping: scoped manager with delegated brain:read sees only
     the project-anchored document
 11. governance boundary: scoped-only caller without delegation gets 403
 12. brain integration: /brain/answer cites document evidence
 13. endpoint contract: 422 blank question, 401/403 anonymous
 14. worker + scheduler: indexing worker registered @ 1800s, idempotent run

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


async def create_document(client: httpx.AsyncClient, headers: dict, title: str, content: str, project_id: str | None = None):
    r = await client.post(f"{API}/documents", json={"title": title, "content": content, "project_id": project_id}, headers=headers)
    assert r.status_code == 201, r.text
    doc = r.json()
    rp = await client.post(f"{API}/documents/{doc['id']}/publish", headers=headers)
    assert rp.status_code == 200, rp.text
    return doc


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 500) -> int:
    r = await client.post(f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("processed", 0)


async def knowledge_search(client: httpx.AsyncClient, headers: dict, question: str, kinds: list[str] | None = None):
    r = await client.post(f"{API}/brain/knowledge/search", json={"question": question, "kinds": kinds}, headers=headers)
    return r


async def wait_indexed(client: httpx.AsyncClient, headers: dict, question: str, kinds: list[str], target_id: str,
                       dispatch_auth: dict | None = None) -> dict:
    """Poll until target_id surfaces (bounded), then return the search body.

    ``dispatch_auth`` may be a stronger caller for the event-dispatch endpoint
    (scoped callers may search but not manage the intelligence event bus).
    """
    dispatcher = dispatch_auth or headers
    for _ in range(12):
        await dispatch(client, dispatcher)
        r = await knowledge_search(client, headers, question, kinds)
        if r.status_code == 200:
            body = r.json()
            if any(res["source_id"] == target_id for res in body.get("results", [])):
                return body
        await asyncio.sleep(3)
    return (await knowledge_search(client, headers, question, kinds)).json()


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.2 acceptance: semantic company knowledge intelligence (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Knowledge Corp", f"kc-{t}", f"ada{t}@kc.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")

        # Drain the global event queue so this run's events are dispatched
        # promptly (the dispatcher is global FIFO across all tenants).
        for _ in range(15):
            if await dispatch(c, auth) == 0:
                break
            await asyncio.sleep(1)

        proj = (
            await c.post(
                f"{API}/projects",
                json={"name": "Nebula", "description": "Slice 4D.2 anchor", "status": "active"},
                headers=auth,
            )
        ).json()
        scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Nebula Scope", "scope_type": "project", "entity_id": proj["id"]},
                headers=auth,
            )
        ).json()
        match = await create_document(
            c, auth, "Refund Policy",
            "Refunds are approved by finance after the customer request is verified against the contract "
            "terms. Escalations go to the approval workflow. Refund Policy refunds finance approval workflow "
            "escalation contract verification. " * 8,
        )
        anchored = await create_document(
            c, auth, "Scoped Finance Doc",
            "Expense policy details visible only inside the Nebula project scope. Expense policy Nebula "
            "project anchored finance details. " * 8,
            project_id=proj["id"],
        )
        policy = (
            await c.post(
                f"{API}/policies",
                json={
                    "title": "Expense Policy",
                    "content": "All expenses above one thousand dollars require manager approval before "
                    "reimbursement. Expense Policy approval reimbursement manager threshold. " * 8,
                },
                headers=auth,
            )
        ).json()
        rsub = await c.post(f"{API}/policies/{policy['id']}/submit", headers=auth)
        rapp = await c.post(f"{API}/policies/{policy['id']}/approve", headers=auth)
        assert rsub.status_code == 200 and rapp.status_code == 200, (rsub.text, rapp.text)
        wiki = (
            await c.post(
                f"{API}/wiki",
                json={
                    "title": "Onboarding Runbook",
                    "content": "New hires follow the equipment request and system access onboarding steps. "
                    "Onboarding Runbook equipment system access new hires. " * 8,
                },
                headers=auth,
            )
        ).json()
        rwp = await c.post(f"{API}/wiki/{wiki['id']}/publish", headers=auth)
        assert rwp.status_code == 200, rwp.text
        await dispatch(c, auth)
        print("2. Knowledge seeded: 2 documents, 1 policy (approved), 1 wiki (published)")

        # ---- 1-3: offline provider, hybrid ranking, evidence lineage ----------
        r = await wait_indexed(c, auth, "how does the refund approval workflow work", ["document"], match["id"])
        res = r.get("results", [])
        top = res[0] if res else {}
        check(
            "1. offline provider: deterministic with explicit scores",
            r.get("provider") == "deterministic"
            and isinstance(top.get("semantic_score"), (int, float))
            and isinstance(top.get("lexical_score"), (int, float))
            and isinstance(top.get("retrieval_score"), (int, float)),
            f"provider={r.get('provider')} top={top.get('source_id')}",
        )
        check(
            "2. hybrid ranking: matching document first",
            bool(res) and top.get("source_id") == match["id"] and top.get("title") == "Refund Policy",
            f"top={top.get('source_id')}",
        )
        check(
            "3. evidence lineage, no embeddings/confidence exposed",
            bool(res)
            and top.get("url", "").startswith("/documents/")
            and top.get("provider") == "deterministic"
            and top.get("updated_at")
            and top.get("indexed_at")
            and "embedding" not in top
            and "confidence" not in top,
            f"keys={sorted(top.keys())}",
        )
        print("3. Provider, ranking and lineage verified")

        # ---- 4-5: multi-kind retrieval ----------------------------------------
        rp = await wait_indexed(c, auth, "manager approval above one thousand dollars", ["policy"], policy["id"])
        check(
            "4. multi-kind: policy searchable under kinds=[policy]",
            any(x["source_id"] == policy["id"] and x["source_type"] == "policy" for x in rp.get("results", [])),
            f"hits={[x['source_type'] for x in rp.get('results', [])]}",
        )
        rw = await wait_indexed(c, auth, "equipment request for new hires", ["wiki"], wiki["id"])
        check(
            "5. multi-kind: wiki searchable under kinds=[wiki]",
            any(x["source_id"] == wiki["id"] and x["source_type"] == "wiki" for x in rw.get("results", [])),
            f"hits={[x['source_type'] for x in rw.get('results', [])]}",
        )
        print("4-5. Policy + wiki kinds indexed and retrievable")

        # ---- 6-8: change-driven lifecycle --------------------------------------
        fresh = await create_document(
            c, auth, "Fresh Handbook",
            "The brand new supplier onboarding handbook describes vendor due diligence. Fresh Handbook "
            "supplier onboarding vendor due diligence. " * 8,
        )
        r6 = await wait_indexed(c, auth, "supplier onboarding vendor due diligence", ["document"], fresh["id"])
        check(
            "6. change-driven create: new published doc becomes searchable",
            any(x["source_id"] == fresh["id"] for x in r6.get("results", [])),
            f"hits={[x['source_id'] for x in r6.get('results', [])]}",
        )

        updated = await c.patch(
            f"{API}/documents/{fresh['id']}",
            json={"content": "The handbook now covers customer success playbooks and renewal motions. "
                             "Handbook customer success renewal motion. " * 8},
            headers=auth,
        )
        assert updated.status_code == 200, updated.text
        r7 = await wait_indexed(c, auth, "customer success renewal motions", ["document"], fresh["id"])
        r7_old = await knowledge_search(c, auth, "supplier onboarding vendor due diligence", ["document"])
        stale_hit = any(x["source_id"] == fresh["id"] for x in r7_old.json().get("results", [])) if r7_old.status_code == 200 else False
        check(
            "7. change-driven update: edited content replaces old content",
            any(x["source_id"] == fresh["id"] for x in r7.get("results", [])) and not stale_hit,
            f"new_hit={any(x['source_id'] == fresh['id'] for x in r7.get('results', []))} old_hit={stale_hit}",
        )

        rd = await c.delete(f"{API}/documents/{fresh['id']}", headers=auth)
        assert rd.status_code == 200, rd.text
        await dispatch(c, auth)
        r8 = await knowledge_search(c, auth, "customer success renewal motions", ["document"])
        r8b = r8.json() if r8.status_code == 200 else {}
        check(
            "8. change-driven delete: removed doc stops surfacing",
            r8.status_code == 200 and not any(x["source_id"] == fresh["id"] for x in r8b.get("results", [])),
            f"hits={[x['source_id'] for x in r8b.get('results', [])]}",
        )
        print("6-8. Change-driven create / update / delete verified")

        # ---- 9: tenant isolation -----------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc-{t}", f"eve{t}@rc.test.co", "Eve Rival")
        r9 = await knowledge_search(c, org_b["headers"], "refund approval workflow finance")
        r9b = r9.json() if r9.status_code == 200 else {}
        check(
            "9. tenant isolation: outsider org sees nothing",
            r9.status_code == 200 and not r9b.get("results"),
            f"status={r9.status_code} total={r9b.get('total')}",
        )
        print("9. Tenant isolation verified")

        # ---- 10-11: governance scoping ------------------------------------------
        emp = await invite_and_accept(c, auth, f"emp{t}@kc.test.co", "Scoped Mgr", role="manager")
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

        r11 = await knowledge_search(c, emp_auth, "refund approval workflow")
        check(
            "11. governance boundary: scoped-only caller without delegation gets 403",
            r11.status_code == 403,
            f"status={r11.status_code}",
        )

        dg = await c.post(
            f"{API}/governance/delegations",
            json={"granted_to_user": emp["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.2"},
            headers=auth,
        )
        assert dg.status_code == 201, dg.text
        r10 = await wait_indexed(c, emp_auth, "expense policy details", ["document"], anchored["id"], dispatch_auth=auth)
        ids = [x["source_id"] for x in r10.get("results", [])]
        first_scope = r10.get("results", [{}])[0].get("scope") if r10.get("results") else None
        check(
            "10. governance scoping: delegated scoped manager sees only the anchored doc",
            anchored["id"] in ids
            and match["id"] not in ids
            and policy["id"] not in ids
            and r10.get("results") and first_scope == "project",
            f"ids={ids[:5]} scope={first_scope}",
        )
        print("10-11. Governance scoping + boundary verified")

        # ---- 12: brain integration ------------------------------------------------
        rb = await c.post(f"{API}/brain/answer", json={"question": "What does the refund policy say about approvals?"}, headers=auth)
        claims = rb.json().get("claims", []) if rb.status_code == 200 else []
        doc_cited = any(
            e.get("type") == "document" and e.get("id") == match["id"]
            for cl in claims for e in cl.get("evidence", [])
        )
        check(
            "12. brain integration: /brain/answer cites document evidence",
            rb.status_code == 200 and doc_cited,
            f"status={rb.status_code} cited={doc_cited}",
        )
        print("12. Brain integration verified")

        # ---- 13: endpoint contract -------------------------------------------------
        r422 = await knowledge_search(c, auth, "   ")
        r_anon = await c.post(f"{API}/brain/knowledge/search", json={"question": "anything"})
        check(
            "13. endpoint contract: 422 blank question, 401/403 anonymous",
            r422.status_code == 422 and r_anon.status_code in (401, 403),
            f"blank={r422.status_code} anon={r_anon.status_code}",
        )
        print("13. Endpoint contract verified")

        # ---- 14: worker + scheduler ------------------------------------------------
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        reg = next((w for w in workers if w["name"] == "indexing"), None)
        run1 = await c.post(f"{API}/intelligence/workers/indexing/run", headers=auth)
        run2 = await c.post(f"{API}/intelligence/workers/indexing/run", headers=auth)
        b1 = run1.json() if run1.status_code == 200 else {}
        check(
            "14. indexing worker registered @ 1800s and runs idempotently on demand",
            reg is not None and reg.get("interval_seconds") == 1800
            and run1.status_code == 200 and run2.status_code == 200
            and b1.get("worker") == "indexing" and isinstance(b1.get("processed"), int),
            f"reg={reg} r1={run1.status_code} r2={run2.status_code} body={run1.text[:140]}",
        )
        print("14. Worker + scheduler verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

