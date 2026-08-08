"""Phase 12 — Customers, CRM & External Relationship Operating System (CROS).

Covers the full external lifecycle: customer foundation (CRUD, tags, notes,
addresses, relationships, timeline, links), contacts, leads with AI scoring,
opportunity pipeline with win probability, contracts with approval/sign/
renewals, support with SLA tracking, partners & vendors, account teams,
customer portal with hard customer isolation, health engine, analytics,
relationship intelligence, the AI customer companion, RBAC gating,
multi-tenant isolation, search integration and the Phase 12 workers.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _create_customer(client, headers, name="Nova Labs", **overrides):
    payload = {
        "company_name": name,
        "status": "customer",
        "segment": "mid_market",
        "tier": "gold",
        "industry": "software",
        "country": "US",
        "timezone": "UTC",
        "employee_count": 120,
        "source": "referral",
        "annual_value": 85000,
        "notes": "Key growth account",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/customers", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ============================================================== customer foundation

@pytest.mark.asyncio
async def test_customer_lifecycle(client):
    org = await register_org(client, email="p12cust@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers)

    listed = await client.get("/api/v1/customers", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == customer_id for item in listed.json())

    detail = await client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["company_name"] == "Nova Labs"
    assert body["status"] == "customer"
    assert body["tier"] == "gold"
    assert len(body["notes"]) == 1
    assert body["note_count"] == 1

    updated = await client.patch(
        f"/api/v1/customers/{customer_id}", json={"status": "inactive", "tier": "platinum"}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "inactive"

    tag = await client.post(
        f"/api/v1/customers/{customer_id}/tags", json={"name": "strategic", "color": "green"}, headers=headers)
    assert tag.status_code == 200, tag.text
    tags = (await client.get("/api/v1/customers", headers=headers, params={"tag": "strategic"})).json()
    assert any(item["id"] == customer_id for item in tags)
    assert "strategic" in (await client.get(f"/api/v1/customers/{customer_id}", headers=headers)).json()["tags"]

    note = await client.post(
        f"/api/v1/customers/{customer_id}/notes",
        json={"content": "Renewal conversation scheduled", "kind": "meeting"}, headers=headers)
    assert note.status_code == 200, note.text

    address = await client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json={"kind": "headquarters", "city": "Berlin", "country": "DE", "is_primary": True}, headers=headers)
    assert address.status_code == 200, address.text
    assert len((await client.get(f"/api/v1/customers/{customer_id}/addresses", headers=headers)).json()) == 1

    rel = await client.post(
        f"/api/v1/customers/{customer_id}/relationships",
        json={"relation_type": "partner", "name": "CloudCo", "status": "active"}, headers=headers)
    assert rel.status_code == 200, rel.text
    assert len((await client.get(f"/api/v1/customers/{customer_id}/relationships", headers=headers)).json()) == 1

    timeline = await client.post(
        f"/api/v1/customers/{customer_id}/timeline",
        json={"event": "executive.sponsor", "title": "Exec sponsor visit", "detail": "QBR held"}, headers=headers)
    assert timeline.status_code == 200, timeline.text
    entries = (await client.get(f"/api/v1/customers/{customer_id}/timeline", headers=headers)).json()
    assert len(entries) >= 4
    assert any(entry["event"] == "customer.created" for entry in entries)

    events = (await client.get("/api/v1/events", headers=headers, params={"name": "customer.created", "page_size": 50})).json()
    assert any(item.get("name") == "customer.created" for item in events.get("items", events))

    deleted = await client.delete(f"/api/v1/customers/{customer_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(f"/api/v1/customers/{customer_id}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_customer_links_and_team(client):
    org = await register_org(client, email="p12links@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="LinkCorp")
    employee_id = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Nova implementation", "description": "Rollout", "owner_id": employee_id},
        headers=headers,
    )
    assert project.status_code in (200, 201), project.text
    project_id = project.json()["id"]

    link = await client.post(
        f"/api/v1/customers/{customer_id}/projects/{project_id}",
        json={"kind": "implementation"}, headers=headers)
    assert link.status_code == 200, link.text

    meeting = await client.post(
        "/api/v1/meetings",
        json={"title": "QBR with LinkCorp", "scheduled_at": "2026-09-01T10:00:00", "duration_minutes": 60},
        headers=headers,
    )
    assert meeting.status_code in (200, 201), meeting.text
    meeting_id = meeting.json().get("id") or meeting.json().get("meeting_id")
    assert meeting_id

    mlink = await client.post(
        f"/api/v1/customers/{customer_id}/meetings/{meeting_id}", json={"kind": "review"}, headers=headers)
    assert mlink.status_code == 200, mlink.text

    detail = (await client.get(f"/api/v1/customers/{customer_id}", headers=headers)).json()
    assert detail["project_count"] >= 1
    assert detail["meeting_count"] >= 1
    assert detail["last_activity_at"]

    member = await client.post(
        f"/api/v1/accounts/{customer_id}/team",
        json={"employee_id": employee_id, "role": "account_manager", "is_primary": True}, headers=headers)
    assert member.status_code == 200, member.text
    team = (await client.get(f"/api/v1/accounts/{customer_id}/team", headers=headers)).json()
    assert any(item["role"] == "account_manager" and item["is_primary"] for item in team)

    unlink = await client.delete(f"/api/v1/customers/{customer_id}/projects/{project_id}", headers=headers)
    assert unlink.status_code == 200, unlink.text


# ============================================================== contacts

@pytest.mark.asyncio
async def test_contacts(client):
    org = await register_org(client, email="p12contacts@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="ContactCo")

    contact = await client.post(
        "/api/v1/contacts",
        json={"customer_id": customer_id, "name": "Jane Doe", "role": "cto",
              "email": "jane@contactco.test", "decision_maker": True, "is_primary": True},
        headers=headers)
    assert contact.status_code == 200, contact.text
    contact_id = contact.json()["id"]

    contact = await client.post(
        "/api/v1/contacts",
        json={"customer_id": customer_id, "name": "Bob Lee", "role": "finance", "email": "bob@contactco.test"},
        headers=headers)
    assert contact.status_code == 200, contact.text

    by_customer = (await client.get(
        "/api/v1/contacts", headers=headers, params={"customer_id": customer_id})).json()
    assert len(by_customer) == 2
    assert by_customer[0]["is_primary"] is True

    all_contacts = (await client.get(
        "/api/v1/contacts", headers=headers, params={"decision_maker": "true"})).json()
    assert len(all_contacts) == 1
    assert all_contacts[0]["customer_name"] == "ContactCo"

    updated = await client.patch(
        f"/api/v1/contacts/{contact_id}", json={"designation": "Chief Technology Officer"}, headers=headers)
    assert updated.status_code == 200, updated.text

    assert (await client.delete(f"/api/v1/contacts/{contact_id}", headers=headers)).status_code == 200


# ============================================================== leads

@pytest.mark.asyncio
async def test_lead_scoring_and_duplicates(client):
    org = await register_org(client, email="p12lead@test.co")
    headers = org["headers"]

    lead = await client.post(
        "/api/v1/leads",
        json={"company_name": "BigEnterprise Inc", "contact_name": "Alice", "contact_email": "alice@be.test",
              "industry": "software", "employee_count": 2000, "needs": "urgent rollout",
              "source": "referral", "expected_value": 150000},
        headers=headers)
    assert lead.status_code == 200, lead.text
    body = lead.json()
    assert body["score"] >= 75
    assert body["duplicate_of"] is None

    dup = await client.post(
        "/api/v1/leads",
        json={"company_name": "BIGENTERPRISE INC", "contact_name": "Mallory", "contact_email": "mallory@other.test"},
        headers=headers)
    assert dup.status_code == 200, dup.text
    assert dup.json()["duplicate_of"] == body["id"]

    activity = await client.post(
        f"/api/v1/leads/{body['id']}/activities",
        json={"kind": "called", "content": "Intro call done"}, headers=headers)
    assert activity.status_code == 200, activity.text
    assert len((await client.get(f"/api/v1/leads/{body['id']}/activities", headers=headers)).json()) >= 2

    qualified = await client.patch(
        f"/api/v1/leads/{body['id']}", json={"status": "qualified", "note": "Budget approved"}, headers=headers)
    assert qualified.status_code == 200, qualified.text
    assert qualified.json()["status"] == "qualified"

    listed = (await client.get("/api/v1/leads", headers=headers, params={"status": "qualified"})).json()
    assert any(item["id"] == body["id"] for item in listed)
    assert listed[0]["priority"] == "high"


# ============================================================== opportunities

@pytest.mark.asyncio
async def test_opportunity_pipeline_and_close_won(client):
    org = await register_org(client, email="p12opp@test.co")
    headers = org["headers"]

    lead_response = await client.post(
        "/api/v1/leads",
        json={"company_name": "DealCorp", "contact_name": "Carol", "contact_email": "carol@dealcorp.test",
              "industry": "fintech", "employee_count": 300, "needs": "platform", "expected_value": 200000},
        headers=headers)
    assert lead_response.status_code == 200, lead_response.text
    lead = lead_response.json()

    opp = await client.post(
        "/api/v1/opportunities",
        json={"lead_id": lead["id"], "title": "DealCorp platform expansion",
              "stage": "proposal", "value": 200000, "expected_close_date": "2026-12-15T00:00:00"},
        headers=headers)
    assert opp.status_code == 200, opp.text
    opp_id = opp.json()["id"]

    pipeline = (await client.get("/api/v1/opportunities/pipeline", headers=headers)).json()
    assert pipeline["stages"]["proposal"]["count"] == 1
    assert pipeline["open_value"] == 200000
    assert pipeline["weighted_value"] > 0

    moved = await client.patch(
        f"/api/v1/opportunities/{opp_id}", json={"stage": "negotiation", "note": "Terms aligned"}, headers=headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["stage"] == "negotiation"
    assert moved.json()["probability"] >= 60

    won = await client.post(
        f"/api/v1/opportunities/{opp_id}/won",
        json={"note": "Signed after final review", "customer_data": {"industry": "fintech", "country": "UK"}},
        headers=headers)
    assert won.status_code == 200, won.text
    assert won.json()["stage"] == "won"
    customer_id = won.json()["customer_id"]
    assert customer_id

    customer = (await client.get(f"/api/v1/customers/{customer_id}", headers=headers)).json()
    assert customer["company_name"] == "DealCorp"
    assert customer["status"] == "customer"
    assert customer["annual_value"] == 200000
    assert customer["contact_count"] >= 1

    lead_detail = (await client.get(f"/api/v1/leads/{lead['id']}", headers=headers)).json()
    assert lead_detail["status"] == "converted"

    pipeline = (await client.get("/api/v1/opportunities/pipeline", headers=headers)).json()
    assert pipeline["won"] == 1
    assert pipeline["win_rate"] == 100.0

    lost = await client.post(
        "/api/v1/opportunities",
        json={"title": "LostDeal project", "value": 50000, "stage": "qualified"}, headers=headers)
    assert lost.status_code == 200, lost.text
    lost_result = await client.post(
        f"/api/v1/opportunities/{lost.json()['id']}/lost", json={"reason": "Chose competitor"}, headers=headers)
    assert lost_result.status_code == 200, lost_result.text
    assert lost_result.json()["stage"] == "lost"

    pipeline = (await client.get("/api/v1/opportunities/pipeline", headers=headers)).json()
    assert pipeline["lost"] == 1
    assert pipeline["win_rate"] == 50.0


# ============================================================== contracts

@pytest.mark.asyncio
async def test_contracts_approval_sign_and_renewals(client):
    org = await register_org(client, email="p12contract@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="ContractorCo")

    contract = await client.post(
        "/api/v1/contracts",
        json={"title": "Master Services Agreement", "contract_type": "msa",
              "customer_id": customer_id, "value": 500000, "currency": "USD",
              "effective_from": "2026-08-01", "expires_at": "2026-08-20",
              "approval_status": "pending_approval", "terms": "Standard terms"},
        headers=headers)
    assert contract.status_code == 200, contract.text
    contract_id = contract.json()["id"]
    assert contract.json()["status"] == "in_approval"

    approved = await client.patch(
        f"/api/v1/contracts/{contract_id}", json={"approval_status": "approved"}, headers=headers)
    assert approved.status_code == 200, approved.text

    signed = await client.post(
        f"/api/v1/contracts/{contract_id}/sign", json={"signed_by": "Carol (Client)"}, headers=headers)
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"

    version = await client.post(
        f"/api/v1/contracts/{contract_id}/versions",
        json={"version": "2.0", "change_note": "Scope change"}, headers=headers)
    assert version.status_code == 200, version.text
    assert len((await client.get(f"/api/v1/contracts/{contract_id}/versions", headers=headers)).json()) >= 1

    expiring = (await client.get("/api/v1/contracts", headers=headers, params={"expiring_soon": "true"})).json()
    assert any(item["id"] == contract_id for item in expiring)
    assert expiring[0]["renewal_status"] == "due_soon"

    renewal = await client.post(
        f"/api/v1/contracts/{contract_id}/renewals",
        json={"proposed_value": 550000, "due_date": "2026-09-15", "recommended": True,
              "reason": "High engagement, expanded scope"}, headers=headers)
    assert renewal.status_code == 200, renewal.text
    renewal_id = renewal.json()["id"]

    completed = await client.patch(
        f"/api/v1/contracts/renewals/{renewal_id}", json={"status": "completed"}, headers=headers)
    assert completed.status_code == 200, completed.text

    detail = (await client.get(f"/api/v1/contracts/{contract_id}", headers=headers)).json()
    assert detail["renewal_status"] == "renewed"

    renewals = (await client.get("/api/v1/contracts/renewals", headers=headers)).json()
    assert any(item["id"] == renewal_id and item["contract_title"] == "Master Services Agreement" for item in renewals)


# ============================================================== support

@pytest.mark.asyncio
async def test_support_tickets_sla_and_knowledge(client):
    org = await register_org(client, email="p12support@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="SupportCo")

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Login failures on EU cluster",
              "description": "Users cannot authenticate after the last deploy",
              "category": "incident", "priority": "high", "status": "open"},
        headers=headers)
    assert ticket.status_code == 200, ticket.text
    ticket_id = ticket.json()["id"]

    summary = (await client.get("/api/v1/support/summary", headers=headers)).json()
    assert summary["total"] == 1
    assert summary["open"] == 1

    escalated = await client.patch(
        f"/api/v1/support/tickets/{ticket_id}", json={"status": "escalated", "note": "Pager duty"}, headers=headers)
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["status"] == "escalated"

    escalated_list = (await client.get("/api/v1/support/tickets", headers=headers, params={"escalated": "true"})).json()
    assert len(escalated_list) == 1

    resolved = await client.patch(
        f"/api/v1/support/tickets/{ticket_id}",
        json={"status": "resolved", "resolution": "Redeployed auth service", "root_cause": "Config drift",
              "satisfaction_rating": 5},
        headers=headers)
    assert resolved.status_code == 200, resolved.text

    doc = await client.post(
        "/api/v1/documents",
        json={"title": "Troubleshooting Login Issues", "content": "How to fix login failures after deploys",
              "category": "support"},
        headers=headers)
    assert doc.status_code in (200, 201), doc.text
    doc_id = doc.json()["id"]

    publish = await client.post(f"/api/v1/documents/{doc_id}/publish", json={}, headers=headers)
    assert publish.status_code == 200, publish.text

    suggest = (await client.get(f"/api/v1/support/tickets/{ticket_id}/suggest", headers=headers)).json()
    assert any(item["document_id"] == doc_id for item in suggest)

    link = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/knowledge",
        json={"document_id": doc_id, "document_title": "Troubleshooting Login Issues", "kind": "resolved"}, headers=headers)
    assert link.status_code == 200, link.text
    assert len((await client.get(f"/api/v1/support/tickets/{ticket_id}/knowledge", headers=headers)).json()) == 1


# ============================================================== partners & vendors

@pytest.mark.asyncio
async def test_partners_and_vendors(client):
    org = await register_org(client, email="p12partner@test.co")
    headers = org["headers"]

    partner = await client.post(
        "/api/v1/partners",
        json={"kind": "partner", "name": "Nimbus Cloud", "partner_type": "technology",
              "website": "nimbus.test", "industry": "cloud", "country": "US",
              "performance_score": 92, "status": "active"},
        headers=headers)
    assert partner.status_code == 200, partner.text
    partner_id = partner.json()["id"]

    vendor = await client.post(
        "/api/v1/partners",
        json={"kind": "vendor", "name": "SecureStack", "rating": 4.5, "payment_terms": "net-30"}, headers=headers)
    assert vendor.status_code == 200, vendor.text

    summary = (await client.get("/api/v1/partners/summary", headers=headers)).json()
    assert summary["total"] == 2
    assert summary["active"] == 2
    assert summary["by_kind"]["partner"] == 1
    assert summary["by_kind"]["vendor"] == 1

    contact = await client.post(
        f"/api/v1/partners/{partner_id}/contacts",
        json={"name": "Sam Patel", "role": "Account Executive", "email": "sam@nimbus.test", "is_primary": True},
        headers=headers)
    assert contact.status_code == 200, contact.text
    assert len((await client.get(f"/api/v1/partners/{partner_id}/contacts", headers=headers)).json()) == 1

    customer_id = await _create_customer(client, headers, name="VendorUserCo")
    contract = await client.post(
        "/api/v1/contracts",
        json={"title": "Cloud Reseller Agreement", "contract_type": "purchase_order",
              "customer_id": customer_id, "partner_id": partner_id, "value": 100000,
              "effective_from": "2026-08-01", "expires_at": "2027-08-01"},
        headers=headers)
    assert contract.status_code == 200, contract.text

    link = await client.post(
        f"/api/v1/partners/{partner_id}/contracts", json={"contract_id": contract.json()["id"]}, headers=headers)
    assert link.status_code == 200, link.text
    assert len((await client.get(f"/api/v1/partners/{partner_id}/contracts", headers=headers)).json()) == 1

    updated = await client.patch(
        f"/api/v1/partners/{partner_id}", json={"status": "inactive"}, headers=headers)
    assert updated.status_code == 200, updated.text


# ============================================================== portal

@pytest.mark.asyncio
async def test_customer_portal_isolation(client):
    org = await register_org(client, email="p12portal@test.co")
    headers = org["headers"]
    customer_a = await _create_customer(client, headers, name="PortalA")
    customer_b = await _create_customer(client, headers, name="PortalB")

    created = await client.post(
        "/api/v1/portal/admin/users",
        json={"customer_id": customer_a, "email": "client@portala.test", "full_name": "Client A",
              "password": "PortalPass123!", "portal_role": "customer_admin"},
        headers=headers)
    assert created.status_code == 200, created.text

    login = await client.post(
        "/api/v1/portal/auth/login",
        json={"email": "client@portala.test", "password": "PortalPass123!"})
    assert login.status_code == 200, login.text
    portal_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = (await client.get("/api/v1/portal/me", headers=portal_headers)).json()
    assert me["customer_id"] == customer_a
    assert me["portal_role"] == "customer_admin"

    data = (await client.get("/api/v1/portal/customer", headers=portal_headers)).json()
    assert data["customer"]["id"] == customer_a
    assert data["customer"]["company_name"] == "PortalA"

    wrong_password = await client.post(
        "/api/v1/portal/auth/login", json={"email": "client@portala.test", "password": "wrong"})
    assert wrong_password.status_code == 401

    other_org = await register_org(client, name="Other Org", email="other-owner@test.co")
    foreign_users = (await client.get(
        "/api/v1/portal/admin/users", headers=other_org["headers"],
        params={"customer_id": customer_a})).json()
    assert foreign_users == [], "portal users must be org-scoped"

    users = (await client.get("/api/v1/portal/admin/users", headers=headers, params={"customer_id": customer_a})).json()
    assert len(users) == 1
    assert users[0]["email"] == "client@portala.test"

    updated = await client.patch(
        f"/api/v1/portal/admin/users/{users[0]['id']}", json={"status": "suspended"}, headers=headers)
    assert updated.status_code == 200, updated.text
    blocked = await client.post(
        "/api/v1/portal/auth/login", json={"email": "client@portala.test", "password": "PortalPass123!"})
    assert blocked.status_code == 401

    created_b = await client.post(
        "/api/v1/portal/admin/users",
        json={"customer_id": customer_b, "email": "client@portalb.test", "full_name": "Client B",
              "password": "PortalPass123!", "portal_role": "customer_viewer"},
        headers=headers)
    assert created_b.status_code == 200, created_b.text
    deleted = await client.delete(f"/api/v1/portal/admin/users/{created_b.json()['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text


@pytest.mark.asyncio
async def test_portal_ticket_and_contracts(client):
    org = await register_org(client, email="p12portaltick@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="PortalTick")

    created = await client.post(
        "/api/v1/portal/admin/users",
        json={"customer_id": customer_id, "email": "tick@portaltick.test", "full_name": "Tick User",
              "password": "PortalPass123!", "portal_role": "customer_viewer"},
        headers=headers)
    assert created.status_code == 200, created.text

    login = await client.post(
        "/api/v1/portal/auth/login", json={"email": "tick@portaltick.test", "password": "PortalPass123!"})
    portal_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    ticket = await client.post(
        "/api/v1/portal/tickets",
        json={"subject": "Cannot reset MFA", "description": "MFA reset link not arriving",
              "category": "question", "priority": "medium"},
        headers=portal_headers)
    assert ticket.status_code == 200, ticket.text
    assert ticket.json()["status"] in ("open", "in_progress")
    assert ticket.json()["priority"] == "medium"

    mine = (await client.get("/api/v1/portal/tickets", headers=portal_headers)).json()
    assert len(mine) == 1
    assert mine[0]["id"] == ticket.json()["id"]

    contract = await client.post(
        "/api/v1/contracts",
        json={"title": "PortalTick Subscription", "customer_id": customer_id, "value": 25000,
              "effective_from": "2026-08-01", "expires_at": "2027-08-01"},
        headers=headers)
    assert contract.status_code == 200, contract.text

    contracts = (await client.get("/api/v1/portal/contracts", headers=portal_headers)).json()
    assert any(item["id"] == contract.json()["id"] for item in contracts)

    internal_tickets = (await client.get(
        "/api/v1/support/tickets", headers=headers, params={"customer_id": customer_id})).json()
    assert internal_tickets[0]["via_portal"] is True


# ============================================================== health engine & analytics

@pytest.mark.asyncio
async def test_customer_health_and_analytics(client):
    org = await register_org(client, email="p12health@test.co")
    headers = org["headers"]

    healthy = await _create_customer(client, headers, name="HealthyCo")
    risky = await _create_customer(client, headers, name="RiskyCo")

    contract = await client.post(
        "/api/v1/contracts",
        json={"title": "HealthyCo Annual", "customer_id": healthy, "value": 200000,
              "effective_from": "2026-08-01", "expires_at": "2026-09-01", "status": "active"},
        headers=headers)
    assert contract.status_code == 200, contract.text

    recompute = await client.post("/api/v1/analytics/health/recompute", json={}, headers=headers)
    assert recompute.status_code == 200, recompute.text
    assert recompute.json()["updated"] == 2

    report = (await client.get("/api/v1/analytics/health", headers=headers)).json()
    assert len(report) == 2
    risky_row = next(item for item in report if item["company_name"] == "RiskyCo")
    healthy_row = next(item for item in report if item["company_name"] == "HealthyCo")
    assert healthy_row["score"] < risky_row["score"], "expiring contract must depress health"
    assert any("expires" in (signal.get("label") or "") for signal in healthy_row["signals"])
    assert "renewal_probability" in risky_row
    assert risky_row["signals"]

    dashboard = (await client.get("/api/v1/analytics/dashboard", headers=headers)).json()
    assert dashboard["total_customers"] == 2
    assert dashboard["active_customers"] == 2

    overview = (await client.get("/api/v1/analytics/overview", headers=headers)).json()
    assert overview["total_customers"] == 2
    assert overview["revenue"] == 200000
    assert overview["top_customers"][0]["company_name"] == "HealthyCo"

    renewals = (await client.get("/api/v1/analytics/renewals", headers=headers)).json()
    assert renewals["total_due"] >= 1
    assert any(item["title"] == "HealthyCo Annual" for item in renewals["contracts"])


@pytest.mark.asyncio
async def test_relationship_intelligence(client):
    org = await register_org(client, email="p12rel@test.co")
    headers = org["headers"]
    customer_a = await _create_customer(client, headers, name="RelAlpha")
    await _create_customer(client, headers, name="RelBeta")
    await _create_customer(client, headers, name="RelGamma")

    built = await client.post("/api/v1/analytics/relationships/build", json={}, headers=headers)
    assert built.status_code == 200, built.text
    assert built.json()["customers"] == 3
    assert built.json()["edges"] >= 3

    relationships = (await client.get("/api/v1/analytics/relationships", headers=headers)).json()
    assert relationships["total"] == 3
    assert any(item["customer_id"] == customer_a for item in relationships["relationships"])
    assert "strength" in relationships["relationships"][0]

    risks = (await client.get("/api/v1/analytics/relationships/risks", headers=headers)).json()
    assert "single_points_of_failure" in risks


# ============================================================== AI companion

@pytest.mark.asyncio
async def test_customer_ai_companion(client):
    org = await register_org(client, email="p12ai@test.co")
    headers = org["headers"]
    await _create_customer(client, headers, name="AskMeCo")
    await _create_customer(client, headers, name="StarCorp")

    overview = await client.post(
        "/api/v1/analytics/ask", json={"question": "Give me an overview of the portfolio"}, headers=headers)
    assert overview.status_code == 200, overview.text
    assert "Portfolio" in overview.json()["answer"]

    risk = await client.post(
        "/api/v1/analytics/ask", json={"question": "Which customers are at risk?"}, headers=headers)
    assert risk.status_code == 200, risk.text

    summary = await client.post(
        "/api/v1/analytics/ask", json={"question": "Summarize the customer StarCorp"}, headers=headers)
    assert summary.status_code == 200, summary.text
    assert "StarCorp" in summary.json()["answer"]

    meeting = await client.post(
        "/api/v1/analytics/ask", json={"question": "Who should I meet next?"}, headers=headers)
    assert meeting.status_code == 200, meeting.text
    assert "Recommend" in meeting.json()["answer"]

    unknown = await client.post(
        "/api/v1/analytics/ask", json={"question": "What is the meaning of life?"}, headers=headers)
    assert unknown.status_code == 200, unknown.text


# ============================================================== RBAC & isolation

@pytest.mark.asyncio
async def test_crm_rbac_and_tenant_isolation(client):
    org = await register_org(client, email="p12rbac@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="TenantACo")

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp@rbac.test.co", "full_name": "Emp One", "role": "employee"},
        headers=headers)
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp One", "password": "EmpPass123!"})
    assert registered.status_code == 201, registered.text
    emp_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    can_read = await client.get("/api/v1/customers", headers=emp_headers)
    assert can_read.status_code == 200, can_read.text

    cannot_write = await client.post(
        "/api/v1/customers", json={"company_name": "Nope Inc"}, headers=emp_headers)
    assert cannot_write.status_code == 403, cannot_write.text

    other_org = await register_org(client, name="Tenant B", email="tenantb@test.co")
    invisible = await client.get(f"/api/v1/customers/{customer_id}", headers=other_org["headers"])
    assert invisible.status_code == 404

    other_list = (await client.get("/api/v1/customers", headers=other_org["headers"])).json()
    assert all(item["id"] != customer_id for item in other_list)

    search = await client.get("/api/v1/search", headers=headers, params={"q": "TenantA"})
    assert search.status_code == 200, search.text
    types = [item.get("type") for item in search.json().get("results", [])]
    assert "customer" in types


# ============================================================== workers

@pytest.mark.asyncio
async def test_phase12_workers(client, monkeypatch, db_session_factory):
    org = await register_org(client, email="p12workers@test.co")
    headers = org["headers"]
    customer_id = await _create_customer(client, headers, name="WorkerCo")

    await client.post(
        "/api/v1/contracts",
        json={"title": "Expiring contract", "customer_id": customer_id, "value": 10000,
              "effective_from": "2026-06-01", "expires_at": "2026-08-10"},
        headers=headers)
    await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Old ticket", "category": "bug",
              "priority": "medium", "status": "open"},
        headers=headers)

    from app.workers.customer_health_worker import run_once as health_run
    from app.workers.renewal_worker import run_once as renewal_run
    from app.workers.relationship_worker import run_once as relationship_run
    from app.workers.support_worker import run_once as support_run

    import app.workers.customer_health_worker as health_module
    import app.workers.renewal_worker as renewal_module
    import app.workers.relationship_worker as relationship_module
    import app.workers.support_worker as support_module
    monkeypatch.setattr(health_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(renewal_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(relationship_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(support_module, "SessionLocal", db_session_factory)

    assert await health_run() >= 0
    assert await renewal_run() >= 0
    assert await relationship_run() >= 0
    assert await support_run() >= 0

    report = (await client.get("/api/v1/analytics/health", headers=headers)).json()
    assert any(item["customer_id"] == customer_id for item in report)
