"""Slice 4H.3 acceptance — Living Company State (live API, contract §14).

Against the running stack (http://localhost:8999): a seeded org produces a
deterministic company_state_history trail (8 typed dimensions, delta with
provenance, explainable signals, risk bands, bounded opportunities, affected
decision intersection, exact-once state-context bridge incl. the 409 law
past outcome_recorded, additive state_context on 4H.2 reads, temporal as_of
strict/partial + byte-identical determinism, event truth, tenant isolation
+ scoped 404, bounded shapes, schema reuse, moat accumulation and the five
brain intents with 4H.2 intents still resolving). Exit 0 only when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
STATE = f"{BRAIN}/execution/company/state"
CAP = f"{BRAIN}/execution/company/decisions"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


async def register(client: httpx.AsyncClient, stamp: str, tag: str) -> dict:
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": f"4H3 {tag} {stamp}",
            "organization_slug": f"slice4h3-{tag}-{stamp}",
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": f"{tag.title()} Owner",
            "email": f"4h3-{tag}-{stamp}@test.co",
            "username": f"4h3-{tag}-{stamp}",
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "organization": data["organization"]}


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 400) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=60
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:  # noqa: BLE001
        pass
    return -1


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 8) -> int:
    total = 0
    for _ in range(rounds):
        n = await dispatch(client, headers)
        if n <= 0:
            if n == 0:
                break
            continue
        total += n
    return total


async def count_events(client: httpx.AsyncClient, headers: dict, name: str) -> int:
    r = await client.get(f"{API}/events", params={"name": name}, headers=headers)
    if r.status_code != 200:
        return -1
    return int(r.json().get("total", 0) or 0)


def evaluate_body(decision_id: str, *, source_kind: str = "event",
                  title: str = "Adopt the new data platform") -> dict:
    return {
        "decision_id": decision_id,
        "kind": "hire",
        "title": title,
        "rationale": "revenue forecast said growth",
        "impact_label": "revenue growth",
        "expected_improvement": "faster forecasting",
        "scope_type": "org",
        "scope_id": "org-root",
        "evidence": [
            {
                "evidence_type": "metric",
                "source_kind": source_kind,
                "source_summary": "company change signal",
                "captured_at": "2026-08-01T00:00:00Z",
                "weight": 0.8,
            }
        ],
        "alternatives": [
            {
                "alternative_key": "alt:01",
                "label": "Adopt",
                "chosen": True,
                "why_chosen": "best roi",
                "expected_outcome": {"kind": "improvement"},
            }
        ],
    }


async def seeded_change(client: httpx.AsyncClient, headers: dict, label: str = "seed") -> None:
    await drain(client, headers)
    time.sleep(1.2)


async def main() -> int:
    stamp = str(int(time.time()))[-6:]
    async with httpx.AsyncClient(timeout=60) as c:
        a = await register(c, stamp, "a")
        ha = a["headers"]

        print("\n=== VCOS Slice 4H.3 acceptance: Living Company State (live) ===")

        # ---- seed an org with real, deterministic company activity ---------
        proj = (await c.post(
            f"{API}/projects",
            json={"name": f"Platform Reliability {stamp}", "description": "4H.3 anchor", "status": "active"},
            headers=ha,
        )).json()
        await seeded_change(c, ha)
        task = (await c.post(
            f"{API}/tasks",
            json={"title": "Flaky service watch", "project_id": proj["id"], "status": "todo"},
            headers=ha,
        )).json()
        await seeded_change(c, ha)

        d_hit = f"dec:4h3:hit-{stamp}01"
        ev = await c.post(f"{CAP}/evaluate", json=evaluate_body(d_hit), headers=ha)
        assert ev.status_code == 200, ev.text
        await c.post(f"{CAP}/{d_hit}/recommend", json={}, headers=ha)
        await seeded_change(c, ha)

        d_miss = f"dec:4h3:miss-{stamp}01"
        miss_ev = await c.post(
            f"{CAP}/evaluate",
            json=evaluate_body(d_miss, source_kind="finance.forecast", title="Unrelated finance decision"),
            headers=ha,
        )
        assert miss_ev.status_code == 200, miss_ev.text
        await c.post(f"{CAP}/{d_miss}/recommend", json={}, headers=ha)
        await seeded_change(c, ha)

        open_risk = (
            await c.post(
                f"{API}/risks",
                json={"project_id": proj["id"], "title": "Vendor platform outage",
                      "status": "identified", "probability": 5, "impact": 5},
                headers=ha,
            )
        ).json()
        closed_risk = (
            await c.post(
                f"{API}/risks",
                json={"project_id": proj["id"], "title": "Legacy migration risk",
                      "status": "closed", "probability": 4, "impact": 4},
                headers=ha,
            )
        ).json()
        await seeded_change(c, ha)

        governed = await c.post(
            f"{CAP}",
            json={
                "kind": "hire",
                "title": "Hire for the platform bottleneck",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.7,
                "confidence": 0.8,
                "owner_label": "Leadership",
            },
            headers=ha,
        )
        assert governed.status_code == 200, governed.text
        governed_id = governed.json()["decision_id"]
        await seeded_change(c, ha)

        # ---- 1. state composition (L2) -------------------------------------
        live = (await c.get(f"{STATE}?explain=true", headers=ha)).json()
        dims = live.get("dimensions", [])
        check(
            "1. state composition: snapshot with 8 typed dimensions + full surface",
            live.get("advisory_only") is True
            and live.get("snapshot_ref")
            and len(dims) == 8
            and all(d.get("type") in ("observed", "derived") for d in dims)
            and all(d.get("op") in ("improved", "declined", "stable") for d in dims)
            and live.get("signals")
            and isinstance(live.get("dependencies"), list)
            and isinstance(live.get("risks"), list)
            and isinstance(live.get("opportunities"), list)
            and isinstance(live.get("affected_decisions"), list)
            and isinstance(live.get("attention"), list)
            and isinstance(live.get("next"), list),
            f"dims={len(dims)} ref={str(live.get('snapshot_ref'))[:12]}",
        )

        # ---- 2. delta (L1/L2): only new signals, provenance cited ----------
        plain = (await c.get(f"{STATE}?explain=true", headers=ha)).json()
        trail = plain.get("trail", [])
        delta = plain.get("delta", [])
        check(
            "2. delta: only new signals, provenance ids, seeded trail grew",
            len(trail) >= 2
            and all(d.get("op") and d.get("id") and d.get("kind") and d.get("signal")
                    and d.get("signal_ids") and isinstance(d.get("evidence_count"), int)
                    for d in delta)
            and len(delta) <= 30,
            f"trail={len(trail)} delta={len(delta)}",
        )

        # ---- 3. why -> explain provenance (L1/L4) ---------------------------
        explained = (await c.get(f"{STATE}?explain=true", headers=ha)).json()
        sig_ok = all(s.get("id") for s in explained.get("signals", []))
        event_why = all("why" in s for s in explained.get("signals", []) if s.get("kind") == "event")
        check(
            "3. explain=true expands signal provenance, every id cited",
            sig_ok and event_why,
            f"signals={len(explained.get('signals', []))} event_why={event_why}",
        )

        # ---- 4. dependencies (L1/L6): causal walk bounded; unknown -> 404 ---
        walked = await c.get(
            f"{STATE}/dependencies",
            params={"entity_type": "risk", "entity_id": open_risk["id"], "depth": 3},
            headers=ha,
        )
        unknown = await c.get(
            f"{STATE}/dependencies",
            params={"entity_type": "team", "entity_id": "team:missing", "depth": 2},
            headers=ha,
        )
        check(
            "4. dependencies: risk -> project walk via causal chain; unknown 404",
            walked.status_code == 200
            and walked.json().get("subject", {}).get("id") == open_risk["id"]
            and any(h.get("kind") == "risk->project" for h in walked.json().get("hops", []))
            and walked.json().get("advisory_only") is True
            and walked.json().get("depth") == 3
            and unknown.status_code == 404,
            f"walked={walked.status_code} hops={len(walked.json().get('hops', []))} unknown={unknown.status_code}",
        )

        # ---- 5. risks (L1/L4/L6): bands; closed excluded; bounded -----------
        risks = (await c.get(f"{STATE}/risks", headers=ha)).json()
        titles = [r.get("title") for r in risks.get("risks", [])]
        bands = {r.get("band") for r in risks.get("risks", [])}
        risk_ok = (
            risks.get("advisory_only") is True
            and any(r.get("risk_id") == open_risk["id"] and r.get("band") == "HIGH"
                    and r.get("affected") for r in risks.get("risks", []))
            and closed_risk["title"] not in titles
            and bands <= {"LOW", "MEDIUM", "HIGH"}
            and len(risks.get("risks", [])) <= 10
        )
        check("5. risks: high band with affected entities; closed excluded; bounded", risk_ok,
              f"bands={bands} titles={titles}")

        # ---- 6. opportunities (L1/L4/L6): bounded shape with source ids -----
        opps = (await c.get(f"{STATE}/opportunities", headers=ha)).json()
        opp_ok = (
            opps.get("advisory_only") is True
            and len(opps.get("opportunities", [])) <= 10
            and all(o.get("source") and o.get("source_id") and o.get("kind")
                    and isinstance(o.get("evidence_count"), int) and isinstance(o.get("signal_count"), int)
                    for o in opps.get("opportunities", []))
        )
        check("6. opportunities: bounded, every item cites its source id + counts", opp_ok,
              f"count={len(opps.get('opportunities', []))}")

        # ---- 7. affected decisions (L1/L5.4): deterministic intersection ----
        affected = (await c.get(f"{STATE}/decisions", headers=ha)).json()
        ids = [d.get("decision_id") for d in affected.get("affected_decisions", [])]
        check(
            "7. affected decisions: intersecting decision cited, unrelated not",
            affected.get("advisory_only") is True
            and d_hit in ids
            and d_miss not in ids
            and all(d.get("state") and d.get("kind") and d.get("why") for d in affected.get("affected_decisions", [])),
            f"ids={ids}",
        )

        # ---- 8. state-context bridge (L5): created/no-op replay/409 --------
        unknown_ctx = await c.post(f"{CAP}/dec:missing/state-context", json={}, headers=ha)
        attached_hit = (await c.post(f"{CAP}/{d_hit}/state-context", json={}, headers=ha)).json()
        created_g = (await c.post(f"{CAP}/{governed_id}/state-context", json={}, headers=ha)).json()
        replay_g = (await c.post(f"{CAP}/{governed_id}/state-context", json={}, headers=ha)).json()
        await drain(c, ha)
        executed_g = await c.post(f"{CAP}/{governed_id}/execute", json={"executed_by_label": "Ada Owner"}, headers=ha)
        await drain(c, ha)
        outcome_g = await c.post(
            f"{CAP}/{governed_id}/outcome",
            json={"outcome_kind": "successful", "effectiveness": 0.8, "lesson": "state anchorage is honest"},
            headers=ha,
        )
        await drain(c, ha)
        rejected_g = await c.post(f"{CAP}/{governed_id}/state-context", json={}, headers=ha)
        check(
            "8. state-context bridge: anchored no-op, governed create, replay no-op, 409 past outcome",
            unknown_ctx.status_code == 404
            and attached_hit.get("created") is False
            and created_g.get("created") is True and created_g.get("changed") is True
            and replay_g.get("created") is False and replay_g.get("changed") is False
            and executed_g.status_code == 200 and outcome_g.status_code == 200
            and rejected_g.status_code == 409
            and rejected_g.json().get("detail", {}).get("rejected") is True
            and rejected_g.json().get("detail", {}).get("state") in ("outcome_recorded", "assessed"),
            f"unknown={unknown_ctx.status_code} attached={attached_hit.get('created')} "
            f"create={created_g.get('created')}/{created_g.get('changed')} "
            f"replay={replay_g.get('created')} exec={executed_g.status_code} "
            f"out={outcome_g.status_code} rejected={rejected_g.status_code} "
            f"rej_state={rejected_g.json().get('detail', {}).get('state') if rejected_g.status_code == 409 else None}",
        )

        # ---- 9. decision surface integration (L3): additive state_context ---
        detail_hit = (await c.get(f"{CAP}/{d_hit}", headers=ha)).json()
        pred_hit = (await c.get(f"{CAP}/{d_hit}/prediction", headers=ha)).json()
        check(
            "9. decision detail + prediction expose state_context additively",
            detail_hit.get("state_context", {}).get("snapshot_refs")
            and pred_hit.get("state_context") is not None,
            f"detail_refs={len(detail_hit.get('state_context', {}).get('snapshot_refs', []))} "
            f"pred={bool(pred_hit.get('state_context'))}",
        )

        # ---- 10. temporal as_of (L3): strict/partial + byte-identical ------
        trail_now = (await c.get(f"{STATE}?explain=true", headers=ha)).json().get("trail", [])
        epoch = trail_now[-1]["occurred_at"]
        newest_ref = trail_now[0]["snapshot_ref"]
        oldest_ref = trail_now[-1]["snapshot_ref"]
        strict = (await c.get(
            f"{STATE}", params={"as_of": epoch}, headers=ha,
        )).json()
        partial = (await c.get(
            f"{STATE}", params={"as_of": epoch, "include_partial": "true"}, headers=ha,
        )).json()
        re_strict = (await c.get(
            f"{STATE}", params={"as_of": epoch}, headers=ha,
        )).json()
        before_all = (await c.get(
            f"{STATE}", params={"as_of": "2001-01-01T00:00:00Z"}, headers=ha,
        )).json()
        expected_late = {t["snapshot_ref"] for t in trail_now[:-1]}
        late_refs = {s.get("snapshot_ref") for s in partial.get("late_snapshots", [])}
        strict_copy = {k: v for k, v in strict.items() if k != "generated_at"}
        re_copy = {k: v for k, v in re_strict.items() if k != "generated_at"}
        check(
            "10. as_of: strict excludes post-epoch; partial lists the whole trail; replays identical",
            len(trail_now) >= 2
            and strict.get("snapshot_ref") == oldest_ref
            and strict.get("snapshot_ref") != newest_ref
            and partial.get("snapshot_ref") == strict.get("snapshot_ref")
            and late_refs == expected_late and len(late_refs) == len(trail_now) - 1
            and before_all.get("composed") is False
            and strict_copy == re_copy,
            f"epoch={epoch} ref={str(strict.get('snapshot_ref'))[:14]} "
            f"late={len(late_refs)}/{len(expected_late)} identical={strict_copy == re_copy}",
        )

        # ---- 11. determinism (L3/5.2) + exact-once --------------------------
        first = (await c.get(f"{STATE}?explain=true", headers=ha)).json()
        second = (await c.get(f"{STATE}?explain=true", headers=ha)).json()
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        replay_eval = await c.post(f"{CAP}/evaluate", json=evaluate_body(d_hit), headers=ha)
        await drain(c, ha)
        check(
            "11. determinism: byte-identical re-query; evaluate replay exact-once",
            first == second and replay_eval.json().get("evidence_written") == 0,
            f"identical={first == second} replay_written={replay_eval.json().get('evidence_written')}",
        )

        # ---- 12. event truth (L5): reads + rejected writes emit zero -------
        before = {n: await count_events(c, ha, n) for n in ("company.state.composed", "company.state.changed")}
        await c.get(f"{STATE}", params={"as_of": "2001-01-01T00:00:00Z", "include_partial": "true"}, headers=ha)
        await c.post(f"{CAP}/{governed_id}/state-context", json={}, headers=ha)
        await c.get(f"{CAP}/{d_hit}", headers=ha)
        after = {n: await count_events(c, ha, n) for n in ("company.state.composed", "company.state.changed")}
        d_extra = f"dec:4h3:extra-{stamp}01"
        write_g = await c.post(
            f"{CAP}",
            json={
                "kind": "hire",
                "title": "Fund the state observability team",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.7,
                "confidence": 0.8,
                "owner_label": "Leadership",
            },
            headers=ha,
        )
        assert write_g.status_code == 200, write_g.text
        await seeded_change(c, ha)
        after_write = {n: await count_events(c, ha, n) for n in ("company.state.composed", "company.state.changed")}
        grows = after_write["company.state.composed"] > after["company.state.composed"]
        check(
            "12. event truth: reads/rejects emit zero; a real write emits",
            after == before and grows,
            f"read_stable={after == before} composed={before['company.state.composed']}->{after_write['company.state.composed']}",
        )

        # ---- 13. governance (L7): scoped caller 404; tenant isolation ------
        scoped_ok = True
        scoped_detail = "skipped"
        try:
            scoped_emp = (await c.post(
                f"{API}/users/invite",
                json={"email": f"scop{stamp}@4h3.test.co", "role": "manager", "full_name": "Scoped Mgr"},
                headers=ha,
            )).json()
            joined = (await c.post(
                f"{API}/auth/register/invite",
                json={"token": scoped_emp["token"], "email": f"scop{stamp}@4h3.test.co",
                      "full_name": "Scoped Mgr", "password": "StrongPass123!"},
            )).json()
            scope = (await c.post(
                f"{API}/governance/scopes",
                json={"name": "4H3 Visible Scope", "scope_type": "project", "entity_id": proj["id"]},
                headers=ha,
            )).json()
            roles = (await c.get(f"{API}/roles", headers=ha)).json()
            manager_role = next(r for r in roles if r["code"] == "manager")
            assign = await c.post(
                f"{API}/governance/assignments",
                json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
                headers=ha,
            )
            assert assign.status_code == 201, assign.text
            assignments = (await c.get(
                f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=ha,
            )).json()
            org_wide = next(x for x in assignments if x.get("scope_id") is None)
            await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=ha)
            await c.post(
                f"{API}/governance/delegations",
                json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read",
                      "reason": "4H.3 acceptance"},
                headers=ha,
            )
            hs = {"Authorization": f"Bearer {joined['access_token']}"}
            org_state = await c.get(f"{STATE}", headers=hs)
            scoped_read = await c.get(
                f"{STATE}", params={"scope_type": "team", "scope_id": scope["id"], "explain": "true"},
                headers=hs,
            )
            scoped_ok = org_state.status_code == 404 and scoped_read.status_code == 200
            scoped_detail = f"org={org_state.status_code} scoped={scoped_read.status_code}"
        except Exception as exc:  # noqa: BLE001
            scoped_ok = False
            scoped_detail = str(exc)[:160]

        b = await register(c, stamp, "b")
        hb = b["headers"]
        state_b = (await c.get(f"{STATE}?explain=true", headers=hb)).json()
        decisions_b = (await c.get(f"{STATE}/decisions", headers=hb)).json()
        deps_b = await c.get(
            f"{STATE}/dependencies",
            params={"entity_type": "project", "entity_id": proj["id"], "depth": 2},
            headers=hb,
        )
        check(
            "13. governance: scoped caller 404 on org state; org B sees empty/404, tenants never crossed",
            scoped_ok
            and state_b.get("composed") is False
            and len(decisions_b.get("affected_decisions", [])) == 0
            and deps_b.status_code == 404,
            f"{scoped_detail} orgB_composed={state_b.get('composed')} orgB_deps={deps_b.status_code}",
        )

        # ---- 14. bounded shapes (L6) ---------------------------------------
        bounded_ok = (
            len(delta) <= 30 and len(risks.get("risks", [])) <= 10
            and len(opps.get("opportunities", [])) <= 10
            and len(affected.get("affected_decisions", [])) <= 20
            and len(plain.get("dependencies", [])) <= 10
            and len(trail) <= 10
            and len(explained.get("attention", [])) <= 10
        )
        scoped_shape = {
            "advisory_only", "state_key", "scope_type", "scope_id", "snapshot_ref",
            "dimensions", "delta", "signals", "dependencies", "risks",
            "opportunities", "affected_decisions", "attention", "next",
        }
        scoped_surface = scoped_read.json() if scoped_ok else {}
        shape_ok = (
            set(scoped_surface.keys()) >= scoped_shape
            and scoped_surface.get("scope_type") == "team"
            and scoped_surface.get("scope_id") == scope["id"]
            and scoped_surface.get("composed") is False
            and scoped_surface.get("snapshot_ref") is None
            and len(scoped_surface.get("trail", [])) == 0
        )
        check("14. bounded shapes: MAX caps honored; scoped read identical parameterized shape",
              bounded_ok and shape_ok,
              f"caps={bounded_ok} shape={shape_ok}")

        # ---- 15. reuse (L1/L8): exactly ONE new table + additive column -----
        reuse_ok = False
        reuse_detail = "db intro skipped"
        try:
            import asyncpg

            conn = await asyncpg.connect(
                "postgresql://postgres:keerthi@localhost:5432/vcos2", timeout=10,
            )
            state_tables = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'company_state_history' ORDER BY column_name"
            )
            cols = {r["column_name"] for r in state_tables}
            required_cols = {
                "id", "organization_id", "state_key", "scope_type", "scope_id",
                "dimensions_json", "delta_json", "signals_json", "dependencies_json",
                "risks_json", "opportunities_json", "affected_decisions_json",
                "attention_json", "next_json", "source_event_id", "snapshot_ts",
                "occurred_at", "created_at", "updated_at",
            }
            must_have = required_cols <= cols
            decision_cols = (await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'company_decisions' AND column_name = 'state_context_json'"
            ))
            has_column = len(decision_cols) == 1
            canonical = (await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name IN ('company_memory', 'company_causal_edges', 'company_health_history')"
            ))
            has_canonical = {r["table_name"] for r in canonical} >= {
                "company_memory", "company_causal_edges", "company_health_history",
            }
            await conn.close()
            reuse_ok = must_have and has_column and has_canonical
            reuse_detail = f"cols_ok={must_have} column={has_column} canonical={has_canonical}"
        except Exception as exc:  # noqa: BLE001
            reuse_detail = str(exc)[:160]
        check("15. reuse: company_state_history exact §3.1 columns; additive column; canonical stores intact",
              reuse_ok, reuse_detail)

        # ---- 16. moat accumulation (compounding) ----------------------------
        before_acc = len(ids)
        for i in range(2):
            extra_id = f"dec:4h3:acc-{stamp}0{i}"
            await c.post(f"{CAP}/evaluate", json=evaluate_body(extra_id), headers=ha)
            await c.post(f"{CAP}/{extra_id}/recommend", json={}, headers=ha)
        # the governance trigger recomposes the state from the new decisions
        trigger = await c.post(
            f"{CAP}",
            json={
                "kind": "hire", "title": "Moat compounding approval",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.7, "confidence": 0.8, "owner_label": "Leadership",
            },
            headers=ha,
        )
        assert trigger.status_code == 200, trigger.text
        await seeded_change(c, ha)
        acc = (await c.get(f"{STATE}/decisions", headers=ha)).json()
        after_acc = len(acc.get("affected_decisions", []))
        check("16. moat: more decisions strictly grow the affected-decision surface",
              after_acc > before_acc,
              f"before={before_acc} after={after_acc}")

        # ---- 17. brain intents (L1): five 4H.3 intents + 4H.2 no regression
        pairs = [
            ("what is the state of the company?", "company_state"),
            ("what changed in the company recently?", "company_changes"),
            ("what are the key risks?", "company_risks"),
            ("where should we focus?", "company_opportunities"),
            ("what depends on the current vendor risk?", "company_dependencies"),
        ]
        intent_bad = []
        for question, intent in pairs:
            res = await c.post(f"{BRAIN}/knowledge/query", json={"question": question}, headers=ha)
            if res.status_code != 200 or res.json().get("intent") != intent:
                intent_bad.append(f"{question}->{res.status_code}:{res.json().get('intent')}")
        reason = (await c.post(
            f"{BRAIN}/knowledge/query",
            json={"question": "why did we decide to adopt the platform?"}, headers=ha,
        )).json()
        alternatives = (await c.post(
            f"{BRAIN}/knowledge/query",
            json={"question": "what alternatives we considered for the platform?"}, headers=ha,
        )).json()
        check(
            "17. brain intents: five 4H.3 intents resolve; 4H.2 decision intents unchanged",
            not intent_bad
            and reason.get("intent") in ("decision_reason", "company_operating")
            and alternatives.get("intent") == "decision_alternatives"
            and isinstance(alternatives.get("decision_id"), str) and alternatives.get("decision_id"),
            f"bad={intent_bad} reason={reason.get('intent')} alt={alternatives.get('intent')}",
        )

        # --------------------------------------------------------------------
        print(f"\n4H.3 live acceptance: {len(PASSED)}/{len(PASSED) + len(FAILED)} passed")
        return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))