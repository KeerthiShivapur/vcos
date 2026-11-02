with open('app/schemas/work.py', 'r') as f:
    content = f.read()

# Find the last occurrence of 'created_at: datetime\n    updated_at: datetime'
idx = content.rfind('created_at: datetime\n    updated_at: datetime')

if idx == -1:
    print("ERROR: Pattern not found")
else:
    # Build new content
    new_content = content[:idx] + '''created_at: datetime
    updated_at: datetime


# =============================================================================
# Approvals
# =============================================================================

class ApprovalCreate(BaseModel):
    approval_type: str = "project"
    title: str
    description: Optional[str] = None
    requester_id: Optional[str] = None
    approver_id: Optional[str] = None
    priority: str = "medium"
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    policy_id: Optional[str] = None


class ApprovalDecide(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: Optional[str] = None


class ApprovalOut(ORMModel):
    id: str
    approval_type: str
    title: str
    description: Optional[str] = None
    requester_id: Optional[str] = None
    requester_name: Optional[str] = None
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    status: str
    priority: str
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    policy_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    policy_id: Optional[str] = None
'''

# Verify
if 'ApprovalCreate' not in new_content:
    print('ERROR: ApprovalCreate not added')
else:
    print('SUCCESS: Approval classes added')

with open('app/schemas/work.py', 'w') as f:
    f.write(new_content)

print('Done!')