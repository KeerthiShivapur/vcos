"""Slice 4F.3 live acceptance against a running backend (default :8999).

Covers: evidence provenance, outcome-driven trust, corroboration,
contradictions (rejected approval), trust/evidence endpoints, and the Company
Brain "why does X know Y" intent. Prints PASS/FAIL per check.
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


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, timeout: int = 60):
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


def main() -> int:
    t = str(int(time.time()))[-8:]
    email = f"accept4f3{t}@acme.com"
    _, reg = call("POST", "/auth/register", {
        "organization_name": f"Accept 4F3 {t}", "organization_slug": f"accept4f3-{t}",
        "industry": "Software", "country": "US", "full_name": "Vera",
        "email": email, "password": "StrongPass123!",
    })
    if reg is None:
        check("register", False, "could not create live org")
        return 1
    auth = {"Authorization": f"Bearer {reg['access_token']}"}
    check("register + login", True)

    status, emp = call("POST", "/employees", {
        "first_name": "Py", "last_name": "Dev", "email": f"pydev{t}@acme.com",
        "designation": "Platform Engineer",
    }, auth)
    check("employee created", status in (200, 201), f"status={status} payload={emp}" if status not in (200, 201) else "")

    for i in range(5):
        st, task = call("POST", "/tasks", {
            "title": f"Build the python telemetry pipeline {i}",
            "assignee_id": emp["id"],
        }, auth)
        st2, _ = call("POST", f"/tasks/{task['id']}/transition", {"status": "completed"}, auth)
        assert st2 == 200, f"transition failed {st2}"
    check("5 python tasks completed", True)

    status, appr = call("POST", "/approvals", {
        "title": f"python toolchain upgrade {t}",
        "requester_id": emp["id"],
    }, auth)
    check("approval created with requester", status == 201)
    st, _ = call("POST", f"/approvals/{appr['id']}/decide",
                 {"decision": "rejected", "note": "insufficient review"}, auth)
    check("approval rejected", st == 200)

    st, _ = call("POST", "/intelligence/events/process", {"limit": 600}, auth)
    check("event worker drained", st == 200)

    st, search = call("GET", f"/brain/expertise/search?q=python", headers=auth)
    experts = search.get("experts", []) if search else []
    me = next((e for e in experts if e.get("person_id") == emp["id"]), None)
    check("search returns expert with trust facets", bool(me))
    if me:
        check("5+ successes", me["successful_count"] >= 5, str(me["successful_count"]))
        check("1+ failure kept", me["failed_count"] >= 1, str(me["failed_count"]))

    st, trust = call("GET",
        f"/brain/people/{emp['id']}/expertise/{me['skill_id']}/trust", headers=auth)
    ok = st == 200 and trust and trust["trust"] is True
    check("trust profile route", ok)
    if trust:
        check("person resolved", trust["person_name"] == "Py Dev", trust["person_name"])
        check("6 distinct lineages", trust["distinct_lineages"] >= 6,
              str(trust["distinct_lineages"]))
        check("contradiction present", len(trust["contradictions"]) >= 1,
              str(len(trust["contradictions"])))
        check("corroborated kinds", trust["corroborated_kinds"] >= 2,
              str(trust["corroborated_kinds"]))

    st, ev = call("GET",
        f"/brain/people/{emp['id']}/expertise/{me['skill_id']}/evidence", headers=auth)
    check("evidence list route", st == 200 and ev and ev.get("evidence"))
    if ev:
        kinds = {e["evidence_kind"] for e in ev["evidence"]}
        check("work + decision kinds", "work" in kinds and "decision" in kinds, str(kinds))
        detailed = next((e for e in ev["evidence"] if e["source_type"] == "task"), None)
        if detailed:
            st2, d = call("GET", f"/brain/expertise/evidence/{detailed['evidence_id']}", headers=auth)
            check("drill-down keeps provenance", st2 == 200 and d and d.get("lineage_key"))
        else:
            check("drill-down keeps provenance", False, "no task evidence item found")

    st, ans = call("POST", "/brain/knowledge/query",
                   {"question": f"why does Py Dev know Python?"}, auth)
    ok = st == 200 and ans and ans.get("intent") == "expertise_trust" and (
        ans.get("kind") == "trust_profile")
    check("NL why-trust intent", ok)
    if ans and ans.get("answers"):
        check("answer cites lineage", "lineage" in (ans["answer"] or ""))

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())