/**
 * Realtime notification channel (Phase 1).
 *
 * The backend publishes events to Redis pub/sub and persists notifications.
 * Phase 1 delivers in-app updates via lightweight polling (30s) with a
 * WebSocket-ready interface, so later phases can swap the transport without
 * touching UI code.
 */

type Listener = () => void;

const POLL_INTERVAL_MS = 30_000;

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
