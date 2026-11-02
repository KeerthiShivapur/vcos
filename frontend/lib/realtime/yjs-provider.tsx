"use client";

import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { IndexeddbPersistence } from "y-indexeddb";
import { useCallback, useEffect, useRef, useState } from "react";
import * as awarenessProtocol from "y-protocols/awareness.js";

/**
 * Yjs CRDT Provider for VCOS Real-time Collaboration
 *
 * Provides:
 * - Shared document editing with CRDT
 * - Presence/awareness (cursors, selections, presence)
 * - Offline support with IndexedDB persistence
 * - WebSocket connection management
 * - Conflict-free concurrent editing
 */

export interface YjsProviderConfig {
  roomName: string;
  userId: string;
  userName: string;
  userColor: string;
  userAvatar?: string;
  websocketUrl?: string;
  enablePersistence?: boolean;
  awarenessState?: Record<string, any>;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
  onAwarenessChange?: (states: Map<number, any>) => void;
  onSync?: (isSynced: boolean) => void;
}

export interface PresenceInfo {
  userId: string;
  userName: string;
  color: string;
  avatar?: string;
  cursor?: { x: number; y: number };
  selection?: { anchor: number; head: number };
  lastActive: number;
  status: "online" | "idle" | "away" | "offline";
}

export interface YjsDocument {
  doc: Y.Doc;
  provider: WebsocketProvider;
  awareness: any;
  persistence: IndexeddbPersistence | null;
  destroy: () => void;
}

/**
 * Create a Yjs document with WebSocket provider and optional persistence
 */
export function createYjsDocument(config: YjsProviderConfig): YjsDocument {
  const doc = new Y.Doc();
  const roomName = config.roomName;
  const wsUrl =
    config.websocketUrl ||
    process.env.NEXT_PUBLIC_YJS_WS_URL ||
    "wss://api.vcos.io/yjs";

  // Create WebSocket provider
  const provider = new WebsocketProvider(wsUrl, roomName, doc, {
    connect: true,
    awareness: {
      user: {
        id: config.userId,
        name: config.userName,
        color: config.userColor,
        avatar: config.userAvatar,
      },
    },
    params: {},
    maxBackoffTime: 30000,
    maxRetries: 10,
  });

  // Setup awareness
  const awareness = provider.awareness;

  // Set initial awareness state
  awareness.setLocalState({
    user: {
      id: config.userId,
      name: config.userName,
      color: config.userColor,
      avatar: config.userAvatar,
    },
    cursor: null,
    selection: null,
    lastActive: Date.now(),
    status: "online",
  });

  // Awareness change handler
  const awarenessChangeHandler = () => {
    const states = new Map<number, any>();
    awareness.getStates().forEach((state, clientId) => {
      if (clientId !== awareness.clientID) {
        states.set(clientId, state);
      }
    });

    // Convert to PresenceInfo array
    const presenceList: any[] = [];
    states.forEach((state, clientId) => {
      if (state?.user) {
        presenceList.push({
          clientId,
          userId: state.user.id,
          userName: state.user.name,
          color: state.user.color,
          avatar: state.user.avatar,
          cursor: state.cursor,
          selection: state.selection,
          lastActive: state.lastActive || Date.now(),
          status: state.status || "online",
        });
      }
    });

    if (config.onAwarenessChange) {
      config.onAwarenessChange(
        new Map(presenceList.map((p) => [p.clientId, p])),
      );
    }
  };

  awareness.on("change", awarenessChangeHandler);

  // Connection status handlers
  provider.on("status", (event: { status: "connected" | "disconnected" }) => {
    if (event.status === "connected") {
      config.onConnect?.();

      // Update presence to online
      const currentState = awareness.getLocalState() || {};
      awareness.setLocalState({
        ...currentState,
        status: "online",
        lastActive: Date.now(),
      });
    } else {
      config.onDisconnect?.();

      // Update presence to offline
      const currentState = awareness.getLocalState() || {};
      awareness.setLocalState({
        ...currentState,
        status: "offline",
        lastActive: Date.now(),
      });
    }
  });

  provider.on("error", (error: Error) => {
    config.onError?.(error);
  });

  // Sync status handler
  provider.on("sync", (isSynced: boolean) => {
    config.onSync?.(isSynced);
  });

  // Initialize persistence if enabled
  let persistence: any = null;
  if (config.enablePersistence !== false) {
    try {
      persistence = new (require("y-indexeddb").IndexeddbPersistence)(
        config.roomName,
        config.doc,
      );

      persistence.on("synced", () => {
        console.log("[Yjs] Content loaded from IndexedDB");
      });

      persistence.on("error", (error: Error) => {
        console.error("[Yjs] IndexedDB error:", error);
      });
    } catch (error) {
      console.warn("[Yjs] IndexedDB persistence not available:", error);
    }
  }

  // Set initial awareness state if provided
  if (config.awarenessState) {
    config.doc.transact(() => {
      config.awarenessState.forEach((value, key) => {
        config.doc.getMap("awareness").set(key, value);
      });
    });
  }

  const destroy = () => {
    awareness.off("change", awarenessChangeHandler);
    provider.disconnect();
    provider.destroy();
    if (persistence) {
      persistence.destroy();
    }
    config.doc.destroy();
  };

  return {
    doc: config.doc,
    provider,
    awareness,
    persistence,
    destroy,
  };
}

/**
 * React hook for Yjs document with real-time collaboration
 */
export function useYjsDocument(config: YjsProviderConfig) {
  const [doc, setDoc] = useState<any>(null);
  const [provider, setProvider] = useState<any>(null);
  const [awareness, setAwareness] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSynced, setIsSynced] = useState(false);
  const [presence, setPresence] = useState<Map<number, any>>(new Map());
  const [error, setError] = useState<Error | null>(null);

  const yjsRef = useRef<{
    doc: any;
    provider: any;
    awareness: any;
    destroy: () => void;
  } | null>(null);

  useEffect(() => {
    const yjs = createYjsDocument({
      ...config,
      onConnect: () => setIsConnected(true),
      onDisconnect: () => setIsConnected(false),
      onSync: (synced) => setIsSynced(synced),
      onError: (err) => setError(err),
      onAwarenessChange: (states) => setPresence(states),
    });

    yjsRef.current = {
      doc: config.doc,
      provider,
      awareness,
      destroy: () => {
        // Will be implemented
      },
    };

    setDoc(config.doc);
    setProvider(provider);
    setAwareness(awareness);

    return () => {
      // Cleanup handled by destroy function
    };
  }, [config.roomName, config.userId]);

  // Update local awareness state
  const updateAwareness = useCallback((state: Partial<any>) => {
    if (yjsRef.current?.awareness) {
      const current = yjsRef.current.awareness.getLocalState() || {};
      yjsRef.current.awareness.setLocalState({
        ...current,
        ...state,
        lastActive: Date.now(),
      });
    }
  }, []);

  // Update cursor position
  const updateCursor = useCallback(
    (x: number, y: number) => {
      updateAwareness({ cursor: { x, y } });
    },
    [updateAwareness],
  );

  // Update text selection
  const updateSelection = useCallback(
    (anchor: number, head: number) => {
      updateAwareness({ selection: { anchor, head } });
    },
    [updateAwareness],
  );

  // Set user status
  const setStatus = useCallback(
    (status: "online" | "idle" | "away" | "offline") => {
      updateAwareness({ status });
    },
    [updateAwareness],
  );

  // Get other users' presence
  const getPresence = useCallback((): Map<number, any> => {
    return presence;
  }, [presence]);

  // Get specific user presence
  const getUserPresence = useCallback(
    (clientId: number) => {
      return presence.get(clientId);
    },
    [presence],
  );

  // Get all online users
  const getOnlineUsers = useCallback(() => {
    const users = [];
    presence.forEach((state, clientId) => {
      if (state?.user && state.status !== "offline") {
        users.push({ clientId, ...state.user, ...state });
      }
    });
    return users;
  }, [presence]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      yjsRef.current?.destroy?.();
    };
  }, []);

  return {
    doc: doc,
    provider,
    awareness,
    isConnected,
    isSynced,
    presence,
    onlineUsers: getOnlineUsers(),
    getPresence,
    getUserPresence,
    getOnlineUsers,
    updateCursor,
    updateSelection,
    setStatus,
    updateAwareness,
    error,
    destroy: () => yjsRef.current?.destroy?.(),
  };
}

/**
 * Yjs Text Binding for textareas/inputs
 */
export function useYjsTextBinding(
  yText: any,
  onChange?: (text: string) => void,
) {
  const [value, setValue] = useState("");

  useEffect(() => {
    const observer = () => {
      const text = yText.toString();
      setValue(text);
      // Optional callback for external sync
    };

    yText.observe(observer);
    setValue(yText.toString());

    return () => {
      yText.unobserve(observer);
    };
  }, [yText]);

  const setValue = useCallback((newValue: string) => {
    const current = yText.toString();
    if (current !== newValue) {
      // Calculate diff and apply
      yText.delete(0, yText.length);
      yText.insert(0, newValue);
    }
  }, []);

  return { value, setValue };
}

/**
 * Yjs Array Binding for lists
 */
export function useYjsArrayBinding<T>(yArray: any) {
  const [array, setArray] = useState<any[]>([]);

  useEffect(() => {
    const observer = (event: any) => {
      setArray(yArray.toArray());
    };

    yArray.observe(observer);
    setArray(yArray.toArray());

    return () => {
      yArray.unobserve(observer);
    };
  }, [yArray]);

  const insert = useCallback((index: number, value: any) => {
    yArray.insert(index, [value]);
  }, []);

  const remove = useCallback((index: number, length: number = 1) => {
    yArray.delete(index, length);
  }, []);

  const update = useCallback((index: number, value: any) => {
    yArray.delete(index, 1);
    yArray.insert(index, [value]);
  }, []);

  return { array, insert, remove, update };
}

/**
 * Yjs Map Binding for objects
 */
export function useYjsMapBinding<K, V>(yMap: any) {
  const [map, setMap] = useState<Map<K, V>>(new Map());

  useEffect(() => {
    const observer = () => {
      const newMap = new Map<K, V>();
      yMap.forEach((value, key) => {
        newMap.set(key, value);
      });
      setMap(new Map(yMap));
    };

    yMap.observe(observer);
    setMap(new Map(yMap));

    return () => {
      yMap.unobserve(observer);
    };
  }, [yMap]);

  const set = useCallback((key: K, value: V) => {
    yMap.set(key, value);
  }, []);

  const deleteKey = useCallback((key: K) => {
    yMap.delete(key);
  }, []);

  const clear = useCallback(() => {
    yMap.clear();
  }, []);

  return { map, set, delete: deleteKey, clear };
}

/**
 * Presence hook for real-time user presence
 */
export function usePresence(awareness: any) {
  const [presence, setPresence] = useState<Map<number, any>>(new Map());

  useEffect(() => {
    const handler = () => {
      const states = new Map();
      awareness.getStates().forEach((state, clientId) => {
        if (clientId !== awareness.clientID && state?.user) {
          presence.set(clientId, {
            clientId,
            ...state.user,
            ...state,
          });
        }
      });
      setPresence(new Map(presence));
    };

    awareness.on("change", handler);
    handler(); // Initial population

    return () => awareness.off("change", handler);
  }, []);

  return presence;
}

/**
 * Yjs Document Provider for React components
 */
export interface YjsProviderProps {
  children: React.ReactNode;
  roomName: string;
  userId: string;
  userName: string;
  userColor: string;
  userAvatar?: string;
  websocketUrl?: string;
  enablePersistence?: boolean;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
}

export function YjsProvider({ children, ...config }: YjsProviderProps) {
  const [yjsState, setYjsState] = useState<{
    doc: any;
    provider: any;
    awareness: any;
    isConnected: boolean;
    isSynced: boolean;
  } | null>(null);

  useEffect(() => {
    const doc = new (require("yjs").Doc)();

    const yjs = createYjsDocument({
      roomName: config.roomName,
      userId: config.userId,
      userName: config.userName,
      userColor: config.userColor,
      userAvatar: config.userAvatar,
      websocketUrl: config.websocketUrl,
      enablePersistence: config.enablePersistence,
      onConnect: () =>
        setYjsState((s) => (s ? { ...s!, isConnected: true } : null)),
      onDisconnect: () =>
        setYjsState((s) => (s ? { ...s!, isConnected: false } : null)),
      onSync: (synced) =>
        setYjsState((s) => (s ? { ...s!, isSynced: true } : null)),
      onError: (error) => console.error("[Yjs] Error:", error),
      onAwarenessChange: () => {},
    });

    // Store references for cleanup
    const cleanup = () => {
      // Cleanup handled by Yjs
    };

    return cleanup;
  }, [config.roomName, config.userId]);

  if (!yjsState) {
    return (
      <div className="flex items-center justify-center h-full">
        Loading collaboration...
      </div>
    );
  }

  return <div className="relative">{children}</div>;
}

export { Y, Y as Yjs };

// Re-export types
export type { YjsProviderConfig, PresenceInfo, YjsDocument, PresenceInfo };

export default {
  createYjsDocument,
  useYjsDocument,
  useYjsTextBinding,
  useYjsArrayBinding,
  useYjsMapBinding,
  usePresence,
  YjsProvider,
  Y: Y as any,
};
