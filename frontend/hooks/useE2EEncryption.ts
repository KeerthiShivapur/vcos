"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "./useAuth";

export interface IdentityKey {
  keyId: string;
  publicKey: string;
  keyType: string;
  createdAt: number;
  expiresAt?: number;
}

export interface PreKeyBundle {
  identityKey: string;
  signedPrekey: string;
  signedPrekeySignature: string;
  onetimePrekeys: string[];
  registrationId: number;
}

export interface SessionState {
  sessionId: string;
  localIdentityKey: string;
  remoteIdentityKey: string;
  rootKey: string;
  messageNumberSend: number;
  messageNumberRecv: number;
  createdAt: number;
}

export interface EncryptedMessage {
  header: {
    senderRegistrationId: number;
    senderEphemeral: string;
    messageNumber: number;
    previousChainLength: number;
  };
  ciphertext: string;
  mac: string;
}

export interface DocumentKey {
  documentId: string;
  hasAccess: boolean;
  key?: string;
}

export interface EncryptedOperation {
  encrypted: string;
}

export interface E2EEncryptionState {
  isInitialized: boolean;
  identityKey: IdentityKey | null;
  prekeyBundle: PreKeyBundle | null;
  sessions: SessionState[];
  activeSessionId: string | null;
  error: string | null;
}

export function useE2EEncryption(
  options: {
    autoInitialize?: boolean;
    onError?: (error: Error) => void;
  } = {},
) {
  const { autoInitialize = true, onError } = options;
  const { user, accessToken } = useAuth();

  const [state, setState] = useState<E2EEncryptionState>({
    isInitialized: false,
    identityKey: null,
    prekeyBundle: null,
    sessions: [],
    activeSessionId: null,
    error: null,
  });

  const [documentKeys, setDocumentKeys] = useState<Map<string, string>>(
    new Map(),
  );
  const [documentAccess, setDocumentAccess] = useState<Map<string, string[]>>(
    new Map(),
  );

  const init = useCallback(async () => {
    if (!user || !accessToken) return;

    try {
      // Initialize identity key
      const identityRes = await fetch("/api/v1/e2e/identity", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (identityRes.ok) {
        const identity = await identityRes.json();
        setState((prev) => ({ ...prev, identityKey: identity }));
      }

      // Initialize prekey bundle
      const prekeyRes = await fetch("/api/v1/e2e/prekeys", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (prekeyRes.ok) {
        const prekeyBundle = await prekeyRes.json();
        setState((prev) => ({ ...prev, prekeyBundle }));
      }

      // Load sessions
      const sessionsRes = await fetch("/api/v1/e2e/sessions", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (sessionsRes.ok) {
        const sessions = await sessionsRes.json();
        setState((prev) => ({
          ...prev,
          sessions,
          activeSessionId: sessions[0]?.sessionId || null,
        }));
      }

      setState((prev) => ({ ...prev, isInitialized: true, error: null }));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      setState((prev) => ({ ...prev, error: err.message }));
      onError?.(err);
    }
  }, [user, accessToken, onError]);

  useEffect(() => {
    if (autoInitialize) {
      init();
    }
  }, [autoInitialize, init]);

  // ==================== Session Management ====================

  const createSession = useCallback(
    async (recipientId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/sessions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ recipient_id: recipientId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to create session");
      }

      const session = await res.json();
      setState((prev) => ({
        ...prev,
        sessions: [...prev.sessions, session],
        activeSessionId: session.sessionId,
      }));

      return session;
    },
    [accessToken],
  );

  const getSession = useCallback(
    (sessionId: string) => {
      return state.sessions.find((s) => s.sessionId === sessionId);
    },
    [state.sessions],
  );

  const setActiveSession = useCallback((sessionId: string) => {
    setState((prev) => ({ ...prev, activeSessionId: sessionId }));
  }, []);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch(`/api/v1/e2e/sessions/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to delete session");
      }

      setState((prev) => ({
        ...prev,
        sessions: prev.sessions.filter((s) => s.sessionId !== sessionId),
        activeSessionId:
          prev.activeSessionId === sessionId ? null : prev.activeSessionId,
      }));
    },
    [accessToken],
  );

  // ==================== Message Encryption ====================

  const encryptMessage = useCallback(
    async (sessionId: string, plaintext: string, associatedData?: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/encrypt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          plaintext,
          associated_data: associatedData,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to encrypt message");
      }

      return (await res.json()) as EncryptedMessage;
    },
    [accessToken],
  );

  const decryptMessage = useCallback(
    async (
      sessionId: string,
      encrypted: EncryptedMessage,
      associatedData?: string,
    ) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/decrypt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          header: encrypted.header,
          ciphertext: encrypted.ciphertext,
          mac: encrypted.mac,
          associated_data: associatedData,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to decrypt message");
      }

      return (await res.json()).plaintext;
    },
    [accessToken],
  );

  // ==================== Document Keys ====================

  const getDocumentKey = useCallback(
    async (documentId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      // Check cache first
      if (documentKeys.has(documentId)) {
        return documentKeys.get(documentId)!;
      }

      const res = await fetch(`/api/v1/e2e/documents/${documentId}/key`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!res.ok) {
        throw new Error("Failed to get document key");
      }

      const result = (await res.json()) as DocumentKey;

      if (result.hasAccess && result.key) {
        setDocumentKeys((prev) => new Map(prev).set(documentId, result.key!));
      }

      return result.key;
    },
    [accessToken, documentKeys],
  );

  const shareDocumentKey = useCallback(
    async (documentId: string, recipientId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch(`/api/v1/e2e/documents/${documentId}/share`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ recipient_id: recipientId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to share document key");
      }

      return res.json();
    },
    [accessToken],
  );

  const grantDocumentAccess = useCallback(
    async (documentId: string, userId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/access/grant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, user_id: userId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to grant access");
      }

      setDocumentAccess((prev) => {
        const newAccess = new Map(prev);
        const users = newAccess.get(request.documentId) || [];
        if (!users.includes(userId)) {
          newAccess.set(request.documentId, [...users, userId]);
        }
        return newAccess;
      });
    },
    [accessToken],
  );

  const revokeDocumentAccess = useCallback(
    async (documentId: string, userId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/access/revoke", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, user_id: userId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to revoke access");
      }

      setDocumentAccess((prev) => {
        const newAccess = new Map(prev);
        const users = newAccess.get(documentId) || [];
        newAccess.set(
          documentId,
          users.filter((u) => u !== userId),
        );
        return newAccess;
      });
    },
    [accessToken],
  );

  // ==================== Document Operations ====================

  const encryptOperation = useCallback(
    async (documentId: string, operation: any) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/operations/encrypt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, operation }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to encrypt operation");
      }

      return ((await res.json()) as EncryptedOperation).encrypted;
    },
    [accessToken],
  );

  const decryptOperation = useCallback(
    async (documentId: string, encrypted: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/operations/decrypt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, encrypted }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to decrypt operation");
      }

      return ((await res.json()) as DocumentOperationDecryptResponse).operation;
    },
    [accessToken],
  );

  // ==================== Key Rotation ====================

  const rotateDocumentKey = useCallback(
    async (documentId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/keys/rotate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to rotate key");
      }

      // Clear cached key
      setDocumentKeys((prev) => {
        const newKeys = new Map(prev);
        newKeys.delete(documentId);
        return newKeys;
      });
    },
    [accessToken],
  );

  const scheduleKeyRotation = useCallback(
    async (documentId: string, intervalHours: number = 24) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/keys/schedule", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          document_id: documentId,
          interval_hours: intervalHours,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to schedule rotation");
      }
    },
    [accessToken],
  );

  // ==================== Access Control ====================

  const grantAccess = useCallback(
    async (documentId: string, userId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/access/grant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, user_id: userId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to grant access");
      }

      setDocumentAccess((prev) => {
        const newAccess = new Map(prev);
        const users = newAccess.get(documentId) || [];
        if (!users.includes(userId)) {
          newAccess.set(documentId, [...users, userId]);
        }
        return newAccess;
      });
    },
    [accessToken],
  );

  const revokeAccess = useCallback(
    async (documentId: string, userId: string) => {
      if (!accessToken) throw new Error("Not authenticated");

      const res = await fetch("/api/v1/e2e/documents/access/revoke", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ document_id: documentId, user_id: userId }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to revoke access");
      }

      setDocumentAccess((prev) => {
        const newAccess = new Map(prev);
        const users = newAccess.get(documentId) || [];
        newAccess.set(
          documentId,
          users.filter((u) => u !== userId),
        );
        return newAccess;
      });
    },
    [accessToken],
  );

  // ==================== Stats ====================

  const getStats = useCallback(async () => {
    if (!accessToken) throw new Error("Not authenticated");

    const res = await fetch("/api/v1/e2e/stats", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!res.ok) {
      throw new Error("Failed to get stats");
    }

    return res.json();
  }, [accessToken]);

  // ==================== Utility ====================

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    documentKeys: Array.from(documentKeys.entries()),
    documentAccess: Array.from(documentAccess.entries()),
    // Session management
    createSession,
    getSession,
    setActiveSession,
    deleteSession,
    // Encryption
    encryptMessage,
    decryptMessage,
    // Document keys
    getDocumentKey,
    shareDocumentKey,
    grantAccess,
    revokeAccess,
    // Operations
    encryptOperation,
    decryptOperation,
    // Rotation
    rotateDocumentKey,
    scheduleKeyRotation,
    // Utility
    clearError,
    refresh: init,
  };
}

// Hook for encrypted CRDT documents
export function useEncryptedCRDT(documentId: string) {
  const {
    getDocumentKey,
    encryptOperation,
    decryptOperation,
    grantAccess,
    revokeAccess,
    rotateDocumentKey,
  } = useE2EEncryption();

  const [documentKey, setDocumentKey] = useState<string | null>(null);
  const [hasAccess, setHasAccess] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const key = await getDocumentKey(documentId);
        setDocumentKey(key);
        setHasAccess(true);
      } catch {
        setHasAccess(false);
      } finally {
        setIsLoading(false);
      }
    };

    load();
  }, [documentId, getDocumentKey]);

  const encrypt = useCallback(
    async (operation: any) => {
      if (!hasAccess) throw new Error("No access to document");
      return encryptOperation(documentId, operation);
    },
    [documentId, hasAccess, encryptOperation],
  );

  const decrypt = useCallback(
    async (encrypted: string) => {
      if (!hasAccess) throw new Error("No access to document");
      return decryptOperation(documentId, encrypted);
    },
    [documentId, hasAccess, decryptOperation],
  );

  const share = useCallback(
    async (recipientId: string) => {
      return grantAccess(documentId, recipientId);
    },
    [documentId, grantAccess],
  );

  const revoke = useCallback(
    async (userId: string) => {
      return revokeAccess(documentId, userId);
    },
    [documentId, revokeAccess],
  );

  const rotate = useCallback(async () => {
    await rotateDocumentKey(documentId);
  }, [documentId, rotateDocumentKey]);

  return {
    documentId,
    documentKey,
    hasAccess,
    isLoading,
    encrypt,
    decrypt,
    share,
    revoke,
    rotate,
  };
}

// Hook for E2E messaging
export function useE2EMessaging(recipientId: string) {
  const {
    createSession,
    activeSessionId,
    setActiveSession,
    encryptMessage,
    decryptMessage,
    sessions,
  } = useE2EEncryption();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<
    Array<{ id: string; content: string; timestamp: number; sender: string }>
  >([]);

  useEffect(() => {
    const init = async () => {
      if (!recipientId) return;

      // Find existing session or create new
      const existing = sessions.find(
        (s) =>
          s.remoteIdentityKey === recipientId ||
          s.sessionId.includes(recipientId),
      );

      if (existing) {
        setSessionId(existing.sessionId);
        setActiveSession(existing.sessionId);
      } else {
        const session = await createSession(recipientId);
        setSessionId(session.sessionId);
      }
    };

    init();
  }, [recipientId, sessions, createSession, setActiveSession]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!sessionId) throw new Error("No active session");

      const encrypted = await encryptMessage(sessionId, content);

      // Send via signaling channel (would integrate with useCall)
      // For now, just add to local messages
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          content,
          timestamp: Date.now(),
          sender: "me",
        },
      ]);

      return encrypted;
    },
    [sessionId, encryptMessage],
  );

  const receiveMessage = useCallback(
    async (encrypted: any, senderId: string) => {
      if (!sessionId) throw new Error("No active session");

      const plaintext = await decryptMessage(sessionId, encrypted);

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          content: plaintext,
          timestamp: Date.now(),
          sender: senderId,
        },
      ]);

      return plaintext;
    },
    [sessionId, decryptMessage],
  );

  return {
    sessionId,
    messages,
    sendMessage,
    receiveMessage,
  };
}
