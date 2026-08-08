"""Industry AI router (Phase 17.13).

Every industry pack ships AI model profiles (system prompt, terminology,
knowledge scope, guardrails, skill prompts). This router turns those profiles
into live, industry-aware assistants that reuse the shared AI gateway — the
same provider pool, safety layer, token accounting and caching used by the
companion.

Routing rules:
  - external providers (groq/openai/anthropic) receive the profile system
    prompt + grounded org context, with guardrails appended;
  - the built-in VCOS intelligence engine (no API key) answers deterministically
    from the pack's knowledge (modules, KPIs, compliance frameworks) so the
    industry assistant is always available, even offline.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ai_gateway
from app.ai.provider import ChatMessage
from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.industry.framework.registry import (
    get_pack,
    pack_ai_models,
    pack_compliance,
    pack_kpis,
    pack_modules,
)
from app.models.industry_configuration import IndustryAIModel
from app.models.organization import gen_uuid

logger = logging.getLogger("vcos.industry.ai")

_EXTERNAL_PROVIDERS = ("groq", "openai", "anthropic")


class IndustryAIRouter:
    """Routes requests to the right industry AI profile and provider."""

    async def list_profiles(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
    ) -> list[IndustryAIModel]:
        """Return the pack's AI profiles, creating rows on first access so
        every installed pack gets queryable, org-scoped profiles."""
        definitions = pack_ai_models(industry_key)
        rows = (
            (
                await db.execute(
                    select(IndustryAIModel).where(
                        IndustryAIModel.industry_key == industry_key
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = {row.model_key: row for row in rows}
        created: list[IndustryAIModel] = []
        for definition in definitions:
            row = existing.get(definition["key"])
            if row is None:
                row = IndustryAIModel(
                    id=gen_uuid(),
                    industry_key=industry_key,
                    model_key=definition["key"],
                    name=definition["name"],
                    system_prompt=definition.get("system_prompt"),
                    terminology=definition.get("terminology") or [],
                    knowledge_scope=definition.get("knowledge_scope") or {},
                    guardrails=definition.get("guardrails") or [],
                    skill_prompts=definition.get("skills") or {},
                )
                db.add(row)
                existing[definition["key"]] = row
                created.append(row)
        if created:
            await db.flush()
        return sorted(existing.values(), key=lambda r: r.name)

    async def default_model_key(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
    ) -> str:
        """First enabled profile for the pack — the chat default."""
        profiles = await self.list_profiles(
            db, organization_id=organization_id, industry_key=industry_key
        )
        enabled = [p for p in profiles if p.enabled]
        if not enabled:
            raise ValueError(f"no enabled AI profile for {industry_key}")
        return enabled[0].model_key

    async def get_profile(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        model_key: str,
    ) -> Optional[IndustryAIModel]:
        profiles = await self.list_profiles(db, organization_id=organization_id, industry_key=industry_key)
        return next((p for p in profiles if p.model_key == model_key and p.enabled), None)

    async def set_enabled(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        model_key: str,
        enabled: bool,
        actor_id: Optional[str] = None,
    ) -> Optional[IndustryAIModel]:
        profile = await self.get_profile(
            db, organization_id=organization_id, industry_key=industry_key, model_key=model_key
        )
        if profile is None:
            profiles = await self.list_profiles(db, organization_id=organization_id, industry_key=industry_key)
            profile = next((p for p in profiles if p.model_key == model_key), None)
        if profile is None:
            return None
        profile.enabled = enabled
        profile.updated_by = actor_id
        await publish_event(
            db,
            name="industry.ai.updated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "industry_key": industry_key,
                "model_key": model_key,
                "field": "enabled",
                "value": enabled,
            },
        )
        return profile

    async def update_profile(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        model_key: str,
        actor_id: Optional[str] = None,
        changes: Optional[dict[str, Any]] = None,
    ) -> Optional[IndustryAIModel]:
        """Org-level overrides: system_prompt / temperature / guardrails."""
        changes = changes or {}
        profile = await self.get_profile(
            db, organization_id=organization_id, industry_key=industry_key, model_key=model_key
        )
        if profile is None:
            profiles = await self.list_profiles(db, organization_id=organization_id, industry_key=industry_key)
            profile = next((p for p in profiles if p.model_key == model_key), None)
        if profile is None:
            return None
        if "system_prompt" in changes:
            profile.system_prompt = changes["system_prompt"]
        if "temperature" in changes:
            profile.temperature = float(changes["temperature"])
        if "guardrails" in changes:
            profile.guardrails = list(changes["guardrails"])
        if "knowledge_scope" in changes:
            profile.knowledge_scope = changes["knowledge_scope"]
        profile.updated_by = actor_id
        await publish_event(
            db,
            name="industry.ai.updated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "industry_key": industry_key,
                "model_key": model_key,
                "field": ",".join(changes.keys()),
            },
        )
        return profile

    # ------------------------------------------------------------------ chat

    async def chat(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        model_key: str,
        question: str,
        skill: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        pack = get_pack(industry_key)
        if pack is None:
            raise ValueError(f"unknown industry '{industry_key}'")
        profile = await self.get_profile(
            db, organization_id=organization_id, industry_key=industry_key, model_key=model_key
        )
        if profile is None:
            available = [p["key"] for p in pack_ai_models(industry_key)]
            raise ValueError(
                f"no enabled AI profile '{model_key}' for {industry_key} "
                f"(available: {', '.join(available)})"
            )

        system_prompt = self._build_system_prompt(pack, profile, skill)
        grounded: dict[str, Any] = {
            "industry_key": industry_key,
            "model_key": profile.model_key,
            "profile": profile.name,
            "_llm": False,
            "_local": True,
        }
        if context:
            grounded.update({k: v for k, v in context.items() if k != "answer"})

        status = await ai_gateway.status()
        if status.get("provider") in _EXTERNAL_PROVIDERS:
            result = await ai_gateway.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(
                        role="user",
                        content=question,
                    ),
                ],
                org_id=organization_id,
            )
            if result.get("available") and result.get("content"):
                grounded["_llm"] = True
                grounded["_local"] = False
                return {
                    "content": result["content"],
                    "provider": result.get("provider", status.get("provider")),
                    "model": result.get("model"),
                    "grounded": grounded,
                    "skill": skill,
                    "profile": profile.model_key,
                }

        return {
            "content": self._local_answer(pack, profile, question, skill),
            "provider": "vcos",
            "model": "industry-rules",
            "grounded": grounded,
            "skill": skill,
            "profile": profile.model_key,
        }

    # ------------------------------------------------------------------ build

    def _build_system_prompt(
        self, pack: dict[str, Any], profile: IndustryAIModel, skill: Optional[str]
    ) -> str:
        blocks: list[str] = []
        if skill and (profile.skill_prompts or {}).get(skill):
            blocks.append(f"AI_DIRECTIVE=structured\nAI_TEMPLATE={profile.skill_prompts[skill]}")
        base = profile.system_prompt or (
            f"You are the {profile.name} for {pack.get('name', pack['key'])}. "
            "Answer from the organization's grounded data only."
        )
        blocks.append(base)
        if profile.terminology:
            blocks.append("Terminology: " + ", ".join(profile.terminology))
        if profile.knowledge_scope and profile.knowledge_scope.get("domains"):
            blocks.append("Knowledge scope: " + ", ".join(profile.knowledge_scope["domains"]))
        if profile.guardrails:
            blocks.append(
                "Guardrails:\n" + "\n".join(f"- {g}" for g in profile.guardrails)
            )
        blocks.append(
            "Answer concisely in the user's language using ONLY the grounded data "
            "provided. If the data is insufficient, say what extra data you need."
        )
        return "\n\n".join(blocks)

    def _local_answer(
        self,
        pack: dict[str, Any],
        profile: IndustryAIModel,
        question: str,
        skill: Optional[str],
    ) -> str:
        industry = pack.get("name", pack["key"])
        if skill and (profile.skill_prompts or {}).get(skill):
            return (
                f"{profile.skill_prompts[skill]} — running in local mode with the "
                f"{industry} pack. Connect an LLM provider in Settings for richer answers."
            )
        modules = ", ".join(m["name"] for m in pack_modules(pack["key"])[:6])
        kpis = ", ".join(f"{k['name']} ({k['benchmark']} {k.get('unit', '')})" for k in pack_kpis(pack["key"])[:5])
        frameworks = ", ".join(c["framework"] for c in pack_compliance(pack["key"]))
        return (
            f"I'm the {profile.name} for {industry}. I can help with operations, "
            f"compliance and analytics. Current pack knowledge:\n"
            f"- Modules: {modules}\n"
            f"- Key KPIs: {kpis}\n"
            f"- Compliance frameworks: {frameworks}\n\n"
            f"Your question: {question[:200]}\n"
            "I'm running in local mode — connect a Groq API key in Settings for "
            "richer, free-form answers."
        )

    async def status(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
    ) -> dict[str, Any]:
        profiles = await self.list_profiles(db, organization_id=organization_id, industry_key=industry_key)
        gateway_status = await ai_gateway.status()
        return {
            "industry_key": industry_key,
            "profiles": [
                {
                    "model_key": p.model_key,
                    "name": p.name,
                    "enabled": p.enabled,
                    "skills": list((p.skill_prompts or {}).keys()),
                    "guardrails": len(p.guardrails or []),
                }
                for p in profiles
            ],
            "gateway": {
                "provider": gateway_status.get("provider"),
                "available": gateway_status.get("available"),
            },
            "updated_at": utcnow().isoformat(),
        }


industry_ai_router = IndustryAIRouter()
