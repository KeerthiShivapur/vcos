"""AI Companion — grounded work intelligence (Phase 7.6 orchestrator).

Pipeline for every companion question:

  1. Build the grounded context bundle (who, page, entities, memories, knowledge).
  2. Detect intents and run the matching agent tool for a rule-based answer.
  3. When an LLM provider is configured, feed the grounded context + tool
     output to the gateway for a natural-language answer (Groq streaming ready).
  4. Persist the conversation and messages, push working memory.

Every answer returns its evidence (grounded data, tools used, intents) so the
frontend can show exactly what the companion based its answer on.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import TOOL_DESCRIPTIONS, agent
from app.ai.actions import action_engine, extract_action
from app.ai.context import context_engine
from app.ai.gateway import ai_gateway
from app.ai.memory import memory_manager
from app.ai.prompts import SYSTEM_CORE
from app.ai.provider import ChatMessage
from app.models.ai import AIConversation, AIMessage
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

_INTENT_PHRASES: dict[str, tuple[str, ...]] = {
    "my_day": ("today", "my day", "what should i work on", "start on", "focus on"),
    "org_pulse": ("org pulse", "company pulse", "org health", "how is the company", "executive summary", "dashboard"),
    "knowledge": (
        "find document", "find a document", "where is the document", "knowledge base", "wiki",
        "company policy", "our policies", "sop for", "decision made", "decisions", "how do we",
        "what is the process", "who wrote", "related documents", "search the knowledge",
    ),
    "expert": ("expert", "who knows", "who is the best", "find someone", "specialist", "skill"),
    "entity": ("summarize", "summary"),
    "search": ("search for", "find me", "look up"),
    "action": (
        "create a task", "add a task", "create task", "add task", "make a task", "new task",
        "to-do", "schedule a meeting", "book a meeting", "set up a meeting", "schedule meeting",
        "remember that", "note that", "mark ",
    ),
}


class CompanionService:
    def detect_intents(self, text: str, context: dict[str, Any]) -> list[str]:
        lowered = (text or "").lower()
        intents: list[str] = []
        for intent, phrases in _INTENT_PHRASES.items():
            if any(phrase in lowered for phrase in phrases):
                intents.append(intent)
        for key in ("project", "task", "goal", "meeting"):
            if key in lowered and context.get(f"{key}_id"):
                intents.append(key)
        return intents

    async def answer(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        message: str,
        context: Optional[dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        context = context or {}
        text = (message or "").strip()
        intents = self.detect_intents(text, context)
        bundle = await context_engine.build(
            db, organization_id=organization_id, user=user, message=text, context=context
        )
        tool_name = agent.intent_to_tool(intents, context)
        tool_result: dict[str, Any] = {"answer": "", "tools": []}
        if tool_name:
            if tool_name in ("search", "expert_finder"):
                context["query"] = self._extract_query(text, tool_name)
            tool_result = await agent.run(
                db, organization_id=organization_id, user=user, tool_name=tool_name, context=context
            )

        action = extract_action(text, context)
        if action:
            action_result = await self._run_action(
                db, organization_id=organization_id, user=user, text=text,
                action_type=action[0], payload=action[1],
            )
            if action_result:
                tool_result = {"answer": action_result["answer"], "tools": ["action"], "data": action_result["data"]}

        answer, source, grounded = await self._compose(
            db, organization_id=organization_id, text=text, context=context,
            bundle=bundle, tool_result=tool_result, intents=intents,
        )

        conversation_id, message_id = await self._persist(
            db, organization_id=organization_id, user=user, text=text,
            answer=answer, intents=intents, source=source, grounded=grounded,
            conversation_id=conversation_id, context=context,
        )
        memory_manager.working.push(
            organization_id=organization_id, user_id=user.id, role="user", content=text
        )
        memory_manager.working.push(
            organization_id=organization_id, user_id=user.id, role="assistant", content=answer
        )
        return {
            "answer": answer,
            "source": source,
            "grounded": grounded,
            "intents": intents,
            "context": context,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "tools": tool_result["tools"],
            "stream": stream,
        }

    async def _run_action(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        text: str,
        action_type: str,
        payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        codes = await permission_service.user_permission_codes(db, user.id, organization_id)
        permitted = action_engine.requires_permission(action_type) in codes
        result = await action_engine.execute(
            db,
            organization_id=organization_id,
            user=user,
            action_type=action_type,
            payload=payload,
            permitted=permitted,
        )
        status = result.get("status")
        if status == "rejected":
            return {
                "answer": (
                    f"I can't do that — it requires the '{result.get('reason', 'permission')}' permission, "
                    "which you don't have. Ask an admin to grant it."
                ),
                "data": {"action": action_type, "status": "rejected"},
            }
        if status == "failed":
            return {
                "answer": f"That didn't work: {result.get('reason', 'unknown error')}",
                "data": {"action": action_type, "status": "failed"},
            }
        if action_type == "create_task":
            answer = f"Done — I created the task '{result['title']}' for you. View it at {result.get('url', '')}."
        elif action_type == "update_task_status":
            answer = f"Done — task '{result['title']}' is now {result['status']}."
        elif action_type == "schedule_meeting":
            answer = f"Done — meeting '{result['title']}' is scheduled. View it at {result.get('url', '')}."
        elif action_type == "remember":
            answer = "Done — I'll remember that."
        else:
            answer = f"Done — {action_type} executed."
        return {"answer": answer, "data": {"action": action_type, "result": result}}

    def _extract_query(self, text: str, tool_name: str) -> str:
        stripped = text
        for prefix in (
            "search for", "search", "find me", "find", "look up", "who knows",
            "who is the best", "find someone", "expert on", "expert in",
            "specialist in", "do you have", "where is",
        ):
            if stripped.lower().startswith(prefix):
                stripped = stripped[len(prefix):].strip(" :,?.")
                break
        return stripped or text

    async def _compose(
        self, db, *, organization_id, text, context, bundle, tool_result, intents,
    ) -> tuple[str, str, dict[str, Any]]:
        org = await db.get(Organization, organization_id)
        org_name = org.name if org else "your company"
        grounded: dict[str, Any] = {"_llm": False}
        if tool_result.get("data"):
            grounded.update(
                {k: v for k, v in tool_result["data"].items() if k not in ("answer",)}
            )
        for key in ("project_id", "task_id", "goal_id", "meeting_id"):
            if context.get(key):
                grounded.setdefault(key, context[key])
        grounded["context"] = bundle.to_json()

        prompt_blocks: list[str] = []
        if bundle.to_prompt():
            prompt_blocks.append(bundle.to_prompt())
        if tool_result.get("answer"):
            prompt_blocks.append(f"## tool_output\n{tool_result['answer']}")
        grounded_context = "\n\n".join(prompt_blocks)

        if not text:
            text = "What should I focus on today?"
        provider_status = await ai_gateway.status()
        if provider_status.get("provider") in ("openai", "anthropic", "groq"):
            result = await ai_gateway.chat(
                [
                    ChatMessage(
                        role="system",
                        content=SYSTEM_CORE.format(organization_name=org_name)
                        + "\nAnswer concisely in the user's language using ONLY the grounded data provided. "
                        + "If the data is insufficient, say what extra data you would need. "
                        + "When citing a document or person, include its URL from the context.",
                    ),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Grounded context:\n{grounded_context}\n\nQuestion: {text}"
                            if grounded_context
                            else text
                        ),
                    ),
                ]
            )
            if result.get("available") and result.get("content"):
                grounded["_llm"] = True
                return result["content"], "llm", grounded

        if tool_result.get("answer"):
            return tool_result["answer"], "rules", grounded
        if intents:
            known = ", ".join(TOOL_DESCRIPTIONS.get(i, i) for i in intents)
            return (
                f"I can help with: {known}. Ask me e.g. 'What should I work on today?' "
                "or 'Give me the org pulse'.",
                "rules",
                grounded,
            )
        return (
            "I can answer with live company data when you ask for: 'What should I work on today?', "
            "'Org pulse', or open a project/task/goal/meeting and ask me to summarize it.",
            "rules",
            grounded,
        )

    async def _persist(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        text: str,
        answer: str,
        intents: list[str],
        source: str,
        grounded: dict[str, Any],
        conversation_id: Optional[str],
        context: dict[str, Any],
    ) -> tuple[str, str]:
        conversation = None
        if conversation_id:
            conversation = await db.get(AIConversation, conversation_id)
        if conversation is None or conversation.organization_id != organization_id:
            conversation = AIConversation(
                organization_id=organization_id,
                user_id=user.id,
                source="chat",
                title=(text or "Companion conversation")[:300],
            )
            db.add(conversation)
            await db.flush()
        user_msg = AIMessage(
            conversation_id=conversation.id,
            organization_id=organization_id,
            user_id=user.id,
            role="user",
            content=text,
            intents=",".join(intents) or None,
        )
        db.add(user_msg)
        assistant_msg = AIMessage(
            conversation_id=conversation.id,
            organization_id=organization_id,
            user_id=user.id,
            role="assistant",
            content=answer,
            intents=",".join(intents) or None,
            source=source,
            model=self._current_model(),
            context_json=grounded.get("context"),
        )
        db.add(assistant_msg)
        await db.flush()
        return conversation.id, assistant_msg.id

    def _current_model(self) -> Optional[str]:
        try:
            status = ai_gateway._config()
            return status.get("model")
        except Exception:
            return None

    async def history(self, db: AsyncSession, *, conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(AIMessage)
                .where(AIMessage.conversation_id == conversation_id)
                .order_by(AIMessage.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "source": m.source,
                "intents": m.intents,
            }
            for m in rows
        ]


companion_service = CompanionService()
