import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix the for loop to use enumerate
content = content.replace(
    'for project in projects[:5]:',
    'for idx, project in enumerate(projects[:5]):'
)

# Fix source_event_id to be unique per decision
content = content.replace(
    'source_event_id=self.context.run_id',
    'source_event_id=f"{self.context.run_id}-dec-{idx}"'
)

# Fix decision_id to be unique
content = content.replace(
    'decision_id=self._create_id("decd-"),',
    'decision_id=self._create_id(f"decd-{idx}-"),'
)

# Fix rationale to include idx
content = content.replace(
    'rationale=f"Key decision regarding {project.name}",',
    'rationale=f"Key decision regarding {project.name} (idx={idx})",'
)

# Also need to fix the for loop to use enumerate
content = content.replace(
    'for project in projects[:5]:',
    'for idx, project in enumerate(projects[:5]):'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed decision uniqueness')