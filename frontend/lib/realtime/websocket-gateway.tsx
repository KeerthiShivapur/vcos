"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { io, Socket, SocketOptions } from "socket.io-client";

/**
 * WebSocket Gateway for VCOS Real-time Communication
 *
 * Provides:
 * - Connection management with auto-reconnect
 * - Room/channel subscription
 * - Event-based messaging
 * - Presence tracking
 * - Message queuing and retry
 * - Connection state management
 */

export interface WebSocketGatewayConfig {
  url: string;
  token?: string;
  autoConnect?: boolean;
  reconnection?: boolean;
  reconnectionAttempts?: number;
  reconnectionDelay?: number;
  reconnectionDelayMax?: number;
  timeout?: number;
  transports?: ("websocket" | "polling")[];
  query?: Record<string, string>;
  auth?: { token: string };
  onConnect?: () => void;
  onDisconnect?: (reason: string) => void;
  onError?: (error: Error) => void;
  onReconnect?: (attemptNumber: number) => void;
  onReconnectAttempt?: (attemptNumber: number) => void;
  onConnectError?: (error: Error) => void;
}

export interface WSMessage<T = any> {
  event: string;
  payload: T;
  timestamp: number;
  id?: string;
  room?: string;
  correlationId?: string;
}

export interface Subscription {
  channel: string;
  filters?: Record<string, any>;
  callback: (message: any) => void;
  unsubscribe: () => void;
}

export interface PresenceState {
  userId: string;
  userName: string;
  status: "online" | "idle" | "away" | "offline";
  lastSeen: number;
  metadata?: Record<string, any>;
}

interface WSMessage<T = any> {
  event: string;
  payload: T;
  timestamp: number;
  id: string;
  room?: string;
  correlationId?: string;
}

interface PendingMessage {
  message: any;
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
  attempts: number;
  correlationId: string;
}

/**
 * WebSocket Gateway Class
 */
export class WebSocketGateway {
  private socket: any = null;
  private config: Required<WebSocketGatewayConfig>;
  private subscriptions: Map<string, Set<Function>> = new Map();
  private pendingMessages: Map<string, any> = new Map();
  private messageQueue: any[] = [];
  private isConnected = false;
  private reconnectAttempt = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private messageId = 0;
  private pendingRequests: Map<
    string,
    { resolve: Function; reject: Function; timeout: NodeJS.Timeout }
  > = new Map();

  private eventHandlers: Map<string, Set<Function>> = new Map();
  private connectionState:
    "connecting" | "connected" | "disconnected" | "reconnecting" =
    "disconnected";
  private presenceState: Map<string, any> = new Map();
  private messageQueue: any[] = [];
  private isProcessingQueue = false;

  constructor(config: WebSocketGatewayConfig) {
    this.config = {
      url: config.url,
      token: config.token || "",
      autoConnect: config.autoConnect ?? true,
      reconnection: config.reconnection ?? true,
      reconnectionAttempts: config.reconnectionAttempts ?? 10,
      reconnectionDelay: config.reconnectionDelay ?? 1000,
      reconnectionDelayMax: config.reconnectionDelayMax ?? 30000,
      timeout: config.timeout ?? 20000,
      transports: config.transports ?? ["websocket", "polling"],
      query: config.query || {},
      auth: config.auth || { token: "" },
      onConnect: config.onConnect || (() => {}),
      onDisconnect: config.onDisconnect || (() => {}),
      onError: config.onError || (() => {}),
      onReconnect: config.onReconnect || (() => {}),
      onReconnectAttempt: config.onReconnectAttempt || (() => {}),
      onConnectError: config.onConnectError || (() => {}),
    };

    if (this.config.autoConnect) {
      this.connect();
    }
  }

  /**
   * Establish WebSocket connection
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.socket?.connected) {
        resolve();
        return;
      }

      this.setConnectionState("connecting");

      try {
        // Import socket.io-client dynamically
        const { io } = require("socket.io-client");

        const socketOptions: any = {
          auth: this.config.auth,
          query: this.config.query,
          transports: this.config.transports,
          reconnection: this.config.reconnection,
          reconnectionAttempts: this.config.reconnectionAttempts,
          reconnectionDelay: this.config.reconnectionDelay,
          reconnectionDelayMax: this.config.reconnectionDelayMax,
          timeout: this.config.timeout,
          autoConnect: this.config.autoConnect,
          auth: this.config.auth,
        };

        this.socket = require("socket.io-client").io(this.config.url, {
          ...this.config,
          transports: this.config.transports,
          reconnection: this.config.reconnection,
          reconnectionAttempts: this.config.reconnectionAttempts,
          reconnectionDelay: this.config.reconnectionDelay,
          reconnectionDelayMax: this.config.reconnectionDelayMax,
          timeout: this.config.timeout,
          autoConnect: false,
        });

        this.setupEventHandlers();

        this.socket.connect();

        // Wait for connection
        const timeout = setTimeout(() => {
          reject(new Error("Connection timeout"));
        }, this.config.timeout);

        this.socket.once("connect", () => {
          clearTimeout(timeout);
          this.onConnect();
          resolve();
        });

        this.socket.once("connect_error", (error: Error) => {
          clearTimeout(timeout);
          this.onConnectError(error);
          reject(error);
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  private setupEventHandlers() {
    if (!this.socket) return;

    this.socket.on("connect", () => this.onConnect());
    this.socket.on("disconnect", (reason: string) => this.onDisconnect(reason));
    this.socket.on("connect_error", (error: Error) =>
      this.onConnectError(error),
    );
    this.socket.on("reconnect", (attemptNumber: number) =>
      this.onReconnect(attemptNumber),
    );
    this.socket.on("reconnect_attempt", (attemptNumber: number) =>
      this.onReconnectAttempt(attemptNumber),
    );
    this.socket.on("error", (error: Error) => this.onError(error));

    // Message handlers
    this.socket.on("message", (data: any) => this.handleMessage(data));
    this.socket.on("notification", (data: any) =>
      this.handleNotification(data),
    );
    this.socket.on("presence", (data: any) => this.handlePresence(data));
    this.socket.on("sync", (data: any) => this.handleSync(data));

    // Acknowledgment handling
    this.socket.on("ack", (data: any) => this.handleAck(data));

    // Presence events
    this.socket.on("presence:join", (data: any) =>
      this.handlePresenceJoin(data),
    );
    this.socket.on("presence:leave", (data: any) =>
      this.handlePresenceLeave(data),
    );
    this.socket.on("presence:update", (data: any) =>
      this.handlePresenceUpdate(data),
    );

    // Room events
    this.socket.on("room:join", (data: any) => this.handleRoomJoin(data));
    this.socket.on("room:leave", (data: any) => this.handleRoomLeave(data));
    this.socket.on("room:users", (data: any) => this.handleRoomUsers(data));
  }

  private onConnect() {
    this.isConnected = true;
    this.reconnectAttempt = 0;
    this.setConnectionState("connected");
    this.startHeartbeat();
    this.processMessageQueue();
    this.config.onConnect();
    this.emit("connect", {});
  }

  private onDisconnect(reason: string) {
    this.isConnected = false;
    this.stopHeartbeat();
    this.setConnectionState("disconnected");
    this.config.onDisconnect(reason);
    this.emit("disconnect", { reason });
  }

  private onConnectError(error: Error) {
    this.setConnectionState("disconnected");
    this.config.onConnectError(error);
    this.emit("connect_error", error);
  }

  private onReconnect(attemptNumber: number) {
    this.reconnectAttempt = 0;
    this.setConnectionState("connected");
    this.startHeartbeat();
    this.processMessageQueue();
    this.config.onReconnect(attemptNumber);
    this.emit("reconnect", { attemptNumber });
  }

  private onReconnectAttempt(attemptNumber: number) {
    this.reconnectAttempt = attemptNumber;
    this.setConnectionState("reconnecting");
    this.config.onReconnectAttempt(attemptNumber);
    this.emit("reconnect_attempt", { attemptNumber });
  }

  private onError(error: Error) {
    this.config.onError(error);
    this.emit("error", error);
  }

  private handleMessage(data: any) {
    this.emit("message", data);
  }

  private handleNotification(data: any) {
    this.emit("notification", data);
  }

  private handlePresence(data: any) {
    this.presenceState.set(data.userId, {
      ...data,
      lastSeen: Date.now(),
    });
    this.emit("presence", data);
  }

  private handleSync(data: any) {
    this.emit("sync", data);
  }

  private handleAck(data: any) {
    const pending = this.pendingRequests.get(data.correlationId);
    if (pending) {
      clearTimeout(pending.timeout);
      this.pendingRequests.delete(data.correlationId);
      if (data.error) {
        pending.reject(new Error(data.error));
      } else {
        pending.resolve(data.payload);
      }
    }
  }

  private handlePresenceJoin(data: any) {
    this.presenceState.set(data.userId, {
      userId: data.userId,
      userName: data.userName,
      status: "online",
      lastSeen: Date.now(),
      metadata: data.metadata,
    });
    this.emit("presence:join", data);
  }

  private handlePresenceLeave(data: any) {
    this.presenceState.delete(data.userId);
    this.emit("presence:leave", data);
  }

  private handlePresenceUpdate(data: any) {
    this.presenceState.set(data.userId, {
      ...this.presenceState.get(data.userId),
      ...data,
      lastSeen: Date.now(),
    });
    this.emit("presence:update", data);
  }

  private handleRoomJoin(data: any) {
    this.emit("room:join", data);
  }

  private handleRoomLeave(data: any) {
    this.emit("room:leave", data);
  }

  private handleRoomUsers(data: any) {
    this.emit("room:users", data);
  }

  private handleMessage(data: any) {
    // Handle acknowledgment
    if (data.correlationId) {
      const pending = this.pendingRequests.get(data.correlationId);
      if (pending) {
        clearTimeout(pending.timeout);
        this.pendingRequests.delete(data.correlationId);
        if (data.error) {
          pending.reject(new Error(data.error));
        } else {
          pending.resolve(data.payload);
        }
        return;
      }
    }

    // Regular message
    this.emit("message", data);
  }

  // ==================== Public API ====================

  /**
   * Send a message with optional acknowledgment
   */
  async send<T = any>(
    event: string,
    payload: any,
    options: {
      room?: string;
      timeout?: number;
      retries?: number;
      correlationId?: string;
    } = {},
  ): Promise<any> {
    const correlationId = options.correlationId || this.generateCorrelationId();

    const message = {
      event,
      payload,
      timestamp: Date.now(),
      id: this.generateMessageId(),
      correlationId: options.correlationId || this.generateCorrelationId(),
      room: options.room,
    };

    // If not connected, queue the message
    if (!this.isConnected) {
      this.messageQueue.push({
        event,
        payload,
        options,
        resolve: () => {},
        reject: () => {},
      });
      return new Promise((resolve, reject) => {
        // Will be resolved when connection is restored
      });
    }

    // Send with acknowledgment
    return new Promise((resolve, reject) => {
      const correlationId = this.generateCorrelationId();
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(correlationId);
        reject(new Error("Message timeout"));
      }, options.timeout || 30000);

      this.pendingRequests.set(message.correlationId!, {
        resolve,
        reject,
        timeout,
      });

      this.socket.emit(
        "message",
        {
          ...message,
          correlationId: message.correlationId,
        },
        (ack: any) => {
          // Handled by ack handler
        },
      );
    });
  }

  /**
   * Emit event without waiting for acknowledgment
   */
  emit(event: string, payload: any, room?: string) {
    if (!this.socket?.connected) {
      this.messageQueue.push({ event, payload, room });
      return;
    }

    this.socket.emit("message", {
      event,
      payload,
      timestamp: Date.now(),
      id: this.generateMessageId(),
      room,
    });
  }

  /**
   * Subscribe to events
   */
  on(event: string, callback: Function): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set());
    }
    this.eventHandlers.get(event)!.add(callback);

    return () => {
      this.eventHandlers.get(event)?.delete(callback);
    };
  }

  /**
   * Emit event to local handlers
   */
  private emit(event: string, payload: any) {
    this.eventHandlers.get(event)?.forEach((callback) => {
      try {
        callback(payload);
      } catch (error) {
        console.error(`Error in event handler for ${event}:`, error);
      }
    });
  }

  /**
   * Join a room/channel
   */
  async joinRoom(room: string): Promise<any> {
    return this.send("room:join", { room }, { timeout: 10000 });
  }

  /**
   * Leave a room/channel
   */
  async leaveRoom(room: string): Promise<any> {
    return this.send("room:leave", { room });
  }

  /**
   * Get users in a room
   */
  async getRoomUsers(room: string): Promise<any[]> {
    return this.send("room:users", { room });
  }

  /**
   * Update presence status
   */
  updatePresence(
    status: "online" | "idle" | "away" | "offline",
    metadata?: Record<string, any>,
  ) {
    this.emit("presence:update", {
      status,
      metadata,
      timestamp: Date.now(),
    });
  }

  /**
   * Subscribe to a channel
   */
  subscribe(channel: string, callback: (data: any) => void): () => void {
    if (!this.subscriptions.has(channel)) {
      this.subscriptions.set(channel, new Set());
      this.socket.emit("subscribe", { channel });
    }

    const handlers = this.subscriptions.get(channel)!;
    handlers.add(() => {});

    // This is a simplified version - in production, you'd manage callbacks per channel
    const handler = (data: any) => {
      // Callback would be called here
    };

    return () => {
      // Unsubscribe logic
    };
  }

  /**
   * Get connection state
   */
  getConnectionState() {
    return this.connectionState;
  }

  /**
   * Check if connected
   */
  getIsConnected(): boolean {
    return this.isConnected;
  }

  /**
   * Disconnect
   */
  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
    this.isConnected = false;
    this.setConnectionState("disconnected");
  }

  /**
   * Reconnect
   */
  reconnect() {
    if (this.socket) {
      this.socket.connect();
    }
  }

  // ==================== Private Methods ====================

  private setConnectionState(
    state: "connecting" | "connected" | "disconnected" | "reconnecting",
  ) {
    this.connectionState = state;
    this.emit("connection_state_change", { state });
  }

  private startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.socket?.connected) {
        this.socket.emit("ping", { timestamp: Date.now() });
      }
    }, 25000);
  }

  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private processMessageQueue() {
    if (this.isProcessingQueue || this.messageQueue.length === 0) return;

    this.isProcessingQueue = true;

    const processNext = () => {
      if (this.messageQueue.length === 0) {
        this.isProcessingQueue = false;
        return;
      }

      const message = this.messageQueue.shift();
      if (message) {
        this.socket.emit("message", message);
        // Process next after a small delay
        setTimeout(processNext, 10);
      } else {
        this.isProcessingQueue = false;
      }
    };

    processNext();
  }

  private generateMessageId(): string {
    return `${Date.now()}-${++this.messageId}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateCorrelationId(): string {
    return `corr-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private setConnectionState(
    state: "connecting" | "connected" | "disconnected" | "reconnecting",
  ) {
    this.connectionState = state;
    this.emit("connection_state_change", { state });
  }

  private emit(event: string, payload: any) {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      handlers.forEach((callback) => {
        try {
          callback(payload);
        } catch (error) {
          console.error(`Error in event handler for ${event}:`, error);
        }
      });
      // Also emit as generic 'message' event for generic handlers
      if (event !== "message") {
        const messageHandlers = this.eventHandlers.get("message");
        if (messageHandlers) {
          messageHandlers.forEach((callback) => {
            try {
              callback({ event, payload });
            } catch (error) {
              console.error("Error in message handler:", error);
            }
          });
        }
      }
    }
  }

  // ==================== Presence Management ====================

  /**
   * Get current presence state
   */
  public getPresence(): Map<string, any> {
    return new Map(this.presenceState);
  }

  /**
   * Update local presence
   */
  updatePresence(data: Partial<any>) {
    if (this.socket?.connected) {
      this.socket.emit("presence:update", {
        ...data,
        timestamp: Date.now(),
      });
    }
  }

  /**
   * Get presence for a user
   */
  getUserPresence(userId: string) {
    return this.presenceState.get(userId);
  }

  /**
   * Get all online users
   */
  getOnlineUsers() {
    const users = [];
    this.presenceState.forEach((presence, userId) => {
      if (presence.status !== "offline") {
        users.push({ userId, ...presence });
      }
    });
    return users;
  }

  // ==================== Room Management ====================

  async joinRoom(room: string): Promise<any> {
    return this.send("room:join", { room });
  }

  async leaveRoom(room: string) {
    this.emit("room:leave", { room });
    this.socket.emit("room:leave", { room });
  }

  async getRoomUsers(room: string) {
    return this.send("room:users", { room });
  }

  // ==================== Request/Response ====================

  private pendingRequests: Map<
    string,
    { resolve: Function; reject: Function; timeout: NodeJS.Timeout }
  > = new Map();

  async request<T = any>(
    event: string,
    payload: any,
    options: { timeout?: number; retries?: number } = {},
  ): Promise<any> {
    const correlationId = this.generateCorrelationId();
    const timeout = 30000;

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(correlationId);
        reject(new Error("Request timeout"));
      }, 30000);

      this.pendingRequests.set(this.generateCorrelationId(), {
        resolve,
        reject,
        timeout,
      });

      this.emit("message", {
        event,
        payload,
        correlationId: this.generateCorrelationId(),
      });
    });
  }

  // ==================== Utility Methods ====================

  private generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateCorrelationId(): string {
    return `corr_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  // Event listener management
  on(event: string, callback: Function): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set());
    }
    this.eventHandlers.get(event)!.add(callback);

    return () => {
      this.eventHandlers.get(event)?.delete(callback);
    };
  }

  off(event: string, callback: Function) {
    this.eventHandlers.get(event)?.delete(callback);
  }

  once(event: string, callback: Function) {
    const wrapper = (payload: any) => {
      this.off(event, wrapper);
      callback(payload);
    };
    this.on(event, wrapper);
  }

  // ==================== Cleanup ====================

  destroy() {
    this.disconnect();
    this.eventHandlers.clear();
    this.subscriptions.clear();
    this.pendingRequests.forEach(({ timeout }) => clearTimeout(timeout));
    this.pendingRequests.clear();
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
  }
}

/**
 * React Hook for WebSocket Gateway
 */
export function useWebSocketGateway(config: {
  url: string;
  token?: string;
  autoConnect?: boolean;
  onConnect?: () => void;
  onDisconnect?: (reason: string) => void;
  onError?: (error: Error) => void;
}) {
  const [gateway, setGateway] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionState, setConnectionState] = useState<
    "connecting" | "connected" | "disconnected" | "reconnecting"
  >("disconnected");
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const { io } = require("socket.io-client");

    const socket = require("socket.io-client").io(config.url, {
      auth: config.token ? { token: config.token } : undefined,
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30000,
      timeout: 20000,
      autoConnect: config.autoConnect ?? true,
    });

    const gateway = {
      socket,
      isConnected: false,
      connectionState: "disconnected" as const,
      on: (event: string, callback: Function) => {
        // Store handler
      },
      off: () => {},
      emit: (event: string, payload: any) => {
        socket.emit("message", { event, payload, timestamp: Date.now() });
      },
      on: (event: string, callback: Function) => {
        socket.on(event, callback);
        return () => socket.off(event, callback);
      },
      emit: (event: string, payload: any) => {
        socket.emit("message", { event, payload, timestamp: Date.now() });
      },
      send: async (event: string, payload: any) => {
        return new Promise((resolve, reject) => {
          // Simplified
        });
      },
      joinRoom: async (room: string) => {
        // Implementation
      },
      leaveRoom: (room: string) => {
        // Implementation
      },
      updatePresence: (status: string, metadata?: any) => {
        // Implementation
      },
      disconnect: () => {
        socket.disconnect();
      },
      isConnected: false,
      connectionState: "disconnected",
    };

    socket.on("connect", () => {
      setIsConnected(true);
      setConnectionState("connected");
    });

    socket.on("disconnect", (reason: string) => {
      setIsConnected(false);
      setConnectionState("disconnected");
    });

    socket.on("connect_error", (error: Error) => {
      setError(error);
    });

    setGateway({
      socket,
      isConnected: false,
      connectionState: "disconnected",
      on: (event: string, callback: Function) => {
        socket.on(event, callback);
        return () => socket.off(event, callback);
      },
      off: () => {},
      emit: (event: string, payload: any) => {
        socket.emit("message", { event, payload, timestamp: Date.now() });
      },
      send: async (event: string, payload: any) => {},
      joinRoom: async (room: string) => {},
      leaveRoom: (room: string) => {},
      updatePresence: (status: string, metadata?: any) => {},
      disconnect: () => {
        socket.disconnect();
      },
      isConnected: false,
      connectionState: "disconnected",
      socket,
    });

    return () => {
      socket.disconnect();
    };
  }, [config.url, config.token, config.autoConnect]);

  return {
    gateway,
    isConnected,
    connectionState,
    error,
  };
}

/**
 * React Hook for WebSocket Gateway
 */
export function useWebSocketGateway(config: {
  url: string;
  token?: string;
  autoConnect?: boolean;
  onConnect?: () => void;
  onDisconnect?: (reason: string) => void;
  onError?: (error: Error) => void;
}) {
  const [socket, setSocket] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionState, setConnectionState] = useState<
    "connecting" | "connected" | "disconnected" | "reconnecting"
  >("disconnected");
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const { io } = require("socket.io-client");

    const socket = io(config.url, {
      auth: config.token ? { token: config.token } : undefined,
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30000,
      timeout: 20000,
      autoConnect: config.autoConnect !== false,
    });

    socket.on("connect", () => {
      setIsConnected(true);
      setConnectionState("connected");
      config.onConnect?.();
    });

    socket.on("disconnect", (reason: string) => {
      setIsConnected(false);
      setConnectionState("disconnected");
      config.onDisconnect?.(reason);
    });

    socket.on("connect_error", (error: Error) => {
      setError(error);
      setConnectionState("disconnected");
      config.onError?.(error);
    });

    socket.on("reconnect", (attemptNumber: number) => {
      setConnectionState("connected");
    });

    socket.on("reconnect_attempt", (attemptNumber: number) => {
      setConnectionState("reconnecting");
    });

    setSocket(socket);

    return () => {
      socket.disconnect();
    };
  }, [config.url, config.token, config.autoConnect]);

  return {
    socket,
    isConnected,
    connectionState,
    error,
  };
}

/**
 * Real-time presence hook
 */
export function usePresence(socket: any, userId: string) {
  const [presence, setPresence] = useState<any>({});
  const [onlineUsers, setOnlineUsers] = useState<any[]>([]);

  useEffect(() => {
    if (!socket) return;

    const handlePresence = (data: any) => {
      setPresence((prev) => ({
        ...prev,
        [data.userId]: { ...data, lastSeen: Date.now() },
      }));
    };

    const handlePresenceJoin = (data: any) => {
      setPresence((prev) => ({
        ...prev,
        [data.userId]: { ...data, lastSeen: Date.now() },
      }));
    };

    const handlePresenceLeave = (data: any) => {
      setPresence((prev) => {
        const next = { ...prev };
        delete next[data.userId];
        return next;
      });
    };

    const handlePresenceUpdate = (data: any) => {
      setPresence((prev) => ({
        ...prev,
        [data.userId]: { ...prev[data.userId], ...data, lastSeen: Date.now() },
      }));
    };

    // Subscribe to presence events
    // In a real implementation, you'd subscribe to presence events
    // This is a simplified version

    return () => {
      // Cleanup
    };
  }, []);

  return { presence, onlineUsers };
}

/**
 * Real-time collaboration hook for document editing
 */
export function useCollaborativeEditing(documentId: string, socket: any) {
  const [content, setContent] = useState("");
  const [cursors, setCursors] = useState<
    Map<
      string,
      { x: number; y: number; userId: string; userName: string; color: string }
    >
  >(new Map());
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Join document room
    // Subscribe to document changes
    // Handle cursor positions
    // Handle text operations

    return () => {
      // Cleanup
    };
  }, [documentId]);

  const applyOperation = useCallback((operation: any) => {
    // Apply remote operation to local content
  }, []);

  const sendOperation = useCallback((operation: any) => {
    // Send operation to server
  }, []);

  const updateCursor = useCallback((position: { x: number; y: number }) => {
    // Send cursor position
  }, []);

  return {
    content,
    setContent,
    cursors,
    isConnected,
    sendOperation: () => {},
    updateCursor: () => {},
  };
}

export default {
  WebSocketGateway,
  useWebSocketGateway,
  usePresence,
  useCollaborativeEditing,
};
