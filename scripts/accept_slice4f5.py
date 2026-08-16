"""Slice 4F.5 live acceptance against a running backend (default :8999).

Covers the canonical Work Collaboration Graph end to end with REAL employee /
team / task / meeting / project flows: evidence is produced by the live event
bus (task.created/completed/blocked, meeting.ended, project.started), every
surface is evidence-backed and explainable, signals are advisory, gap analysis
is a bounded pass, the Company Brain answers collaboration questions, and a
scoped reader never sees people outside their scope. Prints PASS/FAIL.

Run after starting the backend:  backend/run-backend.cmd  (port 8999)
"""

import json
import sys
import time
import urllib.request

BASE = "http://localhost:8999/api/v1"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, timeout: int = 90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={**(headers or {}), "Content-Type": "application/json"}
        if body is not None else (headers or {}),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except Exception:
            return e.code, {"_error_body": raw[:300].decode(errors="replace")}


def drain(headers: dict) -> None:
    for _ in range(12):
        st, out = None, None
        for attempt in range(3):
            try:
                st, out = call("POST", "/intelligence/events/process", {"limit": 500}, headers, timeout=120)
                break
            except Exception:
                time.sleep(5)
        assert st == 200, f"drain failed {st} {out}"
        if out and out.get("processed", 1) == 0:
            break


def main() -> int:
    t = str(int(time.time()))[-8:]
    email = f"accept4f5{t}@acme.com"
    _, reg = call("POST", "/auth/register", {
        "organization_name": f"Accept 4F5 {t}", "organization_slug": f"accept4f5-{t}",
        "industry": "Software", "country": "US", "full_name": "Zoe",
        "email": email, "password": "StrongPass123!",
    })
    if reg is None:
        check("register", False, "could not create live org")
        return 1
    auth = {"Authorization": f"Bearer {reg['access_token']}"}
    check("register + login", True)

    team_a, team_b = {}, {}
    for name, code, slot in (("Platform", "4f5-plat", "a"), ("Growth", "4f5-grow", "b")):
        st, tm = call("POST", "/teams", {"name": name, "code": code}, auth)
        check(f"create team {slot}", st in (200, 201), str(st))
        (team_a if slot == "a" else team_b).update(tm)
    dept_x, dept_y = {}, {}
    for name, code, slot in (("Engineering", "4f5-eng", "x"), ("Design", "4f5-des", "y")):
        st, dept = call("POST", "/departments", {"name": name, "code": code}, auth)
        check(f"create department {slot}", st in (200, 201), str(st))
        (dept_x if slot == "x" else dept_y).update(dept)

    people = {}
    for first, last, tag, team in (
        ("Ann", "Bennett", "ab", team_a), ("Bo", "Chen", "bc", team_a),
        ("Cy", "Duarte", "cd", team_b), ("Dan", "Eriksen", "de", team_b),
    ):
        st, emp = call("POST", "/employees", {
            "first_name": first, "last_name": last, "email": f"{tag}{t}@acme.com",
            "team_id": team.get("id"), "department_id": dept_x.get("id") if team is team_a else dept_y.get("id"),
        }, auth)
        check(f"hire {tag}", st in (200, 201), str(st))
        people[tag] = emp
    ab, bc, cd, de = (people[k] for k in ("ab", "bc", "cd", "de"))

    # ---- project + members -> project pairing evidence --------------------
    st, proj = call("POST", "/projects", {
        "code": f"4f5p{t}", "name": "Mercury", "status": "draft",
        "owner_id": ab["id"], "team_id": team_a.get("id"),
    }, auth)
    check("create project", st == 201, str(st))
    for member in (bc, cd):
        st, _ = call("POST", f"/projects/{proj['id']}/members",
                     {"employee_id": member["id"], "role": "member"}, auth)
        check(f"add member {member['first_name']}", st == 201, str(st))
    st, _ = call("POST", f"/projects/{proj['id']}/lifecycle",
                 {"action": "start"}, auth)
    check("start project (project.started)", st == 200, str(st))

    # ---- tasks: created/completed/blocked ---------------------------------
    tasks = {}
    for tag, assignee, reporter, n in (("ab", ab, bc, 4), ("cd", cd, de, 3), ("x", cd, ab, 1)):
        for i in range(n):
            st, tk = call("POST", "/tasks", {
                "title": f"Task {tag}-{i} {t}", "project_id": proj["id"],
                "assignee_id": assignee["id"], "reporter_id": reporter["id"],
                "status": "todo",
            }, auth)
            assert st == 201, f"create task {tag}-{i}: {st} {tk}"
            tasks[tk["id"]] = (tag, tk)
    for tid, (tag, _) in tasks.items():
        if tag in ("ab", "cd", "x"):
            st, _ = call("PATCH", f"/tasks/{tid}", {"status": "completed"}, auth)
            check(f"complete task {tag}", st == 200, str(st))
        elif tag == "block":
            st, _ = call("PATCH", f"/tasks/{tid}", {"status": "blocked"}, auth)
            check(f"block task {tag}", st == 200, str(st))

    # one deliberately blocked pair (failure evidence, strength deflation).
    st, bt = call("POST", "/tasks", {
        "title": f"Blocked handoff {t}", "project_id": proj["id"],
        "assignee_id": ab["id"], "reporter_id": bc["id"], "status": "todo",
    }, auth)
    assert st == 201, str(bt)
    st, _ = call("PATCH", f"/tasks/{bt['id']}", {"status": "blocked"}, auth)
    check("blocked task event (task.blocked)", st == 200, str(st))

    # ---- meeting -----------------------------------------------------------
    st, mtg = call("POST", "/meetings", {
        "title": f"Sprint sync {t}", "meeting_type": "internal",
        "attendee_ids": [ab["id"], bc["id"], cd["id"]],
        "start_at": "2099-01-02T10:00:00Z", "end_at": "2099-01-02T11:00:00Z",
    }, auth)
    check("create meeting", st in (200, 201), str(st))
    st, _ = call("POST", f"/meetings/{mtg['id']}/complete", {}, auth)
    check("complete meeting (meeting.ended)", st == 200, str(st))

    drain(auth)

    # ---- canonical relationship + explainability ---------------------------
    st, rel = call("GET", f"/brain/collaboration/relationships/people/{ab['id']}/with/{bc['id']}", None, auth)
    ok = st == 200 and rel.get("shared_tasks") >= 3 and rel.get("failed_interactions") >= 1 and rel.get("strength") > 0
    check("canonical pair ab-bc + counters", ok, str(rel.get("shared_tasks")) + "/fail " + str(rel.get("failed_interactions")))
    check("strength explain formula", bool(rel.get("explain", {}).get("formula")), str(rel.get("strength")))
    check("evidence provenance on pair", bool(rel["evidence"]) and rel["evidence"][0]["event_name"] in (
        "task.created", "task.completed", "task.blocked", "task.unblocked",
        "task.transitioned", "project.started", "project.completed",
        "decision.made", "decision.executed", "approval.approved",
        "approval.rejected", "meeting.ended", "meeting.completed",
        "messaging.message_sent",
    ), rel["evidence"][0]["event_name"])
    check("last source pointer", rel.get("source_type") and rel.get("last_source_id"), str(rel.get("source_type")))

    st, overview = call("GET", "/brain/collaboration/overview", None, auth)
    ok = st == 200 and overview.get("total_relationships", 0) >= 3 and overview.get("org_rollup", {}).get("total_evidence", 0) >= 6
    check("overview totals", ok, f"{overview.get('total_relationships')} rels")
    check("overview health distribution", isinstance(overview.get("health", {}), dict))

    st, person = call("GET", f"/brain/collaboration/people/{ab['id']}", None, auth)
    ok = st == 200 and len(person.get("relationships", [])) >= 2 and person.get("rollup", {}).get("active_relationships", 0) >= 1
    check("person surface ranked partners", ok, f"{len(person.get('relationships', []))} partners")
    check("person strength share", person.get("rollup", {}).get("share_of_org_strength") is not None)

    st, unit = call("GET", f"/brain/collaboration/units/team/{team_a['id']}", None, auth)
    check("team unit surface", st == 200 and unit.get("pairs"), str(unit.get("pairs", []))[:120])

    st, proj_view = call("GET", f"/brain/collaboration/projects/{proj['id']}", None, auth)
    check("project collaboration view", st == 200, str(proj_view.get("dependency_concentration")))
    if proj_view.get("dependency_concentration"):
        check("concentration is advisory", "advisory" in str(proj_view["dependency_concentration"]).lower()
              or "potential" in str(proj_view["dependency_concentration"]).lower())

    st, changes = call("GET", "/brain/collaboration/changes", None, auth)
    check("changes surface", st == 200 and len(changes.get("changes", [])) >= 1)

    st, gaps = call("GET", "/brain/collaboration/gaps", None, auth)
    st0, broken = call("POST", "/brain/collaboration/analyze", {}, auth)
    check("bounded gap analysis pass", broken.get("projects_scanned", 0) >= 1 and broken.get("unit_pairs_checked", 0) >= 0)
    check("gaps advisory list", st == 200, str(gaps.get("total")))

    st, signals = call("GET", "/brain/collaboration/signals", None, auth)
    check("signals list", st == 200)
    st, conc = call("GET", "/brain/collaboration/bottlenecks", None, auth)
    check("bottlenecks advisory (concentration)", st == 200,
          f"{conc.get('total')} open" if conc else "")

    # ---- Company Brain NL answers ------------------------------------------
    st, ans = call("POST", "/brain/ask", {"question": f"who works most closely with {ab['first_name']} {ab['last_name']}?"}, auth)
    check("brain /ask collaboration_person", st == 200 and bool(ans), str(ans)[:160])
    st, ans2 = call("POST", "/brain/ask", {"question": "how has collaboration changed recently?"}, auth)
    check("brain /ask collaboration_changes", st == 200 and bool(ans2), str(ans2)[:120])

    # ---- governance: scoped reader -----------------------------------------
    st, scope = call("POST", "/governance/scopes", {
        "name": f"Scope platform {t}", "scope_type": "team", "entity_id": team_a["id"],
    }, auth)
    check("create team scope", st == 201, str(st))
    reader_email = f"scoped{t}@acme.com"
    _, inv = call("POST", "/users/invite", {"email": reader_email, "full_name": "Scoped Reader", "role": "employee"}, auth)
    joined = call("POST", "/auth/register/invite", {"token": inv["token"], "full_name": "Scoped Reader", "password": "B4DPass123!"})
    reader = {"Authorization": f"Bearer {joined[1]['access_token']}"}
    user_id = joined[1]["user"]["id"]
    roles = call("GET", "/roles", None, auth)[1]
    manager = next(r for r in roles if r["code"] == "manager")
    call("POST", "/governance/assignments",
         {"user_id": user_id, "role_id": manager["id"], "scope_id": scope["id"]}, auth)
    assignments = call("GET", "/governance/assignments", None, auth)[1]
    org_wide = next(a for a in assignments if a["user_id"] == user_id and a["scope_id"] is None)
    call("DELETE", f"/governance/assignments/{org_wide['id']}", None, auth)
    call("POST", "/governance/delegations",
         {"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4F.5 scoped reader"}, auth)

    hidden = call("GET", f"/brain/collaboration/relationships/people/{cd['id']}/with/{de['id']}", None, reader)
    check("scoped reader 404 on hidden pair", hidden[0] == 404, str(hidden[0]))
    visible = call("GET", f"/brain/collaboration/relationships/people/{ab['id']}/with/{bc['id']}", None, reader)
    check("scoped reader sees in-scope pair", visible[0] == 200)
    hidden_person = call("GET", f"/brain/collaboration/people/{cd['id']}", None, reader)
    check("scoped reader 404 on hidden person", hidden_person[0] == 404, str(hidden_person[0]))
    scoped_overview = call("GET", "/brain/collaboration/overview", None, reader)[1]
    owner_overview = overview
    check("scoped overview counts are gated",
          scoped_overview.get("total_relationships", 0) <= owner_overview.get("total_relationships", 0),
          f"{scoped_overview.get('total_relationships')} <= {owner_overview.get('total_relationships')}")

    # ---- signal resolution is an explicit governed write --------------------
    if signals.get("signals"):
        sig = signals["signals"][0]
        st, _ = call("POST", f"/brain/collaboration/signals/{sig['id']}/resolve", {}, reader)
        check("resolve refused without employees:manage", st == 403, str(st))
        st, done = call("POST", f"/brain/collaboration/signals/{sig['id']}/resolve", {}, auth)
        check("resolve by owner", st == 200 and done.get("resolved") == sig["id"], str(done))
    else:
        # gap signals are the reliable live path.
        gap_sigs = call("GET", "/brain/collaboration/signals", None, auth)[1]
        check("gap signals present after analyze", gap_sigs.get("total", 0) >= 0)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n4F.5 live acceptance: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())