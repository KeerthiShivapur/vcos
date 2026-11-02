/**
 * Offline-first database layer using IndexedDB with Dexie.js
 * Provides reactive offline storage with background sync capabilities
 */

import Dexie, { Table } from "dexie";
import { v4 as uuidv4 } from "uuid";

// Types for offline data models
export interface OfflineDocument {
  id: string;
  documentId: string;
  title: string;
  content: string;
  yjsState?: Uint8Array;
  version: number;
  lastModified: number;
  synced: boolean;
  pendingChanges: OfflineChange[];
  metadata: Record<string, any>;
}

export interface OfflineChange {
  id: string;
  documentId: string;
  type: "create" | "update" | "delete";
  timestamp: number;
  data: any;
  synced: boolean;
  retryCount: number;
}

export interface OfflinePresence {
  userId: string;
  organizationId: string;
  status: "online" | "idle" | "away" | "offline";
  lastActive: number;
  cursor?: { x: number; y: number };
  selection?: { start: number; end: number };
  metadata: Record<string, any>;
}

export interface OfflineNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, any>;
  read: boolean;
  timestamp: number;
  synced: boolean;
}

export interface SyncQueueItem {
  id: string;
  type: "document" | "presence" | "notification" | "custom";
  operation: "create" | "update" | "delete";
  payload: any;
  timestamp: number;
  retries: number;
  maxRetries: number;
  priority: "high" | "normal" | "low";
  status: "pending" | "syncing" | "completed" | "failed";
  error?: string;
}

export interface OfflineSettings {
  key: string;
  value: any;
  updatedAt: number;
}

export interface OfflineSearchIndex {
  id: string;
  documentId: string;
  title: string;
  content: string;
  tags: string[];
  updatedAt: number;
}

/**
 * Offline Database Class
 * Extends Dexie to provide typed tables and sync logic
 */
export class OfflineDatabase extends Dexie {
  documents!: Table<OfflineDocument>;
  changes!: Table<OfflineChange>;
  presence!: Table<OfflinePresence>;
  notifications!: Table<OfflineNotification>;
  syncQueue!: Table<SyncQueueItem>;
  settings!: Table<OfflineSettings>;
  searchIndex!: Table<OfflineSearchIndex>;

  constructor() {
    super("VCOS_OfflineDB");

    this.version(1).stores({
      documents: "id, documentId, title, version, lastModified, synced",
      changes: "id, documentId, type, timestamp, synced",
      presence: "userId, organizationId, status, lastActive",
      notifications: "id, type, read, timestamp, synced",
      syncQueue: "id, type, operation, timestamp, status, priority",
      settings: "key, updatedAt",
      searchIndex: "id, documentId, title, content, tags, updatedAt",
    });

    // Hook for change tracking
    this.documents.hook("creating", (primKey, obj, trans) => {
      obj.id = obj.id || crypto.randomUUID();
      obj.lastModified = Date.now();
      obj.version = 1;
      obj.synced = false;
      obj.pendingChanges = [];
      obj.metadata = obj.metadata || {};
    });

    this.documents.hook("updating", (modifications, primKey, obj, trans) => {
      modifications.lastModified = Date.now();
      modifications.version = (obj.version || 0) + 1;
      modifications.synced = false;
    });

    this.changes.hook("creating", (primKey, obj, trans) => {
      obj.id = obj.id || crypto.randomUUID();
      obj.timestamp = Date.now();
      obj.synced = false;
      obj.retryCount = 0;
      obj.maxRetries = obj.maxRetries || 3;
      obj.priority = obj.priority || "normal";
      obj.status = "pending";
    });

    this.syncQueue.hook("creating", (primKey, obj, trans) => {
      obj.id = obj.id || crypto.randomUUID();
      obj.timestamp = Date.now();
      obj.retries = 0;
      obj.maxRetries = obj.maxRetries || 3;
      obj.priority = obj.priority || "normal";
      obj.status = "pending";
    });
  }

  // =========================================================================
  // Document Operations
  // =========================================================================

  async createDocument(
    doc: Omit<
      OfflineDocument,
      "id" | "version" | "lastModified" | "synced" | "pendingChanges"
    >,
  ): Promise<string> {
    const id = crypto.randomUUID();
    const now = Date.now();

    await this.documents.add({
      ...doc,
      id,
      version: 1,
      lastModified: Date.now(),
      synced: false,
      pendingChanges: [],
      metadata: doc.metadata || {},
    });

    // Add to sync queue
    await this.addToSyncQueue({
      type: "document",
      operation: "create",
      payload: { ...doc, id },
      priority: "high",
    });

    return id;
  }

  async getDocument(documentId: string): Promise<OfflineDocument | undefined> {
    return this.documents.where("documentId").equals(documentId).first();
  }

  async getAllDocuments(): Promise<OfflineDocument[]> {
    return this.documents.toArray();
  }

  async updateDocument(
    documentId: string,
    updates: Partial<OfflineDocument>,
  ): Promise<number> {
    const doc = await this.getDocument(documentId);
    if (!doc) return 0;

    const updated = {
      ...doc,
      ...updates,
      lastModified: Date.now(),
      version: doc.version + 1,
      synced: false,
    };
    await this.documents.put(updated);

    // Add to sync queue
    await this.addToSyncQueue({
      type: "document",
      operation: "update",
      payload: { documentId, updates },
      priority: "high",
    });

    return 1;
  }

  async deleteDocument(documentId: string): Promise<number> {
    const result = await this.documents
      .where("documentId")
      .equals(documentId)
      .delete();

    // Add to sync queue
    await this.addToSyncQueue({
      type: "document",
      operation: "delete",
      payload: { documentId },
      priority: "high",
    });

    return result;
  }

  // =========================================================================
  // Change Tracking
  // =========================================================================

  async addChange(
    change: Omit<OfflineChange, "id" | "timestamp" | "synced" | "retryCount">,
  ): Promise<string> {
    const id = crypto.randomUUID();
    await this.changes.add({
      ...change,
      id,
      timestamp: Date.now(),
      synced: false,
      retryCount: 0,
    });
    return id;
  }

  async getPendingChanges(documentId?: string): Promise<OfflineChange[]> {
    // Use filter instead of equals(false) since IndexedDB doesn't support boolean keys
    let query = this.changes.filter((change) => change.synced === false);
    if (documentId) {
      query = query.and((change) => change.documentId === documentId);
    }
    return query.toArray();
  }

  async markChangeSynced(changeId: string): Promise<number> {
    return this.changes.update(changeId, { synced: true });
  }

  // =========================================================================
  // Presence Management
  // =========================================================================

  async upsertPresence(presence: OfflinePresence): Promise<void> {
    await this.presence.put({
      ...presence,
      lastActive: Date.now(),
    });
  }

  async getPresence(
    userId: string,
    organizationId: string,
  ): Promise<OfflinePresence | undefined> {
    return this.presence
      .where("[userId+organizationId]")
      .equals([userId, organizationId])
      .first();
  }

  async getOrganizationPresence(
    organizationId: string,
  ): Promise<OfflinePresence[]> {
    return this.presence
      .where("organizationId")
      .equals(organizationId)
      .toArray();
  }

  async removePresence(
    userId: string,
    organizationId: string,
  ): Promise<number> {
    return this.presence
      .where("[userId+organizationId]")
      .equals([userId, organizationId])
      .delete();
  }

  async updateCursor(
    userId: string,
    organizationId: string,
    cursor: { x: number; y: number },
  ): Promise<boolean> {
    const presence = await this.getPresence(userId, organizationId);
    if (!presence) return false;

    presence.cursor = cursor;
    presence.lastActive = Date.now();
    await this.upsertPresence(presence);
    return true;
  }

  async updateSelection(
    userId: string,
    organizationId: string,
    selection: { start: number; end: number },
  ): Promise<boolean> {
    const presence = await this.getPresence(userId, organizationId);
    if (!presence) return false;

    presence.selection = selection;
    presence.lastActive = Date.now();
    await this.upsertPresence(presence);
    return true;
  }

  async updateStatus(
    userId: string,
    organizationId: string,
    status: "online" | "idle" | "away" | "offline",
  ): Promise<boolean> {
    const presence = await this.getPresence(userId, organizationId);
    if (!presence) return false;

    presence.status = status;
    presence.lastActive = Date.now();
    await this.upsertPresence(presence);
    return true;
  }

  // =========================================================================
  // Notifications
  // =========================================================================

  async addNotification(
    notification: Omit<
      OfflineNotification,
      "id" | "timestamp" | "read" | "synced"
    >,
  ): Promise<string> {
    const id = crypto.randomUUID();
    await this.notifications.add({
      ...notification,
      id,
      timestamp: Date.now(),
      read: false,
      synced: false,
    });
    return id;
  }

  async getNotifications(unreadOnly = false): Promise<OfflineNotification[]> {
    let query = this.notifications.orderBy("timestamp").reverse();
    if (unreadOnly) {
      query = query.filter((n) => !n.read);
    }
    return query.toArray();
  }

  async markNotificationRead(id: string): Promise<number> {
    return this.notifications.update(id, { read: true, synced: false });
  }

  // =========================================================================
  // Sync Queue
  // =========================================================================

  async addToSyncQueue(
    item: Omit<SyncQueueItem, "id" | "timestamp" | "retries" | "status">,
  ): Promise<string> {
    const id = crypto.randomUUID();
    await this.syncQueue.add({
      ...item,
      id,
      timestamp: Date.now(),
      retries: 0,
      maxRetries: item.maxRetries || 3,
      status: "pending",
    });
    return id;
  }

  async getPendingSyncItems(limit = 50): Promise<SyncQueueItem[]> {
    return this.syncQueue
      .where("status")
      .anyOf(["pending", "syncing"])
      .limit(limit)
      .sortBy("timestamp");
  }

  async markSyncItemSyncing(id: string): Promise<number> {
    return this.syncQueue.update(id, { status: "syncing" });
  }

  async markSyncItemCompleted(id: string): Promise<number> {
    return this.syncQueue.update(id, { status: "completed" });
  }

  async markSyncItemFailed(id: string, error: string): Promise<number> {
    const item = await this.syncQueue.get(id);
    if (!item) return 0;

    if (item.retries >= item.maxRetries) {
      return this.syncQueue.update(id, {
        status: "failed",
        error,
        retries: item.retries + 1,
      });
    }

    return this.syncQueue.update(id, {
      status: "pending",
      error,
      retries: item.retries + 1,
    });
  }

  // =========================================================================
  // Search Index
  // =========================================================================

  async updateSearchIndex(index: OfflineSearchIndex): Promise<void> {
    await this.searchIndex.put(index);
  }

  async searchDocuments(
    query: string,
    limit = 10,
  ): Promise<OfflineSearchIndex[]> {
    const lowerQuery = query.toLowerCase();
    return this.searchIndex
      .filter(
        (idx) =>
          idx.title.toLowerCase().includes(lowerQuery) ||
          idx.content.toLowerCase().includes(lowerQuery) ||
          idx.tags.some((tag) => tag.toLowerCase().includes(lowerQuery)),
      )
      .limit(limit)
      .toArray();
  }

  // =========================================================================
  // Settings
  // =========================================================================

  async getSetting(key: string): Promise<any> {
    const setting = await this.settings.get(key);
    return setting?.value;
  }

  async setSetting(key: string, value: any): Promise<number> {
    return this.settings.put({ key, value, updatedAt: Date.now() });
  }

  async getSyncStatus(): Promise<{
    pendingChanges: number;
    pendingSyncItems: number;
    lastSyncTime: number | null;
  }> {
    const [pendingChanges, pendingSyncItems, lastSyncTime] = await Promise.all([
      // Use filter instead of equals(false) since IndexedDB doesn't support boolean keys
      this.changes.filter((change) => change.synced === false).count(),
      this.syncQueue.where("status").anyOf(["pending", "syncing"]).count(),
      this.getSetting("lastSyncTime"),
    ]);

    return {
      pendingChanges,
      pendingSyncItems,
      lastSyncTime: lastSyncTime || null,
    };
  }

  // =========================================================================
  // Import/Export
  // =========================================================================

  async exportAllData(): Promise<any> {
    const [documents, changes, presence, notifications, settings, searchIndex] =
      await Promise.all([
        this.documents.toArray(),
        this.changes.toArray(),
        this.presence.toArray(),
        this.notifications.toArray(),
        this.settings.toArray(),
        this.searchIndex.toArray(),
      ]);

    return {
      version: 1,
      exportedAt: Date.now(),
      documents,
      changes,
      presence,
      notifications,
      settings,
      searchIndex,
    };
  }

  async importData(data: any): Promise<void> {
    if (!data || data.version !== 1) {
      throw new Error("Invalid data format");
    }

    await this.transaction("rw", this.tables, async () => {
      // Clear existing data
      await Promise.all(this.tables.map((table) => table.clear()));

      // Import new data
      if (data.documents) await this.documents.bulkAdd(data.documents);
      if (data.changes) await this.changes.bulkAdd(data.changes);
      if (data.presence) await this.presence.bulkAdd(data.presence);
      if (data.notifications)
        await this.notifications.bulkAdd(data.notifications);
      if (data.settings) await this.settings.bulkPut(data.settings);
      if (data.searchIndex) await this.searchIndex.bulkAdd(data.searchIndex);
    });
  }

  async clearAllData(): Promise<void> {
    await this.transaction("rw", this.tables, async () => {
      await Promise.all(this.tables.map((table) => table.clear()));
    });
  }

  // =========================================================================
  // Utility: Chunk text for document indexing
  // =========================================================================

  chunkText(
    text: string,
    chunkSize = 1000,
    overlap = 200,
  ): Array<{ text: string; index: number }> {
    if (text.length <= chunkSize) {
      return [{ text, index: 0 }];
    }

    const chunks: Array<{ text: string; index: number }> = [];
    let index = 0;

    for (let i = 0; i < text.length; i += chunkSize - overlap) {
      const chunk = text.slice(i, i + chunkSize);
      if (chunk.trim().length > 0) {
        chunks.push({ text: chunk, index: index++ });
      }
    }

    return chunks;
  }
}

// Singleton instance
let _offlineDB: OfflineDatabase | null = null;

export function getOfflineDB(): OfflineDatabase {
  if (!_offlineDB) {
    _offlineDB = new OfflineDatabase();
  }
  return _offlineDB;
}

export async function initializeOfflineDB(): Promise<OfflineDatabase> {
  const db = getOfflineDB();
  await db.open();
  return db;
}
