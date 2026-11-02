with open('app/schemas/work.py', 'r') as f:
    content = f.read()

# Find the location to insert - after MeetingActionItemOut and before Approvals
idx = content.rfind('class RiskOut(ORMModel):')

if idx == -1:
    print("ERROR: RiskOut not found")
else:
    # Find the end of RiskOut class
    idx2 = content.find('\n\n', idx)
    if idx2 == -1:
        idx2 = len(content)
    
    # Insert Calendar events after RiskOut
    calendar_classes = '''

# =============================================================================
# Calendar
# =============================================================================


class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_type: str = "event"
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    calendar_scope: str = "personal"
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: str = "confirmed"


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    location: Optional[str] = None
    calendar_scope: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: Optional[str] = None


class CalendarEventOut(ORMModel):
    id: str
    title: str
    description: Optional[str] = None
    event_type: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    calendar_scope: str
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    created_by: Optional[str] = None
    creator_name: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
'''

    new_content = content[:idx2] + calendar_classes + '\n\n' + content[idx2:]

    if 'CalendarEventCreate' not in new_content:
        print('ERROR: CalendarEventCreate not added')
    else:
        print('SUCCESS: CalendarEvent classes added')

    with open('app/schemas/work.py', 'w') as f:
        f.write(new_content)

    print('Done!')