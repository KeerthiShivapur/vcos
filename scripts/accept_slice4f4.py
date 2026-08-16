"""Slice 4F.4 live acceptance against a running backend (default :8999).

Covers: canonical temporal ownership (assign / transfer / close / backup /
continuity / as-of / history), declared-vs-observed analysis that NEVER
auto-fixes, ownership gaps, single-person dependency risk, signal lifecycle,
coverage checks, person responsibilities, summary, and the Company Brain
"who is responsible for X" / "who takes over" intents. Prints PASS/FAIL per
check.
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


def drain(headers: dict) -> None:
    for _ in range(8):
        st, out = call("POST", "/intelligence/events/process", {"limit": 500}, headers)
        assert st == 200, f"drain failed {st} {out}"
        if out and out.get("processed", 1) == 0:
            break


def main() -> int:
    t = str(int(time.time()))[-8:]
    email = f"accept4f4{t}@acme.com"
    _, reg = call("POST", "/auth/register", {
        "organization_name": f"Accept 4F4 {t}", "organization_slug": f"accept4f4-{t}",
        "industry": "Software", "country": "US", "full_name": "Vera",
        "email": email, "password": "StrongPass123!",
    })
    if reg is None:
        check("register", False, "could not create live org")
        return 1
    auth = {"Authorization": f"Bearer {reg['access_token']}"}
    check("register + login", True)

    people = {}
    for first, last, tag in (("Ada", "Draper", "ada"), ("Bob", "Wright", "bob"),
                             ("Cy", "Mellon", "cy"), ("Dee", "Hart", "dee")):
        status, emp = call("POST", "/employees", {
            "first_name": first, "last_name": last,
            "email": f"{tag}{t}@acme.com", "designation": "Engineer",
        }, auth)
        check(f"hire {first} {last}", status in (200, 201),
              f"status={status}" if status not in (200, 201) else "")
        people[tag] = emp["id"]

    projects = {}
    for name, tag, owner in (("Ledger Service", "ledger", "ada"),
                             ("Billing Core", "billing", "bob"),
                             ("Checkout Flow", "checkout", "bob"),
                             ("Payments Platform", "payments", "ada"),
                             ("Data Sync", "sync", "dee")):
        status, proj = call("POST", "/projects", {
            "name": f"{name} {t}", "code": f"{tag}{t}", "owner_id": people[owner],
        }, auth)
        check(f"project {name}", status in (200, 201),
              f"status={status}" if status not in (200, 201) else "")
        projects[tag] = proj["id"]

    # Assign = the governed write; event-bridge reconcile is exact-once, so a
    # re-assign refreshes the same window instead of creating a duplicate.
    payments = projects["payments"]
    for obj_tag, owner in (("ledger", "ada"), ("billing", "bob"),
                           ("checkout", "bob"), ("payments", "ada"), ("sync", "dee")):
        st, out = call("POST", "/brain/ownership/assign", {
            "object_type": "project", "object_id": projects[obj_tag],
            "object_name": f"{obj_tag} {t}", "responsibility_type": "primary",
            "owner_id": people[owner], "reason": "acceptance",
        }, auth)
        check(f"assign {obj_tag} -> {owner}", st == 200, f"status={st}" if st != 200 else "")

    st, out = call("POST", "/brain/ownership/backup", {
        "object_type": "project", "object_id": payments,
        "backup_owner_id": people["cy"],
    }, auth)
    check("backup owner set on payments", st == 200, f"status={st}" if st != 200 else "")
    drain(auth)

    st, obj = call("GET", f"/brain/ownership/objects/project/{payments}", headers=auth)
    ok = st == 200 and obj and obj.get("primary", {}) or {}
    primary_ok = ok and obj["primary"]["owner_label"] == "Ada Draper" and \
        obj["primary"]["backup_owner_label"] == "Cy Mellon"
    check("current object read: primary + backup", bool(primary_ok),
          f"status={st} primary={obj.get('primary') if obj else None}" if not primary_ok else "")

    st, hist = call("GET", f"/brain/ownership/objects/project/{payments}/history", headers=auth)
    check("history retains assignment", st == 200 and hist and
          any(e["action"] == "assigned" for e in hist.get("events", [])),
          f"status={st}" if st != 200 else "")

    # Transfer: old window closed, new one opens; never overwritten.
    st, out = call("POST", "/brain/ownership/transfer", {
        "object_type": "project", "object_id": payments, "to_owner_id": people["bob"],
    }, auth)
    check("transfer payments -> bob", st == 200 and out and out.get("transferred"),
          f"status={st} out={out}" if not (st == 200 and out and out.get("transferred")) else "")

    st, out = call("POST", "/brain/ownership/backup", {
        "object_type": "project", "object_id": payments,
        "backup_owner_id": people["cy"],
    }, auth)
    check("backup re-declared on new tenure", st == 200, f"status={st}" if st != 200 else "")

    st, obj = call("GET", f"/brain/ownership/objects/project/{payments}", headers=auth)
    check("current owner is now bob", st == 200 and obj and
          obj["primary"]["owner_label"] == "Bob Wright", str(obj.get("primary") if obj else None))

    st, asof = call("GET",
                    f"/brain/ownership/objects/project/{payments}/as-of?at=2025-01-01T00:00:00Z",
                    headers=auth)
    check("as-of before tenure = nobody", st == 200 and asof and
          asof.get("primary") is None, str(asof if st == 200 else None))

    st, asof = call("GET",
                    f"/brain/ownership/objects/project/{payments}/as-of",
                    headers=auth)
    check("as-of now = bob", st == 200 and asof and asof.get("primary") and
          asof["primary"]["owner_label"] == "Bob Wright", str(asof if st == 200 else None))

    st, cont = call("GET", f"/brain/ownership/objects/project/{payments}/continuity", headers=auth)
    ok = st == 200 and cont
    if ok:
        check("continuity: primary + backup", cont.get("backup") and
              (cont.get("backup") or {}).get("owner_label") == "Cy Mellon", str(cont)[:220])
    else:
        check("continuity: primary + backup", False, f"status={st}")

    st, resp = call("GET", f"/brain/ownership/people/{people['bob']}/responsibilities",
                    headers=auth)
    ok = st == 200 and resp and resp.get("active")
    check("person responsibilities (bob): billing+checkout+payments",
          ok and len(resp["active"]) == 3 and all(r["owner_label"] == "Bob Wright"
                                                  for r in resp["active"]),
          str(resp.get("active") if ok else resp))

    # Arc a gap: Dee is archived; advisory analysis surfaces the gap with
    # read-only candidates - ownership itself is NOT auto-fixed.
    st, out = call("POST", f"/employees/{people['dee']}/archive",
                   {"reason": "left the company"}, auth)
    check("dee archived", st == 200, f"status={st}" if st != 200 else "")

    st, dry = call("GET", "/brain/ownership/analyze?limit=200", headers=auth)
    check("advisory dry-run is read-only", st == 200 and dry and dry.get("dry_run") is True,
          str(dry)[:200])

    st, out = call("POST", "/brain/ownership/analyze?limit=200", {}, auth)
    ok = st == 200 and out
    if not ok:
        check("bounded analyze batch", False, f"status={st}")
    else:
        check("bounded analyze batch", out.get("scanned", 0) >= 4,
              f"scanned={out.get('scanned')} gap={out.get('gap')} "
              f"single_point={out.get('single_point')} mismatch={out.get('mismatch')}")
        check("gap detected (dee's sync)", out.get("gap", 0) >= 1, str(out.get("gap")))
        check("single-point risks flagged but NOT re-assigned",
              out.get("single_point", 0) >= 1 and out.get("mismatch", 0) == 0,
              f"single={out.get('single_point')} mismatch={out.get('mismatch')}")
        # The surface must never have auto-reassigned: payments is still bob.
        st2, obj2 = call("GET", f"/brain/ownership/objects/project/{payments}", headers=auth)
        check("analysis did not mutate ownership",
              st2 == 200 and obj2["primary"]["owner_label"] == "Bob Wright",
              str(obj2.get("primary") if obj2 else None))

    st, sig = call("GET", "/brain/ownership/signals?status=open", headers=auth)
    ok = st == 200 and sig
    kinds = {s["kind"] for s in sig["signals"]} if ok else set()
    check("open signals listed", ok and "gap" in kinds and "single_point" in kinds,
          str(kinds) if ok else f"status={st}")
    gap_signal = next((s for s in sig["signals"] if s["kind"] == "gap"), None) if ok else None
    if gap_signal:
        check("gap signal is critical + honest", gap_signal["severity"] == "critical" and
              "no longer an active employee" in gap_signal["detail"], str(gap_signal)[:220])
        st, _ = call("POST", f"/brain/ownership/signals/{gap_signal['id']}/resolve", {}, auth)
        check("signal resolve (governed ack)", st == 200, f"status={st}" if st != 200 else "")
    else:
        check("gap signal is critical + honest", False, "no gap signal found")

    st, sum_ = call("GET", "/brain/ownership/summary", headers=auth)
    ok = st == 200 and sum_ and "active_relationships" in sum_
    check("ownership summary", ok, str(sum_)[:200] if st == 200 else f"status={st}")

    st, cv = call("POST", "/brain/ownership/coverage-check", {
        "objects": [{"object_type": "project", "object_id": projects["sync"],
                     "object_name": f"sync {t}"}],
    }, auth)
    check("coverage check on named objects", st == 200 and cv and "unassigned_total" in cv,
          str(cv)[:200] if st == 200 else f"status={st}")

    st, ans = call("POST", "/brain/knowledge/query",
                   {"question": "who is responsible for the Payments Platform?"}, auth)
    ok = st == 200 and ans and ans.get("intent") == "responsibility" and \
        ans.get("kind") == "ownership" and "Bob Wright is responsible for" in (ans.get("answer") or "")
    check("NL responsibility intent", ok, str(ans)[:240] if not ok else "")

    st, ans = call("POST", "/brain/knowledge/query",
                   {"question": "who takes over the Payments Platform if the owner is unavailable?"}, auth)
    ok = st == 200 and ans and ans.get("intent") == "continuity" and \
        "Cy Mellon steps in as backup" in (ans.get("answer") or "")
    check("NL continuity intent", ok, str(ans)[:240] if not ok else "")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())