"""LiveKit WebRTC SFU Integration for Voice/Video Calls.

Provides token generation, room management, recording, and screen share support.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/livekit", tags=["LiveKit WebRTC"])


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from user."""
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")
    return org


class RequirePermission:
    """Dependency to require a specific permission."""
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        codes = await permission_service.user_permission_codes(db, user.id, user.organization_id)
        if self.permission not in codes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.permission}",
            )
        return user


def require_permission(permission: str) -> RequirePermission:
    return RequirePermission(permission)


@dataclass
class LiveKitConfig:
    """LiveKit server configuration."""
    url: str
    api_key: str
    api_secret: str
    
    @classmethod
    def from_settings(cls) -> "LiveKitConfig":
        settings = get_settings()
        return cls(
            url=settings.LIVEKIT_URL or "ws://localhost:7880",
            api_key=settings.LIVEKIT_API_KEY or "devkey",
            api_secret=settings.LIVEKIT_API_SECRET or "secret",
        )


def generate_access_token(
    config: LiveKitConfig,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    permissions: Optional[dict] = None,
    ttl_hours: int = 6,
) -> str:
    """Generate a LiveKit access token (JWT)."""
    import jwt
    
    now = int(time.time())
    exp = now + (ttl_hours * 3600)
    
    video_grants = {
        "room": room_name,
        "roomJoin": True,
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": True,
    }
    
    if permissions:
        video_grants.update(permissions)
    
    payload = {
        "iss": config.api_key,
        "sub": participant_identity,
        "nbf": now,
        "exp": exp,
        "video": video_grants,
        "name": participant_name,
    }
    
    return jwt.encode(payload, config.api_secret, algorithm="HS256")


@router.post("/token")
async def create_token(
    room_name: str,
    participant_identity: str,
    participant_name: str,
    permissions: Optional[dict] = None,
    ttl_hours: int = 6,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:join")),
    db: AsyncSession = Depends(get_db),
):
    """Generate LiveKit access token for a participant."""
    config = LiveKitConfig.from_settings()
    
    # Verify user has access to the room/meeting
    # TODO: Add room access verification
    
    token = generate_access_token(
        config=config,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name=participant_name,
        permissions=permissions,
        ttl_hours=ttl_hours,
    )
    
    return {
        "token": token,
        "url": config.url,
        "room_name": room_name,
        "participant_identity": participant_identity,
    }


@router.post("/rooms")
async def create_room(
    room_name: str,
    empty_timeout: int = 300,
    max_participants: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a LiveKit room."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/CreateRoom"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, room_name, 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "name": room_name,
        "empty_timeout": empty_timeout,
        "max_participants": max_participants,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to create room: {text}")
            result = await resp.json()
    
    return result


@router.get("/rooms")
async def list_rooms(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all LiveKit rooms."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/ListRooms"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to list rooms: {text}")
            result = await resp.json()
    
    return {"rooms": result.get("rooms", [])}


@router.get("/rooms/{room_name}")
async def get_room(
    room_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get LiveKit room details."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/ListRooms"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={"names": [room_name]}, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to get room: {text}")
            result = await resp.json()
    
    rooms = result.get("rooms", [])
    if not rooms:
        raise HTTPException(404, "Room not found")
    
    return rooms[0]


@router.delete("/rooms/{room_name}")
async def delete_room(
    room_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a LiveKit room."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/DeleteRoom"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={"room": room_name}, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to delete room: {text}")
            result = await resp.json()
    
    return result


@router.get("/rooms/{room_name}/participants")
async def list_participants(
    room_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """List participants in a LiveKit room."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/ListParticipants"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={"room": room_name}, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to list participants: {text}")
            result = await resp.json()
    
    return {"participants": result.get("participants", [])}


@router.post("/rooms/{room_name}/participants/{participant_identity}/mute")
async def mute_participant(
    room_name: str,
    participant_identity: str,
    muted: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:moderate")),
    db: AsyncSession = Depends(get_db),
):
    """Mute/unmute a participant."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/MutePublishedTrack"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={
            "room": room_name,
            "identity": participant_identity,
            "muted": muted,
        }, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to mute participant: {text}")
            result = await resp.json()
    
    return result


@router.post("/rooms/{room_name}/participants/{participant_identity}/remove")
async def remove_participant(
    room_name: str,
    participant_identity: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:moderate")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a participant from the room."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.RoomService/RemoveParticipant"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={
            "room": room_name,
            "identity": participant_identity,
        }, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to remove participant: {text}")
            result = await resp.json()
    
    return result


@router.post("/egress/start")
async def start_recording(
    room_name: str,
    output_type: str = "file",  # file, stream, segment
    file_path: Optional[str] = None,
    s3_bucket: Optional[str] = None,
    s3_region: Optional[str] = None,
    s3_credentials: Optional[dict] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:record")),
    db: AsyncSession = Depends(get_db),
):
    """Start recording a room (egress)."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.Egress/StartRoomCompositeEgress"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    # Build output config
    if output_type == "file" and file_path:
        output = {"file": {"filepath": file_path}}
    elif output_type == "s3" and s3_bucket:
        output = {"s3": {"bucket": s3_bucket, "region": s3_region, **s3_credentials}}
    else:
        output = {"file": {"filepath": f"recordings/{room_name}-{int(time.time())}.mp4"}}
    
    payload = {
        "room_name": room_name,
        "layout": "speaker-dark",
        "output": output,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to start recording: {text}")
            result = await resp.json()
    
    return result


@router.post("/egress/{egress_id}/stop")
async def stop_recording(
    egress_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:record")),
    db: AsyncSession = Depends(get_db),
):
    """Stop a recording (egress)."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.Egress/StopEgress"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json={"egress_id": egress_id}, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to stop recording: {text}")
            result = await resp.json()
    
    return result


@router.get("/egress")
async def list_egress(
    room_name: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """List active/completed egress (recordings)."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.Egress/ListEgress"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    payload = {}
    if room_name:
        payload["room_name"] = room_name
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to list egress: {text}")
            result = await resp.json()
    
    return {"egress": result.get("items", [])}


@router.post("/ingress/whip")
async def create_whip_ingress(
    room_name: str,
    participant_identity: str,
    participant_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:moderate")),
    db: AsyncSession = Depends(get_db),
):
    """Create WHIP ingress for screen sharing / external stream."""
    import aiohttp
    
    config = LiveKitConfig.from_settings()
    
    url = config.url.replace("ws://", "http://").replace("wss://", "https://")
    api_url = f"{url}/twirp/livekit.Ingress/CreateIngress"
    
    headers = {
        "Authorization": f"Bearer {generate_access_token(config, 'api', 'api', 'api', ttl_hours=1)}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "input_type": "whip",
        "room_name": room_name,
        "participant_identity": participant_identity,
        "participant_name": participant_name,
        "bypass_transcoding": True,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(500, f"Failed to create WHIP ingress: {text}")
            result = await resp.json()
    
    return result


@router.get("/config")
async def get_config(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
):
    """Get LiveKit client configuration."""
    config = LiveKitConfig.from_settings()
    return {
        "url": config.url,
        "api_key": config.api_key,
    }