"""Phase 8.7 — Scenario Simulation Engine.

Executives ask "what happens if..." and the engine simulates resources,
deadlines, workload, knowledge and risk — with the assumptions it used, so
the answer stays explainable. Every simulation is persisted for the audit
trail and can be replayed later.
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.department import Department
from app.models.employee import Employee
from app.models.executive import Simulation
from app.models.project import Milestone, Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

logger = logging.getLogger("vcos.executive.simulation")

SCENARIOS = [
    "hire_engineers", "delay_release", "lose_specialist", "sales_increase",
    "merge_teams", "expand", "reduce_meetings",
]


class SimulationEngine:
    async def simulate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        scenario: str,
        params: dict[str, Any],
        user_id: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Choose from: {', '.join(SCENARIOS)}")

        employees = (await db.execute(
            select(Employee).where(Employee.organization_id == organization_id, Employee.status == "active")
        )).scalars().all()
        active_projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.status.in_(("active", "draft", "paused")),
            )
        )).scalars().all()
        open_tasks = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.status.notin_(("completed", "archived")),
            ))
        ).scalar() or 0

        baseline = {
            "employees": len(employees),
            "active_projects": len(active_projects),
            "open_tasks": open_tasks,
        }

        handler = getattr(self, f"_sim_{scenario}")
        results, assumptions, risks, opportunities = await handler(
            db, organization_id=organization_id, params=params,
            employees=employees, active_projects=active_projects, open_tasks=open_tasks,
        )

        payload = {
            "organization_id": organization_id,
            "scenario": scenario,
            "title": self._title(scenario, params),
            "params": params,
            "assumptions": assumptions,
            "baseline": baseline,
            "results": results,
            "risks": risks,
            "opportunities": opportunities,
            "simulated_at": utcnow().isoformat(),
        }
        if persist:
            sim = Simulation(
                organization_id=organization_id,
                user_id=user_id,
                scenario=scenario,
                title=payload["title"],
                assumptions_json=json.dumps(assumptions),
                results_json=json.dumps({"results": results, "risks": risks, "opportunities": opportunities, "baseline": baseline, "params": params}),
                status="completed",
            )
            db.add(sim)
            await db.flush()
            payload["id"] = sim.id
        return payload

    def _title(self, scenario: str, params: dict[str, Any]) -> str:
        titles = {
            "hire_engineers": f"Hire {params.get('count', 3)} engineer(s)",
            "delay_release": f"Delay release by {params.get('weeks', 2)} week(s)",
            "lose_specialist": f"Lose specialist: {params.get('employee_name', 'key employee')}",
            "sales_increase": f"Sales increase {params.get('percent', 30)}%",
            "merge_teams": "Merge two teams",
            "expand": f"Expand to {params.get('location', 'a new region')}",
            "reduce_meetings": f"Reduce meetings by {params.get('percent', 30)}%",
        }
        return titles.get(scenario, scenario)

    async def _sim_hire_engineers(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        count = max(1, int(params.get("count", 3)))
        team_size = max(1, len(employees))
        workload_relief = min(30, round(count / team_size * 100, 1))
        delay_reduction = min(25, round(count * 4 + workload_relief * 0.4, 1))
        return (
            {
                "workload_relief_percent": workload_relief,
                "project_delay_probability_change": f"-{delay_reduction}%",
                "tasks_per_engineer": round(open_tasks / (team_size + count), 1) if team_size + count else 0,
                "expected_ramp_up_weeks": 2 + (count // 10),
                "headcount_after": team_size + count,
            },
            [
                f"New engineers reach full productivity in {2 + (count // 10)} weeks",
                f"Workload relief scales linearly with {count} hires over {team_size} current employees",
                "Hiring does not change the total scope of open work",
            ],
            [
                "Ramp-up time temporarily increases coordination load",
                "Hiring cost and onboarding effort are not modeled",
            ],
            [
                "Reduced risk of key-person dependency as load is distributed",
                "Higher delivery velocity on active projects",
            ],
        )

    async def _sim_delay_release(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        weeks = max(1, int(params.get("weeks", 2)))
        project = None
        project_id = params.get("project_id")
        if project_id:
            project = await db.get(Project, project_id)
        if project is None and active_projects:
            project = active_projects[0]
        name = project.name if project else "the release"
        milestones_shifted = 0
        if project:
            ms = (await db.execute(
                select(Milestone).where(
                    Milestone.organization_id == organization_id,
                    Milestone.project_id == project.id,
                    Milestone.status != "completed",
                )
            )).scalars().all()
            milestones_shifted = len(ms)
        idle_cost = round(weeks * len(employees) * 8 * 1.5, 0)  # 8h * blended $1.5/h abstract cost units
        return (
            {
                "release_shifted_weeks": weeks,
                "milestones_affected": milestones_shifted,
                "project": name,
                "quality_gain_percent": min(15, weeks * 3),
                "opportunity_cost_units": idle_cost,
            },
            [
                f"Milestones for '{name}' move right by {weeks} week(s)",
                "Additional time reduces quality risk by ~3% per week",
                "Team stays productive; cost estimate assumes no layoffs",
            ],
            [
                "Customer expectations on the original date may be broken",
                "Dependent projects may also need to slip",
            ],
            [
                "More time for testing and documentation",
                "Lower defect rate at release",
            ],
        )

    async def _sim_lose_specialist(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        employee = None
        employee_id = params.get("employee_id")
        if employee_id:
            employee = await db.get(Employee, employee_id)
        if employee is None:
            employee = next((e for e in employees if (e.display_name or e.first_name).lower() == str(params.get("employee_name", "")).lower()), None)
        if employee is None and employees:
            employee = employees[0]
        name = employee.display_name or f"{employee.first_name} {employee.last_name or ''}".strip() if employee else "a specialist"
        assigned_tasks = 0
        if employee:
            assigned_tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == employee.id,
                    Task.status.notin_(("completed", "archived")),
                ))
            ).scalar() or 0
        rehire_cost_weeks = 8 if assigned_tasks > 5 else 4
        return (
            {
                "specialist": name,
                "open_tasks_affected": assigned_tasks,
                "replacement_ramp_up_weeks": rehire_cost_weeks,
                "knowledge_loss_impact": "high" if assigned_tasks >= 8 else "medium",
                "delay_probability_change": f"+{min(40, assigned_tasks * 3)}%",
            },
            [
                f"{name} is assumed non-replaceable for the first {rehire_cost_weeks} weeks",
                "Their unique knowledge is assumed NOT fully captured in the wiki",
            ],
            [
                "Key-person dependency becomes a realized failure",
                "Mentorship and knowledge-transfer burden falls on the team",
            ],
            [
                "Forces documentation of critical knowledge",
                "Opportunity to redistribute and rebalance work",
            ],
        )

    async def _sim_sales_increase(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        percent = max(5, int(params.get("percent", 30)))
        team_size = max(1, len(employees))
        added_load = round(percent / 100 * open_tasks, 0)
        hires_needed = max(1, round(added_load / 40))
        return (
            {
                "demand_growth_percent": percent,
                "added_task_load": added_load,
                "employees_needed_to_absorb": hires_needed,
                "workload_increase_percent": round(percent * 0.6, 1),
            },
            [
                f"Demand grows {percent}% uniformly across projects",
                "Each engineer can absorb ~40 additional task units per quarter",
            ],
            [
                "Overload and burnout risk rise without hiring",
                "Delivery deadlines compress under higher demand",
            ],
            [
                "Revenue upside funds additional headcount",
                "Momentum attracts talent",
            ],
        )

    async def _sim_merge_teams(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        from app.models.team import Team

        teams = (await db.execute(
            select(Team).where(Team.organization_id == organization_id)
        )).scalars().all()
        team_a = params.get("team_a")
        team_b = params.get("team_b")
        members_a = members_b = 0
        name_a = name_b = ""
        for t in teams:
            if t.id == team_a:
                name_a = t.name
                members_a = len([e for e in employees if e.team_id == t.id])
            if t.id == team_b:
                name_b = t.name
                members_b = len([e for e in employees if e.team_id == t.id])
        if not name_a or not name_b:
            name_a = name_b = "two teams"
            members_a = members_b = max(1, len(employees) // 2)
        return (
            {
                "teams_merged": f"{name_a} + {name_b}",
                "combined_members": members_a + members_b,
                "coordination_overhead_reduction_percent": 15,
                "shared_context_gain": "one backlog, one planning cadence",
            },
            [
                "Merged team keeps both backlogs but shares one planning cadence",
                "Coordination overhead drops ~15%",
            ],
            [
                "Team identity and ownership confusion during transition",
                "Larger teams can reduce focus if not reorganized into squads",
            ],
            [
                "Fewer handoffs, faster cross-team decisions",
                "Siloed knowledge gets shared automatically",
            ],
        )

    async def _sim_expand(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        location = params.get("location", "a new region")
        headcount = max(1, int(params.get("headcount", 10)))
        timezone_overlap = params.get("timezone_overlap_hours", 4)
        ramp_months = max(1, round(headcount / 8))
        return (
            {
                "location": location,
                "initial_headcount": headcount,
                "ramp_months": ramp_months,
                "hours_of_overlap_per_day": timezone_overlap,
                "collaboration_risk": "medium" if timezone_overlap < 5 else "low",
            },
            [
                f"{headcount} hires ramp to full productivity in ~{ramp_months} month(s)",
                f"Only {timezone_overlap} hours of daily overlap with the current office",
            ],
            [
                "Hiring pipeline may not deliver on schedule",
                "Low timezone overlap raises async-communication burden",
            ],
            [
                "24/7 coverage across time zones",
                "Access to a new talent market",
            ],
        )

    async def _sim_reduce_meetings(self, db, *, organization_id, params, employees, active_projects, open_tasks):
        from app.models.meeting import Meeting

        percent = max(5, int(params.get("percent", 30)))
        week_ago = utcnow() - timedelta(days=7)
        meetings_7d = (
            await db.execute(select(func.count(Meeting.id)).where(
                Meeting.organization_id == organization_id,
                Meeting.start_at >= week_ago,
                Meeting.status != "cancelled",
            ))
        ).scalar() or 0
        hours_saved = round(meetings_7d * percent / 100 * 1.0, 1)
        return (
            {
                "meetings_removed_per_week": round(meetings_7d * percent / 100, 0),
                "focus_hours_recovered_per_week": hours_saved,
                "meeting_overload_risk_change": f"-{min(40, percent)}%",
            },
            [
                f"{percent}% of recurring meetings can be replaced with async updates",
                "Focus hours are worth roughly 1 hour per meeting removed",
            ],
            [
                "Information may flow more slowly without sync touchpoints",
                "Team culture risks losing informal connection",
            ],
            [
                "Deep-work throughput rises",
                "Employee wellbeing improves (less meeting fatigue)",
            ],
        )


simulation_engine = SimulationEngine()
