"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { io, Socket } from "socket.io-client";
import { useAuth } from "./useAuth";

export interface RealtimeMessage {
  type: string;
  payload: any;
}

export interface PresenceData {
  user_id: string;
  user_name: string;
  user_color: string;
  organization_id: string;
  status: "online" | "idle" | "away" | "offline";
  cursor?: { x: number; y: number };
  selection?: { start: number; end: number };
  last_activity: string;
}

export interface RoomParticipant {
  connection_id: string;
  user_id: string;
  user_name: string;
  user_color: string;
  cursor?: { x: number; y: number };
}

export interface UseRealtimeOptions {
  organizationId: string;
  onMessage?: (message: RealtimeMessage) => void;
  onPresenceChange?: (presences: PresenceData[]) => void;
  onRoomState?: (state: { participants: RoomParticipant[]; document?: any }) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  autoConnect?: boolean;
}

export function useRealtime(options: UseRealtimeOptions) {
  const {
    organizationId,
    onMessage,
    onPresenceChange,
    onRoomState,
    onConnect,
    onDisconnect,
    autoConnect = true,
  } = options;
  const { user, accessToken } = useAuth();

  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [presences, setPresences] = useState<PresenceData[]>([]);

  const socketRef = useRef<Socket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const baseReconnectDelay = 1000;

  const connect = useCallback(async () => {
    if (!user || !accessToken || !organizationId) return;

    try {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "http://127.0.0.1:8000";
      
      const socket = io(wsUrl, {
        path: "/socket.io",
        auth: { token: accessToken },
        query: { organization_id: organizationId },
        transports: ["websocket", "polling"],
        reconnection: false, // We handle reconnection manually
      });

      socketRef.current = socket;

      socket.on("connect", () => {
        console.log("[Realtime] Connected:", socket.id);
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      });

      socket.on("disconnect", (reason) => {
        console.log("[Realtime] Disconnected:", reason);
        setIsConnected(false);
        onDisconnect?.();

        // Attempt reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttemptsRef.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++;
            connect();
          }, delay);
        } else {
          setConnectionError("Max reconnection attempts reached");
        }
      });

      socket.on("connect_error", (error) => {
        console.error("[Realtime] Connection error:", error);
        setConnectionError(error.message || "Connection failed");
      });

      // Handle incoming events
      socket.on("connected", (data) => {
        console.log("[Realtime] Server confirmed connection:", data);
      });

      socket.on("user_joined", (data) => {
        console.log("[Realtime] User joined:", data);
      });

      socket.on("user_left", (data) => {
        console.log("[Realtime] User left:", data);
      });

      socket.on("user_joined_room", (data) => {
        console.log("[Realtime] User joined room:", data);
      });

      socket.on("user_left_room", (data) => {
        console.log("[Realtime] User left room:", data);
      });

      socket.on("room_state", (data) => {
        console.log("[Realtime] Room state:", data);
        onRoomState?.(data);
      });

      socket.on("cursor_update", (data) => {
        console.log("[Realtime] Cursor update:", data);
        // Update presence with cursor
        setPresences((prev) =>
          prev.map((p) =>
            p.user_id === data.user_id
              ? { ...p, cursor: data.cursor, selection: data.selection }
              : p
          )
        );
        onPresenceChange?.(presences);
      });

      socket.on("crdt_update", (data) => {
        console.log("[Realtime] CRDT update:", data);
        if (onMessage) {
          onMessage({ type: "crdt:update", payload: data });
        }
      });

      socket.on("message", (data) => {
        console.log("[Realtime] Message:", data);
        if (onMessage) {
          onMessage({ type: "message", payload: data });
        }
      });

      socket.on("typing_start", (data) => {
        if (onMessage) {
          onMessage({ type: "typing:start", payload: data });
        }
      });

      socket.on("typing_stop", (data) => {
        if (onMessage) {
          onMessage({ type: "typing:stop", payload: data });
        }
      });

      socket.on("pong", (data) => {
        console.log("[Realtime] Pong:", data);
      });

    } catch (error) {
      console.error("[Realtime] Connection failed:", error);
      setConnectionError("Connection failed");
    }
  }, [
    user,
    accessToken,
    organizationId,
    onMessage,
    onPresenceChange,
    onRoomState,
    onConnect,
    onDisconnect,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const send = useCallback((event: string, data: any) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit(event, data);
    }
  }, []);

  const joinRoom = useCallback(
    (roomId: string, roomType: string = "document") => {
      send("join_room", { room_id: roomId, room_type: roomType });
    },
    [send]
  );

  const leaveRoom = useCallback(
    (roomId: string) => {
      send("leave_room", { room_id: roomId });
    },
    [send]
  );

  const updatePresence = useCallback(
    (status: "online" | "idle" | "away" | "offline") => {
      send("presence:update", { status });
    },
    [send]
  );

  const updateCursor = useCallback(
    (roomId: string, cursor: { x: number; y: number } | null, selection?: { start: number; end: number }) => {
      send("cursor_update", { room_id: roomId, cursor, selection });
    },
    [send]
  );

  const sendCrdtUpdate = useCallback(
    (roomId: string, update: any) => {
      send("crdt_update", { room_id: roomId, update });
    },
    [send]
  );

  const sendMessage = useCallback(
    (roomId: string, content: string, type: string = "text") => {
      send("message", { room_id: roomId, content, type });
    },
    [send]
  );

  const startTyping = useCallback(
    (roomId: string) => {
      send("typing_start", { room_id: roomId });
    },
    [send]
  );

  const stopTyping = useCallback(
    (roomId: string) => {
      send("typing_stop", { room_id: roomId });
    },
    [send]
  );

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    return () => {
      disconnect();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect, disconnect, autoConnect]);

  // Heartbeat to keep connection alive
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      if (socketRef.current?.connected) {
        socketRef.current.emit("ping", { timestamp: new Date().toISOString() });
      }
    }, 30000); // Every 30 seconds

    return () => clearInterval(interval);
  }, [isConnected]);

  return {
    isConnected,
    connectionError,
    presences,
    connect,
    disconnect,
    send,
    joinRoom,
    leaveRoom,
    updatePresence,
    updateCursor,
    sendCrdtUpdate,
    sendMessage,
    startTyping,
    stopTyping,
  };
}

export function usePresence(organizationId: string) {
  const { presences, isConnected } = useRealtime({ organizationId });

  const getUserPresence = useCallback(
    (userId: string) => {
      return presences.find((p) => p.user_id === userId);
    },
    [presences],
  );

  const isUserOnline = useCallback(
    (userId: string) => {
      const presence = presences.find((p) => p.user_id === userId);
      return presence?.status === "online";
    },
    [presences],
  );

  const getOnlineUsers = useCallback(() => {
    return presences.filter((p) => p.status === "online");
  }, [presences]);

  return {
    presences,
    isConnected,
    getUserPresence,
    isUserOnline,
    getOnlineUsers,
  };
}