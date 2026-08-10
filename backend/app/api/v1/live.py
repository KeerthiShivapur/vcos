"""Live collaboration WebSocket (Phase 6.2) — presence, RTC signaling, chat,
whiteboard deltas, reactions, screen share.

Connect with the access token as a query param:

    ws://host/ws/meetings/{meeting_id}?token=<access_token>

Client → server message types:
    heartbeat                      -> server replies `pong`
    presence  {mic_enabled? camera_enabled? screen_sharing? raised_hand? device?}
    screen_share {sharing: bool}
    raise_hand {raised: bool}
    signal   {to_employee_id, kind: offer|answer|ice, payload}
    chat     {content, reply_to?}
    typing   {typing: bool}
    whiteboard.delta {version, ops}
    reaction {emoji}
    request_control {to_employee_id}   (screen share handoff)

Server → client:
    welcome {session, peers, employee}
    peer.online / peer.offline {employee_id, name}
    presence.changed / screen_share.changed / raise_hand.changed {participant}
    signal {from_employee_id, kind, payload}
    chat.message {message} / chat.system {message}
    typing {employee_id, typing}
    whiteboard.delta {from_employee_id, version, ops}
    reaction {employee_id, emoji}
    error {message}
"""

import logging
from typing import Any, Optional

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.chat_service import chat_service
from app.collaboration.live import LiveConnection, live_hub
from app.collaboration.participant_service import participant_service
from app.collaboration.session_service import session_service
from app.core.security import ACCESS, decode_token
from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.user import User
from app.work.meeting_service import meeting_service

logger = logging.getLogger("vcos.live.ws")

router = APIRouter(tags=["Live Collaboration"])


async def _authorize(token: Optional[str]) -> tuple[User, Employee, AsyncSession]:
    if not token:
        raise ValueError("Missing token")
    try:
        payload = decode_token(token, ACCESS)
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc
    db = SessionLocal()
    user = await db.get(User, payload.get("sub"))
    if user is None or user.status != "active":
        await db.close()
        raise ValueError("User not active")
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.user_id == user.id, Employee.organization_id == user.organization_id
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        await db.close()
        raise ValueError("No employee profile linked")
    return user, employee, db


@router.websocket("/ws/messaging")
async def messaging_ws(websocket: WebSocket):
    """Personal messaging channel (Slice 4B).

    Connect with the access token as a query param:

        ws://host/ws/messaging?token=<access_token>

    The server registers the connection on the employee's personal hub
    channel. The event worker pushes `messaging.*` events here as they are
    dispatched from the event bus — no database work happens on this receive
    path (the hub is in-memory). If the socket drops, the client's 30s
    polling fallback keeps the UI coherent.

    Client → server:  heartbeat
    Server → client:  welcome {employee_id}
                      messaging.message.sent {conversation_id, message}
                      messaging.message.updated {conversation_id, message}
                      messaging.message.deleted {conversation_id, message_id}
                      messaging.message.reaction {conversation_id, message_id, emoji, reacted}
                      messaging.member.added {conversation_id, employee_id}
                      pong {at}  /  error {message}
    """
    token = websocket.query_params.get("token")
    try:
        user, employee, db = await _authorize(token)
    except ValueError as exc:
        await websocket.close(code=4401, reason=str(exc))
        return

    await websocket.accept()
    conn = LiveConnection(
        ws=websocket,
        employee_id=employee.id,
        name=employee.full_name or "Unknown",
        role="member",
    )
    live_hub.register_personal(employee.id, conn)
    try:
        await websocket.send_json(
            {
                "type": "welcome",
                "ts": _ts(),
                "data": {"employee_id": employee.id},
            }
        )
    except Exception:  # pragma: no cover - raced close
        live_hub.unregister_personal(employee.id, id(conn))
        await db.close()
        return

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type")
            if msg_type == "heartbeat":
                await _send(websocket, "pong", {"at": _ts()})
                continue
            await _send(websocket, "error", {"message": f"Unknown message type: {msg_type}"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - socket robustness
        logger.warning("live: messaging socket error: %s", exc)
    finally:
        live_hub.unregister_personal(employee.id, id(conn))
        await db.close()


@router.websocket("/ws/meetings/{meeting_id}")
async def meeting_ws(websocket: WebSocket, meeting_id: str):
    token = websocket.query_params.get("token")
    try:
        user, employee, db = await _authorize(token)
    except ValueError as exc:
        await websocket.close(code=4401, reason=str(exc))
        return

    try:
        meeting = await meeting_service.get(db, organization_id=user.organization_id, meeting_id=meeting_id)
        if meeting is None:
            await websocket.close(code=4404, reason="Meeting not found")
            return
        session = await session_service.by_meeting(
            db, organization_id=user.organization_id, meeting_id=meeting.id
        )
        session_id = session.id if session else None
        if session_id is None:
            await websocket.close(code=4404, reason="No session yet — join first")
            return
        if session.organization_id != user.organization_id:
            await websocket.close(code=4403, reason="Forbidden")
            return
    except Exception:  # pragma: no cover - defensive
        await websocket.close(code=4400, reason="Internal error")
        return

    await websocket.accept()
    conn = LiveConnection(
        ws=websocket,
        employee_id=employee.id,
        name=employee.full_name or "Unknown",
        role="host" if meeting.organizer_id == employee.id else "participant",
    )
    live_hub.register(session_id, conn)
    await live_hub.broadcast(
        session_id,
        "peer.online",
        {"employee_id": employee.id, "name": conn.name, "role": conn.role},
        exclude=conn,
    )
    try:
        await websocket.send_json(
            {
                "type": "welcome",
                "ts": _ts(),
                "data": {
                    "session_id": session_id,
                    "meeting_id": meeting.id,
                    "employee_id": employee.id,
                    "peers": live_hub.peers(session_id, exclude_employee=employee.id),
                },
            }
        )
    except Exception:  # pragma: no cover - raced close
        live_hub.unregister(session_id, id(conn))
        await db.close()
        return

    try:
        while True:
            raw = await websocket.receive_json()
            await _handle_message(
                db,
                websocket=websocket,
                conn=conn,
                session_id=session_id,
                meeting=meeting,
                employee=employee,
                raw=raw,
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - message handler robustness
        logger.warning("live: session %s message error: %s", session_id, exc)
    finally:
        live_hub.unregister(session_id, id(conn))
        await live_hub.broadcast(
            session_id,
            "peer.offline",
            {"employee_id": employee.id, "name": conn.name},
            exclude=conn,
        )
        await db.close()


async def _handle_message(
    db: AsyncSession,
    *,
    websocket: WebSocket,
    conn: LiveConnection,
    session_id: str,
    meeting,
    employee: Employee,
    raw: dict[str, Any],
) -> None:
    msg_type = raw.get("type")
    data = raw.get("data") or {}

    if msg_type == "heartbeat":
        await _send(websocket, "pong", {"at": _ts()})
        return

    if msg_type == "presence":
        participant = await participant_service.heartbeat(
            db,
            organization_id=meeting.organization_id,
            session_id=session_id,
            employee_id=employee.id,
            device=data.get("device"),
            mic_enabled=data.get("mic_enabled"),
            camera_enabled=data.get("camera_enabled"),
            screen_sharing=data.get("screen_sharing"),
            raised_hand=data.get("raised_hand"),
        )
        await db.commit()
        if participant is not None:
            await live_hub.broadcast(session_id, "presence.changed", _participant_event(participant, employee))
        return

    if msg_type == "screen_share":
        participant = await participant_service.heartbeat(
            db,
            organization_id=meeting.organization_id,
            session_id=session_id,
            employee_id=employee.id,
            screen_sharing=bool(data.get("sharing")),
        )
        await db.commit()
        if participant is not None:
            event = "screen_share.started" if data.get("sharing") else "screen_share.stopped"
            await live_hub.broadcast(session_id, event, _participant_event(participant, employee))
        return

    if msg_type == "raise_hand":
        participant = await participant_service.heartbeat(
            db,
            organization_id=meeting.organization_id,
            session_id=session_id,
            employee_id=employee.id,
            raised_hand=bool(data.get("raised")),
        )
        await db.commit()
        if participant is not None:
            await live_hub.broadcast(session_id, "raise_hand.changed", _participant_event(participant, employee))
        return

    if msg_type == "signal":
        target = data.get("to_employee_id")
        if target:
            await live_hub.send_to_employee(
                session_id,
                target,
                "signal",
                {
                    "from_employee_id": employee.id,
                    "kind": data.get("kind", "unknown"),
                    "payload": data.get("payload"),
                },
            )
        return

    if msg_type == "chat":
        content = data.get("content")
        if not content:
            return
        message = await chat_service.send(
            db,
            organization_id=meeting.organization_id,
            meeting_id=meeting.id,
            session_id=session_id,
            employee=employee,
            content=content,
            reply_to=data.get("reply_to"),
        )
        await db.commit()
        await live_hub.broadcast(session_id, "chat.message", {"message": message}, exclude=conn)
        return

    if msg_type == "typing":
        await live_hub.broadcast(
            session_id, "typing", {"employee_id": employee.id, "typing": bool(data.get("typing"))}, exclude=conn
        )
        return

    if msg_type == "whiteboard.delta":
        await live_hub.broadcast(
            session_id,
            "whiteboard.delta",
            {
                "from_employee_id": employee.id,
                "version": data.get("version", 0),
                "ops": data.get("ops", []),
            },
            exclude=conn,
        )
        return

    if msg_type == "reaction":
        emoji = str(data.get("emoji") or "👍")[:8]
        await live_hub.broadcast(session_id, "reaction", {"employee_id": employee.id, "emoji": emoji}, exclude=conn)
        return

    if msg_type == "request_control":
        target = data.get("to_employee_id")
        if target:
            await live_hub.send_to_employee(
                session_id,
                target,
                "request_control",
                {"from_employee_id": employee.id, "name": conn.name},
            )
        return

    await _send(websocket, "error", {"message": f"Unknown message type: {msg_type}"})


def _participant_event(participant, employee: Employee) -> dict[str, Any]:
    return {
        "employee_id": participant.employee_id,
        "name": employee.full_name or "Unknown",
        "mic_enabled": participant.mic_enabled,
        "camera_enabled": participant.camera_enabled,
        "screen_sharing": participant.screen_sharing,
        "raised_hand": participant.raised_hand,
        "is_present": participant.is_present,
    }


async def _send(websocket: WebSocket, event: str, data: dict[str, Any]) -> None:
    await websocket.send_json({"type": event, "ts": _ts(), "data": data})


def _ts() -> float:
    import time

    return time.time()
