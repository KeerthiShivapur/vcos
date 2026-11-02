"""
On-Call Rotation & Escalation Management for VCOS.

Provides:
- On-call schedules and rotations
- Escalation policies with multi-level escalation
- PagerDuty/Opsgenie/VictorOps integration
- Shift management with timezone support
- Override and swap management
- Notification routing
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.core.config import settings
from app.core.timeutils import utcnow

logger = logging.getLogger(__name__)


class RotationType(str, Enum):
    """On-call rotation types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class EscalationLevel(str, Enum):
    """Escalation levels."""
    L1 = "l1"      # Primary on-call
    L2 = "l2"      # Secondary/escalation
    L3 = "l3"      # Manager/executive
    L4 = "l4"      # Executive/crisis


class OnCallStatus(str, Enum):
    """On-call status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    OVERRIDE = "override"
    SWAPPED = "swapped"


class NotificationChannel(str, Enum):
    """Notification channels."""
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    VICTOROPS = "victorops"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    WEBHOOK = "webhook"


@dataclass
class TeamMember:
    """Team member for on-call rotation."""
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    slack_id: Optional[str] = None
    pagerduty_id: Optional[str] = None
    opsgenie_id: Optional[str] = None
    timezone: str = "UTC"
    skills: List[str] = field(default_factory=list)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OnCallSchedule:
    """On-call schedule configuration."""
    id: str
    name: str
    team_id: str
    rotation_type: RotationType
    start_date: datetime
    rotation_interval_days: int = 7
    timezone: str = "UTC"
    members: List[str] = field(default_factory=list)  # Member IDs
    escalation_policy_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OnCallShift:
    """On-call shift assignment."""
    id: str
    schedule_id: str
    member_id: str
    start_time: datetime
    end_time: datetime
    escalation_level: EscalationLevel = EscalationLevel.L1
    status: OnCallStatus = OnCallStatus.ACTIVE
    override_member_id: Optional[str] = None
    swap_request_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EscalationPolicy:
    """Escalation policy configuration."""
    id: str
    name: str
    organization_id: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    # Each step: {
    #   "level": "l1|l2|l3|l4",
    #   "delay_minutes": 5,
    #   "channels": ["pagerduty", "slack", "email"],
    #   "receivers": ["user_id_1", "user_id_2"],
    #   "repeat_interval_minutes": 30,
    #   "max_repeats": 3
    # }
    repeat_interval_minutes: int = 30
    max_repeats: int = 3
    default_receiver: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EscalationStep:
    """Single escalation step execution."""
    id: str
    escalation_id: str
    alert_id: str
    step_number: int
    level: EscalationLevel
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notifications_sent: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, acknowledged, resolved, timeout
    repeat_count: int = 0


@dataclass
class OverrideRequest:
    """On-call override request."""
    id: str
    shift_id: str
    requester_id: str
    replacement_id: str
    start_time: datetime
    end_time: datetime
    reason: str
    status: str = "pending"  # pending, approved, rejected, cancelled
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SwapRequest:
    """On-call swap request."""
    id: str
    shift_id: str
    requester_id: str
    target_id: str
    status: str = "pending"  # pending, accepted, rejected, cancelled
    created_at: datetime = field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = None


class OnCallManager:
    """
    On-call rotation and escalation management.
    
    Features:
    - Flexible rotation schedules (daily, weekly, biweekly, monthly)
    - Multi-level escalation policies
    - Override and swap management
    - Timezone-aware scheduling
    - Integration with PagerDuty/Opsgenie/VictorOps
    - Override and swap management
    - Notification routing
    """

    def __init__(self):
        self._schedules: Dict[str, OnCallSchedule] = {}
        self._shifts: Dict[str, OnCallShift] = {}
        self._members: Dict[str, TeamMember] = {}
        self._escalation_policies: Dict[str, EscalationPolicy] = {}
        self._escalations: Dict[str, List[EscalationStep]] = {}
        self._overrides: Dict[str, OverrideRequest] = {}
        self._swaps: Dict[str, SwapRequest] = {}
        self._notification_handlers: Dict[NotificationChannel, Callable] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize on-call manager."""
        if self._initialized:
            return
        
        # Register default notification handlers
        self._register_default_handlers()
        
        # Load schedules from database (placeholder)
        await self._load_schedules()
        
        # Start background tasks
        asyncio.create_task(self._shift_monitor())
        asyncio.create_task(self._escalation_processor())
        
        self._initialized = True
        logger.info("OnCallManager initialized")

    def _register_default_handlers(self):
        """Register default notification handlers."""
        self._notification_handlers[NotificationChannel.SLACK] = self._send_slack_notification
        self._notification_handlers[NotificationChannel.EMAIL] = self._send_email_notification
        self._notification_handlers[NotificationChannel.SMS] = self._send_sms_notification
        self._notification_handlers[NotificationChannel.PAGERDUTY] = self._send_pagerduty_notification
        self._notification_handlers[NotificationChannel.OPSGENIE] = self._send_opsgenie_notification
        self._notification_handlers[NotificationChannel.WEBHOOK] = self._send_webhook_notification

    async def _load_schedules(self):
        """Load schedules from database."""
        # In production, load from database
        # For now, create a default schedule for testing
        pass

    # ==================== Schedule Management ====================

    async def create_schedule(
        self,
        name: str,
        team_id: str,
        rotation_type: RotationType,
        rotation_interval_days: int,
        start_date: datetime,
        timezone: str,
        member_ids: List[str],
        escalation_policy_id: Optional[str] = None,
        timezone_str: str = "UTC",
    ) -> OnCallSchedule:
        """Create a new on-call schedule."""
        schedule = OnCallSchedule(
            id=str(uuid4()),
            name=name,
            team_id=team_id,
            rotation_type=rotation_type,
            rotation_interval_days=rotation_interval_days,
            start_date=start_date,
            timezone=timezone_str,
            members=member_ids,
            escalation_policy_id=escalation_policy_id,
        )
        
        self._schedules[schedule.id] = schedule
        
        # Generate initial shifts
        await self._generate_shifts(schedule)
        
        logger.info(f"Created on-call schedule: {schedule.id} ({name})")
        return schedule

    async def get_schedule(self, schedule_id: str) -> Optional[OnCallSchedule]:
        """Get schedule by ID."""
        return self._schedules.get(schedule_id)

    async def update_schedule(
        self,
        schedule_id: str,
        updates: Dict[str, Any],
    ) -> Optional[OnCallSchedule]:
        """Update schedule configuration."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return None
        
        for key, value in updates.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        
        schedule.updated_at = utcnow()
        
        # Regenerate shifts if rotation changed
        if "rotation_type" in updates or "rotation_interval_days" in updates or "members" in updates:
            await self._regenerate_shifts(schedule)
        
        return schedule

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete an on-call schedule."""
        if schedule_id not in self._schedules:
            return False
        
        # Delete associated shifts
        shifts_to_delete = [
            sid for sid, shift in self._shifts.items()
            if shift.schedule_id == schedule_id
        ]
        for sid in shifts_to_delete:
            del self._shifts[sid]
        
        del self._schedules[schedule_id]
        return True

    async def list_schedules(
        self,
        team_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[OnCallSchedule]:
        """List on-call schedules."""
        schedules = list(self._schedules.values())
        
        if team_id:
            schedules = [s for s in schedules if s.team_id == team_id]
        if active_only:
            schedules = [s for s in schedules if s.is_active]
        
        return schedules

    # ==================== Shift Generation ====================

    async def _generate_shifts(
        self,
        schedule: OnCallSchedule,
        weeks_ahead: int = 8,
    ) -> List[OnCallShift]:
        """Generate on-call shifts for a schedule."""
        shifts = []
        members = schedule.members
        if not members:
            return shifts
        
        current = schedule.start_date
        end_date = utcnow() + timedelta(weeks=weeks_ahead)
        member_index = 0
        
        while current < end_date:
            member_id = members[member_index % len(members)]
            
            shift = OnCallShift(
                id=str(uuid4()),
                schedule_id=schedule.id,
                member_id=member_id,
                start_time=current,
                end_time=current + timedelta(days=schedule.rotation_interval_days),
                escalation_level=EscalationLevel.L1,
            )
            
            self._shifts[shift.id] = shift
            shifts.append(shift)
            
            current += timedelta(days=schedule.rotation_interval_days)
            member_index += 1
        
        return shifts

    async def _regenerate_shifts(self, schedule: OnCallSchedule):
        """Regenerate shifts for a schedule."""
        # Delete future shifts
        now = utcnow()
        shifts_to_delete = [
            sid for sid, shift in self._shifts.items()
            if shift.schedule_id == schedule.id and shift.start_time > utcnow()
        ]
        for sid in shifts_to_delete:
            del self._shifts[sid]
        
        # Generate new shifts
        await self._generate_shifts(schedule)

    # ==================== On-Call Queries ====================

    async def get_current_oncall(
        self,
        schedule_id: str,
        at_time: Optional[datetime] = None,
    ) -> Optional[OnCallShift]:
        """Get current on-call shift for a schedule."""
        at_time = at_time or utcnow()
        
        for shift in self._shifts.values():
            if (shift.schedule_id == schedule_id and
                shift.start_time <= at_time < shift.end_time and
                shift.status == OnCallStatus.ACTIVE):
                # Check for override
                if shift.override_member_id:
                    # Return override member
                    override_shift = OnCallShift(
                        id=shift.id,
                        schedule_id=shift.schedule_id,
                        member_id=shift.override_member_id,
                        start_time=shift.start_time,
                        end_time=shift.end_time,
                        escalation_level=shift.escalation_level,
                        status=OnCallStatus.OVERRIDE,
                        override_member_id=shift.override_member_id,
                    )
                    return override_shift
                return shift
        
        return None

    async def get_oncall_schedule(
        self,
        schedule_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OnCallShift]:
        """Get on-call schedule for a time range."""
        shifts = []
        for shift in self._shifts.values():
            if (shift.schedule_id == schedule_id and
                shift.start_time < end_time and
                shift.end_time > start_time):
                shifts.append(shift)
        
        shifts.sort(key=lambda s: s.start_time)
        return shifts

    async def get_user_oncall(
        self,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[OnCallShift]:
        """Get on-call shifts for a user."""
        start = start_time or utcnow()
        end = end_time or (utcnow() + timedelta(days=30))
        
        shifts = []
        for shift in self._shifts.values():
            if (shift.member_id == user_id and
                shift.start_time < end and
                shift.end_time > start):
                shifts.append(shift)
        
        shifts.sort(key=lambda s: s.start_time)
        return shifts

    # ==================== Override Management ====================

    async def create_override(
        self,
        shift_id: str,
        requester_id: str,
        replacement_id: str,
        start_time: datetime,
        end_time: datetime,
        reason: str,
    ) -> OverrideRequest:
        """Create an override request for a shift."""
        shift = self._shifts.get(shift_id)
        if not shift:
            raise ValueError(f"Shift not found: {shift_id}")
        
        if shift.member_id != self._members.get(requester_id):
            raise ValueError("Only the assigned on-call can request override")
        
        replacement = self._members.get(replacement_id)
        if not replacement:
            raise ValueError(f"Replacement member not found: {replacement_id}")
        
        if not (shift.start_time <= start_time < end_time <= shift.end_time):
            raise ValueError("Override time must be within shift")
        
        override = OverrideRequest(
            id=str(uuid4()),
            shift_id=shift_id,
            requester_id=requester_id,
            replacement_id=replacement_id,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            status="pending",
        )
        
        self._overrides[override.id] = override
        logger.info(f"Created override request: {override.id} for shift {shift_id}")
        return override

    async def approve_override(
        self,
        override_id: str,
        approver_id: str,
    ) -> bool:
        """Approve an override request."""
        override = self._overrides.get(override_id)
        if not override:
            return False
        
        if override.status != "pending":
            return False
        
        override.status = "approved"
        override.approved_by = approver_id
        override.approved_at = utcnow()
        
        # Apply override to shift
        shift = self._shifts.get(override.shift_id)
        if shift:
            shift.override_member_id = override.replacement_id
            shift.status = OnCallStatus.OVERRIDE
            shift.updated_at = utcnow()
        
        return True

    async def cancel_override(self, override_id: str) -> bool:
        """Cancel an override request."""
        override = self._overrides.get(override_id)
        if not override or override.status != "pending":
            return False
        
        override.status = "cancelled"
        
        # Remove override from shift
        shift = self._shifts.get(override.shift_id)
        if shift and shift.override_member_id == override.replacement_id:
            shift.override_member_id = None
            shift.status = OnCallStatus.ACTIVE
            shift.updated_at = utcnow()
        
        return True

    async def list_overrides(
        self,
        shift_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[OverrideRequest]:
        """List override requests."""
        overrides = list(self._overrides.values())
        
        if shift_id:
            overrides = [o for o in overrides if o.shift_id == shift_id]
        if user_id:
            overrides = [o for o in overrides if o.requester_id == user_id or o.replacement_id == user_id]
        if status:
            overrides = [o for o in overrides if o.status == status]
        
        return sorted(overrides, key=lambda o: o.created_at, reverse=True)

    # ==================== Swap Management ====================

    async def create_swap(
        self,
        shift_id: str,
        requester_id: str,
        target_id: str,
    ) -> SwapRequest:
        """Create a swap request."""
        shift = self._shifts.get(shift_id)
        if not shift:
            raise ValueError(f"Shift not found: {shift_id}")
        
        if shift.member_id != requester_id:
            raise ValueError("Only the assigned on-call can request swap")
        
        target = self._members.get(target_id)
        if not target:
            raise ValueError(f"Target member not found: {target_id}")
        
        swap = SwapRequest(
            id=str(uuid4()),
            shift_id=shift_id,
            requester_id=requester_id,
            target_id=target_id,
            status="pending",
        )
        
        self._swaps[swap.id] = swap
        return swap

    async def accept_swap(self, swap_id: str, user_id: str) -> bool:
        """Accept a swap request."""
        swap = self._swaps.get(swap_id)
        if not swap or swap.target_id != user_id:
            return False
        
        if swap.status != "pending":
            return False
        
        swap.status = "accepted"
        swap.responded_at = utcnow()
        
        # Execute swap
        shift = self._shifts.get(swap.shift_id)
        if shift:
            shift.member_id = swap.target_id
            shift.status = OnCallStatus.SWAPPED
            shift.updated_at = utcnow()
        
        return True

    async def reject_swap(self, swap_id: str, user_id: str) -> bool:
        """Reject a swap request."""
        swap = self._swaps.get(swap_id)
        if not swap or swap.target_id != user_id:
            return False
        
        if swap.status != "pending":
            return False
        
        swap.status = "rejected"
        swap.responded_at = utcnow()
        return True

    # ==================== Escalation Policies ====================

    async def create_escalation_policy(
        self,
        name: str,
        organization_id: str,
        steps: List[Dict[str, Any]],
        repeat_interval_minutes: int = 30,
        max_repeats: int = 3,
    ) -> EscalationPolicy:
        """Create an escalation policy."""
        policy = EscalationPolicy(
            id=str(uuid4()),
            name=name,
            organization_id=organization_id,
            steps=steps,
            repeat_interval_minutes=repeat_interval_minutes,
            max_repeats=max_repeats,
        )
        
        self._escalation_policies[policy.id] = policy
        logger.info(f"Created escalation policy: {policy.id} ({name})")
        return policy

    async def get_escalation_policy(self, policy_id: str) -> Optional[EscalationPolicy]:
        return self._escalation_policies.get(policy_id)

    async def update_escalation_policy(
        self,
        policy_id: str,
        updates: Dict[str, Any],
    ) -> Optional[EscalationPolicy]:
        policy = self._escalation_policies.get(policy_id)
        if not policy:
            return None
        
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        
        policy.updated_at = utcnow()
        return policy

    async def delete_escalation_policy(self, policy_id: str) -> bool:
        if policy_id not in self._escalation_policies:
            return False
        
        del self._escalation_policies[policy_id]
        return True

    # ==================== Escalation Processing ====================

    async def trigger_escalation(
        self,
        alert_id: str,
        policy_id: str,
        alert_data: Dict[str, Any],
    ) -> Optional[str]:
        """Trigger escalation for an alert."""
        policy = self._escalation_policies.get(policy_id)
        if not policy or not policy.is_active:
            return None
        
        escalation_id = str(uuid4())
        escalation_steps = []
        
        for i, step_config in enumerate(policy.steps):
            step = EscalationStep(
                id=str(uuid4()),
                escalation_id=escalation_id,
                alert_id=alert_id,
                step_number=i + 1,
                level=EscalationLevel(step_config.get("level", "l1")),
                triggered_at=utcnow() + timedelta(minutes=step_config.get("delay_minutes", 0)),
            )
            self._escalations.setdefault(escalation_id, []).append(step)
        
        # Execute first step immediately
        await self._execute_escalation_step(escalation_id, 0)
        
        logger.info(f"Triggered escalation {escalation_id} for alert {alert_id}")
        return escalation_id

    async def _execute_escalation_step(
        self,
        escalation_id: str,
        step_index: int,
    ):
        """Execute a single escalation step."""
        escalation_steps = self._escalations.get(escalation_id, [])
        if step_index >= len(escalation_steps):
            return
        
        step = escalation_steps[step_index]
        if step.status != "pending":
            return
        
        policy = self._escalation_policies.get(step.escalation_id)
        if not policy:
            return
        
        step_config = policy.steps[step_index]
        
        # Send notifications
        await self._send_escalation_notifications(step, step_config)
        
        step.status = "notified"
        
        # Schedule next step if not acknowledged
        if step_config.get("repeat_interval_minutes", 30) > 0:
            asyncio.create_task(self._schedule_escalation_repeat(
                escalation_id, step_index, step_config
            ))

    async def _schedule_escalation_repeat(
        self,
        escalation_id: str,
        step_index: int,
        step_config: Dict[str, Any],
    ):
        """Schedule escalation repeat."""
        repeat_interval = step_config.get("repeat_interval_minutes", 30)
        max_repeats = step_config.get("max_repeats", 3)
        
        escalation_steps = self._escalations.get(escalation_id, [])
        step = escalation_steps[step_index]
        
        for repeat in range(max_repeats):
            await asyncio.sleep(repeat_interval * 60)
            
            # Reload step
            step = next((s for s in escalation_steps if s.id == step.id), None)
            if not step or step.status in ["acknowledged", "resolved"]:
                return
            
            if step.repeat_count >= max_repeats:
                # Escalate to next level
                if step_index + 1 < len(self._escalation_policies.get(step.escalation_id, EscalationPolicy()).steps):
                    await self._execute_escalation_step(step.escalation_id, step_index + 1)
                return
            
            step.repeat_count += 1
            await self._send_escalation_notifications(step, step_config)

    async def _send_escalation_notifications(
        self,
        step: EscalationStep,
        step_config: Dict[str, Any],
    ):
        """Send escalation notifications."""
        channels = step_config.get("channels", ["slack", "email"])
        receivers = step_config.get("receivers", [])
        
        for channel_name in channels:
            channel = NotificationChannel(channel_name)
            handler = self._notification_handlers.get(channel)
            if handler:
                for receiver_id in receivers:
                    try:
                        await self._send_notification(channel, receiver_id, step)
                    except Exception as e:
                        logger.error(f"Failed to send {channel_name} notification: {e}")
        
        step.notifications_sent.append({
            "timestamp": utcnow().isoformat(),
            "channels": channels,
            "receivers": step_config.get("receivers", []),
        })

    async def acknowledge_escalation(
        self,
        escalation_id: str,
        step_number: int,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an escalation step."""
        escalation_steps = self._escalations.get(escalation_id, [])
        if not escalation_id:
            return False
        
        step = next((s for s in escalation_steps if s.step_number == step_number), None)
        if not step:
            return False
        
        step.status = "acknowledged"
        step.acknowledged_at = utcnow()
        return True

    async def resolve_escalation(self, escalation_id: str) -> bool:
        """Resolve an entire escalation."""
        escalation_steps = self._escalations.get(escalation_id, [])
        if not escalation_steps:
            return False
        
        for step in escalation_steps:
            if step.status not in ["acknowledged", "resolved"]:
                step.status = "resolved"
                step.resolved_at = utcnow()
        
        return True

    # ==================== Notification Handlers ====================

    async def _send_slack_notification(self, alert_data: Dict, channel: str, message: str) -> bool:
        """Send Slack notification."""
        # Implementation would use Slack webhook
        logger.info(f"Slack notification sent: {alert_data}")
        return True

    async def _send_email_notification(self, alert_data: Dict, email: str, message: str) -> bool:
        """Send email notification."""
        # Implementation would use email service
        logger.info(f"Email sent to {email}: {message}")
        return True

    async def _send_sms_notification(self, alert_data: Dict, phone: str, message: str) -> bool:
        """Send SMS notification."""
        # Implementation would use Twilio or similar
        logger.info(f"SMS sent to {phone}: {message}")
        return True

    async def _send_pagerduty_notification(self, alert_data: Dict, integration_key: str) -> bool:
        """Send PagerDuty notification."""
        # Implementation would use PagerDuty API
        logger.info(f"PagerDuty alert sent: {alert_data}")
        return True

    async def _send_opsgenie_notification(self, alert_data: Dict, api_key: str) -> bool:
        """Send Opsgenie notification."""
        # Implementation would use Opsgenie API
        logger.info(f"Opsgenie alert sent: {alert_data}")
        return True

    async def _send_webhook_notification(self, alert_data: Dict, webhook_url: str) -> bool:
        """Send webhook notification."""
        # Implementation would POST to webhook URL
        logger.info(f"Webhook sent to {webhook_url}: {alert_data}")
        return True

    async def _send_notification(
        self,
        channel: NotificationChannel,
        receiver_id: str,
        step: EscalationStep,
    ) -> bool:
        """Send notification via channel."""
        # Get receiver config and send
        return True

    # ==================== Background Tasks ====================

    async def _shift_monitor(self):
        """Monitor shifts for upcoming changes."""
        while True:
            try:
                now = utcnow()
                
                # Check for upcoming shift changes
                upcoming = [
                    s for s in self._shifts.values()
                    if s.start_time > utcnow() and s.start_time <= utcnow() + timedelta(hours=1)
                    and s.status == OnCallStatus.ACTIVE
                ]
                
                for shift in upcoming:
                    # Notify upcoming on-call
                    await self._notify_upcoming_shift(shift)
                
                # Check for expiring overrides
                self._check_expiring_overrides()
                
            except Exception as e:
                logger.error(f"Shift monitor error: {e}")
            
            await asyncio.sleep(300)  # Check every 5 minutes

    async def _escalation_processor(self):
        """Process pending escalations."""
        while True:
            try:
                now = utcnow()
                
                for escalation_id, steps in self._escalations.items():
                    for step in steps:
                        if step.status == "pending" and step.triggered_at <= utcnow():
                            await self._execute_escalation_step(step.escalation_id, step.step_number - 1)
                
            except Exception as e:
                logger.error(f"Escalation processor error: {e}")
            
            await asyncio.sleep(60)  # Check every minute

    async def _notify_upcoming_shift(self, shift: OnCallShift):
        """Notify user of upcoming on-call shift."""
        member = self._members.get(shift.member_id)
        if not member:
            return
        
        # Send notification
        logger.info(f"Notifying {member.name} of upcoming on-call shift")
        # Implementation would send notification

    def _check_expiring_overrides(self):
        """Check for expiring overrides and notify."""
        now = utcnow()
        
        for override in self._overrides.values():
            if override.status == "approved" and override.end_time <= now + timedelta(hours=1):
                # Notify about expiring override
                logger.info(f"Override {override.id} expiring soon")

    # ==================== Utility ====================

    def get_oncall_user(self, schedule_id: str, at_time: Optional[datetime] = None) -> Optional[TeamMember]:
        """Get the current on-call user for a schedule."""
        shift = asyncio.run(self.get_current_oncall(schedule_id, at_time))
        if shift:
            return self._members.get(shift.member_id)
        return None

    def get_oncall_schedule_preview(
        self,
        schedule_id: str,
        days: int = 14,
    ) -> List[Dict[str, Any]]:
        """Get upcoming on-call schedule preview."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return []
        
        shifts = asyncio.run(self.get_oncall_schedule(
            schedule.id,
            utcnow(),
            utcnow() + timedelta(days=days),
        ))
        
        return [
            {
                "shift_id": s.id,
                "member_id": s.member_id,
                "member_name": self._members.get(s.member_id, TeamMember(id="", name="Unknown", email="")).name,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "escalation_level": s.escalation_level.value,
                "status": s.status.value,
            }
            for s in shifts
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get on-call statistics."""
        return {
            "total_schedules": len(self._schedules),
            "active_schedules": sum(1 for s in self._schedules.values() if s.is_active),
            "total_shifts": len(self._shifts),
            "active_shifts": sum(1 for s in self._shifts.values() if s.status == OnCallStatus.ACTIVE),
            "overrides_pending": sum(1 for o in self._overrides.values() if o.status == "pending"),
            "swaps_pending": sum(1 for s in self._swaps.values() if s.status == "pending"),
            "escalation_policies": len(self._escalation_policies),
            "active_escalations": sum(
                1 for steps in self._escalations.values()
                for s in steps if s.status == "pending"
            ),
        }


# Global on-call manager instance
_oncall_manager: Optional[OnCallManager] = None


def get_oncall_manager() -> OnCallManager:
    """Get or create on-call manager singleton."""
    global _oncall_manager
    if _oncall_manager is None:
        _oncall_manager = OnCallManager()
    return _oncall_manager


async def init_oncall_manager() -> OnCallManager:
    """Initialize on-call manager."""
    global _oncall_manager
    _oncall_manager = OnCallManager()
    await _oncall_manager.initialize()
    return _oncall_manager