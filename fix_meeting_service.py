with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\services\\meeting_service.py', 'r') as f:
    content = f.read()

# Fix the MeetingConfig dataclass field order
old = '''@dataclass
class MeetingConfig:
    """Configuration for a meeting."""
    title: str
    description: Optional[str] = None
    meeting_type: MeetingType = MeetingType.STANDARD
    scale: MeetingScale = MeetingScale.TEAM
    organizer_id: str
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

new = '''@dataclass
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

content = content.replace(old, new)
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\services\\meeting_service.py', 'w') as f:
    f.write(content)
print('Done')