"""Contract service (Phase 12.6 — Contract Management).

NDA, MSA, SOW, purchase orders, service agreements and SLAs with approval
workflow, version history, expiry tracking, renewal planning and
signature capture. Renewal reminders are driven by the renewal worker.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import to_date
from app.events.event_bus import EventBus
from app.models.contract import Contract, ContractRenewal, ContractVersion

logger = logging.getLogger("vcos.customers.contract")

_event_bus = EventBus()

CONTRACT_TYPES = ["nda", "msa", "sow", "purchase_order", "service_agreement", "sla", "license", "other"]
STATUSES = ["draft", "in_approval", "signed", "active", "expiring", "expired", "terminated", "renewed"]
APPROVAL_STATUSES = ["draft", "pending_approval", "approved", "rejected"]
RENEWAL_STATUSES = ["not_due", "due_soon", "due", "proposed", "approved", "renewed", "declined"]


class ContractService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Contract:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        contract = Contract(
            organization_id=organization_id,
            customer_id=data.get("customer_id"),
            partner_id=data.get("partner_id"),
            vendor_id=data.get("vendor_id"),
            title=title,
            contract_type=data.get("contract_type", "service_agreement") if data.get("contract_type") in CONTRACT_TYPES else "service_agreement",
            status=data.get("status", "draft") if data.get("status") in STATUSES else "draft",
            version=data.get("version", "1.0"),
            value=data.get("value"),
            currency=data.get("currency", "USD"),
            effective_from=to_date(data.get("effective_from")),
            expires_at=to_date(data.get("expires_at")),
            auto_renew=bool(data.get("auto_renew", False)),
            renewal_terms=data.get("renewal_terms"),
            owner_id=data.get("owner_id") or actor_id,
            description=data.get("description"),
            terms=data.get("terms"),
            file_url=data.get("file_url"),
            signature_method=data.get("signature_method", "none"),
            attributes=data.get("metadata") or data.get("attributes"),
        )
        contract.renewal_status = self._derive_renewal_status(contract.expires_at, contract.auto_renew)
        if data.get("approval_status") in APPROVAL_STATUSES:
            contract.approval_status = data["approval_status"]
            if data["approval_status"] == "pending_approval":
                contract.status = "in_approval"
        db.add(contract)
        await db.flush()
        await _event_bus.publish(
            db, name="contract.created", organization_id=organization_id, actor_id=actor_id,
            payload={"contract_id": contract.id, "title": contract.title,
                     "contract_type": contract.contract_type, "customer_id": contract.customer_id},
            flush=False,
        )
        await db.flush()
        return contract

    async def get(self, db: AsyncSession, *, organization_id: str, contract_id: str) -> Optional[Contract]:
        return (
            await db.execute(
                select(Contract).where(Contract.organization_id == organization_id, Contract.id == contract_id)
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, contract_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Optional[Contract]:
        contract = await self.get(db, organization_id=organization_id, contract_id=contract_id)
        if contract is None:
            return None
        changed = []
        for field in ("title", "customer_id", "partner_id", "vendor_id", "version", "value", "currency",
                      "effective_from", "expires_at", "auto_renew", "renewal_terms", "owner_id",
                      "description", "terms", "file_url", "signature_method", "attributes", "signed_by"):
            if field in data and data[field] is not None:
                old = getattr(contract, field)
                setattr(contract, field, to_date(data[field]) if field in ("effective_from", "expires_at") else data[field])
                if old != data[field]:
                    changed.append(field)
        if data.get("contract_type") in CONTRACT_TYPES:
            contract.contract_type = data["contract_type"]
        if data.get("status"):
            await self._set_status(db, contract, status=data["status"], actor_id=actor_id, note=data.get("note"))
        if data.get("approval_status") in APPROVAL_STATUSES:
            contract.approval_status = data["approval_status"]
            if data["approval_status"] == "approved":
                contract.approver_id = actor_id
                contract.approved_at = utcnow()
            elif data["approval_status"] == "pending_approval":
                contract.status = "in_approval"
        contract.renewal_status = self._derive_renewal_status(contract.expires_at, contract.auto_renew)
        if changed or data.get("status") or data.get("approval_status"):
            await _event_bus.publish(
                db, name="contract.updated", organization_id=organization_id, actor_id=actor_id,
                payload={"contract_id": contract.id, "title": contract.title, "changed": changed,
                         "status": contract.status},
                flush=False,
            )
        await db.flush()
        return contract

    async def _set_status(self, db: AsyncSession, contract: Contract, *, status: str,
                          actor_id: Optional[str] = None, note: Optional[str] = None) -> None:
        if status not in STATUSES or status == contract.status:
            return
        old = contract.status
        contract.status = status
        event_name = "contract.signed" if status == "signed" else "contract.status_changed"
        if status == "signed":
            contract.signed_at = utcnow() if not contract.signed_at else contract.signed_at
            contract.approval_status = "approved" if contract.approval_status != "rejected" else contract.approval_status
        if status == "active":
            contract.signed_at = contract.signed_at or utcnow()
        if status == "renewed":
            contract.renewal_status = "renewed"
        await _event_bus.publish(
            db, name=event_name, organization_id=contract.organization_id, actor_id=actor_id,
            payload={"contract_id": contract.id, "title": contract.title,
                     "from": old, "to": status, "note": note},
            flush=False,
        )

    async def sign(self, db: AsyncSession, *, organization_id: str, contract_id: str,
                   signed_by: str, actor_id: Optional[str] = None) -> Optional[Contract]:
        contract = await self.get(db, organization_id=organization_id, contract_id=contract_id)
        if contract is None:
            return None
        contract.signed_by = signed_by
        contract.signed_at = utcnow()
        contract.status = "signed"
        contract.approval_status = "approved"
        contract.approver_id = actor_id
        contract.approved_at = utcnow()
        await _event_bus.publish(
            db, name="contract.signed", organization_id=organization_id, actor_id=actor_id,
            payload={"contract_id": contract.id, "title": contract.title, "signed_by": signed_by},
            flush=False,
        )
        await db.flush()
        return contract

    async def list_contracts(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
                             contract_type: Optional[str] = None, customer_id: Optional[str] = None,
                             expiring_soon: bool = False, search: Optional[str] = None,
                             ) -> list[dict[str, Any]]:
        query = select(Contract).where(Contract.organization_id == organization_id)
        if status:
            query = query.where(Contract.status == status)
        if contract_type:
            query = query.where(Contract.contract_type == contract_type)
        if customer_id:
            query = query.where(Contract.customer_id == customer_id)
        if expiring_soon:
            horizon = date.today() + timedelta(days=90)
            query = query.where(
                Contract.expires_at.isnot(None),
                Contract.expires_at <= horizon,
                Contract.expires_at >= date.today(),
                Contract.status.in_(("active", "signed")),
            )
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(func.lower(Contract.title).like(pattern), func.lower(Contract.description).like(pattern))
            )
        rows = await db.execute(query.order_by(Contract.updated_at.desc()))
        return [self._dict(c) for c in rows.scalars().all()]

    def _dict(self, contract: Contract) -> dict[str, Any]:
        return {
            "id": contract.id, "customer_id": contract.customer_id, "partner_id": contract.partner_id,
            "vendor_id": contract.vendor_id, "title": contract.title, "contract_type": contract.contract_type,
            "status": contract.status, "version": contract.version, "value": contract.value,
            "currency": contract.currency,
            "effective_from": contract.effective_from.isoformat() if contract.effective_from else None,
            "expires_at": contract.expires_at.isoformat() if contract.expires_at else None,
            "auto_renew": contract.auto_renew, "renewal_terms": contract.renewal_terms,
            "renewal_status": contract.renewal_status, "renewal_probability": contract.renewal_probability,
            "approval_status": contract.approval_status, "approver_id": contract.approver_id,
            "approved_at": ensure_aware(contract.approved_at).isoformat() if contract.approved_at else None,
            "signed_by": contract.signed_by, "signed_at": ensure_aware(contract.signed_at).isoformat() if contract.signed_at else None,
            "signature_method": contract.signature_method, "owner_id": contract.owner_id,
            "description": contract.description, "terms": contract.terms, "file_url": contract.file_url,
            "created_at": ensure_aware(contract.created_at).isoformat() if contract.created_at else None,
            "updated_at": ensure_aware(contract.updated_at).isoformat() if contract.updated_at else None,
        }

    def _derive_renewal_status(self, expires_at: Optional[date], auto_renew: bool) -> str:
        if expires_at is None:
            return "not_due"
        if auto_renew:
            return "not_due"
        days_left = (expires_at - date.today()).days
        if days_left < 0:
            return "due"
        if days_left <= 30:
            return "due_soon"
        return "not_due"

    async def delete(self, db: AsyncSession, *, organization_id: str, contract_id: str) -> bool:
        contract = await self.get(db, organization_id=organization_id, contract_id=contract_id)
        if contract is None:
            return False
        await db.delete(contract)
        await db.flush()
        return True

    # ------------------------------------------------------------------ versions

    async def new_version(self, db: AsyncSession, *, organization_id: str, contract_id: str,
                          version: str, change_note: Optional[str] = None,
                          editor_id: Optional[str] = None, snapshot: Optional[dict[str, Any]] = None) -> Optional[ContractVersion]:
        contract = await self.get(db, organization_id=organization_id, contract_id=contract_id)
        if contract is None:
            return None
        entry = ContractVersion(
            organization_id=organization_id, contract_id=contract_id, version=version,
            change_note=change_note, editor_id=editor_id, content_snapshot=snapshot or {},
        )
        db.add(entry)
        contract.version = version
        await db.flush()
        return entry

    async def versions(self, db: AsyncSession, *, organization_id: str, contract_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(ContractVersion).where(
                ContractVersion.organization_id == organization_id, ContractVersion.contract_id == contract_id
            ).order_by(ContractVersion.created_at.desc())
        )
        result = []
        for entry in rows.scalars().all():
            result.append({
                "id": entry.id, "version": entry.version, "change_note": entry.change_note,
                "editor_id": entry.editor_id,
                "created_at": ensure_aware(entry.created_at).isoformat() if entry.created_at else None,
            })
        return result

    # ------------------------------------------------------------------ renewals

    async def plan_renewal(self, db: AsyncSession, *, organization_id: str, contract_id: str,
                           data: dict[str, Any], actor_id: Optional[str] = None) -> Optional[ContractRenewal]:
        contract = await self.get(db, organization_id=organization_id, contract_id=contract_id)
        if contract is None:
            return None
        renewal = ContractRenewal(
            organization_id=organization_id, contract_id=contract_id,
            status=data.get("status", "planned"),
            proposed_value=data.get("proposed_value"),
            due_date=to_date(data.get("due_date")),
            notes=data.get("notes"),
            recommended=bool(data.get("recommended", False)),
            reason=data.get("reason"),
        )
        db.add(renewal)
        contract.renewal_status = "due_soon" if contract.renewal_status == "not_due" else contract.renewal_status
        await _event_bus.publish(
            db, name="contract.renewal_planned", organization_id=organization_id, actor_id=actor_id,
            payload={"contract_id": contract.id, "renewal_id": renewal.id, "title": contract.title},
            flush=False,
        )
        await db.flush()
        return renewal

    async def list_renewals(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
                            contract_id: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(ContractRenewal, Contract).join(
            Contract, (Contract.organization_id == ContractRenewal.organization_id) & (Contract.id == ContractRenewal.contract_id)
        ).where(ContractRenewal.organization_id == organization_id)
        if status:
            query = query.where(ContractRenewal.status == status)
        if contract_id:
            query = query.where(ContractRenewal.contract_id == contract_id)
        rows = await db.execute(query.order_by(ContractRenewal.created_at.desc()))
        result = []
        for renewal, contract in rows.all():
            result.append({
                "id": renewal.id, "contract_id": renewal.contract_id, "contract_title": contract.title,
                "status": renewal.status, "proposed_value": renewal.proposed_value,
                "due_date": renewal.due_date.isoformat() if renewal.due_date else None,
                "notes": renewal.notes, "recommended": renewal.recommended, "reason": renewal.reason,
                "created_at": ensure_aware(renewal.created_at).isoformat() if renewal.created_at else None,
            })
        return result

    async def update_renewal(self, db: AsyncSession, *, organization_id: str, renewal_id: str,
                             data: dict[str, Any], actor_id: Optional[str] = None) -> Optional[ContractRenewal]:
        renewal = (
            await db.execute(
                select(ContractRenewal).where(
                    ContractRenewal.organization_id == organization_id, ContractRenewal.id == renewal_id
                )
            )
        ).scalar_one_or_none()
        if renewal is None:
            return None
        for field in ("status", "proposed_value", "due_date", "notes", "recommended", "reason"):
            if field in data and data[field] is not None:
                setattr(renewal, field, to_date(data[field]) if field == "due_date" else data[field])
        if data.get("status") == "completed":
            renewal.completed_at = utcnow()
            contract = await db.get(Contract, renewal.contract_id)
            if contract:
                contract.renewal_status = "renewed"
                await _event_bus.publish(
                    db, name="customer.renewed", organization_id=organization_id, actor_id=actor_id,
                    payload={"contract_id": contract.id, "customer_id": contract.customer_id,
                             "title": contract.title, "renewal_id": renewal.id},
                    flush=False,
                )
        await db.flush()
        return renewal

    async def delete_renewal(self, db: AsyncSession, *, organization_id: str, renewal_id: str) -> bool:
        renewal = (
            await db.execute(
                select(ContractRenewal).where(
                    ContractRenewal.organization_id == organization_id, ContractRenewal.id == renewal_id
                )
            )
        ).scalar_one_or_none()
        if renewal is None:
            return False
        await db.delete(renewal)
        await db.flush()
        return True


contract_service = ContractService()
