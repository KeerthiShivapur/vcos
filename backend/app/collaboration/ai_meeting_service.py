"""AI Meeting Intelligence (Phase 6.10/6.13) + knowledge integration.

Runs after a meeting ends to:
  - assemble a transcript from captions/chat/notes (when no STT pipeline is wired)
  - write the AI summary (rule-based when AI_PROVIDER=none)
  - extract action items -> create real Tasks (task.created_from_meeting)
  - record decisions (decision.recorded)
  - snapshot attendance intelligence
  - index the meeting into universal search + audit/event pipeline

The same entry point is used by the end-session API and by the
meeting_intel_worker (idempotent via the analytics snapshot).
"""

import json
import re
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.collab_base import emit_and_audit, parse_json
from app.collaboration.captions_service import transcript_service
from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import (
    MeetingAnalytics,
    MeetingCaption,
    MeetingChatMessage,
    MeetingDecision,
    MeetingNote,
    MeetingParticipant,
    MeetingSession,
)
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAgendaItem, MeetingAttendee


class AIMeetingService:
    # ------------------------------------------------------------- extraction

    _ACTION_PATTERNS = [
        re.compile(r"\b((?:i(?:'ll| will| shall| should)|we (?:should|need to|must|will|have to)) [a-z][\w\s\-]{6,150})", re.I),
        re.compile(r"\b((?:assigned|assign|please assign|someone should) [\w\s]{3,60})", re.I),
        re.compile(r"\b(action item|todo|to-do|follow[- ]up|next step)[:\-]?\s+([\w\s]{3,120})", re.I),
        re.compile(r"\b(need approval|awaiting approval|for approval|approve the)", re.I),
    ]

    _DECISION_PATTERNS = [
        re.compile(r"\b(we (?:decided|agreed|resolved|concluded)[^.!?]{3,140})", re.I),
        re.compile(r"\b(decision[:\-]?\s+[^.!?]{3,160})", re.I),
        re.compile(r"\b(finalized|locked in|going with|moving forward with)[^.!?]{3,120}", re.I),
    ]

    def extract_action_items(self, text: str) -> list[str]:
        found: list[str] = []
        for pattern in self._ACTION_PATTERNS:
            for match in pattern.finditer(text or ""):
                item = match.group(0).strip(" .;")
                item = re.sub(r"\s+", " ", item)
                if len(item) > 8 and item not in found:
                    found.append(item)
        return found[:20]

    def extract_decisions(self, text: str) -> list[str]:
        found: list[str] = []
        for pattern in self._DECISION_PATTERNS:
            for match in pattern.finditer(text or ""):
                item = match.group(0).strip(" .;")
                item = re.sub(r"\s+", " ", item)
                if len(item) > 8 and item not in found:
                    found.append(item)
        return found[:15]

    # ------------------------------------------------------------- summary

    def build_summary(
        self,
        meeting: Meeting,
        transcript_text: str,
        chat_text: list[str],
        notes_text: list[str],
        agenda_titles: list[str],
        attendee_names: list[str],
    ) -> str:
        """Rule-based summary — deterministic, no provider required."""
        parts: list[str] = []
        parts.append(f"{meeting.title} ({meeting.meeting_type})")
        if attendee_names:
            parts.append(f"Attendees: {', '.join(attendee_names[:10])}")
        if agenda_titles:
            parts.append(f"Agenda: {'; '.join(agenda_titles)}")
        if transcript_text:
            sentences = [s.strip() for s in re.split(r"[.!?]+", transcript_text) if len(s.strip()) > 40]
            parts.append(f"Key points: {'; '.join(sentences[:5])}")
        if notes_text:
            parts.append(f"Notes: {' | '.join(n[:140] for n in notes_text[:3])}")
        if chat_text:
            parts.append(f"Chat highlights: {'; '.join(c[:120] for c in chat_text[:3])}")
        actions = self.extract_action_items(transcript_text + " " + " ".join(chat_text))
        if actions:
            parts.append(f"Action items: {'; '.join(actions[:8])}")
        decisions = self.extract_decisions(transcript_text + " " + " ".join(chat_text))
        if decisions:
            parts.append(f"Decisions: {'; '.join(decisions[:6])}")
        return ". ".join(parts) + "."

    # ------------------------------------------------------------- finalize

    async def assemble_transcript(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: Optional[MeetingSession],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Build a pseudo-transcript from captions, chat and notes."""
        captions = (
            await db.execute(
                select(MeetingCaption).where(
                    MeetingCaption.organization_id == organization_id,
                    MeetingCaption.meeting_id == meeting.id,
                ).order_by(MeetingCaption.start_ms.asc())
            )
        ).scalars().all()
        chat = (
            await db.execute(
                select(MeetingChatMessage).where(
                    MeetingChatMessage.organization_id == organization_id,
                    MeetingChatMessage.meeting_id == meeting.id,
                    MeetingChatMessage.kind == "message",
                ).order_by(MeetingChatMessage.created_at.asc())
            )
        ).scalars().all()
        notes = (
            await db.execute(
                select(MeetingNote).where(
                    MeetingNote.organization_id == organization_id,
                    MeetingNote.meeting_id == meeting.id,
                ).order_by(MeetingNote.updated_at.asc())
            )
        ).scalars().all()
        employees: dict[str, Employee] = {}
        for emp_id in {c.employee_id for c in captions if c.employee_id} | {m.employee_id for m in chat if m.employee_id}:
            emp = await db.get(Employee, emp_id)
            if emp:
                employees[emp_id] = emp

        segments: list[dict[str, Any]] = []
        for caption in captions:
            emp = employees.get(caption.employee_id)
            segments.append(
                {
                    "speaker": emp.full_name if emp else "Unknown",
                    "employee_id": caption.employee_id,
                    "start_ms": caption.start_ms,
                    "text": caption.text,
                }
            )
        lines = [f"{seg['speaker']}: {seg['text']}" for seg in segments]
        lines += [f"{employees.get(m.employee_id).full_name if m.employee_id in employees else 'Chat'}: {m.content}" for m in chat]
        lines += [f"Notes: {n.content[:300]}" for n in notes if n.content.strip()]
        text = "\n".join(lines)

        speaker_ms: dict[str, int] = {}
        for caption in captions:
            speaker_ms[caption.employee_id or "unknown"] = speaker_ms.get(caption.employee_id or "unknown", 0) + (caption.end_ms - caption.start_ms)
        speakers = [
            {
                "employee_id": emp_id,
                "name": employees[emp_id].full_name if emp_id in employees else "Unknown",
                "speaking_ms": ms,
            }
            for emp_id, ms in sorted(speaker_ms.items(), key=lambda kv: -kv[1])
        ]
        return text, segments, speakers

    async def finalize(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: Optional[MeetingSession],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> dict[str, Any]:
        """End-of-meeting intelligence. Idempotent: skips work if analytics exist."""
        existing = (
            await db.execute(
                select(MeetingAnalytics.id).where(
                    MeetingAnalytics.organization_id == organization_id,
                    MeetingAnalytics.meeting_id == meeting.id,
                )
            )
        ).scalar_one_or_none()
        already = existing is not None
        if already:
            return {"already_finalized": True}

        transcript_text, segments, speakers = await self.assemble_transcript(
            db, organization_id=organization_id, meeting=meeting, session=session
        )
        await transcript_service.get_or_create(
            db, organization_id=organization_id, meeting_id=meeting.id,
            session_id=session.id if session else None,
        )
        transcript = await transcript_service.get(db, organization_id=organization_id, meeting_id=meeting.id)
        if transcript is not None and transcript.status in ("requested", "transcribing") and transcript_text:
            await transcript_service.save(
                db, transcript=transcript, content=transcript_text,
                segments=segments, speakers=speakers, status="completed",
            )

        chat_rows = (
            await db.execute(
                select(MeetingChatMessage.content).where(
                    MeetingChatMessage.organization_id == organization_id,
                    MeetingChatMessage.meeting_id == meeting.id,
                    MeetingChatMessage.kind == "message",
                )
            )
        ).scalars().all()
        notes_rows = (
            await db.execute(
                select(MeetingNote.content).where(
                    MeetingNote.organization_id == organization_id,
                    MeetingNote.meeting_id == meeting.id,
                )
            )
        ).scalars().all()
        agenda_rows = (
            await db.execute(
                select(MeetingAgendaItem.title).where(
                    MeetingAgendaItem.organization_id == organization_id,
                    MeetingAgendaItem.meeting_id == meeting.id,
                )
            )
        ).scalars().all()
        attendee_rows = (
            await db.execute(
                select(MeetingAttendee.employee_id).where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.meeting_id == meeting.id,
                )
            )
        ).scalars().all()
        names: list[str] = []
        for emp_id in list(attendee_rows)[:12]:
            emp = await db.get(Employee, emp_id)
            if emp:
                names.append(emp.full_name)

        summary = self.build_summary(
            meeting,
            transcript_text,
            list(chat_rows),
            list(notes_rows),
            list(agenda_rows),
            names,
        )
        meeting.ai_summary = summary
        meeting.transcript_summary = summary[:2000]
        meeting.updated_at = utcnow()

        # ---- action items -> real tasks (Phase 6.13)
        from app.work.task_service import task_service
        from app.work.meeting_service import meeting_service

        created_tasks: list[dict[str, Any]] = []
        source_text = transcript_text + " " + " ".join(chat_rows)
        for raw in self.extract_action_items(source_text):
            action = await meeting_service.add_action_item(
                db,
                organization_id=organization_id,
                meeting_id=meeting.id,
                data={"title": raw[:240], "assignee_id": meeting.organizer_id},
            )
            try:
                task = await task_service.create(
                    db,
                    organization_id=organization_id,
                    data={
                        "title": raw[:240],
                        "description": (
                            f"Auto-created from meeting \"{meeting.title}\" (meeting.action_item "
                            f"{action.id}). Source: {raw}"
                        )[:2000],
                        "priority": "medium",
                        "assignee_id": meeting.organizer_id,
                        "project_id": meeting.project_id,
                        "due_date": (ensure_aware(meeting.end_at) + timedelta(days=3)).date()
                        if meeting.end_at else None,
                    },
                    actor=actor,
                    ip_address=ip_address,
                )
                created_tasks.append({"task_id": task.id, "action_item_id": action.id, "title": task.title})
            except Exception:
                pass

        # ---- decisions (Phase 6.10)
        decisions: list[str] = []
        for raw in self.extract_decisions(source_text):
            decision = MeetingDecision(
                organization_id=organization_id,
                meeting_id=meeting.id,
                session_id=session.id if session else None,
                content=raw[:1000],
                made_by=meeting.organizer_id,
                source="ai",
                status="draft",
                created_at=utcnow(),
            )
            db.add(decision)
            await db.flush()
            decisions.append(decision.id)

        # ---- attendance + analytics snapshot (Phase 6.11)
        from app.collaboration.attendance_service import attendance_service

        metrics = await attendance_service.metrics(
            db, organization_id=organization_id, meeting=meeting, session=session
        )
        snapshot = await attendance_service.snapshot(
            db, organization_id=organization_id, meeting=meeting, session=session, metrics=metrics
        )

        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="meeting.intelligence_generated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={
                "meeting_id": meeting.id,
                "session_id": session.id if session else None,
                "summary": bool(summary),
                "action_items": len(created_tasks),
                "decisions": len(decisions),
                "transcript_words": transcript.word_count if transcript else 0,
            },
            resource_type="meeting",
            resource_id=meeting.id,
        )
        return {
            "summary": summary,
            "action_items": created_tasks,
            "decisions": decisions,
            "analytics_id": snapshot.id,
            "already_finalized": False,
        }


ai_meeting_service = AIMeetingService()
