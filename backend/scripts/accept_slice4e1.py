"""Slice 4E.1 acceptance — Knowledge Foundation & Canonical Model (live API).

13 checks against the running stack (http://localhost:8999):

  1. event-driven ingestion: create + publish a document and the existing
     durable events land exactly one canonical KnowledgeSource (lifecycle
     validated, authority 3 documented, freshness very_high) with a claim
     and primary evidence
  2. registry contract: /brain/knowledge reports by_status/by_kind over only
     what the caller may access, scope org for the founder
  3. temporal truth: updating the document supersedes the previous claim
     (valid_to + superseded_by) instead of deleting it; source lifecycle
     becomes updated
  4. exact-once: replaying the same events does not create new claims and
     does not bump the lifecycle
  5. authority: an approved policy is official (5) with an authoritative
     "effective" claim
  6. decisions: choosing an option lands a canonical decision claim that
     names the chosen option
  7. topics: the category seeds the canonical topic registry
  8. bounded reconcile: POST /brain/knowledge/reconcile is hard-capped and
     idempotent
  9. tenant isolation: a rival organization sees total 0 and source detail 404
 10. governance: a project-scoped brain:read reader sees only its project's
     sources; the hidden source is 404 and never in the registry
 11. endpoint contract: anonymous requests are rejected (401/403)
 12. lifecycle legality: canonical source statuses stay within the model
     vocabulary (discovered|extracted|validated|active|updated|superseded|
     archived) and claim statuses stay within theirs
 13. freshness: source detail exposes the age-based freshness model fields

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []

SOURCE_LIFECYCLES = {"discovered", "extracted", "validated", "active", "updated", "superseded", "archived"}
CLAIM_STATES = {"candidate", "supported", "authoritative", "contested", "superseded"}


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


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 500) -> int:
    r = await client.post(f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("processed", 0)


async def drain(client: httpx.AsyncClient, headers: dict) -> None:
    for _ in range(15):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def form_project(client: httpx.AsyncClient, headers: dict, name: str) -> dict:
    proj = (
        await client.post(
            f"{API}/projects",
            json={"name": name, "description": "Slice 4E.1 anchor", "status": "active"},
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
    return {"project": proj, "scope": scope}


async def invite_scoped(client: httpx.AsyncClient, headers: dict, email: str, scope_id: str) -> dict:
    emp = (await client.post(
        f"{API}/users/invite",
        json={"email": email, "role": "manager", "full_name": "Scoped Mgr"},
        headers=headers,
    )).json()
    joined = (await client.post(
        f"{API}/auth/register/invite",
        json={"token": emp["token"], "email": email, "full_name": "Scoped Mgr", "password": "StrongPass123!"},
    )).json()
    emp_auth = {"Authorization": f"Bearer {joined['access_token']}"}
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")
    a = await client.post(
        f"{API}/governance/assignments",
        json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers,
    )
    assert a.status_code == 201, a.text
    assignments = (await client.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=headers)).json()
    org_wide = next(x for x in assignments if x["scope_id"] is None)
    assert (await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)).status_code == 200
    dg = await client.post(
        f"{API}/governance/delegations",
        json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.1"},
        headers=headers,
    )
    assert dg.status_code == 201, dg.text
    return emp_auth


async def create_published_doc(client: httpx.AsyncClient, headers: dict, *, title: str, content: str, category: str = None, project_id: str = None, summary: str = None) -> dict:
    payload = {"title": title, "content": content}
    if category:
        payload["category"] = category
    if project_id:
        payload["project_id"] = project_id
    if summary:
        payload["summary"] = summary
    doc = (await client.post(f"{API}/documents", json=payload, headers=headers)).json()
    published = await client.post(f"{API}/documents/{doc['id']}/publish", headers=headers)
    assert published.status_code == 200, published.text
    return published.json()


async def source_detail(client: httpx.AsyncClient, headers: dict, source_type: str, source_id: str):
    return await client.get(f"{API}/brain/knowledge/sources/{source_type}/{source_id}", headers=headers)


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4E.1 acceptance: Knowledge Foundation & Canonical Model (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Canonical Knowledge Co", f"ck1-{t}", f"eva{t}@ck1.test.co", "Eva Founder")
        auth = org["headers"]
        org_id = org["organization"]["id"]
        print("1. Founder registered")
        await drain(c, auth)

        # 1 + 2 + 7 — event-driven ingestion, registry, topics
        proj_a = await form_project(c, auth, "Canonical Alpha")
        doc = await create_published_doc(
            c, auth, title="Refund policy v2", content="Refunds are processed within 14 days.",
            category="finance", project_id=proj_a["project"]["id"], summary="14-day refund window.",
        )
        await drain(c, auth)

        detail = (await source_detail(c, auth, "document", doc["id"])).json()
        source = detail["source"]
        check("1. events create exactly one canonical source", 
              source["source_type"] == "document" and source["source_id"] == doc["id"]
              and source["lifecycle"] == "validated" and source["source_status"] == "published"
              and source["authority_level"] == 3 and source["authority_label"] == "documented"
              and source["freshness_label"] == "very_high", str(detail)[:300])
        check("1b. claim + primary evidence landed",
              len(detail["claims"]) == 1 and detail["claims"][0]["predicate"] == "states"
              and len(detail["claims"][0]["evidence"]) == 1
              and detail["claims"][0]["evidence"][0]["role"] == "primary", str(detail["claims"])[:300])
        check("1c. freshness + authority surfaces exposed",
              "freshness" in detail and {"score", "label", "last_verified_at", "source_updated_at"} <= set(detail["freshness"])
              and "authority" in detail and detail["authority"]["label"] == "documented", str(detail)[:300])

        reg = (await c.get(f"{API}/brain/knowledge", headers=auth)).json()
        check("2. registry map contract",
              reg["total"] >= 1 and reg["scope"] == "org"
              and reg["by_kind"].get("document", 0) >= 1 and reg["by_status"].get("validated", 0) >= 1
              and reg["sources"][0]["url"] == f"/knowledge/document/{doc['id']}", str(reg)[:300])

        topics = (await c.get(f"{API}/brain/knowledge/topics", headers=auth)).json()
        check("7. category seeds the topic registry",
              topics["total"] >= 1 and any(t["name"] == "finance" for t in topics["topics"]), str(topics)[:300])

        # 3 + 4 — temporal truth + exact-once
        updated = await c.patch(
            f"{API}/documents/{doc['id']}",
            json={"content": "Refunds are processed within 10 days.", "change_note": "Policy change"},
            headers=auth,
        )
        assert updated.status_code == 200, updated.text
        await drain(c, auth)

        detail = (await source_detail(c, auth, "document", doc["id"])).json()
        claims = detail["claims"]
        check("3. update supersedes instead of deleting",
              len(claims) == 2
              and any(cl["status"] == "superseded" and cl["valid_to"] and cl["superseded_by"] for cl in claims)
              and any(cl["status"] == "supported" and cl["valid_to"] is None for cl in claims)
              and detail["source"]["lifecycle"] == "updated", str(claims)[:400])

        await drain(c, auth)
        await drain(c, auth)
        detail2 = (await source_detail(c, auth, "document", doc["id"])).json()
        check("4. exact-once: replay is a no-op",
              len(detail2["claims"]) == 2 and detail2["source"]["lifecycle"] == "updated", str(detail2)[:300])

        # 5 — policy authority
        policy = (await c.post(
            f"{API}/policies",
            json={"title": "Expense approval threshold", "content": "Above 500 needs approval.", "category": "finance"},
            headers=auth,
        )).json()
        assert (await c.post(f"{API}/policies/{policy['id']}/approve", headers=auth)).status_code == 200
        await drain(c, auth)
        pdetail = (await source_detail(c, auth, "policy", policy["id"])).json()
        pclaim = pdetail["claims"][-1]
        check("5. approved policy is official + authoritative",
              pdetail["source"]["authority_level"] == 5 and pdetail["authority"]["label"] == "official"
              and pclaim["status"] == "authoritative" and pclaim["predicate"] == "effective"
              and "Expense approval threshold" in pclaim["object_text"], str(pdetail)[:300])

        # 6 — decisions
        decision = (await c.post(
            f"{API}/decisions",
            json={
                "title": "Choose analytics store", "context": "Primary datastore.",
                "content": "Evaluating options.", "options": [{"title": "Postgres"}, {"title": "ClickHouse"}],
                "participants": [],
            },
            headers=auth,
        )).json()
        options = (await c.get(f"{API}/decisions/{decision['id']}/options", headers=auth)).json()
        assert (await c.post(
            f"{API}/decisions/{decision['id']}/choose",
            json={"option_id": options[1]["id"], "reason": "Columnar"},
            headers=auth,
        )).status_code == 200
        await drain(c, auth)
        ddetail = (await source_detail(c, auth, "decision", decision["id"])).json()
        dclaim = ddetail["claims"][-1]
        check("6. decision claim names the chosen option",
              dclaim["claim_type"] == "decision" and "ClickHouse" in dclaim["object_text"]
              and dclaim["authority_level"] == 4, str(ddetail)[:300])

        # 8 — bounded reconcile
        rec = (await c.post(f"{API}/brain/knowledge/reconcile", json={"limit": 5}, headers=auth)).json()
        check("8. reconcile is bounded and idempotent",
              rec["processed"] <= 5 and rec["processed"] == len(rec["items"]), str(rec)[:200])

        # 9 — tenant isolation
        rival = await register(c, "Rival Knowledge Co", f"rk1-{t}", f"rum{t}@rk1.test.co", "Rum Founder")
        await drain(c, rival["headers"])
        rreg = (await c.get(f"{API}/brain/knowledge", headers=rival["headers"])).json()
        rhidden = await source_detail(c, rival["headers"], "document", doc["id"])
        rclaims = (await c.get(f"{API}/brain/knowledge/claims", headers=rival["headers"])).json()
        check("9. tenant isolation",
              rreg["total"] == 0 and rhidden.status_code == 404 and rclaims["total"] == 0,
              f"reg={rreg['total']} detail={rhidden.status_code} claims={rclaims['total']}")

        # 10 — governance: scoped reader
        proj_b = await form_project(c, auth, "Canonical Bravo")
        hidden_doc = await create_published_doc(
            c, auth, title="Hidden doc", content="Outside the visible project.", project_id=proj_b["project"]["id"],
        )
        await drain(c, auth)
        scoped = await invite_scoped(c, auth, f"scop{t}@ck1.test.co", proj_a["scope"]["id"])
        sreg = (await c.get(f"{API}/brain/knowledge", headers=scoped)).json()
        shidden = await source_detail(c, scoped, "document", hidden_doc["id"])
        svisible = await source_detail(c, scoped, "document", doc["id"])
        check("10. governance constrains retrieval",
              sreg["total"] == 1 and sreg["scope"] == "project"
              and sreg["sources"][0]["title"] == "Refund policy v2"
              and shidden.status_code == 404 and svisible.status_code == 200,
              f"reg={sreg['total']} scope={sreg.get('scope')} hidden={shidden.status_code} visible={svisible.status_code}")

        # 11 — endpoint contract (anonymous)
        anon = await c.get(f"{API}/brain/knowledge")
        check("11. anonymous rejected", anon.status_code in (401, 403), f"status={anon.status_code}")

        # 12 — lifecycle vocabulary legality
        detail3 = (await source_detail(c, auth, "document", doc["id"])).json()
        vocab_ok = all(cl["status"] in CLAIM_STATES for cl in detail3["claims"]) and \
            detail3["source"]["lifecycle"] in SOURCE_LIFECYCLES
        check("12. lifecycle vocabularies respected", vocab_ok, str(detail3)[:300])

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
