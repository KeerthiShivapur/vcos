with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\services\\meeting_service.py', 'r') as f:
    lines = f.readlines()

# Find the MeetingConfig class and fix the field order
new_lines = []
in_meeting_config = False
for i, line in enumerate(lines):
    if '@dataclass' in line and i+1 < len(lines) and 'class MeetingConfig:' in lines[i+1]:
        in_meeting_config = True
    if in_meeting_config and 'class PresentationConfig:' in line:
        in_meeting_config = False
    
    if in_meeting_config:
        # Replace the MeetingConfig class definition with correct field order
        if 'title: str' in line and 'organizer_id' not in lines[i-1]:
            # We're at the title line, next should be organizer_id
            pass
        elif 'description: Optional[str] = None' in line:
            # Insert organizer_id before description
            lines[i] = '    organizer_id: str\n' + line
        elif 'meeting_type: MeetingType = MeetingType.STANDARD' in line and 'organizer_id' not in lines[i-1]:
            # Remove organizer_id from its current position
            pass
    
    new_lines.append(line)

# Actually, let's just rewrite the entire class
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\services\\meeting_service.py', 'r') as f:
    content = f.read()

# Find and replace the MeetingConfig class
import re
pattern = r'(@dataclass\nclass MeetingConfig:.*?)(?=\n@dataclass|\nclass |\n\nclass |\Z)'
replacement = '''@dataclass
class MeetingConfig:
    """Configuration for a meeting."""
    title: str
    organizer_id: str
    description: Optional[str] = None
    meeting_type: MeetingType = MeetingType.STANDARD
    scale: MeetingScale = MeetingScale.TEAM
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    timezone: str = "UTC"
    project_id: Optional[str] = None
    participant_ids: List[str] = field(default_factory=list)
    external_guest_emails: List[str] = field(default_factory=list)
    agenda: List[str] = field(default_factory=list)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)
    # Media settings
    media_provider: MediaProvider = MediaProvider.LIVEKIT
    recording_enabled: bool = False
    transcription_enabled: bool = False
    wait_room_enabled: bool = True
    chat_enabled: bool = True
    reactions_enabled: bool = True
    screen_share_enabled: bool = True
    # Access control
    require_approval: bool = False
    allow_external_guests: bool = True
    password_protected: bool = False
    password: Optional[str] = None'''

import re
content = re.sub(r'@dataclass\nclass MeetingConfig:.*?(?=\n@dataclass|\nclass |\n\nclass |\Z)', replacement, content, flags=re.DOTALL)
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\services\\meeting_service.py', 'w') as f:
    f.write(content)
print('Done')