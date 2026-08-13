"""Slice 4E.3 acceptance — Universal Knowledge Understanding & Synthesis (live API).

Checks against the running stack (http://localhost:8999). Every meaningful
activity event already lands in the canonical model (4E.2); 4E.3 connects
those claims: claims from different families that speak about the same topic
collapse into ONE topic-anchored understanding claim — deterministic, governed
and evidence-backed:

  1. cross-source synthesis: message + task + memory about the same topic land
     in one current understanding with cross-family supporting claims, one
     evidence row per family and graph edges to the topic
  2. contradiction detection: two budget values conflict; the newer chat wins
     on valid_from; the loser stays as contradicting evidence with its
     resolution recorded
  3. authority resolution: a team record (task, authority 2) beats both chat
     values (authority 1) — the winning facet is stated and both chats become
     contradicting evidence
  4. temporal reasoning: the understanding evolves (Friday -> Monday), the old
     version is superseded (valid_to + superseded_by) and the timeline shows
     how understanding developed; "what is true now" is the current version
  5. evidence-backed answers: /evidence returns a deterministic answer plus the
     exact evidence chain (citations with claim ids and excerpts)
  6. exact-once synthesis: replaying drains and re-triggering /synthesize with
     unchanged evidence never creates a duplicate understanding
  7. governance: a project-scoped reader sees the topic with only the evidence
     inside their scope; a topic with no visible evidence is 404
  8. tenant isolation: a rival organization sees topic state and claim detail
     as 404
  9. vocabulary legality: synthesis claims stay inside the claim states and
     authority labels; the one-internal-language rule holds

Exit code 0 when all pass.
"""

import asyncio
import sys
import time
from urllib.parse import quote

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []

CLAIM_STATES = {"candidate", "supported", "authoritative", "contested", "superseded"}
AUTHORITY_LABELS = {1: "unverified", 2: "team_record", 3: "documented", 4: "authoritative", 5: "official"}


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


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 14) -> None:
    for _ in range(rounds):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


def topic_of(name: str) -> str:
    return quote(name, safe="")


async def topic_state(client: httpx.AsyncClient, headers: dict, name: str):
    return await client.get(f"{API}/brain/knowledge/topics/{topic_of(name)}/state", headers=headers)


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4E.3 acceptance: Universal Knowledge Understanding & Synthesis (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        org = await register(c, "Universal Understanding Co", f"uu-{t}", f"uni{t}@uu.test.co", "Una Founder")
        auth = org["headers"]
        org_id = org["organization"]["id"]
        print("1. Founder registered, org", org_id)
        await drain(c, auth)

        # ---------------- 1. cross-source synthesis: message + task + memory
        conv = (
            await c.post(
                f"{API}/conversations",
                json={"type": "channel", "title": "release", "member_ids": [org["user"]["id"]]},
                headers=auth,
            )
        ).json()
        msg = (
            await c.post(
                f"{API}/conversations/{conv['id']}/messages",
                json={"content": "The migration window is confirmed for 2am."},
                headers=auth,
            )
        ).json()
        project = (
            await c.post(f"{API}/projects", json={"name": "Migration Program", "description": "4E.3", "status": "active"}, headers=auth)
        ).json()
        task = (
            await c.post(f"{API}/tasks", json={"title": "Migration runbook", "project_id": project["id"]}, headers=auth)
        ).json()
        mem = (
            await c.post(
                f"{API}/brain/memory",
                json={"memory_type": "lesson", "title": "Migration go-live",
                      "content": "The migration go-live has been agreed for Monday.",
                      "importance": "medium", "tags": ["migration", "go-live"]},
                headers=auth,
            )
        ).json()
        await drain(c, auth)

        state = (await topic_state(c, auth, "migration")).json()
        current = state.get("current_state") or {}
        check("1a. cross-family evidence collapses into one topic state",
              state.get("evidence", {}).get("total") >= 3
              and set(state.get("evidence", {}).get("by_family", {})) >= {"message", "task", "memory"},
              str(state)[:400])
        check("1b. one current understanding with a synthesis claim",
              current.get("claim_type") == "synthesis"
              and current.get("predicate") == "synthesizes"
              and current.get("status") in ("supported", "authoritative")
              and current.get("authority_level") == 3
              and current.get("topic_id") is not None,
              str(current)[:400])
        detail = (await c.get(f"{API}/brain/knowledge/claims/{current['id']}", headers=auth)).json()
        check("1c. supporting claims are cross-family and related entities attach",
              len(detail.get("supporting_claims") or []) >= 3
              and {s["subject_type"] for s in detail.get("supporting_claims") or []}
              >= {"message", "task", "memory"}
              and state.get("related_entities"),
              str(detail)[:400])

        # ---------------- 2. contradiction: newer chat wins on valid_from
        old_msg = (
            await c.post(
                f"{API}/conversations/{conv['id']}/messages",
                json={"content": "The migration budget is 5 lakh."},
                headers=auth,
            )
        ).json()
        await drain(c, auth)
        new_msg = (
            await c.post(
                f"{API}/conversations/{conv['id']}/messages",
                json={"content": "The migration budget is 10 lakh."},
                headers=auth,
            )
        ).json()
        await drain(c, auth)
        state2 = (await topic_state(c, auth, "migration")).json()
        current2 = state2["current_state"]
        detail_new = (await c.get(f"{API}/brain/knowledge/claims/{current2['id']}", headers=auth)).json()
        contra = detail_new.get("contradicting_claims") or []
        check("2a. contradictory evidence produces a contested understanding",
              "contested" in current2["object_text"] and len(contra) == 1
              and contra[0]["facet"] == "currency"
              and contra[0]["winner_claim_id"] != contra[0]["claim_id"],
              str(current2)[:400])
        check("2b. equal authority breaks on valid_from — the loser stays as evidence",
              contra[0]["resolution"] == "newer valid_from"
              and contra[0]["claim_id"] != contra[0]["winner_claim_id"],
              str(contra)[:400])
        check("2c. the loser remains visible in the claim graph as contradicting evidence",
              any(e["role"] == "contradicted" for e in detail_new.get("evidence", [])),
              str(detail_new.get("evidence"))[:400])
        contradictions = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/contradictions", headers=auth)
        ).json()
        check("2d. the contradictions endpoint exposes the resolved conflict",
              contradictions["total"] >= 1 and contradictions["contradictions"][0]["resolution"] == "newer valid_from",
              str(contradictions)[:400])

        # ---------------- 3. authority resolution: team record beats chats
        task2 = (
            await c.post(f"{API}/tasks", json={"title": "Migration budget 8 lakh", "project_id": project["id"]}, headers=auth)
        ).json()
        await drain(c, auth)
        state3 = (await topic_state(c, auth, "migration")).json()
        current3 = state3["current_state"]
        detail3 = (await c.get(f"{API}/brain/knowledge/claims/{current3['id']}", headers=auth)).json()
        contra3 = detail3.get("contradicting_claims") or []
        check("3a. authority resolves: the team record (2) beats both chats (1)",
              current3["authority_level"] == 3 and len(contra3) == 2
              and all(x["resolution"] == "authority 2 > 1" for x in contra3),
              str(current3)[:400])
        check("3b. the winning facet is stated in the understanding",
              "8 lakh" in current3["object_text"], str(current3)[:400])

        # ---------------- 4. temporal reasoning: evolution kept
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "Migration moved to Friday."},
            headers=auth,
        )
        await drain(c, auth)
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "Migration moved to next Monday."},
            headers=auth,
        )
        await drain(c, auth)
        state4 = (await topic_state(c, auth, "migration")).json()
        current4 = state4["current_state"]
        timeline = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/timeline", headers=auth)
        ).json()
        synth_events = [e for e in timeline["events"] if e["kind"] == "synthesis"]
        check("4a. the understanding evolved and 'what is true now' is current",
              "Monday" in current4["object_text"] and current4["valid_to"] is None
              and state4["evolution"]["versions"] >= 1,
              str(current4)[:400])
        check("4b. the old understanding is superseded, never deleted",
              len(synth_events) >= 2
              and any(e["status"] == "superseded" and e["valid_to"] is not None for e in synth_events[:-1]),
              str(synth_events)[:400])
        check("4c. the timeline shows how the company's understanding developed",
              len(synth_events) >= 2 and synth_events[-1]["status"] != "superseded",
              str(timeline.get("total")))

        # ---------------- 5. evidence-backed answer with citations
        answer = (
            await c.get(
                f"{API}/brain/knowledge/topics/{topic_of('migration')}/evidence",
                params={"question": "what is the status of the migration?"},
                headers=auth,
            )
        ).json()
        check("5a. deterministic answer with confidence and risk",
              answer["question"].startswith("what is the status")
              and "migration" in answer["answer"].lower()
              and answer["confidence"] and answer["risk"],
              str(answer)[:400])
        check("5b. the evidence chain is exact: every citation resolves",
              len(answer["evidence"]) >= 3
              and all(x.get("claim_id") and x.get("excerpt") and x.get("valid_from") for x in answer["evidence"]),
              str(answer["evidence"])[:400])

        # ---------------- 6. exact-once synthesis
        before = (await topic_state(c, auth, "migration")).json()["current_state"]["id"]
        await drain(c, auth)
        await drain(c, auth)
        after = (await topic_state(c, auth, "migration")).json()["current_state"]["id"]
        triggered = (
            await c.post(f"{API}/brain/knowledge/topics/{topic_of('migration')}/synthesize", headers=auth)
        ).json()
        check("6a. replaying events never duplicates the understanding",
              before == after, f"before={before} after={after}")
        check("6b. manual re-synthesis with unchanged evidence is a no-op",
              triggered.get("synthesized") is False and triggered.get("claim_id") == after,
              str(triggered)[:300])

        # ---------------- 7. governance: scoped reader
        # a hidden topic exists only through a project the scoped reader
        # cannot see (no scope anchored to this project)
        hidden_proj = (
            await c.post(f"{API}/projects", json={"name": "Hidden Stealth Program", "description": "4E.3", "status": "active"}, headers=auth)
        ).json()
        (
            await c.post(
                f"{API}/tasks", json={"title": "Stealth migration beta", "project_id": hidden_proj["id"]}, headers=auth
            )
        ).json()
        await drain(c, auth)
        scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Migration scope", "scope_type": "project", "entity_id": project["id"]},
                headers=auth,
            )
        ).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sc{t}@uu.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite", json={"token": emp["token"], "email": f"sc{t}@uu.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"}, headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(f"{API}/governance/assignments", json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]}, headers=auth)
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(f"{API}/governance/delegations", json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.3"}, headers=auth)
        assert dg.status_code == 201, dg.text
        sstate = (await topic_state(c, scoped, "migration")).json()
        s_ids = {e["subject_id"] for e in sstate["evidence"]["claims"]}
        check("7a. scoped reader sees only the evidence inside the scope",
              sstate["scope"] == "project"
              and set(s_ids) <= {str(task["id"]), str(task2["id"])}
              and "message" not in {e["subject_type"] for e in sstate["evidence"]["claims"]},
              str(sstate["evidence"])[:400])
        steed = await c.get(f"{API}/brain/knowledge/topics/{topic_of('stealth')}/state", headers=scoped)
        org_steed = await c.get(f"{API}/brain/knowledge/topics/{topic_of('stealth')}/state", headers=auth)
        check("7b. a topic with no visible evidence is hidden from the scoped reader",
              steed.status_code == 404 and org_steed.status_code == 200,
              f"scoped={steed.status_code} org={org_steed.status_code}")

        # ---------------- 8. tenant isolation
        rival = await register(c, "Rival Understanding Co", f"ruu-{t}", f"riv{t}@ruu.test.co", "Riv Founder")
        await drain(c, rival["headers"])
        rstate = await topic_state(c, rival["headers"], "migration")
        rclaim = await c.get(f"{API}/brain/knowledge/claims/{current2['id']}", headers=rival["headers"])
        rreg = (await c.get(f"{API}/brain/knowledge", headers=rival["headers"])).json()
        check("8. tenant isolation: rival sees nothing",
              rstate.status_code == 404 and rclaim.status_code == 404 and rreg["total"] == 0,
              f"state={rstate.status_code} claim={rclaim.status_code} reg={rreg['total']}")

        # ---------------- 9. vocabulary legality: one internal language
        vocab_ok = True
        for cl in (current, current2, current3, current4):
            if cl.get("status") not in CLAIM_STATES:
                vocab_ok = False
            if cl.get("authority_label") not in AUTHORITY_LABELS.values():
                vocab_ok = False
            if cl.get("claim_type") != "synthesis":
                vocab_ok = False
        check("9. synthesis claims speak the established vocabulary",
              vocab_ok, str([c.get("status") for c in (current, current2, current3, current4)]))

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))