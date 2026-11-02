"""
WebRTC Signaling Service for Voice/Video Calls.

Implements WebRTC signaling server with support for:
- ICE candidate exchange
- SDP offer/answer negotiation
- LiveKit/Mediasoup integration
- Screen sharing support
- Recording coordination
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable, TYPE_CHECKING

logger = logging.getLogger(__name__)


class CallType(str, Enum):
    """Types of calls."""
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN_SHARE = "screen_share"
    CONFERENCE = "conference"


class CallState(str, Enum):
    """Call states."""
    INITIATED = "initiated"
    RINGING = "ringing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    HOLD = "hold"
    ENDED = "ended"
    FAILED = "failed"
    REJECTED = "rejected"


class SignalingMessageType(str, Enum):
    """WebRTC signaling message types."""
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    JOIN = "join"
    LEAVE = "leave"
    CALL_INIT = "call_init"
    CALL_ACCEPT = "call_accept"
    CALL_REJECT = "call_reject"
    CALL_END = "call_end"
    CALL_HOLD = "call_hold"
    CALL_RESUME = "call_resume"
    MUTE = "mute"
    UNMUTE = "unmute"
    SCREEN_SHARE_START = "screen_share_start"
    SCREEN_SHARE_STOP = "screen_share_stop"
    RECORDING_START = "recording_start"
    RECORDING_STOP = "recording_stop"
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    ERROR = "error"


@dataclass
class SignalingMessage:
    """WebRTC signaling message."""
    type: SignalingMessageType
    call_id: str
    from_user: str
    to_user: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class CallParticipant:
    """Call participant information."""
    user_id: str
    user_name: str
    user_color: str
    joined_at: float = field(default_factory=time.time)
    media_state: Dict[str, bool] = field(default_factory=lambda: {
        "audio": True,
        "video": True,
        "screen_share": False,
    })
    connection_state: str = "connecting"
    ice_candidates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Call:
    """Active call/conference session."""
    call_id: str
    call_type: CallType
    state: CallState = CallState.INITIATED
    creator_id: str = ""
    participants: Dict[str, CallParticipant] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    max_participants: int = 100
    recording: bool = False
    recording_id: Optional[str] = None
    recording_started_at: Optional[float] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    livekit_room_name: Optional[str] = None
    livekit_room_sid: Optional[str] = None


class SignalingServer:
    """
    WebRTC Signaling Server.
    
    Handles:
    - Call initiation/acceptance/rejection
    - SDP offer/answer exchange
    - ICE candidate exchange
    - Participant management
    - LiveKit/Mediasoup integration
    - Screen sharing coordination
    - Recording coordination
    """
    
    def __init__(
        self,
        presence_service: Optional["PresenceService"] = None,
        livekit_url: Optional[str] = None,
        livekit_api_key: Optional[str] = None,
        livekit_api_secret: Optional[str] = None,
        turn_manager: Optional["TurnManager"] = None,
    ):
        self.presence_service = presence_service
        self.calls: Dict[str, Call] = {}
        self.user_calls: Dict[str, Set[str]] = defaultdict(set)
        self.pending_ice: Dict[str, List[Dict]] = defaultdict(list)
        
        # LiveKit configuration
        self.livekit_url = livekit_url
        self.livekit_api_key = livekit_api_key
        self.livekit_api_secret = livekit_api_secret
        self._livekit_api = None
        
        # TURN/STUN configuration
        self.turn_manager = turn_manager
        
        # Message handlers
        self.handlers: Dict[SignalingMessageType, Callable] = {}
        self._register_handlers()
        
    def _register_handlers(self):
        """Register message handlers."""
        self.handlers[SignalingMessageType.CALL_INIT] = self._handle_call_init
        self.handlers[SignalingMessageType.CALL_ACCEPT] = self._handle_call_accept
        self.handlers[SignalingMessageType.CALL_REJECT] = self._handle_call_reject
        self.handlers[SignalingMessageType.CALL_END] = self._handle_call_end
        self.handlers[SignalingMessageType.OFFER] = self._handle_offer
        self.handlers[SignalingMessageType.ANSWER] = self._handle_answer
        self.handlers[SignalingMessageType.ICE_CANDIDATE] = self._handle_ice_candidate
        self.handlers[SignalingMessageType.JOIN] = self._handle_join
        self.handlers[SignalingMessageType.LEAVE] = self._handle_leave
        self.handlers[SignalingMessageType.CALL_HOLD] = self._handle_hold
        self.handlers[SignalingMessageType.CALL_RESUME] = self._handle_resume
        self.handlers[SignalingMessageType.MUTE] = self._handle_mute
        self.handlers[SignalingMessageType.UNMUTE] = self._handle_unmute
        self.handlers[SignalingMessageType.SCREEN_SHARE_START] = self._handle_screen_share_start
        self.handlers[SignalingMessageType.SCREEN_SHARE_STOP] = self._handle_screen_share_stop
        self.handlers[SignalingMessageType.RECORDING_START] = self._handle_recording_start
        self.handlers[SignalingMessageType.RECORDING_STOP] = self._handle_recording_stop
        
    async def initialize_livekit(self):
        """Initialize LiveKit connection."""
        if self.livekit_url and self.livekit_api_key and self.livekit_api_secret:
            try:
                from livekit import api
                self._livekit_api = api.LiveKitAPI(
                    self.livekit_url,
                    self.livekit_api_key,
                    self.livekit_api_secret,
                )
                logger.info("LiveKit initialized")
            except ImportError:
                logger.warning("LiveKit not installed, using WebRTC peer-to-peer")
            except Exception as e:
                logger.error(f"Failed to initialize LiveKit: {e}")
                
    async def handle_message(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle incoming signaling message."""
        handler = self.handlers.get(message.type)
        if not handler:
            return {"success": False, "error": f"Unknown message type: {message.type}"}
            
        try:
            return await handler(message, sender_id)
        except Exception as e:
            logger.error(f"Error handling {message.type}: {e}")
            return {"success": False, "error": str(e)}
            
    async def _handle_call_init(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call initiation."""
        call_type = CallType(message.payload.get("call_type", "video"))
        target_users = message.payload.get("target_users", [])
        settings = message.payload.get("settings", {})
        
        call_id = str(uuid.uuid4())
        call = Call(
            call_id=call_id,
            call_type=call_type,
            creator_id=sender_id,
            settings=settings,
        )
        
        # Add creator as participant
        call.participants[sender_id] = CallParticipant(
            user_id=sender_id,
            user_name=message.payload.get("user_name", "Unknown"),
            user_color=message.payload.get("user_color", "#6366f1"),
        )
        
        # Create LiveKit room if configured
        if self._livekit_api:
            try:
                room_name = f"call-{call_id}"
                room = await self._livekit_api.room.create_room(
                    name=room_name,
                    empty_timeout=300,
                    max_participants=call.max_participants,
                )
                call.livekit_room_name = room.name
                call.livekit_room_sid = room.sid
            except Exception as e:
                logger.warning(f"Failed to create LiveKit room: {e}")
        
        # Add target users
        for user_id in target_users:
            call.participants[user_id] = CallParticipant(
                user_id=user_id,
                user_name=message.payload.get("target_names", {}).get(user_id, "Unknown"),
                user_color="#6366f1",
            )
            self.user_calls[user_id].add(call_id)
            
        self.user_calls[sender_id].add(call_id)
        self.calls[call_id] = call
        
        # Notify target users
        for user_id in target_users:
            await self._send_to_user(user_id, {
                "type": SignalingMessageType.CALL_INIT.value,
                "call_id": call_id,
                "from_user": sender_id,
                "call_type": call_type.value,
                "settings": settings,
                "livekit_room": call.livekit_room_name,
            })
            
        logger.info(f"Call initiated: {call_id} by {sender_id}")
        
        # Get ICE servers for WebRTC
        ice_servers = []
        if self.turn_manager:
            ice_servers = self.turn_manager.get_ice_servers_json()
        
        return {
            "success": True,
            "call_id": call_id,
            "call_type": call_type.value,
            "livekit_room": call.livekit_room_name,
            "ice_servers": ice_servers,
        }
        
    async def _handle_call_accept(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call acceptance."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        if sender_id not in call.participants:
            call.participants[sender_id] = CallParticipant(
                user_id=sender_id,
                user_name=message.payload.get("user_name", "Unknown"),
                user_color=message.payload.get("user_color", "#6366f1"),
            )
            
        participant = call.participants[sender_id]
        participant.media_state = message.payload.get("media_state", {
            "audio": True,
            "video": True,
            "screen_share": False,
        })
        participant.connection_state = "connected"
        
        self.user_calls[sender_id].add(call_id)
        
        if call.state == CallState.INITIATED:
            call.state = CallState.CONNECTING
        elif call.state == CallState.RINGING:
            call.state = CallState.CONNECTING
            
        # Notify other participants
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.PARTICIPANT_JOINED.value,
            "call_id": call_id,
            "user_id": sender_id,
            "user_name": message.payload.get("user_name", "Unknown"),
            "user_color": message.payload.get("user_color", "#6366f1"),
        }, exclude=sender_id)
        
        # Get ICE servers for WebRTC
        ice_servers = []
        if self.turn_manager:
            ice_servers = self.turn_manager.get_ice_servers_json()
        
        return {
            "success": True,
            "call_id": call_id,
            "livekit_room": call.livekit_room_name,
            "livekit_token": await self._generate_livekit_token(call_id, sender_id) if self._livekit_api else None,
            "ice_servers": ice_servers,
        }
        
    async def _handle_call_reject(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call rejection."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        call.state = CallState.REJECTED
        call.ended_at = time.time()
        
        # Notify caller
        await self._send_to_user(call.creator_id, {
            "type": SignalingMessageType.CALL_REJECT.value,
            "call_id": call_id,
            "rejected_by": sender_id,
        })
        
        # Clean up
        await self._cleanup_call(call_id)
        
        return {"success": True}
        
    async def _handle_call_end(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call end."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        call.state = CallState.ENDED
        call.ended_at = time.time()
        
        # Stop recording if active
        if call.recording:
            await self._stop_recording(call_id)
            
        # Notify all participants
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.CALL_END.value,
            "call_id": call_id,
            "ended_by": sender_id,
        })
        
        # Clean up
        await self._cleanup_call(call_id)
        
        return {"success": True}
        
    async def _handle_offer(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle SDP offer."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        # Forward to target user
        target_user = message.to_user
        if target_user:
            await self._send_to_user(target_user, {
                "type": SignalingMessageType.OFFER.value,
                "call_id": call_id,
                "from_user": sender_id,
                "payload": message.payload,
            })
            
        return {"success": True}
        
    async def _handle_answer(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle SDP answer."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        # Forward to caller
        target_user = message.to_user or call.creator_id
        if target_user:
            await self._send_to_user(target_user, {
                "type": SignalingMessageType.ANSWER.value,
                "call_id": call_id,
                "from_user": sender_id,
                "payload": message.payload,
            })
            
        call.state = CallState.CONNECTED
        call.started_at = call.started_at or time.time()
        
        return {"success": True}
        
    async def _handle_ice_candidate(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle ICE candidate."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        # Store for late joiners
        self.pending_ice[call_id].append({
            "candidate": message.payload,
            "from": sender_id,
            "timestamp": time.time(),
        })
        
        # Forward to target user
        target_user = message.to_user
        if target_user:
            await self._send_to_user(target_user, {
                "type": SignalingMessageType.ICE_CANDIDATE.value,
                "call_id": call_id,
                "from_user": sender_id,
                "payload": message.payload,
            })
            
        return {"success": True}
        
    async def _handle_join(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle participant joining call/conference."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        # Add participant
        call.participants[sender_id] = CallParticipant(
            user_id=sender_id,
            user_name=message.payload.get("user_name", "Unknown"),
            user_color=message.payload.get("user_color", "#6366f1"),
        )
        
        self.user_calls[sender_id].add(call_id)
        
        # Send pending ICE candidates
        if call_id in self.pending_ice:
            for ice in self.pending_ice[call_id]:
                await self._send_to_user(sender_id, {
                    "type": SignalingMessageType.ICE_CANDIDATE.value,
                    "call_id": call_id,
                    "from_user": ice["from"],
                    "payload": ice["candidate"],
                })
                
        # Notify others
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.PARTICIPANT_JOINED.value,
            "call_id": call_id,
            "user_id": sender_id,
            "user_name": message.payload.get("user_name", "Unknown"),
            "user_color": message.payload.get("user_color", "#6366f1"),
        }, exclude=sender_id)
        
        # Return call state
        # Get ICE servers for WebRTC
        ice_servers = []
        if self.turn_manager:
            ice_servers = self.turn_manager.get_ice_servers_json()
        
        return {
            "success": True,
            "call_id": call_id,
            "call_type": call.call_type.value,
            "state": call.state.value,
            "participants": {
                uid: {
                    "user_id": p.user_id,
                    "user_name": p.user_name,
                    "user_color": p.user_color,
                    "media_state": p.media_state,
                }
                for uid, p in call.participants.items()
            },
            "livekit_room": call.livekit_room_name,
            "livekit_token": await self._generate_livekit_token(call_id, sender_id) if self._livekit_api else None,
            "pending_ice": self.pending_ice.get(call_id, []),
            "ice_servers": ice_servers,
        }
        
    async def _handle_leave(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle participant leaving."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        # Remove participant
        call.participants.pop(sender_id, None)
        self.user_calls[sender_id].discard(call_id)
        
        # Notify others
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.PARTICIPANT_LEFT.value,
            "call_id": call_id,
            "user_id": sender_id,
        })
        
        # If creator leaves, end call
        if sender_id == call.creator_id:
            call.state = CallState.ENDED
            call.ended_at = time.time()
            await self._broadcast_to_call(call_id, {
                "type": SignalingMessageType.CALL_END.value,
                "call_id": call_id,
                "ended_by": sender_id,
            })
            await self._cleanup_call(call_id)
            
        return {"success": True}
        
    async def _handle_hold(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call hold."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        call.state = CallState.HOLD
        
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.CALL_HOLD.value,
            "call_id": call_id,
            "held_by": sender_id,
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_resume(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle call resume."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        call.state = CallState.CONNECTED
        
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.CALL_RESUME.value,
            "call_id": call_id,
            "resumed_by": sender_id,
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_mute(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle mute/unmute."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        participant = call.participants.get(sender_id)
        if participant:
            participant.media_state["audio"] = False
            
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.MUTE.value,
            "call_id": call_id,
            "user_id": sender_id,
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_unmute(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle unmute."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        participant = call.participants.get(sender_id)
        if participant:
            participant.media_state["audio"] = True
            
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.UNMUTE.value,
            "call_id": call_id,
            "user_id": sender_id,
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_screen_share_start(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle screen share start."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        participant = call.participants.get(sender_id)
        if participant:
            participant.media_state["screen_share"] = True
            
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.SCREEN_SHARE_START.value,
            "call_id": call_id,
            "user_id": sender_id,
            "user_name": message.payload.get("user_name", "Unknown"),
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_screen_share_stop(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle screen share stop."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        participant = call.participants.get(sender_id)
        if participant:
            participant.media_state["screen_share"] = False
            
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.SCREEN_SHARE_STOP.value,
            "call_id": call_id,
            "user_id": sender_id,
        }, exclude=sender_id)
        
        return {"success": True}
        
    async def _handle_recording_start(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle recording start."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        if call.recording:
            return {"success": False, "error": "Already recording"}
            
        call.recording = True
        call.recording_started_at = time.time()
        call.recording_id = str(uuid.uuid4())
        
        # Start LiveKit recording if available
        if self._livekit_api and call.livekit_room_name:
            try:
                await self._livekit_api.egress.start_room_composite_egress(
                    room_name=call.livekit_room_name,
                    file_output={
                        "filepath": f"recordings/{call.recording_id}.mp4",
                    },
                )
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.RECORDING_START.value,
            "call_id": call_id,
            "recording_id": call.recording_id,
            "started_by": sender_id,
        })
        
        return {
            "success": True,
            "recording_id": call.recording_id,
        }
        
    async def _handle_recording_stop(self, message: SignalingMessage, sender_id: str) -> Dict[str, Any]:
        """Handle recording stop."""
        call_id = message.call_id
        call = self.calls.get(call_id)
        
        if not call:
            return {"success": False, "error": "Call not found"}
            
        if not call.recording:
            return {"success": False, "error": "Not recording"}
            
        await self._stop_recording(call_id)
        
        await self._broadcast_to_call(call_id, {
            "type": SignalingMessageType.RECORDING_STOP.value,
            "call_id": call_id,
            "recording_id": call.recording_id,
            "stopped_by": sender_id,
        })
        
        return {"success": True}
        
    async def _stop_recording(self, call_id: str):
        """Stop recording."""
        call = self.calls.get(call_id)
        if not call or not call.recording:
            return
            
        call.recording = False
        
        # Stop LiveKit recording
        if self._livekit_api and call.recording_id:
            try:
                # Find and stop the egress
                egresses = await self._livekit_api.egress.list_egress(
                    room_name=call.livekit_room_name,
                )
                for egress in egresses:
                    if egress.room_name == call.livekit_room_name:
                        await self._livekit_api.egress.stop_egress(egress.egress_id)
            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")
                
    async def _generate_livekit_token(self, call_id: str, user_id: str) -> Optional[str]:
        """Generate LiveKit access token."""
        if not self._livekit_api:
            return None
            
        try:
            from livekit import api
            call = self.calls.get(call_id)
            if not call or not call.livekit_room_name:
                return None
                
            token = api.AccessToken(self.livekit_api_key, self.livekit_api_secret) \
                .with_identity(user_id) \
                .with_name(f"user_{user_id}") \
                .with_grants(api.VideoGrants(
                    room_join=True,
                    room=call.livekit_room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )) \
                .to_jwt()
            return token
        except Exception as e:
            logger.error(f"Failed to generate LiveKit token: {e}")
            return None
            
    async def _send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Send message to user via presence service."""
        if self.presence_service:
            await self.presence_service.send_to_user(user_id, message)
            
    async def _broadcast_to_call(
        self,
        call_id: str,
        message: Dict[str, Any],
        exclude: Optional[str] = None,
    ):
        """Broadcast message to all participants in a call."""
        call = self.calls.get(call_id)
        if not call:
            return
            
        for user_id in call.participants:
            if user_id != exclude:
                await self._send_to_user(user_id, message)
                
    async def _cleanup_call(self, call_id: str):
        """Clean up call resources."""
        call = self.calls.pop(call_id, None)
        if call:
            self.pending_ice.pop(call_id, None)
            for user_id in call.participants:
                self.user_calls[user_id].discard(call_id)
                
    def get_call(self, call_id: str) -> Optional[Call]:
        """Get call by ID."""
        return self.calls.get(call_id)
        
    def get_user_calls(self, user_id: str) -> List[str]:
        """Get active calls for user."""
        return list(self.user_calls.get(user_id, set()))
        
    def get_active_calls(self) -> List[Call]:
        """Get all active calls."""
        return [c for c in self.calls.values() if c.state in (CallState.CONNECTING, CallState.CONNECTED, CallState.RINGING)]
        
    def get_call_state(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call state for sync."""
        call = self.calls.get(call_id)
        if not call:
            return None
            
        return {
            "call_id": call.call_id,
            "call_type": call.call_type.value,
            "state": call.state.value,
            "creator_id": call.creator_id,
            "participants": {
                uid: {
                    "user_id": p.user_id,
                    "user_name": p.user_name,
                    "user_color": p.user_color,
                    "media_state": p.media_state,
                    "connection_state": p.connection_state,
                }
                for uid, p in call.participants.items()
            },
            "created_at": call.created_at,
            "started_at": call.started_at,
            "ended_at": call.ended_at,
            "recording": call.recording,
            "recording_id": call.recording_id,
            "livekit_room": call.livekit_room_name,
            "settings": call.settings,
        }


# Global signaling server instance
_signaling_server: Optional[SignalingServer] = None


def get_signaling_server(
    presence_service: Optional["PresenceService"] = None,
    livekit_url: Optional[str] = None,
    livekit_api_key: Optional[str] = None,
    livekit_api_secret: Optional[str] = None,
    turn_manager: Optional["TurnManager"] = None,
) -> SignalingServer:
    """Get or create signaling server singleton."""
    global _signaling_server
    if _signaling_server is None:
        _signaling_server = SignalingServer(
            presence_service,
            livekit_url,
            livekit_api_key,
            livekit_api_secret,
            turn_manager,
        )
    return _signaling_server


def init_signaling_server(
    presence_service: Optional["PresenceService"] = None,
    livekit_url: Optional[str] = None,
    livekit_api_key: Optional[str] = None,
    livekit_api_secret: Optional[str] = None,
    turn_manager: Optional["TurnManager"] = None,
) -> SignalingServer:
    """Initialize signaling server."""
    global _signaling_server
    _signaling_server = SignalingServer(
        presence_service,
        livekit_url,
        livekit_api_key,
        livekit_api_secret,
        turn_manager,
    )
    return _signaling_server