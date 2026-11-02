import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Add _create_goal method to WorkAdapter
goal_method = '''
    async def _create_goal(self, commitment: CompanyCommitment) -> str:
        """Create a goal for the commitment."""
        goal = CompanyGoal(
            id=self._create_id("goal-"),
            organization_id=self.context.organization_id,
            title=f"Goal for {commitment.title}",
            description=f"Goal linked to commitment: {commitment.title}",
            kind="commitment_outcome",
            status="active",
            priority=3,
            owner_label=self.context.caller.employee_id,
        )
        self.context.db.add(goal)
        await self.context.db.flush()
        return goal.id

'''

# Find the WorkAdapter class and add the method before _create_outcomes
idx = content.find('async def _create_outcomes')
if idx >= 0:
    # Find the class definition
    class_idx = content.rfind('class WorkAdapter', 0, idx)
    if class_idx >= 0:
        # Find the end of the class (next class or end of file)
        next_class = content.find('\nclass ', idx)
        if next_class < 0:
            next_class = len(content)
        # Insert the method before _create_outcomes
        content = content[:idx] + goal_method + content[idx:]

# Fix Employee creation - use joining_date instead of start_date
content = content.replace(
    'start_date=datetime.now(timezone.utc).date(),',
    'joining_date=datetime.now(timezone.utc).date(),'
)

# Fix Project creation - use start_date instead of joining_date
content = content.replace(
    'joining_date=datetime.now(timezone.utc).date(),',
    'start_date=datetime.now(timezone.utc).date(),'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed CompanyGoal requirement and Employee joining_date')