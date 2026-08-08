"""AI Learning Companion (Phase 10.15 — AI Learning Companion).

Heuristic AI that answers the companion questions the spec demands:
  - "What should I learn?"          → skill gaps + courses
  - "Who should mentor me?"         → recommended mentors
  - "Am I ready for promotion?"     → career readiness + evidence
  - "What skills are missing?"      → open skill gaps
  - "Recommend next certification"  → gap-aligned certifications
  - "Find an internal expert."      → experts by skill
  - "Create my learning roadmap."   → enroll in a path + refresh feed

The engine is deterministic and provider-agnostic so it works identically
in tests (AI_PROVIDER=none) and production.
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.academy_service import academy_service
from app.learning.career_service import career_service
from app.learning.certification_service import certification_service
from app.learning.course_service import course_service
from app.learning.learning_path_service import learning_path_service
from app.learning.mentorship_service import mentorship_service
from app.learning.recommendation_service import recommendation_service
from app.learning.skill_service import skill_service

logger = logging.getLogger("vcos.learning.ai")

_INTENTS = {
    "learn": ("what should i learn", "what should i learn?", "recommend learning", "recommend me learning"),
    "mentor": ("who should mentor me", "recommend a mentor", "find me a mentor", "who can mentor"),
    "promotion": ("am i ready for promotion", "promotion readiness", "ready for a promotion"),
    "missing": ("what skills are missing", "what skills am i missing", "skill gaps", "missing skills"),
    "certification": ("recommend next certification", "next certification", "recommend a certification"),
    "expert": ("find an internal expert", "find an expert", "who knows", "internal expert"),
    "roadmap": ("create my learning roadmap", "learning roadmap", "create a roadmap"),
    "plan": ("create study plan", "study plan", "create a study plan"),
}


class LearningAiService:
    def classify(self, question: str) -> Optional[str]:
        text = question.lower().strip()
        best: Optional[str] = None
        best_score = 0
        for intent, phrases in _INTENTS.items():
            for phrase in phrases:
                if phrase in text or (len(text) > 8 and all(word in text for word in phrase.split(" ")[:2])):
                    score = len(phrase)
                    if score > best_score:
                        best_score = score
                        best = intent
        return best

    async def answer(self, db: AsyncSession, *, organization_id: str, employee_id: str, question: str) -> dict[str, Any]:
        result = await self._route_answer(
            db, organization_id=organization_id, employee_id=employee_id, question=question
        )
        result["response"] = result.get("answer", "")
        return result

    async def _route_answer(self, db: AsyncSession, *, organization_id: str, employee_id: str, question: str) -> dict[str, Any]:
        intent = self.classify(question)
        if intent is None:
            return {
                "intent": "general",
                "answer": "I can help with: what should I learn? who should mentor me? am I ready for promotion? "
                "what skills are missing? recommend a certification. find an internal expert. create my learning roadmap.",
                "suggestions": list(_INTENTS.keys()),
            }
        if intent == "learn":
            return await self._what_to_learn(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "mentor":
            return await self._mentors(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "promotion":
            return await self._promotion(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "missing":
            return await self._missing(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "certification":
            return await self._certification(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "expert":
            return await self._expert(db, organization_id=organization_id, employee_id=employee_id, question=question)
        if intent == "roadmap":
            return await self._roadmap(db, organization_id=organization_id, employee_id=employee_id)
        if intent == "plan":
            return await self._plan(db, organization_id=organization_id, employee_id=employee_id)
        result = {"intent": intent, "answer": "Let me look that up."}
        return result

    async def _what_to_learn(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        gaps = await skill_service.list_gaps(db, organization_id=organization_id, employee_id=employee_id, status="open")
        courses = await course_service.recommended_for(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_names=[gap.skill_name for gap in gaps], limit=5,
        )
        return {
            "intent": "learn",
            "answer": "Focus on your highest-priority skill gaps.",
            "gaps": [
                {
                    "skill": gap.skill_name,
                    "current": gap.current_level,
                    "required": gap.required_level,
                    "priority": gap.priority,
                }
                for gap in gaps[:6]
            ],
            "courses": [{"id": course.id, "title": course.title, "category": course.category} for course in courses],
        }

    async def _mentors(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        progress = await career_service.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        skills = [r.get("skill") or r.get("name") for r in (progress.get("next") or {}).get("required_skills", [])]
        mentors = await mentorship_service.recommend_mentors(
            db, organization_id=organization_id, employee_id=employee_id, skills=skills, limit=4
        )
        return {
            "intent": "mentor",
            "answer": "Here are the mentors best matched to your goals.",
            "mentors": [
                {"employee_id": m["employee_id"], "name": m["name"], "topics": m["topics"], "availability": m["availability"]}
                for m in mentors
            ],
        }

    async def _promotion(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        progress = await career_service.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        ready = progress.get("promotion_ready", False)
        return {
            "intent": "promotion",
            "answer": (
                f"You are {'ready' if ready else 'not yet ready'} for {progress.get('next', {}).get('title', 'the next step')} "
                f"(readiness {progress.get('readiness', 0)}%)."
            ),
            "readiness": progress.get("readiness"),
            "next": progress.get("next"),
            "evidence": progress.get("evidence", [])[:10],
        }

    async def _missing(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        gaps = await skill_service.list_gaps(db, organization_id=organization_id, employee_id=employee_id, status="open")
        return {
            "intent": "missing",
            "answer": f"You have {len(gaps)} open skill gaps.",
            "gaps": [
                {
                    "skill": gap.skill_name,
                    "current": gap.current_level,
                    "required": gap.required_level,
                    "priority": gap.priority,
                    "source": gap.source,
                }
                for gap in gaps[:10]
            ],
        }

    async def _certification(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        gaps = await skill_service.list_gaps(db, organization_id=organization_id, employee_id=employee_id, status="open")
        certifications = await certification_service.recommended_for(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_names=[gap.skill_name for gap in gaps], limit=4,
        )
        return {
            "intent": "certification",
            "answer": "These internal certifications align with your skill gaps.",
            "certifications": [
                {"id": cert.id, "name": cert.name, "category": cert.category, "level": cert.level}
                for cert in certifications
            ],
        }

    async def _expert(self, db: AsyncSession, *, organization_id: str, employee_id: str, question: str) -> dict[str, Any]:
        # extract a possible skill mention from the question
        skills = await self._catalog_skills(db, organization_id=organization_id)
        found = None
        for skill in skills:
            if skill.lower() in question.lower():
                found = skill
                break
        experts = await skill_service.who_has_skill(
            db, organization_id=organization_id, skill_name=found or " ", min_level=3, limit=5
        ) if found else []
        return {
            "intent": "expert",
            "answer": f"Experts in {found or 'your organization'}:" if found else "Name a skill to find its experts (e.g. Kubernetes).",
            "experts": experts[:5],
        }

    async def _catalog_skills(self, db: AsyncSession, *, organization_id: str) -> list[str]:
        from sqlalchemy import select
        from app.models.skill import Skill
        rows = await db.execute(
            select(Skill.name).where(Skill.organization_id == organization_id).limit(200)
        )
        return [name for (name,) in rows.all()]

    async def _roadmap(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        paths = await learning_path_service.list_paths(db, organization_id=organization_id)
        progress = await career_service.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        recommended = None
        for path in paths:
            if progress.get("path_title") and progress["path_title"].lower() in path.title.lower():
                recommended = path
                break
        recommended = recommended or paths[0] if paths else None
        if recommended is None:
            return {"intent": "roadmap", "answer": "No learning paths published yet.", "paths": []}
        enrollment = await learning_path_service.enroll(
            db, organization_id=organization_id, path_id=recommended.id, employee_id=employee_id
        )
        created = await recommendation_service.refresh_for_employee(
            db, organization_id=organization_id, employee_id=employee_id
        )
        return {
            "intent": "roadmap",
            "answer": f"Your learning roadmap starts with {recommended.title}. I refreshed your recommendation feed ({created} new items).",
            "path": {"id": recommended.id, "title": recommended.title, "target_role": recommended.target_role},
            "recommendations_created": created,
        }

    async def _plan(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        roadmap = await self._roadmap(db, organization_id=organization_id, employee_id=employee_id)
        roadmap["intent"] = "plan"
        roadmap["answer"] = f"Study plan: {roadmap['answer']} Follow the path steps and your daily recommendation feed."
        return roadmap


learning_ai_service = LearningAiService()
