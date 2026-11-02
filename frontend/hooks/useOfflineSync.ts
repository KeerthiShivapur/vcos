/**
 * Offline Sync Hook
 * React hook for managing offline-first data synchronization
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  getOfflineDB,
  initializeOfflineDB,
  OfflineDatabase,
  SyncQueueItem,
} from "@/lib/offline-db";
import { useRealtime } from "./useRealtime";

interface OfflineSyncState {
  isInitialized: boolean;
  isOnline: boolean;
  isSyncing: boolean;
  pendingChanges: number;
  pendingSyncItems: number;
  lastSyncTime: number | null;
  syncError: string | null;
  lastSyncStatus: "idle" | "syncing" | "completed" | "failed";
}

interface UseOfflineSyncOptions {
  organizationId: string;
  autoSync?: boolean;
  syncInterval?: number; // ms
  onSyncComplete?: (synced: number, failed: number) => void;
  onSyncError?: (error: Error) => void;
  onOnlineStatusChange?: (isOnline: boolean) => void;
}

export function useOfflineSync(options: UseOfflineSyncOptions) {
  const {
    organizationId,
    autoSync = true,
    syncInterval = 30000, // 30 seconds
    onSyncComplete,
    onSyncError,
    onOnlineStatusChange,
  } = options;

  const [state, setState] = useState<OfflineSyncState>({
    isInitialized: false,
    isOnline: navigator.onLine,
    isSyncing: false,
    pendingChanges: 0,
    pendingSyncItems: 0,
    lastSyncTime: null,
    syncError: null,
    lastSyncStatus: "idle",
  });

  const dbRef = useRef<OfflineDatabase | null>(null);
  const syncIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const realtime = useRealtime({
    organizationId,
    autoConnect: true,
    onConnect: () => {
      setState((prev) => ({ ...prev, isOnline: true }));
      onOnlineStatusChange?.(true);
      if (autoSync) triggerSync();
    },
    onDisconnect: () => {
      setState((prev) => ({ ...prev, isOnline: false }));
      onOnlineStatusChange?.(false);
    },
  });

  // Initialize database
  useEffect(() => {
    const init = async () => {
      try {
        const db = await initializeOfflineDB();
        dbRef.current = db;

        const status = await db.getSyncStatus();
        setState((prev) => ({
          ...prev,
          isInitialized: true,
          isOnline: navigator.onLine,
          pendingChanges: status.pendingChanges,
          pendingSyncItems: status.pendingSyncItems,
          lastSyncTime: status.lastSyncTime,
        }));

        // Set up online/offline listeners
        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);

        // Start periodic sync if enabled
        if (autoSync) {
          startPeriodicSync();
        }
      } catch (error) {
        console.error("Failed to initialize offline DB:", error);
        setState((prev) => ({
          ...prev,
          syncError:
            error instanceof Error ? error.message : "Initialization failed",
        }));
      }
    };

    init();

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      stopPeriodicSync();
    };
  }, [organizationId, autoSync]);

  const handleOnline = useCallback(() => {
    setState((prev) => ({ ...prev, isOnline: true }));
    onOnlineStatusChange?.(true);
    if (autoSync) triggerSync();
  }, [autoSync, onOnlineStatusChange]);

  const handleOffline = useCallback(() => {
    setState((prev) => ({ ...prev, isOnline: false }));
    onOnlineStatusChange?.(false);
  }, [autoSync, onOnlineStatusChange]);

  const startPeriodicSync = useCallback(() => {
    if (syncIntervalRef.current) {
      clearInterval(syncIntervalRef.current);
    }
    syncIntervalRef.current = setInterval(() => {
      if (navigator.onLine && !state.isSyncing) {
        triggerSync();
      }
    }, syncInterval);
  }, [syncInterval, state.isSyncing]);

  const stopPeriodicSync = useCallback(() => {
    if (syncIntervalRef.current) {
      clearInterval(syncIntervalRef.current);
      syncIntervalRef.current = null;
    }
  }, []);

  const triggerSync = useCallback(async () => {
    if (!state.isOnline || state.isSyncing || !dbRef.current) return;

    setState((prev) => ({
      ...prev,
      isSyncing: true,
      lastSyncStatus: "syncing",
      syncError: null,
    }));

    const db = dbRef.current!;
    let synced = 0;
    let failed = 0;

    try {
      // Get pending sync items
      const pendingItems = await db.getPendingSyncItems(50);

      for (const item of pendingItems) {
        await db.markSyncItemSyncing(item.id);

        try {
          // Perform the actual sync operation based on item type
          await performSyncOperation(db, item);

          await db.markSyncItemCompleted(item.id);
          synced++;
        } catch (error) {
          console.error(`Sync failed for item ${item.id}:`, error);
          await db.markSyncItemFailed(
            item.id,
            error instanceof Error ? error.message : "Unknown error",
          );
          failed++;
        }
      }

      // Also sync unsynced documents
      const unsyncedDocs = await db.getUnsyncedDocuments();
      for (const doc of unsyncedDocs) {
        try {
          await syncDocumentToServer(db, doc);
          synced++;
        } catch (error) {
          console.error(`Failed to sync document ${doc.documentId}:`, error);
          failed++;
        }
      }

      // Update last sync time
      await db.setSetting("lastSyncTime", Date.now());

      const newSyncStatus =
        failed === 0 ? "completed" : synced > 0 ? "completed" : "failed";
      const newSyncError =
        failed > 0 && synced === 0 ? `${failed} items failed to sync` : null;

      // Get pending counts asynchronously outside of setState
      const pendingChangesCount = await db.getUnsyncedDocuments();
      const pendingSyncItemsCount = await db.getPendingSyncItems();

      setState((prev) => ({
        ...prev,
        isSyncing: false,
        lastSyncStatus: newSyncStatus,
        lastSyncTime: Date.now(),
        syncError: newSyncError,
        pendingChanges: pendingChangesCount.length,
        pendingSyncItems: pendingSyncItemsCount.length,
      }));

      onSyncComplete?.(synced, failed);
    } catch (error) {
      console.error("Sync failed:", error);
      const err = error instanceof Error ? error : new Error("Sync failed");
      setState((prev) => {
        return {
          ...prev,
          isSyncing: false,
          lastSyncStatus: "failed",
          syncError: err.message,
        };
      });
      onSyncError?.(err);
    }
  }, [
    state.isOnline,
    state.isSyncing,
    autoSync,
    onSyncComplete,
    onSyncError,
    syncInterval,
  ]);

  const performSyncOperation = async (
    db: OfflineDatabase,
    item: SyncQueueItem,
  ): Promise<void> => {
    // Call actual API endpoint based on item type
    const response = await fetch(`/api/v1/realtime/sync/${item.type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item.payload),
    });

    if (!response.ok) {
      throw new Error(`Sync failed: ${response.status} ${response.statusText}`);
    }
  };

  const syncDocumentToServer = async (
    db: OfflineDatabase,
    doc: any,
  ): Promise<void> => {
    const response = await fetch(`/api/v1/realtime/sync/document`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc),
    });

    if (!response.ok) {
      throw new Error(
        `Document sync failed: ${response.status} ${response.statusText}`,
      );
    }

    const result = await response.json();
    if (result.success) {
      await db.documents.update(doc.id, {
        synced: true,
        version: result.server_version,
      });
    } else {
      throw new Error(result.error || "Document sync failed");
    }
  };

  // Manual sync trigger
  const syncNow = useCallback(() => {
    triggerSync();
  }, [triggerSync]);

  // Force offline mode (for testing)
  const goOffline = useCallback(() => {
    setState((prev) => ({ ...prev, isOnline: false }));
  }, []);

  const goOnline = useCallback(() => {
    setState((prev) => ({ ...prev, isOnline: true }));
    if (autoSync) triggerSync();
  }, [autoSync, triggerSync]);

  // Get pending changes count
  const refreshCounts = useCallback(async () => {
    if (!dbRef.current) return;
    const status = await dbRef.current.getSyncStatus();
    setState((prev) => ({
      ...prev,
      pendingChanges: status.pendingChanges,
      pendingSyncItems: status.pendingSyncItems,
      lastSyncTime: status.lastSyncTime,
    }));
  }, []);

  // Export/Import for backup
  const exportData = useCallback(async () => {
    if (!dbRef.current) return null;
    return dbRef.current.exportAllData();
  }, []);

  const importData = useCallback(
    async (data: any) => {
      if (!dbRef.current) return;
      await dbRef.current.importData(data);
      await refreshCounts();
    },
    [refreshCounts],
  );

  // Clear all offline data
  const clearData = useCallback(async () => {
    if (!dbRef.current) return;
    await dbRef.current.clearAllData();
    await refreshCounts();
  }, [refreshCounts]);

  return {
    ...state,
    syncNow,
    goOffline,
    goOnline,
    refreshCounts,
    exportData,
    importData,
    clearData,
    db: dbRef.current,
  };
}

// Helper hook for using offline documents
export function useOfflineDocument(documentId: string) {
  const [document, setDocument] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dbRef = useRef<OfflineDatabase | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const db = await initializeOfflineDB();
        dbRef.current = db;
        const doc = await db.getDocument(documentId);
        setDocument(doc);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load document",
        );
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [documentId]);

  const update = useCallback(
    async (updates: any) => {
      if (!dbRef.current || !document) return;
      await dbRef.current!.updateDocument(documentId, updates);
      setDocument((prev) => ({
        ...prev,
        ...updates,
        lastModified: Date.now(),
      }));
    },
    [documentId, document],
  );

  const deleteDoc = useCallback(async () => {
    if (!dbRef.current) return;
    await dbRef.current!.deleteDocument(documentId);
    setDocument(null);
  }, [documentId]);

  return { document, loading, error, update, delete: deleteDoc };
}

// Helper hook for offline documents list
export function useOfflineDocuments(filter?: { synced?: boolean }) {
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dbRef = useRef<OfflineDatabase | null>(null);

  const load = useCallback(async () => {
    try {
      const db = await initializeOfflineDB();
      dbRef.current = db;

      let docs;
      if (filter?.synced === true) {
        docs = await db.documents.where("synced").equals(true).toArray();
      } else if (filter?.synced === false) {
        docs = await db.getUnsyncedDocuments();
      } else {
        docs = await db.getAllDocuments();
      }
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(() => load(), [load]);

  const create = useCallback(
    async (doc: any) => {
      if (!dbRef.current) return;
      const id = await dbRef.current!.createDocument(doc);
      await load();
      return id;
    },
    [load],
  );

  const update = useCallback(
    async (documentId: string, updates: any) => {
      if (!dbRef.current) return;
      await dbRef.current!.updateDocument(documentId, updates);
      await load();
    },
    [load],
  );

  const deleteDoc = useCallback(
    async (documentId: string) => {
      if (!dbRef.current) return;
      await dbRef.current!.deleteDocument(documentId);
      await load();
    },
    [load],
  );

  return {
    documents,
    loading,
    error,
    refresh,
    create,
    update,
    delete: deleteDoc,
  };
}

// Helper hook for offline notifications
export function useOfflineNotifications() {
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const dbRef = useRef<OfflineDatabase | null>(null);

  const load = useCallback(async () => {
    try {
      const db = await initializeOfflineDB();
      dbRef.current = db;
      const notifications = await db.notifications.toArray();
      const unread = notifications.filter((n) => !n.read).length;
      setNotifications(notifications);
      setUnreadCount(unread);
    } catch (err) {
      console.error("Failed to load notifications:", err);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markRead = useCallback(
    async (id: string) => {
      if (!dbRef.current) return;
      await dbRef.current!.markNotificationRead(id);
      await load();
    },
    [load],
  );

  const add = useCallback(
    async (notification: any) => {
      if (!dbRef.current) return;
      await dbRef.current!.addNotification(notification);
      await load();
    },
    [load],
  );

  return {
    notifications,
    unreadCount,
    loading: false,
    markRead,
    add,
    refresh: load,
  };
}
