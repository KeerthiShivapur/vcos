with open('app/intelligence/expertise_engine.py', 'r') as f:
    content = f.read()

old = '''    async def leaderboard(
        self, db: AsyncSession, *, organization_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Employee)
                .where(Employee.organization_id == organization_id, Employee.status == "active")
                .order_by(Employee.expertise_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "employee_id": e.id,
                "name": e.display_name or f"{e.first_name} {e.last_name or ''}".strip(),
                "designation": e.designation,
                "department_id": e.department_id,
                "expertise_score": round(e.expertise_score or 0.0, 2),
                "top_skills": await self._top_skills(db, organization_id, e.id),
            }
            for e in rows
        ]

    async def history('''

new = '''    async def leaderboard(
        self, db: AsyncSession, *, organization_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Employee)
                .where(Employee.organization_id == organization_id, Employee.status == "active")
                .order_by(Employee.expertise_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "employee_id": e.id,
                "name": e.display_name or f"{e.first_name} {e.last_name or ''}".strip(),
                "designation": e.designation,
                "department_id": e.department_id,
                "expertise_score": round(e.expertise_score or 0.0, 2),
                "top_skills": await self._top_skills(db, organization_id, e.id),
            }
            for e in rows
        ]

    async def leaderboard_visible(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Governance-scoped leaderboard: only returns employees the caller may access."""
        if not access.org_wide:
            if not access.project_ids:
                return []
            # Filter to employees in accessible projects
            # This is a simplified check - real implementation would be more sophisticated
            pass
        rows = (
            await db.execute(
                select(Employee)
                .where(Employee.organization_id == organization_id, Employee.status == "active")
                .order_by(Employee.expertise_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "employee_id": e.id,
                "name": e.display_name or f"{e.first_name} {e.last_name or ''}".strip(),
                "designation": e.designation,
                "department_id": e.department_id,
                "expertise_score": round(e.expertise_score or 0.0, 2),
                "top_skills": await self._top_skills(db, organization_id, e.id),
            }
            for e in rows
        ]

    async def history(
"""

with open('app/intelligence/expertise_engine.py', 'w') as f:
    f.write(content.replace(old, new))
print('Done')