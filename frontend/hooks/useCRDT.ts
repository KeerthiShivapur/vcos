/**
 * CRDT Document Hook
 * React hook for managing CRDT-based collaborative documents via Socket.IO
 */

"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useAuth } from "./useAuth";
import { useRealtime, RoomParticipant } from "./useRealtime";

interface CRDTDocumentState {
  docId: string;
  crdtType: "ytext" | "yarray" | "ymap" | "counter";
  content: string | any[];
  version: number;
  clients: Map<
    string,
    {
      cursor?: { x: number; y: number };
      selection?: { start: number; end: number };
      userName: string;
      userColor: string;
      status: "online" | "idle" | "away" | "offline";
    }
  >;
  lastModified: number;
  lastModifiedBy: string;
}

export interface CRDTOperation {
  id: string;
  type: "insert" | "delete" | "update" | "retain";
  position: number;
  content?: string;
  length?: number;
  attributes?: Record<string, any>;
  timestamp: number;
  clientId: string;
}

interface UseCRDTDocumentOptions {
  documentId: string;
  crdtType?: "ytext" | "yarray" | "ymap" | "counter";
  autoConnect?: boolean;
  onContentChange?: (content: string | any[]) => void;
  onPresenceChange?: (clients: Map<string, any>) => void;
  onConnectionChange?: (connected: boolean) => void;
}

export function useCRDTDocument(options: UseCRDTDocumentOptions) {
  const { documentId, crdtType = "ytext", autoConnect = true, onContentChange, onPresenceChange, onConnectionChange } = options;
  const { user, accessToken, organization } = useAuth();
  const organizationId = organization?.id || "";

  // Use the Socket.IO based realtime hook
  const realtime = useRealtime({
    organizationId,
    autoConnect,
    onRoomState: (roomState) => {
      if (roomState.document) {
        setState((prev) => ({
          ...prev,
          content: roomState.document,
          version: 0, // Would come from roomState in production
        }));
      }
      if (roomState.participants) {
        const newClients = new Map<string, any>();
        roomState.participants.forEach((p: RoomParticipant) => {
          newClients.set(p.user_id, {
            cursor: p.cursor,
            selection: p.selection,
            userName: p.user_name,
            userColor: p.user_color,
            status: "online",
          });
        });
        setState((prev) => ({ ...prev, clients: newClients }));
        onPresenceChange?.(newClients);
      }
    },
    onMessage: (message) => {
      if (message.type === "crdt:update") {
        const update = message.payload.update;
        const newContent = applyOperation(state.content, update);
        setState((prev) => ({
          ...prev,
          content: newContent,
          version: prev.version + 1,
          lastModified: Date.now(),
        }));
        onContentChange?.(newContent);
      }
    },
  });

  const [state, setState] = useState<{
    content: string | any[];
    version: number;
    clients: Map<string, any>;
    isConnected: boolean;
    connectionError: string | null;
    lastModified: number;
  }>({
    content: crdtType === "ytext" ? "" : [],
    version: 0,
    clients: new Map(),
    isConnected: false,
    connectionError: null,
    lastModified: 0,
  });

  // Sync connection state from realtime hook
  useEffect(() => {
    setState((prev) => ({ ...prev, isConnected: realtime.isConnected }));
    onConnectionChange?.(realtime.isConnected);
  }, [realtime.isConnected, onConnectionChange]);

  // Apply local operation immediately (optimistic UI)
  const applyLocalOperation = useCallback(
    (operation: Omit<CRDTOperation, "id" | "timestamp" | "clientId">) => {
      setState((prev) => {
        const newContent = applyOperation(prev.content, operation);
        onContentChange?.(newContent);
        return {
          ...prev,
          content: newContent,
          version: prev.version + 1,
          lastModified: Date.now(),
        };
      });

      // Send to server via Socket.IO
      if (realtime.isConnected) {
        realtime.sendCrdtUpdate(documentId, operation);
      }
    },
    [realtime, documentId, onContentChange]
  );

  // Update cursor/selection
  const updateCursor = useCallback(
    (position: { x: number; y: number }) => {
      realtime.updateCursor(documentId, position);
    },
    [realtime, documentId]
  );

  const updateSelection = useCallback(
    (selection: { start: number; end: number }) => {
      realtime.updateCursor(documentId, null, selection);
    },
    [realtime, documentId]
  );

  // Join/leave room
  useEffect(() => {
    if (realtime.isConnected) {
      realtime.joinRoom(documentId, crdtType);
    }
    return () => {
      realtime.leaveRoom(documentId);
    };
  }, [realtime.isConnected, documentId, crdtType, realtime]);

  // Presence updates
  const updateStatus = useCallback(
    (status: "online" | "idle" | "away" | "offline") => {
      realtime.updatePresence(status);
    },
    [realtime]
  );

  return {
    content: state.content,
    version: state.version,
    clients: state.clients,
    isConnected: state.isConnected,
    connectionError: state.connectionError,
    lastModified: state.lastModified,
    sendOperation: applyLocalOperation,
    updateCursor,
    updateSelection,
    updateStatus,
    joinRoom: () => realtime.joinRoom(documentId, crdtType),
    leaveRoom: () => realtime.leaveRoom(documentId),
  };
}

// Hook for managing multiple CRDT documents
export function useCRDTDocuments(
  documentIds: string[],
  options: { crdtType?: "ytext" | "yarray" | "ymap" | "counter"; autoConnect?: boolean } = {}
) {
  const { crdtType = "ytext", autoConnect = true } = options;

  const documents = useMemo(
    () =>
      documentIds.map((id) =>
        useCRDTDocument({
          documentId: id,
          crdtType,
          autoConnect,
        })
      ),
    [documentIds, crdtType, autoConnect]
  );

  const allConnected = documents.every((d) => d.isConnected);
  const anyError = documents.some((d) => d.connectionError);

  return {
    documents,
    allConnected,
    anyError,
    getDocument: (id: string) => documents.find((d) => d.content && d.content.docId === id),
  };
}

// Hook for comment threads on CRDT documents
export function useCRDTComments(documentId: string) {
  const [comments, setComments] = useState<Array<{
    id: string;
    threadId: string;
    parentId?: string;
    authorId: string;
    authorName: string;
    content: string;
    createdAt: number;
    updatedAt: number;
    resolved: boolean;
    reactions: Record<string, string[]>;
  }>>([]);

  const { sendMessage } = useRealtime({ organizationId: "", autoConnect: false });

  const addComment = useCallback(
    async (content: string, parentId?: string) => {
      const comment = {
        id: crypto.randomUUID(),
        threadId: documentId,
        parentId,
        authorId: "", // Will be filled by auth
        authorName: "", // Will be filled by auth
        content,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        resolved: false,
        reactions: {},
      };

      // Send via real-time message
      await sendMessage(documentId, content, "comment");

      setComments((prev) => [...prev, comment]);
      return comment;
    },
    [documentId, sendMessage]
  );

  const updateComment = useCallback((commentId: string, content: string) => {
    setComments((prev) =>
      prev.map((c) => (c.id === commentId ? { ...c, content, updatedAt: Date.now() } : c))
    );
  }, []);

  const deleteComment = useCallback((commentId: string) => {
    setComments((prev) => prev.filter((c) => c.id !== commentId));
  }, []);

  const resolveThread = useCallback(() => {
    setComments((prev) => prev.map((c) => ({ ...c, resolved: true })));
  }, []);

  return {
    comments,
    addComment,
    updateComment,
    deleteComment,
    resolveThread,
  };
}

// Hook for real-time cursors and selections
export function useCRDTCursors(documentId: string) {
  const { clients } = useCRDTDocument({ documentId });

  const cursors = useMemo(
    () =>
      Array.from(clients.entries()).map(([clientId, data]) => ({
        clientId,
        cursor: data.cursor,
        selection: data.selection,
        userName: data.userName,
        userColor: data.userColor,
        status: data.status,
      })),
    [clients]
  );

  const { updateCursor: updateCursorRealtime } = useCRDTDocument({ documentId });

  const updateCursor = useCallback(
    (position: { x: number; y: number }) => {
      updateCursorRealtime(position);
    },
    [updateCursorRealtime]
  );

  const updateSelection = useCallback(
    (selection: { start: number; end: number }) => {
      updateSelection(selection);
    },
    [updateSelection]
  );

  return {
    cursors,
    updateCursor,
    updateSelection,
  };
}

// Helper function to apply CRDT operation
function applyOperation(content: string | any[], operation: CRDTOperation): string | any[] {
  if (typeof content === "string") {
    // Text operations
    if (operation.type === "insert") {
      const pos = Math.min(operation.position, content.length);
      return content.slice(0, pos) + (operation.content || "") + content.slice(pos);
    } else if (operation.type === "delete") {
      const pos = Math.min(operation.position, content.length);
      const end = Math.min(pos + (operation.length || 0), content.length);
      return content.slice(0, pos) + content.slice(end);
    }
  } else if (Array.isArray(content)) {
    // Array operations
    if (operation.type === "insert") {
      const pos = Math.min(operation.position, content.length);
      return [...content.slice(0, pos), operation.content, ...content.slice(pos)];
    } else if (operation.type === "delete") {
      const pos = Math.min(operation.position, content.length);
      const end = Math.min(pos + (operation.length || 0), content.length);
      return [...content.slice(0, pos), ...content.slice(end)];
    }
  }
  return content;
}