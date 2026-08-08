"""Finance & Business Operations API (Phase 13 — Finance).

Budgets, expenses, procurement, vendors, vendor contracts, invoices,
payments, forecasting, integrations, analytics, risk and the finance
AI companion. Reads require finance:read; writes require finance:manage.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.finance.ai_service import finance_ai_service
from app.finance.analytics_service import financial_analytics
from app.finance.budget_service import budget_service
from app.finance.expense_service import expense_service
from app.finance.forecasting_service import forecasting_service
from app.finance.integration_service import finance_integration_service
from app.finance.invoice_service import invoice_service
from app.finance.procurement_service import procurement_service
from app.finance.risk_service import risk_service
from app.finance.vendor_contract_service import vendor_contract_service
from app.finance.vendor_service import vendor_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/finance", tags=["Finance"])


def _not_found(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{name} not found")


# ---------------------------------------------------------------- analytics

@router.get("/analytics/dashboard")
async def dashboard(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await financial_analytics.dashboard(db, organization_id=org.id)


@router.get("/analytics/revenue")
async def revenue(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    months: int = Query(12, ge=1, le=36),
):
    return await financial_analytics.revenue(db, organization_id=org.id, months=months)


@router.get("/analytics/costs")
async def costs(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    months: int = Query(12, ge=1, le=36),
):
    return await financial_analytics.costs(db, organization_id=org.id, months=months)


@router.get("/analytics/projects")
async def project_financials(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await financial_analytics.project_financials(db, organization_id=org.id)


@router.get("/analytics/expense-trends")
async def expense_trends(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    months: int = Query(6, ge=1, le=24),
):
    return await financial_analytics.expense_trends(db, organization_id=org.id, months=months)


@router.get("/analytics/vendor-spend")
async def vendor_spend(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await financial_analytics.vendor_spend(db, organization_id=org.id)


@router.get("/analytics/approvals-pipeline")
async def approvals_pipeline(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await financial_analytics.approvals_pipeline(db, organization_id=org.id)


@router.get("/analytics/metrics")
async def metrics(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    metric_type: Optional[str] = None,
    limit: int = Query(60, ge=1, le=200),
):
    return await financial_analytics.metrics(db, organization_id=org.id, metric_type=metric_type, limit=limit)


@router.post("/analytics/metrics")
async def record_metric(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.get("metric_type") or not payload.get("period") or payload.get("value") is None:
        raise HTTPException(status_code=422, detail="metric_type, period and value are required")
    row = await financial_analytics.record_metric(
        db, organization_id=org.id, metric_type=payload["metric_type"],
        period=payload["period"], value=float(payload["value"]), payload=payload.get("payload"),
    )
    await db.commit()
    return {"id": row.id, "metric_type": row.metric_type, "period": row.period, "value": row.value}


# -------------------------------------------------------------------- risks

@router.post("/risks/scan")
async def scan_risks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await risk_service.scan(db, organization_id=org.id, actor_id=user.id)
    await db.commit()
    return result


@router.get("/risks/summary")
async def risk_summary(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await risk_service.summarize(db, organization_id=org.id)


# ------------------------------------------------------------------- budgets

@router.post("/budgets")
async def create_budget(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        budget = await budget_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return await budget_service.detail(db, organization_id=org.id, budget_id=budget.id)


@router.get("/budgets")
async def list_budgets(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    budget_type: Optional[str] = None,
    status: Optional[str] = None,
    department_id: Optional[str] = None,
    project_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    search: Optional[str] = None,
):
    return await budget_service.list_budgets(
        db, organization_id=org.id, budget_type=budget_type, status=status,
        department_id=department_id, project_id=project_id, owner_id=owner_id, search=search,
    )


@router.get("/budgets/summary")
async def budgets_summary(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await budget_service.summary(db, organization_id=org.id)


@router.get("/budgets/{budget_id}")
async def get_budget(
    budget_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await budget_service.detail(db, organization_id=org.id, budget_id=budget_id)
    if item is None:
        raise _not_found("Budget")
    return item


@router.patch("/budgets/{budget_id}")
async def update_budget(
    budget_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    budget = await budget_service.get(db, organization_id=org.id, budget_id=budget_id)
    if budget is None:
        raise _not_found("Budget")
    try:
        await budget_service.update(db, organization_id=org.id, budget=budget, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return await budget_service.detail(db, organization_id=org.id, budget_id=budget_id)


@router.delete("/budgets/{budget_id}")
async def delete_budget(
    budget_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    budget = await budget_service.get(db, organization_id=org.id, budget_id=budget_id)
    if budget is None:
        raise _not_found("Budget")
    await budget_service.delete(db, organization_id=org.id, budget=budget)
    await db.commit()
    return {"deleted": budget_id}


# ------------------------------------------------------------------ expenses

@router.post("/expenses")
async def create_expense(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await expense_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/expenses")
async def list_expenses(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    expense_type: Optional[str] = None,
    employee_id: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    return await expense_service.list_expenses(
        db, organization_id=org.id, status=status, expense_type=expense_type,
        employee_id=employee_id, project_id=project_id, limit=limit,
    )


@router.get("/expenses/{expense_id}")
async def get_expense(
    expense_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await expense_service.detail(db, organization_id=org.id, expense_id=expense_id)
    if item is None:
        raise _not_found("Expense")
    return item


@router.patch("/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    expense = await expense_service.get(db, organization_id=org.id, expense_id=expense_id)
    if expense is None:
        raise _not_found("Expense")
    try:
        item = await expense_service.update(db, organization_id=org.id, expense=expense, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.post("/expenses/{expense_id}/decide")
async def decide_expense(
    expense_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    expense = await expense_service.get(db, organization_id=org.id, expense_id=expense_id)
    if expense is None:
        raise _not_found("Expense")
    try:
        item = await expense_service.decide(
            db, organization_id=org.id, expense=expense,
            decision=payload.get("decision", ""), note=payload.get("note"), actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


# ------------------------------------------------------------------ vendors

@router.post("/vendors")
async def create_vendor(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        vendor = await vendor_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return await vendor_service.detail(db, organization_id=org.id, vendor_id=vendor.id)


@router.get("/vendors")
async def list_vendors(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    kind: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    return await vendor_service.list_vendors(db, organization_id=org.id, kind=kind, status=status, search=search)


@router.get("/vendors/summary")
async def vendors_summary(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await vendor_service.summary(db, organization_id=org.id)


@router.get("/vendors/{vendor_id}")
async def get_vendor(
    vendor_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await vendor_service.detail(db, organization_id=org.id, vendor_id=vendor_id)
    if item is None:
        raise _not_found("Vendor")
    return item


@router.get("/vendors/{vendor_id}/risk")
async def vendor_risk(
    vendor_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await vendor_service.risk_profile(db, organization_id=org.id, vendor_id=vendor_id)
    if item is None:
        raise _not_found("Vendor")
    return item


@router.patch("/vendors/{vendor_id}")
async def update_vendor(
    vendor_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    vendor = await vendor_service.get(db, organization_id=org.id, vendor_id=vendor_id)
    if vendor is None:
        raise _not_found("Vendor")
    try:
        await vendor_service.update(db, organization_id=org.id, vendor=vendor, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return await vendor_service.detail(db, organization_id=org.id, vendor_id=vendor_id)


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(
    vendor_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    vendor = await vendor_service.get(db, organization_id=org.id, vendor_id=vendor_id)
    if vendor is None:
        raise _not_found("Vendor")
    await vendor_service.delete(db, organization_id=org.id, vendor=vendor)
    await db.commit()
    return {"deleted": vendor_id}


# ---------------------------------------------------------- vendor contracts

@router.post("/vendor-contracts")
async def create_vendor_contract(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await vendor_contract_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/vendor-contracts")
async def list_vendor_contracts(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    vendor_id: Optional[str] = None,
    status: Optional[str] = None,
    expiring_soon: bool = False,
    limit: int = Query(200, ge=1, le=500),
):
    return await vendor_contract_service.list_contracts(
        db, organization_id=org.id, vendor_id=vendor_id, status=status,
        expiring_soon=expiring_soon, limit=limit,
    )


@router.get("/vendor-contracts/{contract_id}")
async def get_vendor_contract(
    contract_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    contract = await vendor_contract_service.get(db, organization_id=org.id, contract_id=contract_id)
    if contract is None:
        raise _not_found("Vendor contract")
    return await vendor_contract_service._dict(db, contract, organization_id=org.id)


@router.patch("/vendor-contracts/{contract_id}")
async def update_vendor_contract(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    contract = await vendor_contract_service.get(db, organization_id=org.id, contract_id=contract_id)
    if contract is None:
        raise _not_found("Vendor contract")
    try:
        item = await vendor_contract_service.update(db, organization_id=org.id, contract=contract, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.post("/vendor-contracts/{contract_id}/renew")
async def renew_vendor_contract(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    contract = await vendor_contract_service.get(db, organization_id=org.id, contract_id=contract_id)
    if contract is None:
        raise _not_found("Vendor contract")
    item = await vendor_contract_service.renew(db, organization_id=org.id, contract=contract, data=payload, actor_id=user.id)
    await db.commit()
    return item


@router.delete("/vendor-contracts/{contract_id}")
async def delete_vendor_contract(
    contract_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    contract = await vendor_contract_service.get(db, organization_id=org.id, contract_id=contract_id)
    if contract is None:
        raise _not_found("Vendor contract")
    await vendor_contract_service.delete(db, organization_id=org.id, contract=contract)
    await db.commit()
    return {"deleted": contract_id}


# ------------------------------------------------------------------- invoices

@router.post("/invoices")
async def create_invoice(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await invoice_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/invoices")
async def list_invoices(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    direction: Optional[str] = None,
    status: Optional[str] = None,
    vendor_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    return await invoice_service.list_invoices(
        db, organization_id=org.id, direction=direction, status=status,
        vendor_id=vendor_id, customer_id=customer_id, project_id=project_id, limit=limit,
    )


@router.get("/invoices/summary")
async def invoices_summary(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await invoice_service.summary(db, organization_id=org.id)


@router.post("/invoices/mark-overdue")
async def mark_invoices_overdue(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    count = await invoice_service.mark_overdue(db, organization_id=org.id)
    await db.commit()
    return {"marked_overdue": count}


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await invoice_service.detail(db, organization_id=org.id, invoice_id=invoice_id)
    if item is None:
        raise _not_found("Invoice")
    return item


@router.patch("/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.get(db, organization_id=org.id, invoice_id=invoice_id)
    if invoice is None:
        raise _not_found("Invoice")
    try:
        item = await invoice_service.update(db, organization_id=org.id, invoice=invoice, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.get(db, organization_id=org.id, invoice_id=invoice_id)
    if invoice is None:
        raise _not_found("Invoice")
    await invoice_service.delete(db, organization_id=org.id, invoice=invoice)
    await db.commit()
    return {"deleted": invoice_id}


# ---------------------------------------------------------------- payments

@router.get("/payments")
async def list_payments(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    vendor_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    return await invoice_service.list_payments(db, organization_id=org.id, status=status, vendor_id=vendor_id, limit=limit)


@router.post("/payments")
async def create_payment(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await invoice_service.create_payment(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


# ---------------------------------------------------------------- procurement

@router.post("/requests")
async def create_purchase_request(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await procurement_service.create_request(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/requests")
async def list_purchase_requests(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    category: Optional[str] = None,
    employee_id: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    return await procurement_service.list_requests(
        db, organization_id=org.id, status=status, category=category,
        employee_id=employee_id, project_id=project_id, limit=limit,
    )


@router.get("/requests/{request_id}")
async def get_purchase_request(
    request_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await procurement_service.detail_request(db, organization_id=org.id, request_id=request_id)
    if item is None:
        raise _not_found("Purchase request")
    return item


@router.post("/requests/{request_id}/decide")
async def decide_purchase_request(
    request_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    request = await procurement_service.get_request(db, organization_id=org.id, request_id=request_id)
    if request is None:
        raise _not_found("Purchase request")
    try:
        item = await procurement_service.decide_request(
            db, organization_id=org.id, request=request,
            decision=payload.get("decision", ""), note=payload.get("note"), actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.delete("/requests/{request_id}")
async def delete_purchase_request(
    request_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    request = await procurement_service.get_request(db, organization_id=org.id, request_id=request_id)
    if request is None:
        raise _not_found("Purchase request")
    await procurement_service.delete_request(db, organization_id=org.id, request=request)
    await db.commit()
    return {"deleted": request_id}


@router.post("/purchase-orders")
async def create_purchase_order(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await procurement_service.create_order(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/purchase-orders")
async def list_purchase_orders(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    vendor_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    return await procurement_service.list_orders(db, organization_id=org.id, status=status, vendor_id=vendor_id, limit=limit)


@router.get("/purchase-orders/{order_id}")
async def get_purchase_order(
    order_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await procurement_service.detail_order(db, organization_id=org.id, order_id=order_id)
    if item is None:
        raise _not_found("Purchase order")
    return item


@router.patch("/purchase-orders/{order_id}")
async def update_purchase_order(
    order_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    order = await procurement_service.get_order(db, organization_id=org.id, order_id=order_id)
    if order is None:
        raise _not_found("Purchase order")
    try:
        item = await procurement_service.update_order(db, organization_id=org.id, order=order, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


# ---------------------------------------------------------------- forecasts

@router.post("/forecasts/generate")
async def generate_forecasts(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await forecasting_service.generate(
            db, organization_id=org.id, kind=payload.get("kind", "all"),
            actor_id=user.id, horizon_months=int(payload.get("horizon_months", 6)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return result


@router.get("/forecasts")
async def list_forecasts(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
    kind: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    return await forecasting_service.list_forecasts(db, organization_id=org.id, kind=kind, limit=limit)


@router.get("/forecasts/latest/{kind}")
async def latest_forecast(
    kind: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await forecasting_service.latest(db, organization_id=org.id, kind=kind)
    if item is None:
        raise _not_found("Forecast")
    return item


# -------------------------------------------------------------- integrations

@router.post("/integrations")
async def create_integration(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await finance_integration_service.create(
            db, organization_id=org.id, platform=payload.get("platform", ""),
            display_name=payload.get("display_name"), config=payload.get("config") or {}, actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return item


@router.get("/integrations")
async def list_integrations(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await finance_integration_service.list_integrations(db, organization_id=org.id)


@router.get("/integrations/health")
async def integrations_health(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    return await finance_integration_service.health(db, organization_id=org.id)


@router.get("/integrations/{integration_id}")
async def get_integration(
    integration_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await finance_integration_service.get(db, organization_id=org.id, integration_id=integration_id)
    except LookupError:
        raise _not_found("Integration")


@router.patch("/integrations/{integration_id}")
async def update_integration(
    integration_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await finance_integration_service.update(
            db, organization_id=org.id, integration_id=integration_id, data=payload, actor_id=user.id,
        )
    except LookupError:
        raise _not_found("Integration")
    await db.commit()
    return item


@router.delete("/integrations/{integration_id}")
async def delete_integration(
    integration_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await finance_integration_service.delete(db, organization_id=org.id, integration_id=integration_id)
    except LookupError:
        raise _not_found("Integration")
    await db.commit()
    return {"deleted": integration_id}


@router.post("/integrations/{integration_id}/sync")
async def sync_integration(
    integration_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await finance_integration_service.sync(
            db, organization_id=org.id, integration_id=integration_id,
            actor_id=user.id, dry_run=bool(payload.get("dry_run", True)),
        )
    except LookupError:
        raise _not_found("Integration")
    await db.commit()
    return result


@router.post("/integrations/import")
async def import_csv(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("finance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await finance_integration_service.import_csv(
            db, organization_id=org.id, kind=payload.get("kind", ""),
            content=payload.get("content", ""), actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return result


# ------------------------------------------------------------------ AI chat

@router.post("/ask")
async def ask_finance_ai(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("finance:read")),
    db: AsyncSession = Depends(get_db),
):
    message = payload.get("message") or payload.get("question") or ""
    if not message.strip():
        return {"reply": "Ask about budgets, approvals, at-risk projects, forecasts or recommendations."}
    return await finance_ai_service.chat(db, organization_id=org.id, message=message)
