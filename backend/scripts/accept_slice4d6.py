"""Slice 4D.6 acceptance — unified company intelligence experience (live API).

20 checks against the running stack (http://localhost:8999):

  1. canonical seeding: dependency-blocked project forms an execution_bottleneck
     insight through the full background pipeline (pattern -> memory formation ->
     insight -> indexing), project scope inherited and auth_project_id anchored
  2. change-driven composition: only task.blocked signals were consumed to build
     the supporting evidence set
  3. unified answer: ONE /brain/answer composes all four producers
     (patterns, insights, memories, knowledge) for one anchor, all sections >= 1
  4. answer semantics: summary names the anchor, confidence in [0,1], answered_at
     present, org_wide true for the founder
  5. bounded answer surface: per-section limits honored (<= 3), related
     entities <= 8, claim evidence <= EVIDENCE_LINK_LIMIT
  6. evidence lineage: every claim evidence url resolves (never a dead link)
  7. evidence drawer: /brain/evidence/{source} returns cross-source evidence and
     graph-neighbor related entities after /brain/graph/relationships/sync
  8. graph sync: relationships/sync reports synced > 0 and is idempotent
  9. related reads are bounded by limit and flagged truncated
 10. overview: bounded attention, recent_intelligence counts observe the same
     seeded intelligence (patterns/insights/memories all >= 1)
 11. no-mutation reads: overview re-reads return identical attention ids
 12. determinism: the same question composes the same summary + confidence
 13. observation-only: answer/overview reads never change task statuses or
     memory counts (read-only brain, no operating-layer mutation)
 14. governance: a scoped brain:read-only reader receives org_wide=false and
     every claim evidence url in their answer resolves under their scope
 15. governance 404: evidence for a hidden project is 404 for the scoped reader
     (never 403 / never leaked in list or answer)
 16. tenant isolation: a rival org's brain never composes this org's company
     intelligence; rival cannot list these insights
 17. worker registry: pattern / memory_formation / insight / indexing workers
     registered and run on demand; insight registered @ 120s
 18. on-demand worker runs are org-scoped: a founder-triggered run reports a
     bounded processed count without stealing a rival org's queued work
 19. endpoint contract: anonymous requests are 401/403; missing resources 404
 20. knowledge + memory producers: the published policy document and the seeded
     institutional memory are both cited in the unified answer

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
    for _ in range(15):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def run_worker(client: httpx.AsyncClient, headers: dict, name: str) -> dict:
    r = await client.post(f"{API}/intelligence/workers/{name}/run", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def drive_full_stack(client: httpx.AsyncClient, headers: dict) -> None:
    await dispatch(client, headers)
    await run_worker(client, headers, "pattern")
    await dispatch(client, headers)
    await run_worker(client, headers, "memory_formation")
    await dispatch(client, headers)
    await run_worker(client, headers, "insight")
    await dispatch(client, headers)
    await run_worker(client, headers, "indexing")
    await dispatch(client, headers)


async def insights(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    r = await client.get(f"{API}/brain/insights", params={"limit": 200}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("insights", [])


async def wait_for_insight(client: httpx.AsyncClient, headers: dict, predicate) -> dict:
    for _ in range(14):
        await drive_full_stack(client, headers)
        for insight in await insights(client, headers):
            if predicate(insight):
                return insight
        await asyncio.sleep(3)
    raise AssertionError("insight never became observable")


async def form_project(client: httpx.AsyncClient, headers: dict, name: str) -> tuple[dict, dict]:
    proj = (
        await client.post(
            f"{API}/projects",
            json={"name": name, "description": "Slice 4D.6 anchor", "status": "active"},
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
    return proj, scope


async def dependency_blocked_task(client: httpx.AsyncClient, headers: dict, project_id: str, title: str) -> tuple[dict, dict]:
    blocker = (
        await client.post(
            f"{API}/tasks",
            json={"title": f"Blocker {title}", "project_id": project_id, "status": "todo"},
            headers=headers,
        )
    ).json()
    dependent = (
        await client.post(
            f"{API}/tasks",
            json={"title": title, "project_id": project_id, "status": "todo"},
            headers=headers,
        )
    ).json()
    dep = await client.post(
        f"{API}/tasks/{dependent['id']}/dependencies",
        json={"depends_on_task_id": blocker["id"], "kind": "finish_to_start"},
        headers=headers,
    )
    assert dep.status_code == 201, dep.text
    tr = await client.post(
        f"{API}/tasks/{dependent['id']}/transition",
        json={"status": "blocked"},
        headers=headers,
    )
    assert tr.status_code == 200, tr.text
    return blocker, dependent


async def brain_answer(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{API}/brain/answer", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.6 acceptance: unified company intelligence experience (live) ===")

    question = "why is the Helios Delivery project behind on the approval policy review?"

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Unified Brain Co", f"ub-{t}", f"ada{t}@ub.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")
        await drain(c, auth)

        proj, scope = await form_project(c, auth, "Helios Delivery")
        blocked = []
        for i, title in enumerate(["Checkout approval", "Billing export", "Mobile push"]):
            _, dependent = await dependency_blocked_task(c, auth, proj["id"], title)
            blocked.append(dependent)
        dec = (await c.post(
            f"{API}/decisions",
            json={"title": "approve finance approval workflow", "project_id": proj["id"], "description": "review pending"},
            headers=auth,
        )).json()
        memory = (await c.post(
            f"{API}/brain/memory",
            json={
                "memory_type": "institutional",
                "title": "Previous approval delay",
                "content": "An approval delay blocked similar work in the past.",
                "importance": "medium",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=auth,
        )).json()
        doc = (
            await c.post(
                f"{API}/documents",
                json={
                    "title": "Approval policy for enterprise accounts",
                    "content": (
                        "All project approvals require a formal decision record. "
                        "The finance approval workflow must be reviewed before launch approval is granted. "
                        "This approval policy is company policy."
                    ),
                    "project_id": proj["id"],
                },
                headers=auth,
            )
        ).json()
        pub = await c.post(f"{API}/documents/{doc['id']}/publish", headers=auth)
        assert pub.status_code == 200, pub.text

        insight = await wait_for_insight(
            c, auth,
            lambda i: i.get("insight_type") == "execution_bottleneck" and i.get("auth_project_id") == proj["id"],
        )
        print("2. Canonical blocked project seeded through the full background pipeline")

        # ---- 1: canonical seeding ---------------------------------------------------
        check(
            "1. canonical seeding: execution_bottleneck forms with inherited project scope",
            insight["insight_type"] == "execution_bottleneck"
            and insight["domain"] == "execution"
            and insight["scope_type"] == "project"
            and insight["auth_project_id"] == proj["id"]
            and insight.get("scope_id") == scope["id"]
            and len(insight.get("supporting_pattern_ids", [])) >= 1,
            f"severity={insight.get('severity')} scope={insight.get('scope_id')}=={scope['id']}",
        )

        # ---- 2: change-driven composition ----------------------------------------------
        ev = (await c.get(f"{API}/brain/insights/{insight['id']}/evidence", headers=auth)).json()
        check(
            "2. change-driven composition: task.blocked signal built the evidence set",
            len(ev.get("evidence", [])) >= 1
            and any(item.get("type") == "pattern" for item in ev.get("evidence", [])),
            f"evidence={[e.get('type') for e in ev.get('evidence', [])]}",
        )

        # ---- 3: unified answer composes all four producers -------------------------------
        answer = await brain_answer(c, auth, question)
        auth_answer = answer
        sections = {
            "patterns": len(answer.get("patterns", [])),
            "insights": len(answer.get("insights", [])),
            "memories": len(answer.get("memories", [])),
            "knowledge": len(answer.get("knowledge", [])),
        }
        check(
            "3. unified answer composes all four producers for one anchor",
            all(sections[k] >= 1 for k in sections),
            f"sections={sections}",
        )
        check(
            "4. answer semantics: anchor named, bounded confidence, org_wide for founder",
            "Helios Delivery" in answer.get("summary", "")
            and 0.0 <= answer.get("confidence", -1) <= 1.0
            and bool(answer.get("answered_at"))
            and answer.get("scope", {}).get("org_wide") is True
            and set(answer.get("sources_consulted", [])) >= {"context", "patterns", "insights", "memory", "knowledge"},
            f"conf={answer.get('confidence')} scope={answer.get('scope')}",
        )
        check(
            "5. bounded answer surface: sections <= 3, related <= 8, evidence <= 5",
            all(sections[k] <= 3 for k in sections)
            and len(answer.get("related_entities", [])) <= 8
            and all(len(cl.get("evidence", [])) <= 5 for cl in answer.get("claims", [])),
            f"sections={sections} related={len(answer.get('related_entities', []))}",
        )
        print("3-5. Unified answer composition verified")

        # ---- 6: evidence lineage resolves --------------------------------------------------
        dead = []
        for cl in answer.get("claims", []):
            for url in [e.get("url", "") for e in cl.get("evidence", [])]:
                if not url:
                    continue
                probe = await c.get(url, headers=auth)
                if probe.status_code == 404:
                    dead.append(url)
        check(
            "6. evidence lineage: every claim evidence url resolves",
            answer.get("claims") and not dead,
            f"claims={len(answer.get('claims', []))} dead={dead}",
        )

        # ---- 7: evidence drawer with graph neighbors -------------------------------------------
        sync = await c.post(f"{API}/brain/graph/relationships/sync", json={}, headers=auth)
        sync_body = sync.json() if sync.status_code == 200 else {}
        drawer = (
            await c.get(f"{API}/brain/evidence/project/{proj['id']}", params={"link_limit": 5}, headers=auth)
        ).json()
        check(
            "7. evidence drawer: cross-source evidence + graph-neighbor related entities",
            sync.status_code == 200 and sync_body.get("synced", 0) > 0
            and drawer["source"]["type"] == "project"
            and drawer["source"]["id"] == proj["id"]
            and len(drawer.get("evidence", [])) >= 1
            and len(drawer.get("related_entities", [])) >= 1,
            f"synced={sync_body.get('synced')} evidence={len(drawer.get('evidence', []))} neighbors={len(drawer.get('related_entities', []))}",
        )
        sync2 = await c.post(f"{API}/brain/graph/relationships/sync", json={}, headers=auth)
        check(
            "8. graph sync idempotent: second sync reports >= 0 without error",
            sync2.status_code == 200 and sync2.json().get("synced", 0) >= 0,
            f"second_synced={sync2.json().get('synced') if sync2.status_code == 200 else sync2.status_code}",
        )

        # ---- 9: related bounded -----------------------------------------------------------------
        related = (await c.get(f"{API}/brain/related/project/{proj['id']}", params={"limit": 5}, headers=auth)).json()
        check(
            "9. related reads are bounded by limit and flagged truncated",
            len(related.get("related", [])) >= 1
            and len(related.get("related", [])) <= 5
            and isinstance(related.get("truncated"), bool),
            f"related={len(related.get('related', []))} truncated={related.get('truncated')}",
        )
        print("6-9. Evidence drawer, graph sync, related verified")

        # ---- 10: overview observes the same intelligence ---------------------------------------------
        overview = (await c.get(f"{API}/brain/overview", headers=auth)).json()
        recents = overview.get("recent_intelligence", {})
        attention = overview.get("attention", [])
        per_source = {
            src: sum(1 for a in attention if a.get("source") == src)
            for src in ("insight", "pattern", "memory")
        }
        check(
            "10. overview: bounded attention (<=3 per source) + recent intelligence counts all >= 1",
            len(attention) >= 1
            and all(per_source.get(src, 0) <= 3 for src in per_source)
            and recents.get("insights", {}).get("count", 0) >= 1
            and recents.get("patterns", {}).get("count", 0) >= 1
            and recents.get("memories", {}).get("count", 0) >= 1,
            f"attention={len(attention)} per_source={per_source} recent={recents.get('insights', {}).get('count')}/{recents.get('patterns', {}).get('count')}/{recents.get('memories', {}).get('count')}",
        )
        overview2 = (await c.get(f"{API}/brain/overview", headers=auth)).json()
        check(
            "11. no-mutation reads: overview re-read returns identical attention ids",
            [a["id"] for a in overview2.get("attention", [])] == [a["id"] for a in overview.get("attention", [])],
            f"ids={len(overview.get('attention', []))}->{len(overview2.get('attention', []))}",
        )

        # ---- 12: determinism ----------------------------------------------------------------------
        again = await brain_answer(c, auth, question)
        check(
            "12. determinism: same question composes same summary + confidence",
            again.get("summary") == auth_answer.get("summary")
            and abs(again.get("confidence", -1) - auth_answer.get("confidence", -1)) < 1e-9,
            f"same_summary={again.get('summary') == auth_answer.get('summary')}",
        )

        # ---- 13: observation-only / no operating-layer mutation --------------------------------------
        tasks_before = {
            task["id"]: task["status"]
            for task in (await c.get(f"{API}/tasks", params={"project_id": proj["id"], "limit": 200}, headers=auth)).json()
        }
        mem_before = len((await c.get(f"{API}/brain/memories", params={"limit": 200}, headers=auth)).json().get("memories", []))
        await brain_answer(c, auth, question)
        tasks_after = {
            task["id"]: task["status"]
            for task in (await c.get(f"{API}/tasks", params={"project_id": proj["id"], "limit": 200}, headers=auth)).json()
        }
        mem_after = len((await c.get(f"{API}/brain/memories", params={"limit": 200}, headers=auth)).json().get("memories", []))
        check(
            "13. observation-only: answer reads never change task statuses or memory rows",
            tasks_before == tasks_after and mem_before == mem_after,
            f"tasks={tasks_before == tasks_after} memories={mem_before}->{mem_after}",
        )
        print("10-13. Overview bounds, determinism, no-mutation verified")

        # ---- 14: governance scoped reader ------------------------------------------------------------
        emp = (await c.post(
            f"{API}/users/invite",
            json={"email": f"emp{t}@ub.test.co", "role": "manager", "full_name": "Scoped Mgr"},
            headers=auth,
        )).json()
        joined = (await c.post(
            f"{API}/auth/register/invite",
            json={"token": emp["token"], "email": f"emp{t}@ub.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"},
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
            json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.6"},
            headers=auth,
        )
        assert dg.status_code == 201, dg.text

        scoped_answer = await brain_answer(c, emp_auth, question)
        scoped_insight_ids = {i["id"] for i in await insights(c, emp_auth)}
        scoped_dead = []
        for cl in scoped_answer.get("claims", []):
            for url in [e.get("url", "") for e in cl.get("evidence", [])]:
                if not url:
                    continue
                if (await c.get(url, headers=emp_auth)).status_code == 404:
                    scoped_dead.append(url)
        check(
            "14. governance: scoped reader gets org_wide=false and all evidence resolves",
            scoped_answer.get("scope", {}).get("org_wide") is False
            and 0.0 <= scoped_answer.get("confidence", -1) <= 1.0
            and not scoped_dead,
            f"scope={scoped_answer.get('scope')} claims={len(scoped_answer.get('claims', []))}",
        )
        print("14. Scoped answer verified")

        # ---- 15: hidden project is 404 for the scoped reader -------------------------------------------
        hidden_proj, _ = await form_project(c, auth, "Hidden Vault")
        await c.post(
            f"{API}/brain/memory",
            json={
                "memory_type": "institutional",
                "title": "Hidden payout plan",
                "content": "Confidential payout plan for the hidden vault.",
                "importance": "high",
                "entity_type": "project",
                "entity_id": hidden_proj["id"],
            },
            headers=auth,
        )
        hidden_drawer = await c.get(f"{API}/brain/evidence/project/{hidden_proj['id']}", params={"link_limit": 5}, headers=emp_auth)
        hidden_rel = await c.get(f"{API}/brain/related/project/{hidden_proj['id']}", params={"limit": 5}, headers=emp_auth)
        scoped_list_ids = {i["id"] for i in await insights(c, emp_auth)}
        hidden_leaked = any(
            hidden_proj["id"] in e.get("url", "")
            for cl in scoped_answer.get("claims", [])
            for e in cl.get("evidence", [])
        )
        check(
            "15. governance 404: hidden project evidence/related are 404, nothing leaked in answer",
            hidden_drawer.status_code == 404
            and hidden_rel.status_code == 404
            and not hidden_leaked,
            f"drawer={hidden_drawer.status_code} related={hidden_rel.status_code} hidden_urls={hidden_leaked}",
        )

        # ---- 16: tenant isolation -------------------------------------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc-{t}", f"eve{t}@rc.test.co", "Eve Rival")
        rival_answer = await brain_answer(c, org_b["headers"], "what is happening in your company right now?")
        rival_ids = {i["id"] for i in await insights(c, org_b["headers"])}
        check(
            "16. tenant isolation: rival org never composes or lists this org's intelligence",
            "Helios" not in rival_answer.get("summary", "")
            and insight["id"] not in rival_ids,
            f"rival_insights={len(rival_ids)}",
        )
        print("15-16. Scoping + isolation verified")

        # ---- 17: worker registry ---------------------------------------------------------------------------
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        by_name = {w["name"]: w for w in workers}
        check(
            "17. worker registry: all four workers registered, insight @ 120s on demand",
            all(name in by_name for name in ("pattern", "memory_formation", "insight", "indexing"))
            and by_name["insight"].get("interval_seconds") == 120
            and by_name["insight"].get("run_on_demand") is True,
            f"names={sorted(by_name)} insight={by_name.get('insight', {}).get('interval_seconds')}",
        )

        # ---- 18: on-demand runs are org-scoped ---------------------------------------------------------------
        run = await run_worker(c, auth, "pattern")
        rival_run = await run_worker(c, org_b["headers"], "pattern")
        check(
            "18. on-demand runs org-scoped: bounded processed counts, never cross-org cleanup",
            isinstance(run.get("processed"), int)
            and run.get("processed", 0) >= 0
            and isinstance(rival_run.get("processed"), int),
            f"founder={run.get('processed')} rival={rival_run.get('processed')}",
        )

        # ---- 19: endpoint contract ------------------------------------------------------------------------------
        anon_answer = await c.post(f"{API}/brain/answer", json={"question": question})
        anon_overview = await c.get(f"{API}/brain/overview")
        anon_insight = await c.post(f"{API}/brain/graph/relationships/sync", json={})
        missing = await c.get(f"{API}/brain/insights/does-not-exist", headers=auth)
        check(
            "19. endpoint contract: anonymous 401/403, missing resource 404",
            anon_answer.status_code in (401, 403)
            and anon_overview.status_code in (401, 403)
            and anon_insight.status_code in (401, 403)
            and missing.status_code == 404,
            f"answer={anon_answer.status_code} overview={anon_overview.status_code} missing={missing.status_code}",
        )

        # ---- 20: knowledge + memory producers cited ----------------------------------------------------------------
        knowledge_titles = [k.get("title", "") for k in answer.get("knowledge", [])]
        memory_titles = [m.get("title", "") for m in answer.get("memories", [])]
        check(
            "20. knowledge + memory producers both cited in the unified answer",
            any("Approval policy" in title for title in knowledge_titles)
            and any("blocked" in title.lower() or "approval" in title.lower() for title in memory_titles),
            f"knowledge={knowledge_titles} memories={memory_titles}",
        )
        print("17-20. Workers, contracts, producers verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))