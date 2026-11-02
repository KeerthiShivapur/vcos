/**
 * Realtime channels (Phase 1 + Slice 4B).
 *
 * `notificationChannel` keeps the Phase 1 lightweight 30s polling contract for
 * the notification bell (UI code subscribes without caring about the
 * transport).
 *
 * `messagingChannel` is the Slice 4B realtime leg of the messaging loop: it
 * holds a single `ws://host/ws/messaging` socket authenticated with the access
 * token, sends heartbeats, reconnects with capped exponential backoff, and
 * dispatches `messaging.*` server events to per-type listeners. If the socket
 * drops, clients keep the 30s polling fallback so the UI stays coherent.
 */

import { API_URL, tokenStore } from "@/lib/api";

type Listener = () => void;
type EventListener = (data: Record<string, unknown>) => void;

const POLL_INTERVAL_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 25_000;
const MAX_RECONNECT_MS = 15_000;

class NotificationChannel {
  private listeners = new Set<Listener>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private running = false;

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    this.start();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.stop();
    };
  }

  notify() {
    Array.from(this.listeners).forEach((listener) => listener());
  }

  private start() {
    if (this.running) return;
    this.running = true;
    if (typeof window !== "undefined") {
      this.timer = setInterval(() => this.notify(), POLL_INTERVAL_MS);
    }
  }

  private stop() {
    this.running = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}

export const notificationChannel = new NotificationChannel();

function messagingWsUrl(token: string): string {
  const base = API_URL.replace(/^http/, "ws");
  const apiPath =
    base.indexOf("/api/") >= 0 ? base.slice(0, base.indexOf("/api/")) : base;
  return `${apiPath}/ws/messaging?token=${encodeURIComponent(token)}`;
}

class MessagingChannel {
  private listeners = new Map<string, Set<EventListener>>();
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private disposed = false;
  private attempts = 0;

  subscribe(type: string, listener: EventListener): () => void {
    this.disposed = false;
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(listener);
    this.connect();
    return () => {
      set.delete(listener);
      if (set.size === 0) this.listeners.delete(type);
      if (this.listeners.size === 0) this.teardown();
    };
  }

  private connect() {
    if (this.disposed || this.ws) return;
    if (typeof window === "undefined") return;
    const token = tokenStore.getAccess();
    if (!token) {
      this.scheduleReconnect(5_000);
      return;
    }
    let ws: WebSocket;
    try {
      ws = new WebSocket(messagingWsUrl(token));
    } catch {
      this.scheduleReconnect(3_000);
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.attempts = 0;
      this.heartbeat = setInterval(
        () => this.send("heartbeat"),
        HEARTBEAT_INTERVAL_MS,
      );
    };
    ws.onmessage = (event) => {
      let envelope: { type?: string; data?: Record<string, unknown> };
      try {
        envelope = JSON.parse(String(event.data));
      } catch {
        return;
      }
      const type = envelope.type;
      if (!type || type === "welcome" || type === "pong") return;
      const set = this.listeners.get(type);
      if (set) {
        const data = envelope.data ?? {};
        set.forEach((listener) => listener(data));
      }
    };
    ws.onclose = () => {
      if (this.heartbeat) {
        clearInterval(this.heartbeat);
        this.heartbeat = null;
      }
      if (this.ws === ws) this.ws = null;
      if (!this.disposed) this.scheduleReconnect();
    };
    ws.onerror = () => {
      ws.close();
    };
  }

  private send(type: string, data: Record<string, unknown> = {}) {
    const ws = this.ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, data }));
    }
  }

  private scheduleReconnect(delay?: number) {
    if (this.disposed || this.reconnectTimer || this.listeners.size === 0)
      return;
    const backoff = Math.min(3_000 * 2 ** this.attempts, MAX_RECONNECT_MS);
    this.attempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay ?? backoff);
  }

  private teardown() {
    this.disposed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

export const messagingChannel = new MessagingChannel();
