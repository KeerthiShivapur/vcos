"""Phase 17 — Industry Solutions & Vertical Intelligence Platform.

Covers the universal industry core: catalog & marketplace, pack lifecycle
(select/install/enable/disable/uninstall via the Phase 15 plugin framework),
tenancy isolation, modules, templates, industry workflows (linked to the core
workflow engine), per-region compliance with org overrides, industry AI
profiles routed through the shared AI gateway, KPI analytics with benchmarks,
RBAC gating, multi-industry coexistence and Phase 17 events.
"""

import pytest

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Industry Worker", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Industry Worker", "password": "IndPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _select(client, headers, industry_key="healthcare", **overrides):
    payload = {"industry_key": industry_key, "business_type": "hospital",
               "company_size": "500-1000", "country": "US", "regulations": ["HIPAA"]}
    payload.update(overrides)
    response = await client.post("/api/v1/industry/select", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=100", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


# ------------------------------------------------------------ catalog


async def test_catalog_and_marketplace(client):
    org = await register_org(client, email="p17cat@test.co")
    headers = org["headers"]

    catalog = (await client.get("/api/v1/industry/catalog", headers=headers)).json()
    keys = {item["key"] for item in catalog}
    assert len(catalog) >= 17
    assert {"healthcare", "manufacturing", "education", "retail", "finance",
            "government", "construction", "logistics", "hospitality", "legal",
            "research", "media", "agriculture", "energy", "telecommunications",
            "nonprofit", "software"} <= keys
    healthcare = next(item for item in catalog if item["key"] == "healthcare")
    assert healthcare["installed"] is None

    detail = (await client.get("/api/v1/industry/catalog/healthcare", headers=headers)).json()
    assert any(m["key"] == "patients" for m in detail["modules"])
    assert any(w["key"] == "patient-admission" for w in detail["workflows"])
    assert any(f["framework"] == "HIPAA" for f in detail["compliance"])
    assert any(m["key"] == "healthcare-assistant" for m in detail["ai_models"])
    assert any(k["key"] == "bed_occupancy_rate" for k in detail["kpis"])

    marketplace = (await client.get("/api/v1/industry/marketplace", headers=headers)).json()
    assert len(marketplace) == 17
    assert all(item["status"] == "not_installed" for item in marketplace)

    unknown = await client.get("/api/v1/industry/catalog/nope", headers=headers)
    assert unknown.status_code == 404


# ---------------------------------------------------------- select/install


async def test_select_installs_pack_and_records_selection(client):
    org = await register_org(client, email="p17sel@test.co")
    headers = org["headers"]

    installed = await _select(client, headers)
    assert installed["installed"]["status"] == "installed"
    assert installed["installed"]["industry_key"] == "healthcare"
    assert installed["installed"]["plugin"]["scan_status"] == "clean"
    assert installed["selection"]["business_type"] == "hospital"
    assert installed["selection"]["country"] == "US"
    assert installed["selection"]["regulations"] == ["HIPAA"]
    assert installed["selection"]["status"] == "active"

    duplicate = await client.post(
        "/api/v1/industry/select",
        json={"industry_key": "healthcare"}, headers=headers,
    )
    assert duplicate.status_code == 400

    invalid_business = await client.post(
        "/api/v1/industry/select",
        json={"industry_key": "healthcare", "business_type": "spaceship"}, headers=headers,
    )
    assert invalid_business.status_code == 400

    selections = (await client.get("/api/v1/industry/selections", headers=headers)).json()
    assert len(selections) == 1
    assert selections[0]["industry_key"] == "healthcare"

    installed_list = (await client.get("/api/v1/industry/installed", headers=headers)).json()
    assert len(installed_list) == 1
    assert installed_list[0]["modules_enabled"] == [
        m["key"] for m in (await client.get("/api/v1/industry/catalog/healthcare", headers=headers)).json()["modules"]
    ]

    names = await _event_names(client, headers)
    assert "industry.pack.installed" in names
    assert "industry.enabled" in names


async def test_tenancy_isolation(client):
    org_a = await register_org(client, email="p17tena@test.co")
    org_b = await register_org(client, email="p17tenb@test.co")
    await _select(client, org_a["headers"])

    installed_b = (await client.get("/api/v1/industry/installed", headers=org_b["headers"])).json()
    assert installed_b == []
    marketplace_b = (await client.get("/api/v1/industry/marketplace", headers=org_b["headers"])).json()
    assert next(i for i in marketplace_b if i["key"] == "healthcare")["status"] == "not_installed"


async def test_multi_industry_coexistence(client):
    org = await register_org(client, email="p17multi@test.co")
    headers = org["headers"]
    await _select(client, headers, industry_key="healthcare", business_type="hospital")
    await _select(client, headers, industry_key="manufacturing", business_type="factory",
                  country="DE", regulations=["ISO 9001"])

    installed = (await client.get("/api/v1/industry/installed", headers=headers)).json()
    assert {c["industry_key"] for c in installed} == {"healthcare", "manufacturing"}
    selections = (await client.get("/api/v1/industry/selections", headers=headers)).json()
    assert len(selections) == 2


# ------------------------------------------------------ config & modules


async def test_enable_disable_and_module_toggle(client):
    org = await register_org(client, email="p17cfg@test.co")
    headers = org["headers"]
    await _select(client, headers)

    disabled = await client.patch(
        "/api/v1/industry/installed/healthcare",
        json={"enabled": False}, headers=headers,
    )
    assert disabled.json()["status"] == "disabled"

    enabled = await client.patch(
        "/api/v1/industry/installed/healthcare",
        json={"enabled": True, "country": "GB"}, headers=headers,
    )
    assert enabled.json()["status"] == "enabled"
    assert enabled.json()["settings"]["country"] == "GB"

    toggled = await client.post(
        "/api/v1/industry/installed/healthcare/modules/patients/toggle",
        json={"enabled": False}, headers=headers,
    )
    assert "patients" not in toggled.json()["modules_enabled"]

    restored = await client.post(
        "/api/v1/industry/installed/healthcare/modules/patients/toggle",
        json={"enabled": True}, headers=headers,
    )
    assert "patients" in restored.json()["modules_enabled"]

    names = await _event_names(client, headers)
    assert "industry.module.disabled" in names

    missing_pack = await client.get("/api/v1/industry/installed/nope", headers=headers)
    assert missing_pack.status_code == 404


# ------------------------------------------------------------- templates


async def test_templates_apply(client):
    org = await register_org(client, email="p17tpl@test.co")
    headers = org["headers"]
    await _select(client, headers)

    templates = (await client.get("/api/v1/industry/installed/healthcare/templates", headers=headers)).json()
    assert any(t["key"] == "patient-consent" for t in templates)
    kinds = {t["kind"] for t in templates}
    assert {"document", "dashboard", "report"} <= kinds

    applied = await client.post(
        "/api/v1/industry/installed/healthcare/templates/patient-consent/apply",
        json={}, headers=headers,
    )
    assert applied.json()["kind"] == "document"
    assert "Patient details" in applied.json()["content"]["sections"]

    names = await _event_names(client, headers)
    assert "industry.template.applied" in names


# ------------------------------------------------------------- workflows


async def test_industry_workflow_lifecycle(client):
    org = await register_org(client, email="p17wf@test.co")
    headers = org["headers"]
    await _select(client, headers)

    templates = (await client.get("/api/v1/industry/installed/healthcare/workflows/templates", headers=headers)).json()
    assert any(t["key"] == "patient-admission" for t in templates)

    activated = await client.post(
        "/api/v1/industry/installed/healthcare/workflows/activate",
        json={"template_key": "patient-admission"}, headers=headers,
    )
    assert activated.json()["status"] == "active"
    workflow_id = activated.json()["id"]
    assert len(activated.json()["steps"]) == 6
    assert activated.json()["source_workflow_id"]

    duplicate = await client.post(
        "/api/v1/industry/installed/healthcare/workflows/activate",
        json={"template_key": "patient-admission"}, headers=headers,
    )
    assert duplicate.status_code == 400

    runs = (await client.get("/api/v1/industry/installed/healthcare/workflows", headers=headers)).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "active"

    detail = (await client.get(f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}", headers=headers)).json()
    assert detail["current_step"] == "patient-registration"
    assert detail["source_workflow_id"]

    for _ in range(6):
        step = (await client.get(f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}", headers=headers)).json()
        if step["status"] == "completed":
            break
        advanced = await client.post(
            f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}/advance",
            json={}, headers=headers,
        )
        assert advanced.status_code == 200, advanced.text

    done = (await client.get(f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}", headers=headers)).json()
    assert done["status"] == "completed"
    assert done["progress"] == 100.0
    assert done["completed_at"] is not None

    names = await _event_names(client, headers)
    assert "industry.workflow.created" in names
    assert "industry.workflow.completed" in names


async def test_workflow_pause_resume_cancel(client):
    org = await register_org(client, email="p17wf2@test.co")
    headers = org["headers"]
    await _select(client, headers)

    activated = await client.post(
        "/api/v1/industry/installed/healthcare/workflows/activate",
        json={"template_key": "appointment-booking"}, headers=headers,
    )
    workflow_id = activated.json()["id"]

    paused = await client.post(
        f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}/pause", headers=headers
    )
    assert paused.json()["status"] == "paused"

    resumed = await client.post(
        f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}/resume", headers=headers
    )
    assert resumed.json()["status"] == "active"

    cancelled = await client.post(
        f"/api/v1/industry/installed/healthcare/workflows/{workflow_id}/cancel", headers=headers
    )
    assert cancelled.json()["status"] == "cancelled"


# ------------------------------------------------------------- compliance


async def test_compliance_policies_and_run(client):
    org = await register_org(client, email="p17comp@test.co")
    headers = org["headers"]
    await _select(client, headers, country="US")

    policies = (await client.get("/api/v1/industry/installed/healthcare/compliance/policies", headers=headers)).json()
    frameworks = {p["framework"] for p in policies}
    assert "HIPAA" in frameworks
    assert "Hospital Licensing" in frameworks
    assert "GDPR" not in frameworks  # EU-only rule excluded for a US org
    assert any(p["policy_key"] == "hipaa-privacy" and p["severity"] == "critical" for p in policies)

    result = await client.post(
        "/api/v1/industry/installed/healthcare/compliance/run",
        json={"auto_status": "pass"}, headers=headers,
    )
    assert result.json()["total"] == len(policies)
    assert result.json()["passed"] == len(policies)
    assert result.json()["failed"] == 0
    assert result.json()["score"] == 100.0

    checks = (await client.get("/api/v1/industry/installed/healthcare/compliance/checks", headers=headers)).json()
    assert len(checks) == len(policies)
    assert all(c["status"] == "pass" for c in checks)

    posture = (await client.get("/api/v1/industry/installed/healthcare/compliance/posture", headers=headers)).json()
    assert posture["score"] == 100.0
    assert posture["passed"] == len(policies)

    names = await _event_names(client, headers)
    assert "industry.compliance.checked" in names


async def test_compliance_partial_failure_and_overrides(client):
    org = await register_org(client, email="p17comp2@test.co")
    headers = org["headers"]
    await _select(client, headers, country="US")

    policies = (await client.get("/api/v1/industry/installed/healthcare/compliance/policies", headers=headers)).json()
    evidence = {p["policy_key"]: {"status": "pass"} for p in policies}
    evidence["hipaa-breach"] = {"status": "fail", "notes": "No incident log"}
    result = await client.post(
        "/api/v1/industry/installed/healthcare/compliance/run",
        json={"evidence": evidence}, headers=headers,
    )
    assert result.json()["passed"] == len(policies) - 1
    assert result.json()["failed"] == 1
    assert result.json()["score"] < 100.0

    # disable the failing rule via settings override
    settings = await client.patch(
        "/api/v1/industry/installed/healthcare",
        json={"settings": {"compliance_overrides": {"rules": {"hipaa-breach": {"enabled": False}}}}},
        headers=headers,
    )
    assert settings.status_code == 200

    policies_after = (await client.get("/api/v1/industry/installed/healthcare/compliance/policies", headers=headers)).json()
    assert all(p["policy_key"] != "hipaa-breach" for p in policies_after)
    assert len(policies_after) == len(policies) - 1


# ------------------------------------------------------------------- AI


async def test_industry_ai_profiles_and_chat(client):
    org = await register_org(client, email="p17ai@test.co")
    headers = org["headers"]
    await _select(client, headers)

    profiles = (await client.get("/api/v1/industry/installed/healthcare/ai/profiles", headers=headers)).json()
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile["model_key"] == "healthcare-assistant"
    assert profile["enabled"] is True
    assert "Never make diagnostic or treatment decisions" in profile["guardrails"]
    assert "summarize" in profile["skills"]

    chat = await client.post(
        "/api/v1/industry/installed/healthcare/ai/chat",
        json={"model_key": "healthcare-assistant", "question": "How is my hospital doing?"},
        headers=headers,
    )
    assert chat.json()["provider"] == "vcos"
    assert "Healthcare Operations Assistant" in chat.json()["content"]
    assert chat.json()["grounded"]["_local"] is True

    status = (await client.get("/api/v1/industry/installed/healthcare/ai/status", headers=headers)).json()
    assert status["profiles"][0]["model_key"] == "healthcare-assistant"
    assert "gateway" in status

    toggled = await client.post(
        "/api/v1/industry/installed/healthcare/ai/profiles/healthcare-assistant/toggle",
        json={"enabled": False}, headers=headers,
    )
    assert toggled.json()["enabled"] is False

    names = await _event_names(client, headers)
    assert "industry.ai.updated" in names


# -------------------------------------------------------------- analytics


async def test_industry_analytics_kpis_and_dashboard(client):
    org = await register_org(client, email="p17an@test.co")
    headers = org["headers"]
    await _select(client, headers)

    kpis = (await client.get("/api/v1/industry/installed/healthcare/analytics/kpis", headers=headers)).json()
    assert any(k["key"] == "bed_occupancy_rate" and k["benchmark"] == 80 for k in kpis)

    recorded = await client.post(
        "/api/v1/industry/installed/healthcare/analytics/record",
        json={"values": [{"metric_key": "bed_occupancy_rate", "value": 86.0},
                         {"metric_key": "no_show_rate", "value": 8.0}]},
        headers=headers,
    )
    assert recorded.json()["recorded"] == 2

    dashboard = (await client.get("/api/v1/industry/installed/healthcare/analytics/dashboard", headers=headers)).json()
    assert dashboard["tracked"] == 2
    occupancy = next(c for c in dashboard["metrics"] if c["metric_key"] == "bed_occupancy_rate")
    assert occupancy["value"] == 86.0
    assert occupancy["benchmark"] == 80
    assert occupancy["status"] == "above_benchmark"

    series = (await client.get(
        "/api/v1/industry/installed/healthcare/analytics/timeseries",
        params={"metric_key": "bed_occupancy_rate"}, headers=headers,
    )).json()
    assert len(series) == 1
    assert series[0]["value"] == 86.0

    names = await _event_names(client, headers)
    assert "industry.analytics.generated" in names


# ------------------------------------------------------------------- RBAC


async def test_industry_rbac_gating(client):
    org = await register_org(client, email="p17rbac@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p17emp@test.co", role="employee")

    catalog = await client.get("/api/v1/industry/catalog", headers=employee["headers"])
    assert catalog.status_code == 200

    select = await client.post(
        "/api/v1/industry/select",
        json={"industry_key": "healthcare"}, headers=employee["headers"],
    )
    assert select.status_code == 403

    install = await client.post(
        "/api/v1/industry/installed/healthcare/install", headers=employee["headers"]
    )
    assert install.status_code == 403

    unauthenticated = await client.get("/api/v1/industry/catalog")
    assert unauthenticated.status_code == 401


# --------------------------------------------------------------- uninstall


async def test_uninstall_pack(client):
    org = await register_org(client, email="p17uni@test.co")
    headers = org["headers"]
    await _select(client, headers)

    removed = await client.delete("/api/v1/industry/installed/healthcare", headers=headers)
    assert removed.json()["uninstalled"] is True

    installed = (await client.get("/api/v1/industry/installed", headers=headers)).json()
    assert installed[0]["status"] == "uninstalled"

    selections = (await client.get("/api/v1/industry/selections", headers=headers)).json()
    assert selections[0]["status"] == "inactive"

    reinstall = await client.post("/api/v1/industry/installed/healthcare/install", headers=headers)
    assert reinstall.json()["status"] == "installed"

    names = await _event_names(client, headers)
    assert "industry.pack.uninstalled" in names


# ------------------------------------------------------------ pack routers


async def test_industry_pack_router_surface(client):
    org = await register_org(client, email="p17pack@test.co")
    headers = org["headers"]
    await _select(client, headers)

    overview = (await client.get("/api/v1/industries/healthcare", headers=headers)).json()
    assert overview["installed"] is True
    assert overview["status"] == "installed"
    assert any(m["key"] == "patients" for m in overview["modules"])
    assert overview["selection"]["country"] == "US"

    modules = (await client.get("/api/v1/industries/healthcare/modules", headers=headers)).json()
    assert modules[0]["enabled"] is True

    compliance = (await client.get("/api/v1/industries/healthcare/compliance", headers=headers)).json()
    assert compliance["posture"] is not None
    assert any(r["framework"] == "HIPAA" for r in compliance["rules"])

    ai = (await client.get("/api/v1/industries/healthcare/ai", headers=headers)).json()
    assert ai["profiles"][0]["model_key"] == "healthcare-assistant"

    analytics = (await client.get("/api/v1/industries/healthcare/analytics", headers=headers)).json()
    assert "metrics" in analytics

    chat = await client.post(
        "/api/v1/industries/healthcare/ai/chat",
        json={"question": "Summarize operations"}, headers=headers,
    )
    assert chat.json()["provider"] == "vcos"


# ----------------------------------------------------------- event catalog


async def test_industry_events_are_catalogued(client):
    from app.events.event_models import EVENT_CATALOG

    required = {
        "industry.enabled", "industry.pack.installed", "industry.pack.updated",
        "industry.pack.uninstalled", "industry.pack.disabled",
        "industry.module.enabled", "industry.module.disabled",
        "industry.template.applied", "industry.ai.updated",
        "industry.workflow.created", "industry.workflow.completed",
        "industry.compliance.checked", "industry.analytics.generated",
    }
    assert required <= set(EVENT_CATALOG)


# ------------------------------------------------------------- permissions


async def test_industry_permissions_registered(client):
    from app.services.permission_service import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS

    codes = {p[0] for p in PERMISSIONS}
    assert {"industry:read", "industry:manage"} <= codes
    assert "industry:read" in DEFAULT_ROLE_PERMISSIONS["employee"]
    assert {"industry:read", "industry:manage"} <= set(DEFAULT_ROLE_PERMISSIONS["ceo"])
