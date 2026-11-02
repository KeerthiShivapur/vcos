with open('app/schemas/work.py', 'r') as f:
    content = f.read()

# Find the end of MeetingOut class
idx = content.find('class MeetingOut(ORMModel):')
if idx >= 0:
    end_idx = content.find('\n\nclass ', content.find('\n\nclass ', idx + 1) + 1)
    if end_idx == -1:
        end_idx = len(content)

    missing_classes = '''

class MeetingAgendaItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: Optional[int] = None


class MeetingAgendaItemOut(ORMModel):
    id: str
    meeting_id: str
    title: str
    description: Optional[str] = None
    sort_order: int
    duration_minutes: Optional[int] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    version: int
    fingerprint: str
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    source_event_id: Optional[str] = None
    actor_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MeetingActionItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[datetime] = None


class MeetingActionItemOut(ORMModel):
    id: str
    meeting_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str
    completed_at: Optional[datetime] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    version: int
    fingerprint: str
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    source_event_id: Optional[str] = None
    actor_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
'''

# Insert after MeetingOut class
new_content = content[:end_idx] + '\n\n' + missing_classes + '\n\n' + content[end_idx:]

with open('app/schemas/work.py', 'w') as f:
    f.write(new_content)

print('Done!')