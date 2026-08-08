"""Phase 13 — Finance & Business Operating System.

Covers the full financial intelligence lifecycle: budgets with allocations
and revisions, expenses with policy flags and reimbursement, procurement
with two-stage approval and purchase orders, vendors with risk profiles and
contracts with renewals, invoices and payments, explainable forecasting,
ERP integrations and CSV imports, financial analytics, risk scanning, the
finance AI companion, RBAC gating, multi-tenant isolation, search
integration and the Phase 13 workers.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _create_budget(client, headers, name="Ops Budget", allocated=50000, **overrides):
    payload = {
        "name": name,
        "budget_type": "department",
        "allocated_amount": allocated,
        "currency": "USD",
        "status": "active",
        "fiscal_year": 2026,
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/finance/budgets", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _create_expense(client, headers, amount=120, expense_type="travel", **overrides):
    payload = {
        "expense_type": expense_type,
        "amount": amount,
        "currency": "USD",
        "incurred_at": "2026-07-01",
        "description": "Team offsite travel",
        "merchant": "AirlineCo",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/finance/expenses", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _create_vendor(client, headers, name="Acme Supplies", **overrides):
    payload = {
        "name": name,
        "kind": "vendor",
        "contact_name": "Jane Doe",
        "email": "jane@acme.test.co",
        "country": "US",
        "payment_terms": "net30",
        "status": "active",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/finance/vendors", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ============================================================== budgets

@pytest.mark.asyncio
async def test_budget_lifecycle(client):
    org = await register_org(client, email="p13budget@test.co")
    headers = org["headers"]
    budget_id = await _create_budget(client, headers)

    listed = await client.get("/api/v1/finance/budgets", headers=headers, params={"budget_type": "department"})
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == budget_id for item in listed.json())

    detail = await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["name"] == "Ops Budget"
    assert body["allocated_amount"] == 50000
    assert body["remaining_amount"] == 50000
    assert body["used_amount"] == 0

    revised = await client.patch(
        f"/api/v1/finance/budgets/{budget_id}",
        json={"revision_delta": 5000, "revision_reason": "Headcount growth"}, headers=headers)
    assert revised.status_code == 200, revised.text
    assert revised.json()["allocated_amount"] == 55000
    assert len(revised.json()["revisions"]) == 1

    summary = await client.get("/api/v1/finance/budgets/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_budgets"] == 1
    assert summary.json()["allocated"] == 55000

    events = (await client.get("/api/v1/events", headers=headers, params={"name": "budget.created", "page_size": 50})).json()
    assert any(item.get("name") == "budget.created" for item in events.get("items", events))

    deleted = await client.delete(f"/api/v1/finance/budgets/{budget_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_budget_tracks_expense_and_order_usage(client):
    org = await register_org(client, email="p13budgetuse@test.co")
    headers = org["headers"]
    budget_id = await _create_budget(client, headers, allocated=5000)

    await _create_expense(client, headers, amount=1000, budget_id=budget_id, status="approved")

    request = await client.post(
        "/api/v1/finance/requests",
        json={"title": "Laptop batch", "category": "laptop", "estimated_cost": 2000, "budget_id": budget_id},
        headers=headers)
    request_id = request.json()["id"]
    await client.post(f"/api/v1/finance/requests/{request_id}/decide", json={"decision": "approve"}, headers=headers)
    await client.post(f"/api/v1/finance/requests/{request_id}/decide", json={"decision": "approve"}, headers=headers)
    order = await client.post(
        "/api/v1/finance/purchase-orders",
        json={"purchase_request_id": request_id, "total_amount": 2000},
        headers=headers)
    assert order.status_code == 200, order.text

    detail = (await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=headers)).json()
    assert detail["used_amount"] == 3000
    assert detail["remaining_amount"] == 2000
    assert detail["risk_level"] == "medium"


# ============================================================== expenses

@pytest.mark.asyncio
async def test_expense_lifecycle_and_policy(client):
    org = await register_org(client, email="p13exp@test.co")
    headers = org["headers"]
    expense_id = await _create_expense(client, headers, amount=2500, expense_type="travel")

    detail = (await client.get(f"/api/v1/finance/expenses/{expense_id}", headers=headers)).json()
    assert detail["status"] == "submitted"
    assert detail["policy_flags"]["flagged"] is True
    assert detail["policy_flags"]["high_amount"]["threshold"] == 500

    decided = await client.post(
        f"/api/v1/finance/expenses/{expense_id}/decide", json={"decision": "approved"}, headers=headers)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    reimbursed = await client.post(
        f"/api/v1/finance/expenses/{expense_id}/decide", json={"decision": "reimbursed"}, headers=headers)
    assert reimbursed.status_code == 200, reimbursed.text
    assert reimbursed.json()["status"] == "reimbursed"

    rejected = await _create_expense(client, headers, amount=60, expense_type="food",
                                     description="Dinner with client")
    await client.post(f"/api/v1/finance/expenses/{rejected}/decide",
                      json={"decision": "rejected", "note": "Receipt missing"}, headers=headers)
    assert (await client.get(f"/api/v1/finance/expenses/{rejected}", headers=headers)).json()["status"] == "rejected"

    listed = await client.get("/api/v1/finance/expenses", headers=headers, params={"status": "reimbursed"})
    assert any(item["id"] == expense_id for item in listed.json())


# ============================================================== procurement

@pytest.mark.asyncio
async def test_purchase_request_to_order_flow(client):
    org = await register_org(client, email="p13proc@test.co")
    headers = org["headers"]
    budget_id = await _create_budget(client, headers, allocated=20000)
    vendor_id = await _create_vendor(client, headers, name="HardwareHub")

    created = await client.post(
        "/api/v1/finance/requests",
        json={"title": "4K monitors", "category": "equipment", "quantity": 4,
              "estimated_cost": 3200, "budget_id": budget_id, "vendor_id": vendor_id},
        headers=headers)
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]
    assert created.json()["status"] == "submitted"

    approved_once = await client.post(
        f"/api/v1/finance/requests/{request_id}/decide", json={"decision": "approve"}, headers=headers)
    assert approved_once.status_code == 200, approved_once.text
    assert approved_once.json()["status"] == "manager_approved"

    approved_twice = await client.post(
        f"/api/v1/finance/requests/{request_id}/decide", json={"decision": "approve"}, headers=headers)
    assert approved_twice.json()["status"] == "approved"

    order = await client.post(
        "/api/v1/finance/purchase-orders",
        json={"purchase_request_id": request_id, "vendor_id": vendor_id, "total_amount": 3200},
        headers=headers)
    assert order.status_code == 200, order.text
    order_id = order.json()["id"]
    assert order.json()["po_number"].startswith("PO-2026-")

    delivered = await client.patch(
        f"/api/v1/finance/purchase-orders/{order_id}", json={"status": "delivered"}, headers=headers)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"

    budget = (await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=headers)).json()
    assert budget["used_amount"] == 3200

    rejected = await client.post(
        "/api/v1/finance/requests",
        json={"title": "Unneeded chairs", "category": "furniture", "estimated_cost": 900},
        headers=headers)
    reject_id = rejected.json()["id"]
    await client.post(f"/api/v1/finance/requests/{reject_id}/decide",
                      json={"decision": "reject", "note": "Budget cut"}, headers=headers)
    assert (await client.get(f"/api/v1/finance/requests/{reject_id}", headers=headers)).json()["status"] == "rejected"


# ============================================================== vendors

@pytest.mark.asyncio
async def test_vendor_and_contract_flow(client):
    org = await register_org(client, email="p13vendor@test.co")
    headers = org["headers"]
    vendor_id = await _create_vendor(client, headers, name="SecureHosting")

    detail = (await client.get(f"/api/v1/finance/vendors/{vendor_id}", headers=headers)).json()
    assert detail["name"] == "SecureHosting"
    assert detail["risk"]["score"] == 50

    contract = await client.post(
        "/api/v1/finance/vendor-contracts",
        json={"vendor_id": vendor_id, "title": "Hosting agreement", "value": 12000,
              "currency": "USD", "effective_from": "2026-01-01", "expires_at": "2026-08-15"},
        headers=headers)
    assert contract.status_code == 200, contract.text
    contract_id = contract.json()["id"]
    assert contract.json()["renewal_status"] in ("due_soon", "overdue")

    expiring = await client.get(
        "/api/v1/finance/vendor-contracts", headers=headers, params={"expiring_soon": "true"})
    assert any(item["id"] == contract_id for item in expiring.json())

    renewed = await client.post(
        f"/api/v1/finance/vendor-contracts/{contract_id}/renew",
        json={"expires_at": "2027-08-15", "value": 13500}, headers=headers)
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["renewal_status"] == "not_due"
    assert renewed.json()["value"] == 13500

    summary = await client.get("/api/v1/finance/vendors/summary", headers=headers)
    assert summary.json()["total"] == 1


# ============================================================== invoices & payments

@pytest.mark.asyncio
async def test_invoice_payment_lifecycle(client):
    org = await register_org(client, email="p13inv@test.co")
    headers = org["headers"]
    vendor_id = await _create_vendor(client, headers, name="CloudWorks")

    payable = await client.post(
        "/api/v1/finance/invoices",
        json={"direction": "payable", "vendor_id": vendor_id, "title": "Cloud invoice July",
              "amount": 1500, "due_at": "2026-07-20", "issued_at": "2026-07-01", "invoice_number": "INV-7001"},
        headers=headers)
    assert payable.status_code == 200, payable.text
    invoice_id = payable.json()["id"]

    payment = await client.post(
        "/api/v1/finance/payments",
        json={"invoice_id": invoice_id, "amount": 1500, "method": "bank_transfer",
              "status": "completed", "reference": "PAY-2026-001"},
        headers=headers)
    assert payment.status_code == 200, payment.text
    assert payment.json()["status"] == "completed"

    paid = (await client.get(f"/api/v1/finance/invoices/{invoice_id}", headers=headers)).json()
    assert paid["status"] == "paid"
    assert paid["paid_total"] == 1500

    customer = await client.post(
        "/api/v1/customers",
        json={"company_name": "ReceivableCo", "status": "customer", "segment": "mid_market"},
        headers=headers)
    assert customer.status_code == 200, customer.text
    customer_id = customer.json()["id"]

    receivable = await client.post(
        "/api/v1/finance/invoices",
        json={"direction": "receivable", "customer_id": customer_id, "title": "Client milestone",
              "amount": 4000, "due_at": "2026-07-25", "issued_at": "2026-07-05"},
        headers=headers)
    assert receivable.status_code == 200, receivable.text

    summary = await client.get("/api/v1/finance/invoices/summary", headers=headers)
    assert summary.json()["total"] == 2
    assert summary.json()["payable"]["count"] == 1
    assert summary.json()["payable"]["paid"] == 1500

    payments = await client.get("/api/v1/finance/payments", headers=headers)
    assert len(payments.json()) == 1


# ============================================================== forecasting

@pytest.mark.asyncio
async def test_forecasting_generate_and_latest(client):
    org = await register_org(client, email="p13forecast@test.co")
    headers = org["headers"]
    customer = await client.post(
        "/api/v1/customers",
        json={"company_name": "ForecastCo", "status": "customer", "segment": "mid_market"},
        headers=headers)
    customer_id = customer.json()["id"]
    for index in range(3):
        await client.post(
            "/api/v1/finance/invoices",
            json={"direction": "receivable", "customer_id": customer_id,
                  "title": f"Revenue {index}", "amount": 5000 + index * 500,
                  "due_at": "2026-07-20", "issued_at": f"2026-0{index + 1}-15"},
            headers=headers)

    generated = await client.post(
        "/api/v1/finance/forecasts/generate", json={"kind": "all", "horizon_months": 3}, headers=headers)
    assert generated.status_code == 200, generated.text
    assert generated.json()["generated"] == 5

    revenue = await client.get("/api/v1/finance/forecasts/latest/revenue", headers=headers)
    assert revenue.status_code == 200, revenue.text
    assert revenue.json()["kind"] == "revenue"
    assert revenue.json()["confidence"] >= 0

    listed = await client.get("/api/v1/finance/forecasts", headers=headers, params={"kind": "cash_flow"})
    assert any(item["kind"] == "cash_flow" for item in listed.json())


# ============================================================== integrations

@pytest.mark.asyncio
async def test_integrations_and_csv_import(client):
    org = await register_org(client, email="p13int@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/finance/integrations",
        json={"platform": "QuickBooks", "display_name": "QB Production",
              "config": {"integration_type": "rest", "expenses_count": 2,
                         "expense_1_amount": 150, "expense_2_amount": 75}},
        headers=headers)
    assert created.status_code == 200, created.text
    integration_id = created.json()["id"]
    assert created.json()["provider"] == "QuickBooks"
    assert created.json()["status"] == "enabled"
    assert "api_key" not in str(created.json()["config"])

    dry = await client.post(
        f"/api/v1/finance/integrations/{integration_id}/sync", json={"dry_run": True}, headers=headers)
    assert dry.status_code == 200, dry.text
    assert dry.json()["dry_run"] is True
    assert len(dry.json()["discovered"]) == 2

    real = await client.post(
        f"/api/v1/finance/integrations/{integration_id}/sync", json={"dry_run": False}, headers=headers)
    assert real.status_code == 200, real.text
    assert real.json()["imported"] == 2

    csv_content = (
        "expense_type,amount,currency,incurred_at,description,merchant\n"
        "office,80,USD,2026-07-02,Printer paper,OfficeDepot\n"
        "software,240,USD,2026-07-03,Design tool seat,Figma\n"
    )
    imported = await client.post(
        "/api/v1/finance/integrations/import",
        json={"kind": "expenses", "content": csv_content}, headers=headers)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 2

    health = await client.get("/api/v1/finance/integrations/health", headers=headers)
    assert health.json()["connected"] == 1


# ============================================================== analytics & risk

@pytest.mark.asyncio
async def test_finance_analytics_dashboard_and_risk(client):
    org = await register_org(client, email="p13analytics@test.co")
    headers = org["headers"]
    vendor_id = await _create_vendor(client, headers, name="BigCloud")
    budget_id = await _create_budget(client, headers, allocated=1000)
    await _create_expense(client, headers, amount=1100, budget_id=budget_id, status="approved")

    dashboard = await client.get("/api/v1/finance/analytics/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["operating_costs"] >= 1100

    revenue = await client.get("/api/v1/finance/analytics/revenue", headers=headers)
    assert revenue.status_code == 200, revenue.text

    costs = await client.get("/api/v1/finance/analytics/costs", headers=headers)
    assert costs.status_code == 200, costs.text

    projects = await client.get("/api/v1/finance/analytics/projects", headers=headers)
    assert projects.status_code == 200, projects.text
    assert isinstance(projects.json()["projects"], list)

    trends = await client.get("/api/v1/finance/analytics/expense-trends", headers=headers)
    assert trends.status_code == 200, trends.text

    vendor_spend = await client.get("/api/v1/finance/analytics/vendor-spend", headers=headers)
    assert vendor_spend.status_code == 200, vendor_spend.text

    pipeline = await client.get("/api/v1/finance/analytics/approvals-pipeline", headers=headers)
    assert pipeline.status_code == 200, pipeline.text

    scanned = await client.post("/api/v1/finance/risks/scan", headers=headers)
    assert scanned.status_code == 200, scanned.text
    types = {risk["type"] for risk in scanned.json()["risks"]}
    assert "budget_overrun" in types

    summary = await client.get("/api/v1/finance/risks/summary", headers=headers)
    assert summary.json()["health_score"] >= 0
    assert summary.json()["total"] >= 1

    metric = await client.post(
        "/api/v1/finance/analytics/metrics",
        json={"metric_type": "revenue", "period": "2026-07", "value": 42000}, headers=headers)
    assert metric.status_code == 200, metric.text
    metrics = await client.get("/api/v1/finance/analytics/metrics", headers=headers, params={"metric_type": "revenue"})
    assert any(item["metric_type"] == "revenue" for item in metrics.json()["metrics"])


# ============================================================== AI companion

@pytest.mark.asyncio
async def test_finance_ai_companion(client):
    org = await register_org(client, email="p13ai@test.co")
    headers = org["headers"]
    budget_id = await _create_budget(client, headers, allocated=10000)

    answer = await client.post(
        "/api/v1/finance/ask", json={"message": "What is my budget remaining?"}, headers=headers)
    assert answer.status_code == 200, answer.text
    assert answer.json()["intent"] == "budget_remaining"
    assert "10,000" in answer.json()["reply"]

    recommendations = await client.post(
        "/api/v1/finance/ask", json={"message": "Give me cost-saving recommendations"}, headers=headers)
    assert recommendations.json()["intent"] == "recommendations"


# ============================================================== RBAC & isolation

@pytest.mark.asyncio
async def test_finance_rbac_gating(client):
    org = await register_org(client, email="p13rbac@test.co")
    headers = org["headers"]
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp13@rbac.test.co", "full_name": "Emp Thirteen", "role": "employee"},
        headers=headers)
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Thirteen", "password": "EmpPass123!"})
    assert registered.status_code == 201, registered.text
    emp_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    read = await client.get("/api/v1/finance/budgets", headers=emp_headers)
    assert read.status_code == 200, read.text

    denied = await client.post(
        "/api/v1/finance/budgets",
        json={"name": "Sneaky budget", "allocated_amount": 100}, headers=emp_headers)
    assert denied.status_code == 403

    ask = await client.post("/api/v1/finance/ask", json={"message": "overview"}, headers=emp_headers)
    assert ask.status_code == 200, ask.text


@pytest.mark.asyncio
async def test_finance_multi_tenant_isolation(client):
    org_a = await register_org(client, email="p13iso1@test.co")
    org_b = await register_org(client, email="p13iso2@test.co")
    budget_id = await _create_budget(client, org_a["headers"], name="Alpha Budget")

    other = await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=org_b["headers"])
    assert other.status_code == 404

    listed = await client.get("/api/v1/finance/budgets", headers=org_b["headers"])
    assert not any(item["id"] == budget_id for item in listed.json())


# ============================================================== search

@pytest.mark.asyncio
async def test_finance_search_integration(client):
    org = await register_org(client, email="p13search@test.co")
    headers = org["headers"]
    await _create_vendor(client, headers, name="ZebraLabs")
    await _create_budget(client, headers, name="Marketing 2026")

    results = (await client.get("/api/v1/search", headers=headers, params={"q": "zebra"})).json()
    assert any(item["type"] == "vendor" for item in results["results"])

    results = (await client.get("/api/v1/search", headers=headers, params={"q": "marketing"})).json()
    assert any(item["type"] == "budget" for item in results["results"])


# ============================================================== workers

@pytest.mark.asyncio
async def test_phase13_workers(client, monkeypatch, db_session_factory):
    org = await register_org(client, email="p13workers@test.co")
    headers = org["headers"]
    await _create_budget(client, headers, allocated=50000)
    await _create_expense(client, headers, amount=200)

    from app.workers.budget_worker import run_once as budget_run
    from app.workers.forecasting_worker import run_once as forecasting_run
    from app.workers.reconciliation_worker import run_once as reconciliation_run
    from app.workers.finance_analytics_worker import run_once as analytics_run
    from app.workers.optimization_worker import run_once as optimization_run

    import app.workers.budget_worker as budget_module
    import app.workers.forecasting_worker as forecasting_module
    import app.workers.reconciliation_worker as reconciliation_module
    import app.workers.finance_analytics_worker as analytics_module
    import app.workers.optimization_worker as optimization_module
    monkeypatch.setattr(budget_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(forecasting_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(reconciliation_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(analytics_module, "SessionLocal", db_session_factory)
    monkeypatch.setattr(optimization_module, "SessionLocal", db_session_factory)

    assert await budget_run() >= 0
    assert await forecasting_run() >= 5
    assert await reconciliation_run() >= 0
    assert await analytics_run() >= 0
    assert await optimization_run() >= 0

    forecasts = await client.get("/api/v1/finance/forecasts", headers=headers)
    assert len(forecasts.json()) >= 5
