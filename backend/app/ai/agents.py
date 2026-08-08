"""Phase 7.5 — agent layer.

A lightweight tool-calling agent: the companion's intents map to concrete
tools that read live tenant data (my day, org pulse, entity summaries,
universal search, expert finder). Each run returns the answer text plus the
list of tools used and their outputs so the response can cite evidence.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.search import universal_search
from app.models.employee import Employee
from app.models.goal import Goal, KeyResult
from app.models.meeting import Meeting, MeetingActionItem, MeetingAgendaItem, MeetingAttendee
from app.models.organization import Organization
from app.models.project import Project
from app.models.skill import ExpertiseScore, Skill
from app.models.task import Task
from app.models.user import User


async def tool_my_day(db, organization_id: str, user: User, **kwargs) -> dict[str, Any]:
    from app.core.timeutils import utcnow

    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id, Employee.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        return {"error": "no_employee_profile"}
    now = utcnow()
    today = now.date()
    tasks = (
        await db.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.assignee_id == employee.id,
                Task.status.notin_(("completed", "archived")),
            )
            .order_by(Task.due_date.asc().nulls_last())
        )
    ).scalars().all()
    meetings = (
        await db.execute(
            select(Meeting)
            .join(MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id)
            .where(
                Meeting.organization_id == organization_id,
                MeetingAttendee.employee_id == employee.id,
                Meeting.status.in_(("scheduled", "in_progress")),
                Meeting.start_at >= now,
            )
            .order_by(Meeting.start_at.asc())
            .limit(10)
        )
    ).scalars().all()
    goals = (
        await db.execute(
            select(Goal).where(
                Goal.organization_id == organization_id, Goal.owner_id == employee.id
            )
        )
    ).scalars().all()
    overdue = [t for t in tasks if t.due_date and t.due_date < today]
    open_tasks = [t for t in tasks if t.status != "completed"]
    lines = [f"Here's your day, {employee.full_name.split(' ')[0]}:"]
    if overdue:
        lines.append(f"- Warning: {len(overdue)} overdue task(s) need attention first.")
    if open_tasks:
        lines.append(f"- {len(open_tasks)} open task(s):")
        for task in open_tasks[:5]:
            due = f" (due {task.due_date.isoformat()})" if task.due_date else ""
            lines.append(f"  - {task.title}{due}")
    else:
        lines.append("- No open tasks assigned to you. Enjoy the headroom!")
    if meetings:
        next_meeting = meetings[0]
        lines.append(
            f"- {len(meetings)} upcoming meeting(s); next: '{next_meeting.title}' at "
            f"{next_meeting.start_at.isoformat() if next_meeting.start_at else 'TBD'}."
        )
    if goals:
        in_progress = [g for g in goals if g.status == "in_progress"]
        lines.append(
            f"- You own {len(goals)} goal(s), {len(in_progress)} in progress "
            f"(avg {round(sum(g.progress or 0 for g in goals) / len(goals))}%)."
        )
    return {
        "answer": "\n".join(lines),
        "overdue_tasks": [t.title for t in overdue][:5],
        "open_tasks": len(open_tasks),
        "next_tasks": [t.title for t in open_tasks[:3]],
        "upcoming_meetings": [m.title for m in meetings[:3]],
        "goals_owned": len(goals),
    }


async def tool_org_pulse(db, organization_id: str, user: User, **kwargs) -> dict[str, Any]:
    from app.work.intelligence_service import intelligence_service

    dashboard = await intelligence_service.executive_dashboard(db, organization_id=organization_id)
    lines = [
        "Org pulse:",
        f"- {dashboard['projects_active']} active project(s), avg health {dashboard['avg_project_health']}/100 ({dashboard['project_status']}).",
        f"- {dashboard['tasks_completion_rate']}% task completion ({dashboard['tasks_completed']}/{dashboard['tasks_total']}).",
        f"- {dashboard['goals_completion_rate']}% goal completion ({dashboard['goals_completed']}/{dashboard['goals_total']}).",
        f"- {dashboard['risks_open']} open risk(s), {dashboard['high_risks']} high/critical.",
        f"- {dashboard['meetings_last_7d']} meeting(s) in the last 7 days, {dashboard['overloaded_employees']} overloaded employee(s).",
    ]
    return {
        "answer": "\n".join(lines),
        "projects_active": dashboard["projects_active"],
        "avg_project_health": dashboard["avg_project_health"],
        "tasks_completion_rate": dashboard["tasks_completion_rate"],
        "goals_completion_rate": dashboard["goals_completion_rate"],
        "risks_open": dashboard["risks_open"],
        "high_risks": dashboard["high_risks"],
        "overloaded_employees": dashboard["overloaded_employees"],
    }


async def tool_entity_summary(db, organization_id: str, user: User, **kwargs) -> dict[str, Any]:
    kind = kwargs.get("kind")
    entity_id = kwargs.get("entity_id")
    handler = {
        "project": _sum_project,
        "task": _sum_task,
        "goal": _sum_goal,
        "meeting": _sum_meeting,
    }.get(kind)
    if handler is None or not entity_id:
        return {"answer": "I can summarize projects, tasks, goals and meetings.", "error": "missing_entity"}
    return await handler(db, organization_id, entity_id)


async def _sum_project(db, organization_id: str, project_id: str) -> dict[str, Any]:
    from app.work.intelligence_service import intelligence_service

    project = await db.get(Project, project_id)
    if project is None or project.organization_id != organization_id:
        return {"answer": "I couldn't find that project.", "error": "not_found"}
    health = await intelligence_service.project_health(
        db, organization_id=organization_id, project_id=project_id
    )
    owner = await db.get(Employee, project.owner_id) if project.owner_id else None
    lines = [
        f"{project.name} ({project.code}) — {project.status}.",
        f"Health {health['health']}/100 ({health['status']}), {health['progress']}% complete.",
        f"{health['completed_tasks']}/{health['total_tasks']} tasks done, {health['blocked_tasks']} blocked, {health['overdue_tasks']} overdue.",
    ]
    if health["signals"]:
        lines.append(f"Signals: {', '.join(health['signals'])}.")
    if health["risks"]:
        top = health["risks"][0]
        lines.append(f"Top risk: '{top['title']}' ({top['risk_score']} · {top['severity']}).")
    if owner:
        lines.append(f"Owned by {owner.full_name}.")
    return {"answer": "\n".join(lines), "status": project.status, "health": health["health"]}


async def _sum_task(db, organization_id: str, task_id: str) -> dict[str, Any]:
    from app.work.task_service import task_service

    task = await task_service.get(db, organization_id=organization_id, task_id=task_id)
    if task is None:
        return {"answer": "I couldn't find that task.", "error": "not_found"}
    lines = [
        f"{task.title} — {task.status} · {task.priority} priority.",
        (task.description or "No description."),
    ]
    if task.dependencies:
        lines.append(
            f"Depends on {len(task.dependencies)} task(s): {', '.join(d['title'] for d in task.dependencies[:3])}."
        )
    if task.due_date:
        lines.append(f"Due {task.due_date.isoformat()}.")
    if task.assignee_name:
        lines.append(f"Assigned to {task.assignee_name}.")
    return {"answer": "\n".join(lines), "status": task.status, "priority": task.priority}


async def _sum_goal(db, organization_id: str, goal_id: str) -> dict[str, Any]:
    goal = await db.get(Goal, goal_id)
    if goal is None or goal.organization_id != organization_id:
        return {"answer": "I couldn't find that goal.", "error": "not_found"}
    krs = (
        await db.execute(
            select(KeyResult).where(
                KeyResult.organization_id == organization_id, KeyResult.goal_id == goal_id
            )
        )
    ).scalars().all()
    owner = await db.get(Employee, goal.owner_id) if goal.owner_id else None
    lines = [f"{goal.name} — {goal.status} · {goal.progress}%."]
    if goal.description:
        lines.append(goal.description)
    else:
        lines.append(f"Scope: {goal.scope}.")
    if krs:
        lines.append(f"{len(krs)} key result(s):")
        for kr in krs:
            target = kr.target or 0
            current = kr.current or 0
            pct = min(100, round(current / target * 100)) if target else 0
            lines.append(f"- {kr.title}: {current}/{target} ({pct}%).")
    if owner:
        lines.append(f"Owned by {owner.full_name}.")
    return {
        "answer": "\n".join(lines),
        "status": goal.status,
        "progress": goal.progress,
        "key_results": len(krs),
    }


async def _sum_meeting(db, organization_id: str, meeting_id: str) -> dict[str, Any]:
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None or meeting.organization_id != organization_id:
        return {"answer": "I couldn't find that meeting.", "error": "not_found"}
    agenda = (
        await db.execute(
            select(MeetingAgendaItem)
            .where(
                MeetingAgendaItem.organization_id == organization_id,
                MeetingAgendaItem.meeting_id == meeting_id,
            )
            .order_by(MeetingAgendaItem.sort_order.asc())
        )
    ).scalars().all()
    action_items = (
        await db.execute(
            select(MeetingActionItem).where(
                MeetingActionItem.organization_id == organization_id,
                MeetingActionItem.meeting_id == meeting_id,
            )
        )
    ).scalars().all()
    attendees = (
        await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.organization_id == organization_id,
                MeetingAttendee.meeting_id == meeting_id,
            )
        )
    ).scalars().all()
    lines = [
        f"{meeting.title} — {meeting.meeting_type} · {meeting.status}.",
        f"Scheduled {meeting.start_at.isoformat() if meeting.start_at else 'TBD'} · {len(attendees)} attendee(s).",
    ]
    if agenda:
        lines.append(f"Agenda ({len(agenda)} item(s)): " + "; ".join(a.title for a in agenda[:5]) + ".")
    if action_items:
        pending = [a for a in action_items if a.status != "completed"]
        lines.append(f"{len(action_items)} action item(s), {len(pending)} open.")
    return {
        "answer": "\n".join(lines),
        "status": meeting.status,
        "attendees": len(attendees),
        "agenda": [a.title for a in agenda],
        "action_items_open": len([a for a in action_items if a.status != "completed"]),
    }


async def tool_search(db, organization_id: str, user: User, **kwargs) -> dict[str, Any]:
    data = await universal_search.search(
        db,
        organization_id=organization_id,
        query=kwargs.get("query") or "",
        limit=6,
    )
    results = data["results"]
    if not results:
        return {"answer": "I couldn't find anything matching that.", "hits": 0}
    lines = [f"Found {data['total']} match(es). Top results:"]
    for r in results[:6]:
        lines.append(f"- {r['title']} ({r['type']}) → {r['url']}")
        if r.get("snippet"):
            lines.append(f"    {r['snippet'][:140]}")
    return {"answer": "\n".join(lines), "hits": len(results), "top": results[:6]}


async def tool_expert_finder(db, organization_id: str, user: User, **kwargs) -> dict[str, Any]:
    topic = (kwargs.get("topic") or "").strip()
    if not topic:
        return {"answer": "Tell me the topic you need an expert for.", "error": "missing_topic"}
    lowered = topic.lower()
    skill_rows = (
        await db.execute(
            select(Skill).where(
                Skill.organization_id == organization_id,
                Skill.name.ilike(f"%{lowered}%"),
            ).limit(5)
        )
    ).scalars().all()
    scored: list[dict[str, Any]] = []
    skill_ids = [s.id for s in skill_rows]
    if skill_ids:
        rows = (
            await db.execute(
                select(ExpertiseScore)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.skill_id.in_(skill_ids),
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(8)
            )
        ).scalars().all()
        for row in rows:
            employee = await db.get(Employee, row.employee_id)
            skill = await db.get(Skill, row.skill_id)
            if employee is None:
                continue
            scored.append(
                {
                    "name": employee.full_name,
                    "designation": employee.designation,
                    "email": employee.email,
                    "skill": skill.name if skill else topic,
                    "score": round(row.score, 2),
                    "level": row.level,
                }
            )
    if not scored:
        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                    or_(
                        Employee.designation.ilike(f"%{lowered}%"),
                        Employee.first_name.ilike(f"%{lowered}%"),
                        Employee.last_name.ilike(f"%{lowered}%"),
                    ),
                ).limit(8)
            )
        ).scalars().all()
        scored = [
            {
                "name": e.full_name,
                "designation": e.designation,
                "email": e.email,
                "skill": topic,
                "score": 0.5,
                "level": 0,
            }
            for e in employees
        ]
    if not scored:
        return {
            "answer": f"I couldn't find an expert on '{topic}'. Try a different topic, or check the Skills workspace.",
            "hits": 0,
        }
    lines = [f"Top expert(s) on '{topic}':"]
    for s in scored[:5]:
        lines.append(f"- {s['name']} ({s['designation'] or 'employee'}): {s['email']}")
    return {"answer": "\n".join(lines), "hits": len(scored), "experts": scored[:5]}


TOOLS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "my_day": tool_my_day,
    "org_pulse": tool_org_pulse,
    "entity_summary": tool_entity_summary,
    "search": tool_search,
    "expert_finder": tool_expert_finder,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "my_day": "current tasks, meetings and goals for the asking user",
    "org_pulse": "company-wide dashboard: projects, tasks, goals, risks, meetings",
    "entity_summary": "summarize a specific project, task, goal or meeting",
    "search": "search across employees, knowledge, projects, tasks, meetings, goals",
    "expert_finder": "find employees with expertise on a topic",
}


class Agent:
    def __init__(self) -> None:
        self._registry = TOOLS

    def intent_to_tool(self, intents: list[str], context: dict[str, Any]) -> Optional[str]:
        if "my_day" in intents:
            return "my_day"
        if "org_pulse" in intents:
            return "org_pulse"
        if "knowledge" in intents or "search" in intents:
            return "search"
        if "expert" in intents:
            return "expert_finder"
        if "entity" in intents:
            return "entity_summary"
        return None

    async def run(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        tool_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._registry.get(tool_name)
        if handler is None:
            return {"answer": "", "tools": [], "error": f"unknown_tool:{tool_name}"}
        kwargs: dict[str, Any] = {}
        if tool_name == "entity_summary":
            kind = next(
                (k for k in ("project", "task", "goal", "meeting") if context.get(f"{k}_id")), None
            )
            kwargs = {"kind": kind, "entity_id": context.get(f"{kind}_id")} if kind else {}
        elif tool_name == "search":
            kwargs = {"query": context.get("query") or ""}
        elif tool_name == "expert_finder":
            kwargs = {"topic": context.get("query") or ""}
        result = await handler(db, organization_id=organization_id, user=user, **kwargs)
        return {"answer": result.get("answer", ""), "tools": [tool_name], "data": result}


agent = Agent()
