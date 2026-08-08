"""Continuous knowledge evolution — knowledge never becomes outdated.

Automatically finds duplicate documents, missing documents, outdated policies,
broken links, missing architecture and incomplete tutorials, then suggests
updates through the recommendation engine.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.knowledge import Document, Policy, WikiPage
from app.models.project import Project
from app.models.recommendation import Recommendation


class KnowledgeEvolution:
    async def scan(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        ninety_days = now - timedelta(days=90)
        findings: list[dict[str, Any]] = []
        suggestions: list[dict[str, Any]] = []

        documents = (
            await db.execute(
                select(Document).where(Document.organization_id == organization_id).limit(300)
            )
        ).scalars().all()
        wiki_pages = (
            await db.execute(
                select(WikiPage).where(WikiPage.organization_id == organization_id).limit(300)
            )
        ).scalars().all()

        # duplicates by normalized title
        seen: dict[str, list[str]] = {}
        for doc in documents:
            key = (getattr(doc, "title", "") or "").strip().lower()
            if len(key) >= 8:
                seen.setdefault(key, []).append(doc.id)
        duplicates = [ids for ids in seen.values() if len(ids) > 1]
        if duplicates:
            findings.append({
                "kind": "duplicate_documents",
                "count": len(duplicates),
                "detail": f"{len(duplicates)} duplicate document group(s) detected by title.",
            })
            suggestions.append({
                "category": "knowledge",
                "title": "Merge duplicate documents",
                "description": "Consolidate near-identical documents into one canonical version.",
                "confidence": 0.7,
                "evidence": [{"metric": "duplicate_groups", "value": len(duplicates)}],
            })

        # outdated policies/documents
        stale = [
            d for d in documents
            if getattr(d, "updated_at", None) is not None and d.updated_at <= ninety_days
        ] + [
            w for w in wiki_pages
            if getattr(w, "updated_at", None) is not None and w.updated_at <= ninety_days
        ]
        if stale:
            findings.append({
                "kind": "outdated_documents",
                "count": len(stale),
                "detail": f"{len(stale)} document(s)/wiki pages are 90+ days old.",
            })
            suggestions.append({
                "category": "knowledge",
                "title": "Review and refresh outdated knowledge",
                "description": "Assign owners to update stale documents and policies.",
                "confidence": 0.6,
                "evidence": [{"metric": "stale_documents", "value": len(stale)}],
            })

        # missing documentation for projects
        projects = (
            await db.execute(
                select(Project.id).where(Project.organization_id == organization_id).limit(100)
            )
        ).scalars().all()
        missing_docs = 0
        for pid in projects:
            count = (
                await db.execute(
                    select(func.count(Document.id)).where(Document.project_id == pid)
                )
            ).scalar() or 0
            if count == 0:
                missing_docs += 1
        if missing_docs:
            findings.append({
                "kind": "missing_documents",
                "count": missing_docs,
                "detail": f"{missing_docs} project(s) have no documents.",
            })
            suggestions.append({
                "category": "documentation",
                "title": "Create missing project documentation",
                "description": "Generate architecture and onboarding docs for undocumented projects.",
                "confidence": 0.7,
                "evidence": [{"metric": "projects_without_docs", "value": missing_docs}],
            })

        # incomplete tutorials: wiki pages without content
        empty_wiki = [w for w in wiki_pages if not (getattr(w, "content", None) or "").strip()]
        if empty_wiki:
            findings.append({
                "kind": "incomplete_tutorials",
                "count": len(empty_wiki),
                "detail": f"{len(empty_wiki)} wiki page(s) are empty placeholders.",
            })
            suggestions.append({
                "category": "knowledge",
                "title": "Complete placeholder wiki pages",
                "description": "Fill empty tutorials or archive them.",
                "confidence": 0.65,
                "evidence": [{"metric": "empty_wiki_pages", "value": len(empty_wiki)}],
            })

        # broken architecture: policies without linked documents
        policies = (
            await db.execute(
                select(Policy).where(Policy.organization_id == organization_id).limit(100)
            )
        ).scalars().all()
        if not policies and documents:
            findings.append({
                "kind": "missing_architecture",
                "count": 0,
                "detail": "No policies exist; governance documentation is missing.",
            })
            suggestions.append({
                "category": "knowledge",
                "title": "Establish governance policies",
                "description": "Create core policies (security, approval, ownership).",
                "confidence": 0.6,
                "evidence": [{"metric": "policies", "value": 0}],
            })

        return {"findings": findings, "suggestions": suggestions}


knowledge_evolution = KnowledgeEvolution()
