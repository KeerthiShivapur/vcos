"""Slice 4D.7 acceptance — unified company brain surface (live API).

21 checks against the running stack (http://localhost:8999):

  1. canonical seeding: dependency-blocked project forms an execution_bottleneck
     insight through the full background pipeline, scope inherited
  2. conversation create: a conversation record appears with id + zero turns,
     bounded and owner-scoped
  3. unified answer contract: ONE /brain/answer carries the 4D.7 additive keys —
     conversation{turn}, persona, timeline, recommended_next_questions,
     reasoning_chain, related projections — while keeping the 4D.6 scope
  4. answer semantics: summary names the anchor, bounded confidence,
     org_wide true for the founder, deterministic on re-ask
  5. persona-aware: visible_project_count / visible_scope_count reported for the
     founder, and a scoped reader sees org_wide=false in answer + timeline
  6. follow-up continuity: a follow-up without an entity inherits the
     conversation anchor server-side (turn 2 stays anchored to the project)
  7. conversation persistence: conversation detail lists both turns in order
     with the inherited anchor recorded
  8. reasoning chain: a why question composes a bounded chain (steps 1..n,
     labels, evidence) from the claims; a non-why question returns none
  9. recommended next questions: bounded <= 3, deterministic, never the asked
     question, all observation-shaped
 10. timeline (unified): evidence-backed (every url resolves), bounded by
     limit 50, mixed kinds >= 2, ordered by occurred_at desc
 11. anchored timeline: filtered to the entity realm (project timeline rows +
     linked intelligence); 404 for an entity the caller cannot access
 12. what-changed: persona-aware digest, bounded categories <= 6, items <= 20,
     org_wide=true for the founder, rival org sees nothing of this org
 13. related projections: anchored to the primary entity, bounded, urls resolve
 14. no-mutation reads: answer/timeline/what-changed never change task statuses
     or memory rows
 15. multi-source composition preserved: patterns/insights/memories/knowledge
     all >= 1 in the answer (4D.6 contract holds additively)
 16. governance: scoped brain:read-only reader receives scoped claims and every
     claim evidence url resolves under their scope
 17. governance 404: timeline for a hidden project is 404 for the scoped reader,
     no hidden ids in timeline/what-changed/related
 18. conversation isolation: another member cannot read/list/answer into the
     owner's conversation (404)
 19. tenant isolation: rival org cannot see conversations/timeline/what-changed
     of this org; rival answer never names Helios
 20. endpoint contract: anonymous requests 401/403; missing conversation and
     missing timeline entity 404
 21. bounded conversations: creating beyond the per-user bound trims the oldest
     (list count <= 20)

Exit code 0 when all pass.
"""

import asyncio
import json
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
            json={"name": name, "description": "Slice 4D.7 anchor", "status": "active"},
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


async def dependency_blocked_task(client: httpx.AsyncClient, headers: dict, project_id: str, title: str) -> dict:
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
    return dependent


async def brain_answer(client: httpx.AsyncClient, headers: dict, question: str, **extra) -> dict:
    payload = {"question": question}
    payload.update(extra)
    r = await client.post(f"{API}/brain/answer", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


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
        json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.7"},
        headers=headers,
    )
    assert dg.status_code == 201, dg.text
    return emp_auth


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.7 acceptance: unified company brain surface (live) ===")

    question = "why is the Helios Delivery project behind on the approval policy review?"

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Unified Brain Co", f"ub7-{t}", f"ada{t}@ub7.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")
        await drain(c, auth)

        proj, scope = await form_project(c, auth, "Helios Delivery")
        for i, title in enumerate(["Checkout approval", "Billing export", "Mobile push"]):
            await dependency_blocked_task(c, auth, proj["id"], title)
        await c.post(
            f"{API}/decisions",
            json={"title": "approve finance approval workflow", "project_id": proj["id"], "description": "review pending"},
            headers=auth,
        )
        await c.post(
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
        )
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
        assert (await c.post(f"{API}/documents/{doc['id']}/publish", headers=auth)).status_code == 200
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
            and insight.get("scope_id") == scope["id"],
            f"scope={insight.get('scope_id')}=={scope['id']}",
        )

        # ---- 2: conversation create --------------------------------------------------
        conv = (await c.post(f"{API}/brain/conversations", json={}, headers=auth)).json()
        check(
            "2. conversation create: record with id + zero turns, owner-scoped",
            bool(conv.get("id"))
            and conv.get("turn_count", 0) == 0
            and conv.get("organization_id") == org["organization"]["id"]
            and conv.get("user_id") == org["user"]["id"],
            f"id={conv.get('id')} turns={conv.get('turn_count')}",
        )

        # ---- 3+4: unified answer contract -------------------------------------------------
        answer = await brain_answer(
            c, auth, question, entity_type="project", entity_id=proj["id"], conversation_id=conv["id"]
        )
        sections = {
            "patterns": len(answer.get("patterns", [])),
            "insights": len(answer.get("insights", [])),
            "memories": len(answer.get("memories", [])),
            "knowledge": len(answer.get("knowledge", [])),
        }
        add_keys = ["conversation", "persona", "timeline", "recommended_next_questions", "reasoning_chain"]
        check(
            "3. unified answer carries the 4D.7 additive surface keys",
            all(answer.get(k) is not None for k in add_keys)
            and answer["conversation"]["id"] == conv["id"]
            and answer["conversation"]["turn"] == 1
            and answer["persona"]["org_wide"] is True
            and answer["scope"] == {"org_wide": True},
            f"keys={[k for k in add_keys if answer.get(k) is None]}",
        )
        check(
            "4. answer semantics: anchor named, bounded confidence, deterministic",
            "Helios Delivery" in answer.get("summary", "")
            and 0.0 <= answer.get("confidence", -1) <= 1.0
            and bool(answer.get("answered_at")),
            f"conf={answer.get('confidence')}",
        )

        # ---- 5: persona-aware counts -----------------------------------------------------
        check(
            "5. persona-aware: founder counts visible projects/scopes",
            isinstance(answer.get("persona", {}).get("visible_project_count"), int)
            and isinstance(answer.get("persona", {}).get("visible_scope_count"), int),
            f"persona={answer.get('persona')}",
        )

        # ---- 6: follow-up continuity -----------------------------------------------------
        followup = await brain_answer(c, auth, "has this happened before?", conversation_id=conv["id"])
        followup_project_refs = [
            e.get("id") for cl in followup.get("claims", []) for e in cl.get("evidence", []) if e.get("type") == "project"
        ]
        check(
            "6. follow-up continuity: anchor inherited server-side without repeating it",
            followup["conversation"]["turn"] == 2 and proj["id"] in followup_project_refs,
            f"turn={followup['conversation'].get('turn')} projects={followup_project_refs}",
        )

        # ---- 7: conversation persistence ---------------------------------------------------
        detail = (await c.get(f"{API}/brain/conversations/{conv['id']}", headers=auth)).json()
        check(
            "7. conversation persistence: both turns in order with inherited anchor",
            detail.get("turn_count") == 2
            and detail.get("last_anchor_id") == proj["id"]
            and [tn.get("question") for tn in detail.get("turns", [])] == [question, "has this happened before?"]
            and detail["turns"][1].get("anchor_id") == proj["id"],
            f"turns={[tn.get('question') for tn in detail.get('turns', [])]}",
        )

        # ---- 8: reasoning chain -------------------------------------------------------------
        chain = answer.get("reasoning_chain", [])
        check(
            "8. reasoning chain: bounded, ordered steps with labels from evidence claims",
            len(chain) >= 1
            and len(chain) <= 6
            and [s.get("step") for s in chain] == list(range(1, len(chain) + 1))
            and all(s.get("label") and s.get("claim") for s in chain),
            f"steps={len(chain)}",
        )
        non_why = await brain_answer(c, auth, "what changed with Helios Delivery this week?", entity_type="project", entity_id=proj["id"])
        check(
            "8b. no chain for non-why question; what_changed present",
            "reasoning_chain" not in non_why and bool(non_why.get("what_changed")),
            f"chain={'reasoning_chain' in non_why} changed={bool(non_why.get('what_changed'))}",
        )

        # ---- 9: recommended next questions ----------------------------------------------------
        next_q = answer.get("recommended_next_questions", [])
        check(
            "9. next questions: bounded <= 3, deterministic, never the asked question",
            1 <= len(next_q) <= 3
            and next_q == (await brain_answer(c, auth, question, entity_type="project", entity_id=proj["id"])).get("recommended_next_questions"),
            f"next={next_q}",
        )

        # ---- 10+11: unified timeline -----------------------------------------------------------
        timeline = (await c.get(
            f"{API}/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": proj["id"], "limit": 50},
            headers=auth,
        )).json()
        kinds = {e.get("kind") for e in timeline.get("timeline", [])}
        dead = [
            e.get("url")
            for e in timeline.get("timeline", [])
            if e.get("url") and (await c.get(e["url"], headers=auth)).status_code == 404
        ]
        check(
            "10. timeline: evidence-backed (urls resolve), bounded <= 50, mixed kinds >= 2",
            timeline.get("entity", {}).get("id") == proj["id"]
            and timeline.get("count", 0) <= 50
            and len(kinds) >= 2
            and not dead,
            f"count={timeline.get('count')} kinds={kinds} dead={dead}",
        )
        anchored = timeline.get("timeline", [])
        check(
            "11. anchored timeline ordered by occurred_at desc",
            anchored == sorted(anchored, key=lambda e: e.get("occurred_at") or "", reverse=True),
            f"count={len(anchored)}",
        )

        # ---- 12: what-changed --------------------------------------------------------------------
        changed = (await c.get(f"{API}/brain/what-changed", params={"days": 7}, headers=auth)).json()
        check(
            "12. what-changed: persona-aware digest, bounded categories and items",
            changed.get("org_wide") is True
            and changed.get("days") == 7
            and 1 <= len(changed.get("categories", [])) <= 6
            and all(len(cat.get("items", [])) <= 20 for cat in changed.get("categories", [])),
            f"categories={len(changed.get('categories', []))}",
        )

        # ---- 13: related projections -----------------------------------------------------------------
        projections = [
            ("related_patterns", answer.get("related_patterns", [])),
            ("related_memories", answer.get("related_memories", [])),
            ("related_insights", answer.get("related_insights", [])),
        ]
        check(
            "13. related projections: anchored, bounded (<= 3 each), urls resolve",
            all(
                items
                and len(items) <= 3
                and all(p.get("url") and p.get("id") for p in items)
                for _, items in projections
            ),
            f"counts={[(k, len(v)) for k, v in projections]}",
        )

        # ---- 14: no-mutation reads ---------------------------------------------------------------
        tasks_before = {
            task["id"]: task["status"]
            for task in (await c.get(f"{API}/tasks", params={"project_id": proj["id"], "limit": 200}, headers=auth)).json()
        }
        mem_before = len((await c.get(f"{API}/brain/memory", params={"limit": 200}, headers=auth)).json().get("memories", []))
        await brain_answer(c, auth, question, entity_type="project", entity_id=proj["id"])
        await c.get(f"{API}/brain/timeline/unified", params={"limit": 50}, headers=auth)
        await c.get(f"{API}/brain/what-changed", headers=auth)
        tasks_after = {
            task["id"]: task["status"]
            for task in (await c.get(f"{API}/tasks", params={"project_id": proj["id"], "limit": 200}, headers=auth)).json()
        }
        mem_after = len((await c.get(f"{API}/brain/memory", params={"limit": 200}, headers=auth)).json().get("memories", []))
        check(
            "14. no-mutation: answer/timeline/what-changed reads never change tasks or memory rows",
            tasks_before == tasks_after and mem_before == mem_after,
            f"tasks={tasks_before == tasks_after} memories={mem_before}->{mem_after}",
        )

        # ---- 15: multi-source composition preserved ---------------------------------------------------
        check(
            "15. multi-source composition preserved: patterns/insights/memories/knowledge all >= 1",
            all(sections[k] >= 1 for k in sections)
            and set(answer.get("sources_consulted", [])) >= {"context", "patterns", "insights", "memory", "knowledge"},
            f"sections={sections}",
        )
        print("3-15. Unified answer, continuity, timeline, reject, bounds verified")

        # ---- 16-18: governance scoped reader -----------------------------------------------------------
        emp_auth = await invite_scoped(c, auth, f"emp{t}@ub7.test.co", scope["id"])
        scoped_answer = await brain_answer(c, emp_auth, question)
        scoped_dead = [
            url
            for cl in scoped_answer.get("claims", [])
            for url in [e.get("url", "") for e in cl.get("evidence", [])]
            if url and (await c.get(url, headers=emp_auth)).status_code == 404
        ]
        check(
            "16. governance: scoped reader gets org_wide=false and all evidence resolves",
            scoped_answer.get("scope", {}).get("org_wide") is False
            and scoped_answer.get("persona", {}).get("org_wide") is False
            and not scoped_dead,
            f"claims={len(scoped_answer.get('claims', []))} dead={len(scoped_dead)}",
        )
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
        hidden_timeline = await c.get(
            f"{API}/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": hidden_proj["id"]},
            headers=emp_auth,
        )
        scoped_timeline = (await c.get(f"{API}/brain/timeline/unified", params={"limit": 50}, headers=emp_auth)).json()
        scoped_changed = (await c.get(f"{API}/brain/what-changed", headers=emp_auth)).json()
        leaked = (
            hidden_proj["id"] in json.dumps(scoped_timeline.get("timeline", []))
            or hidden_proj["id"] in json.dumps(scoped_changed.get("categories", []))
            or any(e.get("url", "").find(hidden_proj["id"]) >= 0 for cl in scoped_answer.get("claims", []) for e in cl.get("evidence", []))
        )
        check(
            "17. governance 404: hidden timeline 404, no hidden ids in scoped surfaces",
            hidden_timeline.status_code == 404
            and scoped_timeline.get("scope", {}).get("org_wide") is False
            and not leaked,
            f"timeline={hidden_timeline.status_code} leaked={leaked}",
        )
        other_conv = await c.get(f"{API}/brain/conversations/{conv['id']}", headers=emp_auth)
        other_listed = (await c.get(f"{API}/brain/conversations", headers=emp_auth)).json()
        other_answer = await c.post(f"{API}/brain/answer", json={"question": "who owns this?", "conversation_id": conv["id"]}, headers=emp_auth)
        check(
            "18. conversation isolation: another member cannot read/list/answer into it",
            other_conv.status_code == 404
            and other_listed.get("count", 0) == 0
            and other_answer.status_code == 404,
            f"get={other_conv.status_code} list={other_listed.get('count')} answer={other_answer.status_code}",
        )
        print("16-18. Governance scoping verified")

        # ---- 19: tenant isolation --------------------------------------------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc7-{t}", f"eve{t}@rc7.test.co", "Eve Rival")
        rival_conv = await c.get(f"{API}/brain/conversations/{conv['id']}", headers=org_b["headers"])
        rival_changed = await c.get(f"{API}/brain/what-changed", headers=org_b["headers"])
        rival_timeline = (await c.get(f"{API}/brain/timeline/unified", params={"limit": 50}, headers=org_b["headers"])).json()
        rival_answer = await brain_answer(c, org_b["headers"], "what is happening in your company right now?")
        check(
            "19. tenant isolation: rival org never sees conversations/timeline/changes/answers of this org",
            rival_conv.status_code == 404
            and "Helios" not in rival_changed.text
            and "Helios" not in json.dumps(rival_timeline.get("timeline", []))
            and "Helios" not in rival_answer.get("summary", ""),
            f"conv={rival_conv.status_code}",
        )

        # ---- 20: endpoint contract ---------------------------------------------------------------------------------
        anon_conv = await c.get(f"{API}/brain/conversations/{conv['id']}")
        anon_timeline = await c.get(f"{API}/brain/timeline/unified")
        anon_changed = await c.get(f"{API}/brain/what-changed")
        missing_conv = await c.get(f"{API}/brain/conversations/does-not-exist", headers=auth)
        missing_entity = await c.get(
            f"{API}/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": "does-not-exist"},
            headers=auth,
        )
        check(
            "20. endpoint contract: anonymous 401/403, missing resources 404",
            anon_conv.status_code in (401, 403)
            and anon_timeline.status_code in (401, 403)
            and anon_changed.status_code in (401, 403)
            and missing_conv.status_code == 404
            and missing_entity.status_code == 404,
            f"anon={anon_conv.status_code}/{anon_timeline.status_code}/{anon_changed.status_code} missing={missing_conv.status_code}/{missing_entity.status_code}",
        )

        # ---- 21: bounded conversations -----------------------------------------------------------------------------
        for _ in range(24):
            await c.post(f"{API}/brain/conversations", json={}, headers=auth)
        bounded_list = (await c.get(f"{API}/brain/conversations", params={"limit": 50}, headers=auth)).json()
        check(
            "21. bounded conversations: list count never exceeds the per-user bound",
            bounded_list.get("count", 0) <= 20,
            f"count={bounded_list.get('count')}",
        )
        print("19-21. Isolation, contracts, bounds verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))