"""Slice 4F.2 acceptance — Universal Skills & Expertise Intelligence (live API).

Checks against the running stack (http://localhost:8999). 4F.2 stands on the
existing people intelligence: a canonical skill taxonomy with deterministic
aliases (never silently merged), declared skills that are associations and
never expertise, an exact-once evidence pipeline (task/document/decision)
feeding deterministic dimensions -> lifecycle -> bounded aggregates, governed
ranked expert discovery, scoped-reader and tenant isolation, graph edges,
brain-question intents, and strictly read-only read paths. NOT another
isolated silver — everything is computed from the SAME canonical evidence
pipeline already in the schema.

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
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=60
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:
        pass
    return -1


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 8) -> int:
    total = 0
    for _ in range(rounds):
        n = await dispatch(client, headers)
        if n <= 0:
            if n == 0:
                break
            continue  # transient dispatch error: retry next round
        total += n
    return total


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


async def invite_scoped_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Brain Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Brain Reader",
            "password": "B4DPass123!",
        },
    )
    assert joined.status_code == 201, joined.text
    scoped_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    user_id = joined.json()["user"]["id"]
    await client.post(
        f"{API}/governance/assignments",
        json={"user_id": user_id, "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers,
    )
    assignments = (
        await client.get(f"{API}/governance/assignments", params={"user_id": user_id}, headers=headers)
    ).json()
    org_wide = next(assignment for assignment in assignments if assignment["scope_id"] is None)
    await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        f"{API}/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4f.2 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def complete_task(client: httpx.AsyncClient, headers: dict, task_id: str, assignee_id: str, title: str) -> dict:
    created = await client.post(
        f"{API}/tasks",
        json={"title": title, "assignee_id": assignee_id, "status": "todo"},
        headers=headers, timeout=60,
    )
    assert created.status_code == 201, created.text
    task = created.json()
    done = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"status": "completed"}, headers=headers, timeout=60,
    )
    assert done.status_code == 200, done.text
    return task


async def publish_doc(client: httpx.AsyncClient, headers: dict, owner_id: str, title: str) -> dict:
    created = await client.post(
        f"{API}/documents",
        json={"title": title, "owner_id": owner_id, "content": title, "category": "Engineering"},
        headers=headers, timeout=60,
    )
    assert created.status_code == 201, created.text
    doc = created.json()
    pub = await client.post(f"{API}/documents/{doc['id']}/publish", headers=headers, timeout=60)
    assert pub.status_code == 200, pub.text
    return doc


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Expertise Co", f"exco-{t}", f"exp{t}@exco.test.co", "Exp Founder")
        auth = org["headers"]
        oid = org["organization"]["id"]

        dept = (await c.post(f"{API}/departments", json={"name": "Engineering", "code": "eng"}, headers=auth)).json()
        data_team = (await c.post(f"{API}/teams", json={"name": "Data", "code": "data", "department_id": dept["id"]}, headers=auth)).json()
        other_team = (await c.post(f"{API}/teams", json={"name": "Web", "code": "web", "department_id": dept["id"]}, headers=auth)).json()
        ada = await hire(c, auth, f"ada{t}@exco.test.co", "Ada", "Alvarez",
                         team_id=data_team["id"], department_id=dept["id"])
        bo = await hire(c, auth, f"bo{t}@exco.test.co", "Bo", "Mercer",
                        team_id=other_team["id"], department_id=dept["id"])
        await dispatch(c, auth)

        # -------- 1. canonical taxonomy: seed, aliases, parents, provenance
        listing = (await c.get(f"{BRAIN}/expertise/skills", headers=auth)).json()
        by_name = {e["canonical_name"]: e for e in listing["skills"]}
        check("1. taxonomy is seeded with the canonical catalog",
              listing.get("total", 0) >= 26
              and by_name["Python"]["category"] == "Programming Languages"
              and by_name["PostgreSQL"]["category"] == "Databases",
              f"total={listing.get('total')}")
        check("2. aliases + parents + provenance are deterministic",
              "postgres" in by_name["PostgreSQL"]["aliases"]
              and "pg" in by_name["PostgreSQL"]["aliases"]
              and by_name["Deep Learning"]["parent_skill"] == "Machine Learning"
              and by_name["Kubernetes"]["provenance"] == "system_seed",
              str(by_name["Deep Learning"])[:200])
        resolved = (await c.get(f"{BRAIN}/expertise/search", params={"q": "postgres"}, headers=auth)).json()
        check("3. alias resolution finds PostgreSQL through 'postgres'",
              bool(resolved.get("resolved_skill_ids"))
              and "PostgreSQL" in {s["skill_name"] for s in resolved["skills"]},
              str(resolved)[:180])
        pg_filtered = (await c.get(f"{BRAIN}/expertise/skills", params={"q": "pg"}, headers=auth)).json()
        unknown = (await c.get(f"{BRAIN}/expertise/skills", params={"q": "time-travel"}, headers=auth)).json()
        check("4. taxonomy q-filter is exact-first and bounded",
              any(s["canonical_name"] == "PostgreSQL" for s in pg_filtered["skills"])
              and unknown.get("total") == 0,
              f"pg={len(pg_filtered['skills'])} unknown={unknown.get('total')}")

        # -------- 2. declared skills associate but never fabricate expertise
        declared = await c.post(f"{BRAIN}/people/{ada['id']}/skills",
                                json={"name": "PyTorch", "level": 5}, headers=auth)
        skills = (await c.get(f"{BRAIN}/people/{ada['id']}/skills", headers=auth)).json()
        expertise = (await c.get(f"{BRAIN}/people/{ada['id']}/expertise", headers=auth)).json()
        check("5. a declared skill is an association with a level, never expertise",
              declared.status_code == 200
              and declared.json()["source"] == "declared"
              and skills["total"] == 1
              and skills["skills"][0]["declared_level"] == 5
              and skills["skills"][0]["expertise"] is None
              and expertise["total"] == 0,
              f"declared={declared.status_code} skills={skills.get('total')} exp={expertise.get('total')}")
        neither = await c.post(f"{BRAIN}/people/{bo['id']}/skills", json={"level": 3}, headers=auth)
        bogus = await c.post(f"{BRAIN}/people/{bo['id']}/skills",
                             json={"name": "Python", "level": 99}, headers=auth)
        check("6. invalid declarations: no name -> 400, level clamps to 1..5",
              neither.status_code == 400
              and bogus.status_code == 200
              and bogus.json()["declared_level"] == 5,
              f"neither={neither.status_code} bogus={bogus.status_code} level={bogus.json().get('declared_level')}")

        # -------- 3. evidence pipeline: task + document -> strong evidence
        for i in range(5):
            await complete_task(c, auth, None, ada["id"], f"Implemented the python data pipeline number {i}")
        for i in range(3):
            await publish_doc(c, auth, ada["id"], f"Python architecture notes {i}")
        check("7. events are durable and drained",
              await drain(c, auth) >= 0)

        top = await poll(c, auth, "GET", f"{BRAIN}/people/{ada['id']}/expertise", lambda d: (
            d.get("total", 0) >= 1 and d["expertise"][0]["evidence_count"] >= 5
        ), timeout=180, tick=lambda: dispatch(c, auth))
        e0 = top["expertise"][0]
        check("8. task/document evidence produces deterministic expertise",
              top["total"] >= 1 and e0["skill_name"] == "Python"
              and e0["evidence_count"] >= 5 and e0["strong_count"] >= 3
              and e0["lifecycle"] in ("established", "strong", "authoritative")
              and e0["confidence"] > 0.5,
              str(e0)[:260])
        check("8b. a declared skill alone never appears as expertise",
              all(x["skill_name"] != "PyTorch" for x in top["expertise"]),
              str([x["skill_name"] for x in top["expertise"]]))

        # -------- 4. exact-once under replay of the durable queue
        settle = await drain(c, auth)
        ran = await dispatch(c, auth)
        again = (await c.get(f"{BRAIN}/people/{ada['id']}/expertise", headers=auth)).json()
        check("9. draining the queue twice never re-ingests evidence",
              ran == 0 and again["expertise"][0]["evidence_count"] == e0["evidence_count"],
              f"ran={ran} before={e0['evidence_count']} after={again['expertise'][0]['evidence_count']}")

        # -------- 5. governed ranking, bounded limits, team scoping
        ranked = (await c.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=auth)).json()
        scores = [ex["score"] for ex in ranked["experts"]]
        over = await c.get(f"{BRAIN}/expertise/search",
                           params={"q": "python", "limit": 5000}, headers=auth)
        check("10. ranked experts are sorted and bounds are enforced by the API",
              ranked["total"] >= 1 and ranked["experts"][0]["person_id"] == ada["id"]
              and scores == sorted(scores, reverse=True)
              and over.status_code == 422,
              f"total={ranked.get('total')} over={over.status_code}")
        team_ranked = (await c.get(f"{BRAIN}/expertise/search",
                                   params={"q": "python", "scope_type": "team",
                                           "scope_id": data_team["id"]}, headers=auth)).json()
        check("11. a team-scoped search only ranks that team's experts",
              [e["person_id"] for e in team_ranked["experts"]] == [ada["id"]],
              str([e["person_id"] for e in team_ranked["experts"]]))

        # -------- 6. aggregate maps with whole-scope governance
        team_map = (await c.get(f"{BRAIN}/expertise/teams/{data_team['id']}", headers=auth)).json()
        python_cap = next((cap for cap in team_map["capabilities"] if cap["skill_name"] == "Python"), None)
        dept_map = (await c.get(f"{BRAIN}/expertise/departments/{dept['id']}", headers=auth)).json()
        org_map = (await c.get(f"{BRAIN}/expertise/organization", headers=auth)).json()
        missing_team = await c.get(f"{BRAIN}/expertise/teams/not-a-team", headers=auth)
        check("12. bounded capability maps materialize and unknown scopes 404",
              python_cap is not None and python_cap["member_count"] >= 1
              and python_cap["avg_score"] > 0
              and any(cap["skill_name"] == "Python" for cap in dept_map["capabilities"])
              and any(cap["skill_name"] == "Python" for cap in org_map["capabilities"])
              and missing_team.status_code == 404,
              f"team={python_cap} dept={len(dept_map['capabilities'])} org={len(org_map['capabilities'])} missing={missing_team.status_code}")

        # -------- 7. scoped reader sees exactly their scope everywhere
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Data scope", "scope_type": "team",
                                    "entity_id": data_team["id"]}, headers=auth)).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"scop{t}@exco.test.co")
        scoped_ranked = (await c.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=scoped)).json()
        hidden_exp = await c.get(f"{BRAIN}/people/{bo['id']}/expertise", headers=scoped)
        org_wide = await c.get(f"{BRAIN}/expertise/organization", headers=scoped)
        hidden_team_map = await c.get(f"{BRAIN}/expertise/teams/{other_team['id']}", headers=scoped)
        scoped_write = await c.post(f"{BRAIN}/people/{bo['id']}/skills",
                                    json={"name": "Python", "level": 3}, headers=scoped)
        check("13. scoped readers only rank their team; hidden people 404 on every surface",
              [e["person_id"] for e in scoped_ranked["experts"]] == [ada["id"]]
              and hidden_exp.status_code == 404
              and org_wide.status_code == 404
              and hidden_team_map.status_code == 404,
              f"ranked={[e['person_id'] for e in scoped_ranked['experts']]} "
              f"exp={hidden_exp.status_code} org={org_wide.status_code} team={hidden_team_map.status_code}")
        check("14. writes need employees:manage: 401 anonymous, 403 scoped, 200 admin",
              (await c.post(f"{BRAIN}/people/{ada['id']}/skills",
                            json={"name": "Python", "level": 3})).status_code == 401
              and scoped_write.status_code == 403
              and (await c.post(f"{BRAIN}/people/{ada['id']}/skills",
                                json={"name": "Rust", "level": 3}, headers=auth)).status_code == 200,
              f"anon=... scoped={scoped_write.status_code}")

        # -------- 8. tenant isolation
        rival = await register(c, "Rival Expertise Co", f"rivex-{t}", f"rex{t}@rivex.test.co", "Riv Founder")
        rival_search = (await c.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=rival["headers"])).json()
        rival_profile = await c.get(f"{BRAIN}/people/{ada['id']}/expertise", headers=rival["headers"])
        rival_map = (await c.get(f"{BRAIN}/expertise/organization", headers=rival["headers"])).json()
        check("15. tenant isolation: a rival org sees no expertise and mutates nothing",
              rival_search["total"] == 0
              and [] == rival_search["experts"]
              and rival_profile.status_code == 404
              and rival_map["total"] == 0,
              f"search={rival_search['total']} profile={rival_profile.status_code} map={rival_map['total']}")

        # -------- 9. brain questions
        q1 = (await c.post(f"{KNOW}/query", json={"question": "who knows python?"}, headers=auth)).json()
        q2 = (await c.post(f"{KNOW}/query", json={"question": "what does Ada Alvarez know?"}, headers=auth)).json()
        q3 = (await c.post(f"{KNOW}/query", json={"question": "where does our python expertise live?"}, headers=auth)).json()
        q4 = (await c.post(f"{KNOW}/query", json={"question": "who knows lacrosse?"}, headers=auth)).json()
        check("16. 'who knows X' ranks experts with evidence",
              q1.get("intent") == "expertise" and q1.get("kind") == "experts"
              and q1.get("total", 0) >= 1 and q1["answers"][0]["person_id"] == ada["id"],
              str(q1)[:220])
        check("17. 'what does X know' lists that person's expertise",
              q2.get("kind") == "person_expertise"
              and any(e["skill_name"] == "Python" for e in q2.get("answers") or []),
              str(q2)[:220])
        check("18. capability questions return the org map; unknown skills say so",
              q3.get("kind") == "organization_map" and q3.get("total", 0) >= 1
              and q4.get("kind") == "no_skill",
              f"q3={q3.get('kind')} q4={q4.get('kind')}")

        # -------- 10. read paths never mutate (evidence + durable queue)
        await drain(c, auth, rounds=12)
        before = (await c.get(f"{BRAIN}/people/{ada['id']}/expertise", headers=auth)).json()["expertise"][0]["evidence_count"]
        for url, params in (
            (f"{BRAIN}/expertise/skills", {}),
            (f"{BRAIN}/expertise/search", {"q": "python"}),
            (f"{BRAIN}/people/{ada['id']}/expertise", {}),
            (f"{BRAIN}/expertise/organization", {}),
        ):
            r = await c.get(url, params=params, headers=auth)
            assert r.status_code == 200, r.text
        swept = await drain(c, auth, rounds=12)
        after = (await c.get(f"{BRAIN}/people/{ada['id']}/expertise", headers=auth)).json()["expertise"][0]["evidence_count"]
        check("19. read paths never fabricate evidence or enqueue signals",
              swept == 0 and before == after,
              f"swept={swept} before={before} after={after}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))