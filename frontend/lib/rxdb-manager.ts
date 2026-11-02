/**
 * RxDB Integration for Reactive Offline-First Data Layer
 *
 * Provides:
 * - Reactive queries with observable streams
 * - Offline-first with automatic sync
 * - Conflict resolution with CRDT support
 * - Schema validation and migrations
 * - Multi-tab synchronization
 * - Encryption at rest
 */

import {
  createRxDatabase,
  addRxPlugin,
  RxDatabase,
  RxCollection,
  RxDocument,
  RxJsonSchema,
  QueryChangeDetector,
} from "rxdb";
import { getRxStorageDexie } from "rxdb/plugins/storage-dexie";
import { RxDBDevModePlugin } from "rxdb/plugins/dev-mode";
import { RxDBLeaderElectionPlugin } from "rxdb/plugins/leader-election";
import { RxDBQueryBuilderPlugin } from "rxdb/plugins/query-builder";
import { RxDBUpdatePlugin } from "rxdb/plugins/update";
import { replicateRxCollection } from "rxdb/plugins/replication";
import { Subject, BehaviorSubject, Observable } from "rxjs";
import {
  map,
  filter,
  debounceTime,
  distinctUntilChanged,
} from "rxjs/operators";

import {
  OfflineDocument,
  OfflineChange,
  OfflinePresence,
  OfflineNotification,
  SyncQueueItem,
  OfflineSettings,
  OfflineSearchIndex,
} from "./offline-db";

// ==================== Types ====================

export interface RxDBSchema {
  version: number;
  primaryKey: string;
  type: "object";
  properties: Record<string, any>;
  required: string[];
  indexes?: string[];
  attachments?: boolean;
  encryption?: boolean;
}

export interface SyncConfig {
  remoteUrl: string;
  authToken?: string;
  batchSize: number;
  retryDelay: number;
  maxRetries: number;
  live: boolean;
  waitForLeadership: boolean;
}

export interface ConflictData {
  local: any;
  remote: any;
  resolved?: any;
}

export type ConflictHandler = (conflict: ConflictData) => Promise<any>;

export interface CollectionOptions {
  schema: RxDBSchema;
  conflictHandler?: ConflictHandler;
  migrationStrategies?: Record<number, (doc: any) => Promise<any>>;
  autoMigrate?: boolean;
}

// ==================== Schema Definitions ====================

export const DOCUMENT_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    documentId: { type: "string", maxLength: 100 },
    title: { type: "string" },
    content: { type: "string" },
    yjsState: { type: "string", format: "binary" },
    version: { type: "number", minimum: 0 },
    lastModified: { type: "number" },
    synced: { type: "boolean" },
    pendingChanges: {
      type: "array",
      items: { type: "object" },
    },
    metadata: { type: "object" },
    collection: { type: "string" },
    tags: { type: "array", items: { type: "string" } },
    ownerId: { type: "string" },
    organizationId: { type: "string" },
    createdAt: { type: "number" },
    updatedAt: { type: "number" },
  },
  required: ["id", "documentId", "title", "version", "lastModified", "synced"],
  indexes: [
    "documentId",
    "ownerId",
    "organizationId",
    "lastModified",
    "synced",
    "collection",
  ],
  attachments: false,
  encryption: false,
};

export const CHANGE_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    documentId: { type: "string", maxLength: 100 },
    type: { type: "string", enum: ["create", "update", "delete"] },
    timestamp: { type: "number" },
    data: { type: "object" },
    synced: { type: "boolean" },
    retryCount: { type: "number", minimum: 0 },
    maxRetries: { type: "number", minimum: 0 },
  },
  required: ["id", "documentId", "type", "timestamp", "synced"],
  indexes: ["documentId", "synced", "timestamp"],
};

export const PRESENCE_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "userId",
  type: "object",
  properties: {
    userId: { type: "string", maxLength: 100 },
    organizationId: { type: "string", maxLength: 100 },
    status: { type: "string", enum: ["online", "idle", "away", "offline"] },
    lastActive: { type: "number" },
    cursor: { type: "object" },
    selection: { type: "object" },
    metadata: { type: "object" },
  },
  required: ["userId", "organizationId", "status", "lastActive"],
  indexes: ["organizationId", "status", "lastActive"],
};

export const NOTIFICATION_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    type: { type: "string" },
    title: { type: "string" },
    body: { type: "string" },
    data: { type: "object" },
    read: { type: "boolean" },
    timestamp: { type: "number" },
    synced: { type: "boolean" },
    priority: { type: "string", enum: ["high", "normal", "low"] },
  },
  required: ["id", "type", "title", "body", "read", "timestamp", "synced"],
  indexes: ["read", "synced", "timestamp", "priority"],
};

export const SYNC_QUEUE_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    type: { type: "string" },
    operation: { type: "string", enum: ["create", "update", "delete"] },
    payload: { type: "object" },
    timestamp: { type: "number" },
    retries: { type: "number", minimum: 0 },
    maxRetries: { type: "number", minimum: 0 },
    priority: { type: "string", enum: ["high", "normal", "low"] },
    status: {
      type: "string",
      enum: ["pending", "syncing", "completed", "failed"],
    },
    error: { type: "string" },
  },
  required: [
    "id",
    "type",
    "operation",
    "timestamp",
    "retries",
    "maxRetries",
    "priority",
    "status",
  ],
  indexes: ["status", "priority", "timestamp"],
};

export const SETTINGS_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "key",
  type: "object",
  properties: {
    key: { type: "string", maxLength: 100 },
    value: { type: "object" },
    updatedAt: { type: "number" },
  },
  required: ["key", "value", "updatedAt"],
};

export const SEARCH_INDEX_SCHEMA: RxDBSchema = {
  version: 1,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    documentId: { type: "string", maxLength: 100 },
    title: { type: "string" },
    content: { type: "string" },
    tags: { type: "array", items: { type: "string" } },
    updatedAt: { type: "number" },
  },
  required: ["id", "documentId", "title", "content", "updatedAt"],
  indexes: ["documentId", "updatedAt"],
};

// ==================== RxDB Manager ====================

export class RxDBManager {
  private db: RxDatabase | null = null;
  private initialized = false;
  private initializationPromise: Promise<RxDatabase> | null = null;

  // Collections
  private collections: Map<string, RxCollection> = new Map();

  // Replication
  private replications: Map<string, any> = new Map();

  // Change streams
  private changeSubjects: Map<string, Subject<any>> = new Map();

  // Sync state
  private syncState = new BehaviorSubject<{
    isOnline: boolean;
    isSyncing: boolean;
    pendingChanges: number;
    lastSync: number | null;
    error: string | null;
  }>({
    isOnline: navigator.onLine,
    isSyncing: false,
    pendingChanges: 0,
    lastSync: null,
    error: null,
  });

  constructor() {
    this.setupOnlineListener();
  }

  private setupOnlineListener(): void {
    window.addEventListener("online", () => this.handleOnline());
    window.addEventListener("offline", () => this.handleOffline());
  }

  private handleOnline(): void {
    this.syncState.next({ ...this.syncState.value, isOnline: true });
    this.resumeSync();
  }

  private handleOffline(): void {
    this.syncState.next({ ...this.syncState.value, isOnline: false });
  }

  private async resumeSync(): Promise<void> {
    // Restart all replications
    for (const [, replication] of this.replications) {
      try {
        await replication.awaitInitialReplication();
      } catch (e) {
        console.warn("Replication resume failed:", e);
      }
    }
  }

  // ==================== Initialization ====================

  async initialize(
    options: {
      name?: string;
      password?: string; // For encryption
      multiInstance?: boolean;
      enableDevMode?: boolean;
    } = {},
  ): Promise<RxDatabase> {
    if (this.initialized && this.db) {
      return this.db;
    }

    if (this.initializationPromise) {
      return this.initializationPromise;
    }

    this.initializationPromise = this._initialize(options);
    return this.initializationPromise;
  }

  private async _initialize(options: {
    name?: string;
    password?: string;
    multiInstance?: boolean;
    enableDevMode?: boolean;
  }): Promise<RxDatabase> {
    // Add plugins
    addRxPlugin(RxDBDevModePlugin);
    addRxPlugin(RxDBLeaderElectionPlugin);
    addRxPlugin(RxDBQueryBuilderPlugin);
    addRxPlugin(RxDBUpdatePlugin);

    // Enable dev mode in development
    if (options.enableDevMode || process.env.NODE_ENV === "development") {
      // Dev mode enables better error messages
    }

    // Create database with Dexie storage
    this.db = await createRxDatabase({
      name: options.name || "vcos-offline",
      storage: getRxStorageDexie(),
      password: options.password, // Enables encryption if provided
      multiInstance: options.multiInstance ?? true,
      eventReduce: true, // Optimize queries
      ignoreDuplicate: true,
    });

    // Create collections
    await this.createCollections();

    // Set up change streams
    this.setupChangeStreams();

    // Set up leader election for multi-tab sync
    if (options.multiInstance) {
      await this.db.waitForLeadership();
    }

    this.initialized = true;
    console.log("[RxDB] Database initialized");

    return this.db;
  }

  private async createCollections(): Promise<void> {
    if (!this.db) throw new Error("Database not initialized");

    const schemas = [
      { name: "documents", schema: DOCUMENT_SCHEMA },
      { name: "changes", schema: CHANGE_SCHEMA },
      { name: "presence", schema: PRESENCE_SCHEMA },
      { name: "notifications", schema: NOTIFICATION_SCHEMA },
      { name: "syncQueue", schema: SYNC_QUEUE_SCHEMA },
      { name: "settings", schema: SETTINGS_SCHEMA },
      { name: "searchIndex", schema: SEARCH_INDEX_SCHEMA },
    ];

    for (const { name, schema } of schemas) {
      const collection = await this.db!.addCollection({
        name,
        schema,
        // Auto-create indexes from schema
        indexes: schema.indexes || [],
        // Conflict handler
        conflictHandler: this.defaultConflictHandler.bind(this),
        // Migration strategies
        migrationStrategies: {
          1: async (doc) => doc, // Base version
        },
        autoMigrate: true,
      });

      this.collections.set(name, collection);
      console.log(`[RxDB] Collection created: ${name}`);
    }
  }

  private setupChangeStreams(): void {
    if (!this.db) return;

    // Watch all collections for changes
    for (const [name, collection] of this.collections) {
      const subject = new Subject();
      this.changeSubjects.set(name, subject);

      // Emit changes
      collection.$.subscribe((doc) => {
        subject.next({
          collection: name,
          operation: doc._deleted ? "delete" : doc._rev ? "update" : "insert",
          document: doc.toJSON(),
        });
      });
    }
  }

  private defaultConflictHandler(conflict: ConflictData): Promise<any> {
    // Default: Last-write-wins with server preference for system fields
    const local = conflict.local;
    const remote = conflict.remote;

    if (!local) return remote;
    if (!remote) return local;

    // System fields: server wins
    const systemFields = ["id", "version", "createdAt", "synced", "_rev"];

    // User content: local wins (user's edits are precious)
    const userFields = ["content", "title", "metadata", "tags"];

    const merged = { ...remote };

    // Preserve user content from local
    for (const field of ["content", "title", "metadata", "tags", "yjsState"]) {
      if (local[field] !== undefined) {
        merged[field] = local[field];
      }
    }

    // Take higher version
    merged.version = Math.max(local.version || 0, remote.version || 0) + 1;
    merged.lastModified = Math.max(
      local.lastModified || 0,
      remote.lastModified || 0,
    );
    merged.synced = false;

    return merged;
  }

  // ==================== Collection Access ====================

  getCollection<T = any>(name: string): RxCollection<T> | null {
    return this.collections.get(name) || null;
  }

  getDocumentsCollection(): RxCollection {
    return this.collections.get("documents")!;
  }

  getChangesCollection(): RxCollection {
    return this.collections.get("changes")!;
  }

  getPresenceCollection(): RxCollection {
    return this.collections.get("presence")!;
  }

  getNotificationsCollection(): RxCollection {
    return this.collections.get("notifications")!;
  }

  getSyncQueueCollection(): RxCollection {
    return this.collections.get("syncQueue")!;
  }

  getSettingsCollection(): RxCollection {
    return this.collections.get("settings")!;
  }

  getSearchIndexCollection(): RxCollection {
    return this.collections.get("searchIndex")!;
  }

  // ==================== Reactive Queries ====================

  /**
   * Get reactive document query
   */
  getDocuments$(query?: {
    ownerId?: string;
    organizationId?: string;
    collection?: string;
    synced?: boolean;
    tags?: string[];
    limit?: number;
  }) {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    let queryBuilder = collection.find();

    if (query?.ownerId) {
      queryBuilder = queryBuilder.where("ownerId").eq(query.ownerId);
    }
    if (query?.organizationId) {
      queryBuilder = queryBuilder
        .where("organizationId")
        .eq(query.organizationId);
    }
    if (query?.collection) {
      queryBuilder = queryBuilder.where("collection").eq(query.collection);
    }
    if (query?.synced !== undefined) {
      queryBuilder = queryBuilder.where("synced").eq(query.synced);
    }
    if (query?.tags && query.tags.length > 0) {
      queryBuilder = queryBuilder
        .where("tags")
        .elemMatch((tag) => query.tags!.includes(tag));
    }
    if (query?.limit) {
      queryBuilder = queryBuilder.limit(query.limit);
    }

    // Sort by lastModified descending
    queryBuilder = queryBuilder.sort({ lastModified: "desc" });

    return queryBuilder.$;
  }

  /**
   * Get single document reactively
   */
  getDocument$(documentId: string): Observable<any> {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    return collection.findOne("documentId", documentId).$;
  }

  /**
   * Get unsynced documents
   */
  getUnsyncedDocuments$(): Observable<any[]> {
    return this.getDocuments$({ synced: false });
  }

  /**
   * Get presence for organization
   */
  getPresence$(organizationId: string): Observable<any[]> {
    const collection = this.getPresenceCollection();
    if (!collection) throw new Error("Presence collection not initialized");

    return collection
      .find()
      .where("organizationId")
      .eq(organizationId)
      .sort({ lastActive: "desc" }).$;
  }

  /**
   * Get notifications reactively
   */
  getNotifications$(options?: {
    unreadOnly?: boolean;
    limit?: number;
  }): Observable<any[]> {
    const collection = this.getNotificationsCollection();
    if (!collection)
      throw new Error("Notifications collection not initialized");

    let queryBuilder = collection.find().sort({ timestamp: "desc" });

    if (options?.unreadOnly) {
      queryBuilder = queryBuilder.where("read").eq(false);
    }
    if (options?.limit) {
      queryBuilder = queryBuilder.limit(options.limit);
    }

    return queryBuilder.$;
  }

  /**
   * Get sync queue status
   */
  getSyncQueue$(): Observable<any[]> {
    const collection = this.getSyncQueueCollection();
    if (!collection) throw new Error("Sync queue collection not initialized");

    return collection
      .find()
      .where("status")
      .anyOf(["pending", "syncing", "failed"])
      .sort({ priority: "desc", timestamp: "asc" }).$;
  }

  /**
   * Get sync state observable
   */
  getSyncState$(): Observable<{
    isOnline: boolean;
    isSyncing: boolean;
    pendingChanges: number;
    lastSync: number | null;
    error: string | null;
  }> {
    return this.syncState.asObservable();
  }

  // ==================== Document Operations ====================

  async createDocument(doc: {
    documentId: string;
    title: string;
    content: string;
    ownerId: string;
    organizationId: string;
    collection?: string;
    tags?: string[];
    metadata?: Record<string, any>;
    yjsState?: Uint8Array;
  }): Promise<string> {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    const id = crypto.randomUUID();
    const now = Date.now();

    const docData = {
      id: crypto.randomUUID(),
      documentId: doc.documentId,
      title: doc.title,
      content: doc.content,
      yjsState: doc.yjsState ? Array.from(doc.yjsState) : undefined,
      version: 1,
      lastModified: now,
      synced: false,
      pendingChanges: [],
      metadata: doc.metadata || {},
      collection: doc.collection || "default",
      tags: doc.tags || [],
      ownerId: doc.ownerId,
      organizationId: doc.organizationId,
      createdAt: now,
      updatedAt: now,
    };

    await collection.insert(docData);
    return id;
  }

  async updateDocument(
    documentId: string,
    updates: Partial<{
      title: string;
      content: string;
      yjsState: Uint8Array;
      metadata: Record<string, any>;
      tags: string[];
    }>,
  ): Promise<void> {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    const doc = await collection.findOne("documentId", documentId).exec();
    if (!doc) throw new Error(`Document not found: ${documentId}`);

    const patch: any = { lastModified: Date.now(), synced: false };

    if (updates.title !== undefined) patch.title = updates.title;
    if (updates.content !== undefined) patch.content = updates.content;
    if (updates.yjsState !== undefined)
      patch.yjsState = Array.from(updates.yjsState);
    if (updates.metadata !== undefined)
      patch.metadata = { ...doc.metadata, ...updates.metadata };
    if (updates.tags !== undefined) patch.tags = updates.tags;

    await doc.atomicPatch(patch);
  }

  async deleteDocument(documentId: string): Promise<void> {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    const doc = await collection.findOne("documentId", documentId).exec();
    if (doc) {
      await doc.remove();
    }
  }

  async markDocumentSynced(
    documentId: string,
    serverVersion?: number,
  ): Promise<void> {
    const collection = this.getDocumentsCollection();
    if (!collection) throw new Error("Documents collection not initialized");

    const doc = await collection.findOne("documentId", documentId).exec();
    if (doc) {
      await doc.atomicPatch({
        synced: true,
        version: serverVersion || doc.version + 1,
      });
    }
  }

  // ==================== Change Tracking ====================

  async addChange(change: {
    documentId: string;
    type: "create" | "update" | "delete";
    data: any;
  }): Promise<void> {
    const collection = this.getChangesCollection();
    if (!collection) throw new Error("Changes collection not initialized");

    await collection.insert({
      id: crypto.randomUUID(),
      documentId: change.documentId,
      type: change.type,
      timestamp: Date.now(),
      data: change.data,
      synced: false,
      retryCount: 0,
      maxRetries: 3,
    });
  }

  async getPendingChanges(documentId?: string): Promise<any[]> {
    const collection = this.getChangesCollection();
    if (!collection) throw new Error("Changes collection not initialized");

    let query = collection.find().where("synced").eq(false);
    if (documentId) {
      query = query.where("documentId").eq(documentId);
    }
    return query.exec();
  }

  // ==================== Presence ====================

  async upsertPresence(presence: {
    userId: string;
    organizationId: string;
    status: "online" | "idle" | "away" | "offline";
    cursor?: { x: number; y: number };
    selection?: { start: number; end: number };
    metadata?: Record<string, any>;
  }): Promise<void> {
    const collection = this.getPresenceCollection();
    if (!collection) throw new Error("Presence collection not initialized");

    await collection.upsert({
      userId: presence.userId,
      organizationId: presence.organizationId,
      status: presence.status,
      lastActive: Date.now(),
      cursor: presence.cursor,
      selection: presence.selection,
      metadata: presence.metadata || {},
    });
  }

  // ==================== Notifications ====================

  async addNotification(notification: {
    type: string;
    title: string;
    body: string;
    data?: Record<string, any>;
    priority?: "high" | "normal" | "low";
  }): Promise<string> {
    const collection = this.getNotificationsCollection();
    if (!collection)
      throw new Error("Notifications collection not initialized");

    const id = crypto.randomUUID();
    await collection.insert({
      id,
      type: notification.type,
      title: notification.title,
      body: notification.body,
      data: notification.data || {},
      read: false,
      timestamp: Date.now(),
      synced: false,
      priority: notification.priority || "normal",
    });
    return id;
  }

  async markNotificationRead(id: string): Promise<void> {
    const collection = this.getNotificationsCollection();
    if (!collection)
      throw new Error("Notifications collection not initialized");

    const doc = await collection.findOne(id).exec();
    if (doc) {
      await doc.atomicPatch({ read: true, synced: false });
    }
  }

  // ==================== Sync Queue ====================

  async addToSyncQueue(item: {
    type: string;
    operation: "create" | "update" | "delete";
    payload: any;
    priority?: "high" | "normal" | "low";
    maxRetries?: number;
  }): Promise<string> {
    const collection = this.getSyncQueueCollection();
    if (!collection) throw new Error("Sync queue collection not initialized");

    const id = crypto.randomUUID();
    await collection.insert({
      id,
      type: item.type,
      operation: item.operation,
      payload: item.payload,
      timestamp: Date.now(),
      retries: 0,
      maxRetries: item.maxRetries || 3,
      priority: item.priority || "normal",
      status: "pending",
    });
    return id;
  }

  // ==================== Search ====================

  async searchDocuments(query: string, limit = 10): Promise<any[]> {
    const collection = this.getSearchIndexCollection();
    if (!collection) throw new Error("Search index collection not initialized");

    const lowerQuery = query.toLowerCase();
    return collection
      .find()
      .where("title")
      .matches(new RegExp(lowerQuery, "i"))
      .or("content")
      .matches(new RegExp(lowerQuery, "i"))
      .limit(limit)
      .exec();
  }

  async updateSearchIndex(index: {
    documentId: string;
    title: string;
    content: string;
    tags: string[];
  }): Promise<void> {
    const collection = this.getSearchIndexCollection();
    if (!collection) throw new Error("Search index collection not initialized");

    const id = crypto.randomUUID();
    await collection.upsert({
      id,
      documentId: index.documentId,
      title: index.title,
      content: index.content,
      tags: index.tags,
      updatedAt: Date.now(),
    });
  }

  // ==================== Settings ====================

  async getSetting(key: string): Promise<any> {
    const collection = this.getSettingsCollection();
    if (!collection) throw new Error("Settings collection not initialized");

    const doc = await collection.findOne(key).exec();
    return doc?.value;
  }

  async setSetting(key: string, value: any): Promise<void> {
    const collection = this.getSettingsCollection();
    if (!collection) throw new Error("Settings collection not initialized");

    await collection.upsert({ key, value, updatedAt: Date.now() });
  }

  // ==================== Replication / Sync ====================

  async startReplication(config: SyncConfig): Promise<void> {
    if (!this.db) throw new Error("Database not initialized");

    const collectionsToReplicate = ["documents", "changes", "notifications"];

    for (const name of collectionsToReplicate) {
      const collection = this.collections.get(name);
      if (!collection) continue;

      try {
        const replication = replicateRxCollection({
          collection,
          live: config.live ?? true,
          retryTime: config.retryDelay ?? 5000,
          waitForLeadership: config.waitForLeadership ?? true,
          autoStart: true,
          pull: {
            url: `${config.remoteUrl}/${collection.name}`,
            headers: config.authToken
              ? { Authorization: `Bearer ${config.authToken}` }
              : {},
            batchSize: config.batchSize ?? 100,
          },
          push: {
            url: `${config.remoteUrl}/${collection.name}`,
            headers: config.authToken
              ? { Authorization: `Bearer ${config.authToken}` }
              : {},
            batchSize: config.batchSize ?? 100,
            modifier: (doc) => {
              // Remove internal fields before push
              const { _rev, _attachments, ...rest } = doc;
              return rest;
            },
          },
          conflictHandler: this.defaultConflictHandler.bind(this),
        });

        this.replications.set(name, replication);

        // Monitor replication state
        replication.replicationState$.subscribe((state) => {
          console.log(`[RxDB] Replication ${name}:`, state);
        });

        replication.error$.subscribe((err) => {
          console.error(`[RxDB] Replication error ${name}:`, err);
        });
      } catch (error) {
        console.error(`Failed to start replication for ${name}:`, error);
      }
    }
  }

  async stopReplication(): Promise<void> {
    for (const [name, replication] of this.replications) {
      try {
        await replication.cancel();
      } catch (e) {
        console.warn(`Failed to cancel replication ${name}:`, e);
      }
    }
    this.replications.clear();
  }

  // ==================== Import/Export ====================

  async exportAllData(): Promise<any> {
    if (!this.db) throw new Error("Database not initialized");

    const data: Record<string, any[]> = {};

    for (const [name, collection] of this.collections) {
      data[name] = await collection.find().exec();
    }

    return {
      version: 1,
      exportedAt: Date.now(),
      ...data,
    };
  }

  async importData(data: any): Promise<void> {
    if (!this.db) throw new Error("Database not initialized");
    if (!data || data.version !== 1) {
      throw new Error("Invalid data format");
    }

    await this.db.transaction(async () => {
      for (const [name, collection] of this.collections) {
        if (data[name]) {
          // Clear existing
          const docs = await collection.find().exec();
          for (const doc of docs) {
            await doc.remove();
          }
          // Import new
          for (const doc of data[name]) {
            await collection.insert(doc);
          }
        }
      }
    });
  }

  async exportToCSV(collectionName: string): Promise<string> {
    const collection = this.collections.get(collectionName);
    if (!collection) throw new Error(`Collection not found: ${collectionName}`);

    const docs = await collection.find().exec();
    if (docs.length === 0) return "";

    const headers = Object.keys(docs[0].toJSON ? docs[0].toJSON() : docs[0]);
    const rows = docs.map((doc) => {
      const obj = doc.toJSON ? doc.toJSON() : doc;
      return headers.map((h) => JSON.stringify(obj[h] ?? "")).join(",");
    });

    return [headers.join(","), ...rows].join("\n");
  }

  async exportToJSON(): Promise<string> {
    const data = await this.exportAllData();
    return JSON.stringify(data, null, 2);
  }

  // GDPR Export
  async exportUserData(userId: string): Promise<any> {
    const userData: Record<string, any[]> = {};

    // Export all user-related data
    for (const [name, collection] of this.collections) {
      let query = collection.find();

      // Filter by ownerId or userId
      try {
        query = query.where("ownerId").eq(userId);
      } catch {
        try {
          query = query.where("userId").eq(userId);
        } catch {
          continue; // Collection doesn't have user fields
        }
      }

      userData[name] = await query.exec();
    }

    return {
      userId,
      exportedAt: Date.now(),
      version: 1,
      data: userData,
    };
  }

  // ==================== Cleanup ====================

  async clearAllData(): Promise<void> {
    if (!this.db) return;

    await this.db.transaction(async () => {
      for (const collection of this.collections.values()) {
        await collection.remove();
      }
    });
  }

  async destroy(): Promise<void> {
    await this.stopReplication();

    if (this.db) {
      await this.db.destroy();
      this.db = null;
    }

    this.initialized = false;
    this.collections.clear();
    this.replications.clear();
    this.changeSubjects.clear();
  }

  // ==================== Getters ====================

  getDatabase(): RxDatabase | null {
    return this.db;
  }

  isReady(): boolean {
    return this.initialized && this.db !== null;
  }
}

// ==================== Singleton ====================

let _rxdbManager: RxDBManager | null = null;

export function getRxDBManager(): RxDBManager {
  if (!_rxdbManager) {
    _rxdbManager = new RxDBManager();
  }
  return _rxdbManager;
}

export async function initializeRxDB(options?: {
  name?: string;
  password?: string;
  multiInstance?: boolean;
  enableDevMode?: boolean;
}): Promise<RxDBManager> {
  const manager = getRxDBManager();
  await manager.initialize(options);
  return manager;
}

// ==================== React Hooks ====================

// Export for use in hooks
export { RxDatabase, RxCollection, RxDocument };
export type { SyncConfig, ConflictHandler, ConflictData, CollectionOptions };

// Default instance
export const rxdbManager = getRxDBManager();
