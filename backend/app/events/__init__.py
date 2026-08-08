"""Phase 9 — Background Intelligence event bus.

Events are the first step of every background workflow:

    API / service action
        -> event_service.emit() persists an Event row (durable, replayable)
        -> BackgroundJob("event.dispatch", {event_id}) is enqueued (retry + observability)
        -> event worker dispatches the event to registered handlers
        -> handlers update expertise, graph, knowledge, learning, notifications

The existing `events` table doubles as the durable queue: handlers only run
once per event (processed_at guard), failures are retried via the job
attempts counter, and every step is auditable.
"""

from app.events.event_bus import EventBus, event_bus  # noqa: F401
from app.events.subscriber import on  # noqa: F401
