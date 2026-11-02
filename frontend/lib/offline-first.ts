/**
 * Universal Data Layer & Offline-First - Main Entry Point
 *
 * Unified API for all offline-first capabilities:
 * - RxDB for reactive queries
 * - Enhanced sync engine with exponential backoff
 * - Selective sync with user-defined filters
 * - CRDT integration for collaborative data
 * - Conflict resolution with multiple strategies
 * - Data portability (JSON/CSV/Parquet + GDPR)
 * - Data portability (JSON/CSV/Parquet + GDPR)
 */

export {
  SyncEngine,
  SyncConfig,
  SyncResult,
  SyncStats,
  SelectiveSyncFilter,
  createSyncEngine,
  defaultConflictResolver,
} from "./sync-engine";
export {
  RxDBManager,
  RxDBSchema,
  SyncConfig as RxDBSyncConfig,
  DocumentChunk,
  getRxDBManager,
  initializeRxDB,
  rxdbManager,
} from "./rxdb-manager";
export {
  SelectiveSyncManager,
  SyncProfile,
  SelectiveSyncOptions,
  SyncStatus,
  SyncConflict,
  SyncAuditEntry,
  getSelectiveSyncManager,
  useSelectiveSync,
} from "./selective-sync";
export {
  DataPortabilityManager,
  ExportOptions,
  ImportOptions,
  ExportFormat,
  ExportResult,
  ImportResult,
  GDPRExportOptions,
  GDPRExportResult,
  getDataPortabilityManager,
  useDataPortability,
} from "./data-portability";
export {
  CRDTManager,
  CRDTDocumentConfig,
  CRDTSyncConfig,
  CRDTMetrics,
  CRDTConflictInfo,
  CRDTType,
  getCRDTManager,
  useCRDTDocument,
  useCRDTArray,
  useCRDTMap,
  useCRDTAwareness,
} from "./crdt-integration";
export {
  ConflictResolutionEngine,
  ConflictType,
  ResolutionStrategy,
  ConflictContext,
  ResolutionResult,
  ResolutionRule,
  ConflictAuditEntry,
  ConflictResolver,
  getConflictResolutionEngine,
  useConflictResolution,
} from "./conflict-resolution";
export {
  OfflineDatabase,
  OfflineDocument,
  OfflineChange,
  OfflinePresence,
  OfflineNotification,
  SyncQueueItem,
  OfflineSettings,
  OfflineSearchIndex,
  getOfflineDB,
  initializeOfflineDB,
} from "./offline-db";

// ==================== Unified Offline-First Manager ====================

import { RxDBManager } from "./rxdb-manager";
import { OfflineDatabase } from "./offline-db";
import { SyncEngine } from "./sync-engine";
import { SelectiveSyncManager } from "./selective-sync";
import { DataPortabilityManager } from "./data-portability";
import { CRDTManager } from "./crdt-integration";
import { ConflictResolutionEngine } from "./conflict-resolution";

export interface OfflineFirstConfig {
  // Database
  dbName?: string;
  dbPassword?: string;
  enableEncryption?: boolean;

  // Sync
  syncEndpoint?: string;
  syncBatchSize?: number;
  syncInterval?: number;
  syncBaseDelay?: number;
  syncMaxDelay?: number;
  syncMaxRetries?: number;

  // Selective Sync
  defaultSyncProfile?: {
    collections?: string[];
    tags?: string[];
    maxSize?: number;
    maxItems?: number;
    syncOnConnect?: boolean;
    syncInterval?: number;
  };

  // CRDT
  crdtSyncEndpoint?: string;

  // Conflict Resolution
  defaultConflictStrategy?:
    "crdt" | "lww" | "ot" | "server-wins" | "client-wins" | "merge";

  // Data Portability
  defaultExportFormat?: "json" | "csv" | "parquet" | "zip";

  // Dev mode
  enableDevMode?: boolean;
  multiInstance?: boolean;
}

export interface OfflineFirstStatus {
  isInitialized: boolean;
  isOnline: boolean;
  isSyncing: boolean;
  dbReady: boolean;
  syncEngineReady: boolean;
  selectiveSyncReady: boolean;
  crdtReady: boolean;
  conflictEngineReady: boolean;
  pendingChanges: number;
  pendingSyncItems: number;
  lastSync: number | null;
  storageUsed: number;
  storageAvailable: number;
  activeProfile: string | null;
}

export class OfflineFirstManager {
  private config: OfflineFirstConfig;

  // Core components
  private rxdb: RxDBManager;
  private db: OfflineDatabase;
  private syncEngine: SyncEngine;
  private selectiveSync: SelectiveSyncManager;
  private dataPortability: DataPortabilityManager;
  private crdtManager: CRDTManager;
  private conflictEngine: ConflictResolutionEngine;

  // State
  private initialized = false;
  private initializationPromise: Promise<void> | null = null;
  private statusSubject = new BehaviorSubject<OfflineFirstStatus>({
    isInitialized: false,
    isOnline: navigator.onLine,
    isSyncing: false,
    dbReady: false,
    syncEngineReady: false,
    selectiveSyncReady: false,
    crdtReady: false,
    conflictEngineReady: false,
    pendingChanges: 0,
    pendingSyncItems: 0,
    lastSync: null,
    storageUsed: 0,
    storageAvailable: 0,
    activeProfile: null,
  });

  private statusListeners: Set<(status: OfflineFirstStatus) => void> =
    new Set();

  constructor(config: OfflineFirstConfig = {}) {
    this.config = {
      dbName: config.dbName || "vcos-offline",
      dbPassword: config.dbPassword,
      enableEncryption: config.enableEncryption || false,
      syncEndpoint: config.syncEndpoint,
      syncBatchSize: config.syncBatchSize || 50,
      syncInterval: config.syncInterval || 30000,
      syncBaseDelay: config.syncBaseDelay || 1000,
      syncMaxDelay: config.syncMaxDelay || 300000,
      syncMaxRetries: config.syncMaxRetries || 10,
      defaultSyncProfile: config.defaultSyncProfile,
      crdtSyncEndpoint: config.crdtSyncEndpoint,
      defaultConflictStrategy: config.defaultConflictStrategy || "crdt",
      defaultExportFormat: config.defaultExportFormat || "json",
      enableDevMode:
        config.enableDevMode || process.env.NODE_ENV === "development",
      multiInstance: config.multiInstance ?? true,
    };

    // Initialize core components
    this.rxdb = new RxDBManager();
    this.db = new OfflineDatabase();

    // Initialize sync engine with API operations
    this.syncEngine = new SyncEngine(
      this.db,
      async (item, db) => {
        await this.performSyncOperation(item, db);
      },
      {
        baseDelay: this.config.syncBaseDelay,
        maxDelay: this.config.syncMaxDelay,
        maxRetries: this.config.syncMaxRetries,
        batchSize: this.config.syncBatchSize,
        syncInterval: this.config.syncInterval,
      },
    );

    // Other managers will be initialized after RxDB
    this.selectiveSync = new SelectiveSyncManager(
      this.rxdb,
      this.syncEngine,
      this.db,
    );
    this.dataPortability = new DataPortabilityManager(this.rxdb, this.db);
    // crdtManager and conflictEngine need rxdb and db - will init after
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    if (this.initializationPromise) return this.initializationPromise;

    this.initializationPromise = this._initialize();
    return this.initializationPromise;
  }

  private async _initialize(): Promise<void> {
    try {
      // Initialize RxDB first
      await this.rxdb.initialize({
        name: this.config.dbName,
        password: this.config.dbPassword,
        enableDevMode: this.config.enableDevMode,
        multiInstance: this.config.multiInstance,
      });
      this.updateStatus({ dbReady: true });

      // Initialize IndexedDB
      await initializeOfflineDB();

      // Initialize selective sync
      await this.selectiveSync.initialize();
      this.updateStatus({ selectiveSyncReady: true });

      // Initialize CRDT manager
      this.crdtManager = new CRDTManager(this.rxdb, this.db, this.syncEngine);
      await this.crdtManager.initialize();
      this.updateStatus({ crdtReady: true });

      // Initialize conflict resolution engine
      this.conflictEngine = new ConflictResolutionEngine(
        this.rxdb,
        this.db,
        this.crdtManager,
      );
      this.updateStatus({ conflictEngineReady: true });

      // Start sync engine
      this.syncEngine.start();
      this.updateStatus({ syncEngineReady: true });

      // Set up default sync profile if provided
      if (this.config.defaultSyncProfile) {
        await this.selectiveSync.createProfile({
          name: "Default",
          description: "Default sync profile",
          options: this.config.defaultSyncProfile,
          isDefault: true,
        });
      }

      // Set up online/offline listeners
      this.setupOnlineListener();

      // Start status monitoring
      this.startStatusMonitoring();

      this.initialized = true;
      this.updateStatus({ isInitialized: true, isOnline: navigator.onLine });

      console.log("[OfflineFirst] Fully initialized");
    } catch (error) {
      console.error("[OfflineFirst] Initialization failed:", error);
      throw error;
    }
  }

  private setupOnlineListener(): void {
    window.addEventListener("online", () => this.handleOnline());
    window.addEventListener("offline", () => this.handleOffline());
  }

  private handleOnline(): void {
    this.updateStatus({ isOnline: true });
    this.syncEngine.start();
    this.selectiveSync.resume();

    // Resume CRDT connections
    for (const [docId] of this.crdtManager.getAllDocuments()) {
      this.crdtManager.connect(docId);
    }
  }

  private handleOffline(): void {
    this.updateStatus({ isOnline: false });
    this.syncEngine.stop();
    this.selectiveSync.pause();

    // Disconnect CRDT
    for (const [docId] of this.crdtManager.getAllDocuments()) {
      this.crdtManager.disconnect(docId);
    }
  }

  private startStatusMonitoring(): void {
    setInterval(async () => {
      if (!this.initialized) return;

      try {
        const syncStatus = await this.db.getSyncStatus();
        const storageStats = await this.selectiveSync.getStorageStats();

        this.updateStatus({
          isOnline: navigator.onLine,
          pendingChanges: syncStatus.pendingChanges,
          pendingSyncItems: syncStatus.pendingSyncItems,
          lastSync: syncStatus.lastSyncTime,
          storageUsed: storageStats.used,
          storageAvailable: storageStats.available,
        });
      } catch (e) {
        console.warn("[OfflineFirst] Status update failed:", e);
      }
    }, 5000);
  }

  private updateStatus(partial: Partial<OfflineFirstStatus>): void {
    const current = this.statusSubject.value;
    this.statusSubject.next({ ...current, ...partial });
    this.statusListeners.forEach((listener) =>
      listener(this.statusSubject.value),
    );
  }

  // ==================== Public API ====================

  getRxDB(): RxDBManager {
    return this.rxdb;
  }
  getDatabase(): OfflineDatabase {
    return this.db;
  }
  getSyncEngine(): SyncEngine {
    return this.syncEngine;
  }
  getSelectiveSync(): SelectiveSyncManager {
    return this.selectiveSync;
  }
  getDataPortability(): DataPortabilityManager {
    return this.dataPortability;
  }
  getCRDTManager(): CRDTManager {
    return this.crdtManager;
  }
  getConflictEngine(): ConflictResolutionEngine {
    return this.conflictEngine;
  }

  getStatus$(): Observable<OfflineFirstStatus> {
    return this.statusSubject.asObservable();
  }

  getStatus(): OfflineFirstStatus {
    return this.statusSubject.value;
  }

  subscribe(listener: (status: OfflineFirstStatus) => void): () => void {
    this.statusListeners.add(listener);
    listener(this.statusSubject.value);
    return () => this.statusListeners.delete(listener);
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
    crdtType?: "ytext" | "yarray" | "ymap" | "yxml" | "counter";
  }): Promise<string> {
    // Create in RxDB
    const docId = await this.rxdb.createDocument({
      documentId: doc.documentId,
      title: doc.title,
      content: doc.content,
      ownerId: doc.ownerId,
      organizationId: doc.organizationId,
      collection: doc.collection || "default",
      tags: doc.tags || [],
      metadata: doc.metadata || {},
    });

    // Create CRDT document if specified
    if (doc.crdtType) {
      await this.crdtManager.createDocument({
        documentId: doc.documentId,
        type: doc.crdtType,
        initialContent: doc.content,
        syncEndpoint: this.config.crdtSyncEndpoint,
      });
    }

    return docId;
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
    // Update RxDB
    await this.rxdb.updateDocument(documentId, updates);

    // Update CRDT if exists
    if (updates.content) {
      const ytext = this.crdtManager.getText(documentId);
      if (ytext) {
        ytext.delete(0, ytext.length);
        ytext.insert(0, updates.content);
      }
    }
  }

  async markSynced(documentId: string): Promise<void> {
    await this.rxdb.markDocumentSynced(documentId);
  }

  // ==================== Sync Operations ====================

  async syncNow(): Promise<any> {
    return this.syncEngine.syncNow();
  }

  async selectiveSyncNow(): Promise<any> {
    return this.selectiveSync.syncNow();
  }

  // ==================== CRDT Operations ====================

  async createCRDTDocument(config: {
    documentId: string;
    type: "ytext" | "yarray" | "ymap" | "yxml" | "counter" | "awareness";
    initialContent?: any;
    syncEndpoint?: string;
  }): Promise<any> {
    return this.crdtManager.createDocument(config);
  }

  getCRDTDocument(documentId: string): any {
    return this.crdtManager.getDocument(documentId);
  }

  // ==================== Conflict Resolution ====================

  async resolveConflicts(documentId: string, userId: string): Promise<any[]> {
    // Get local and remote data
    // Detect conflicts
    // Resolve using conflict engine
    return [];
  }

  // ==================== Data Portability ====================

  async exportData(options: any): Promise<any> {
    return this.dataPortability.exportData(options);
  }

  async downloadExport(options: any): Promise<void> {
    return this.dataPortability.downloadExport(options);
  }

  async importData(data: any, options: any): Promise<any> {
    return this.dataPortability.importData(data, options);
  }

  async exportGDPR(userId: string, format?: string): Promise<any> {
    return this.dataPortability.exportUserDataGDPR({
      userId,
      format: format as any,
    });
  }

  async downloadGDPR(userId: string, format?: string): Promise<void> {
    return this.dataPortability.downloadGDPRExport({
      userId,
      format: format as any,
    });
  }

  // ==================== Selective Sync ====================

  async createSyncProfile(profile: any): Promise<any> {
    return this.selectiveSync.createProfile(profile);
  }

  async setActiveSyncProfile(profileId: string): Promise<void> {
    await this.selectiveSync.setActiveProfile(profileId);
    this.updateStatus({ activeProfile: profileId });
  }

  getSyncProfiles(): any[] {
    return this.selectiveSync.getProfiles();
  }

  // ==================== Utility ====================

  async clearAllData(): Promise<void> {
    await this.db.clearAllData();
    await this.rxdb.clearAllData();
  }

  async destroy(): Promise<void> {
    this.syncEngine.stop();
    this.selectiveSync.destroy();
    this.crdtManager.destroyAll();
    await this.rxdb.destroy();
    await this.db.close?.();
    this.initialized = false;
  }

  isReady(): boolean {
    return this.initialized;
  }

  // ==================== Sync Operation Implementation ====================

  private async performSyncOperation(
    item: any,
    db: OfflineDatabase,
  ): Promise<void> {
    // This would call actual API endpoints
    // For now, simulate network request
    await new Promise((resolve) => setTimeout(resolve, 50));

    switch (item.type) {
      case "document":
        // Sync document to server
        break;
      case "crdt":
        // Sync CRDT update
        break;
      case "presence":
        // Sync presence
        break;
    }
  }
}

// ==================== Singleton ====================

import { BehaviorSubject, Observable } from "rxjs";

let _offlineFirstManager: OfflineFirstManager | null = null;

export function getOfflineFirstManager(
  config?: OfflineFirstConfig,
): OfflineFirstManager {
  if (!_offlineFirstManager) {
    _offlineFirstManager = new OfflineFirstManager(config);
  }
  return _offlineFirstManager;
}

export async function initializeOfflineFirst(
  config?: OfflineFirstConfig,
): Promise<OfflineFirstManager> {
  const manager = getOfflineFirstManager(config);
  await manager.initialize();
  return manager;
}

// ==================== React Hook ====================

import { useState, useEffect, useCallback } from "react";

export function useOfflineFirst(config?: OfflineFirstConfig) {
  const [manager] = useState(() => getOfflineFirstManager(config));
  const [status, setStatus] = useState<OfflineFirstStatus | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        await manager.initialize();
        setIsInitializing(false);
      } catch (error) {
        console.error("OfflineFirst initialization failed:", error);
        setIsInitializing(false);
      }
    };
    init();

    const statusSub = manager.getStatus$().subscribe((s) => setStatus(s));

    return () => {
      statusSub.unsubscribe();
    };
  }, [manager]);

  // Document operations
  const createDocument = useCallback(
    async (doc: any) => {
      return manager.createDocument(doc);
    },
    [manager],
  );

  const updateDocument = useCallback(
    async (id: string, updates: any) => {
      return manager.updateDocument(id, updates);
    },
    [manager],
  );

  const markSynced = useCallback(
    async (id: string) => {
      return manager.markSynced(id);
    },
    [manager],
  );

  // Sync operations
  const syncNow = useCallback(async () => {
    return manager.syncNow();
  }, [manager]);

  const selectiveSyncNow = useCallback(async () => {
    return manager.selectiveSyncNow();
  }, [manager]);

  // CRDT operations
  const createCRDTDocument = useCallback(
    async (config: any) => {
      return manager.createCRDTDocument(config);
    },
    [manager],
  );

  // Export/Import
  const exportData = useCallback(
    async (options: any) => {
      return manager.exportData(options);
    },
    [manager],
  );

  const downloadExport = useCallback(
    async (options: any) => {
      return manager.downloadExport(options);
    },
    [manager],
  );

  const importData = useCallback(
    async (data: any, options: any) => {
      return manager.importData(data, options);
    },
    [manager],
  );

  const exportGDPR = useCallback(
    async (userId: string, format?: string) => {
      return manager.exportGDPR(userId, format);
    },
    [manager],
  );

  const downloadGDPR = useCallback(
    async (userId: string, format?: string) => {
      return manager.downloadGDPR(userId, format);
    },
    [manager],
  );

  // Selective sync profiles
  const createSyncProfile = useCallback(
    async (profile: any) => {
      return manager.createSyncProfile(profile);
    },
    [manager],
  );

  const setActiveSyncProfile = useCallback(
    async (id: string) => {
      return manager.setActiveSyncProfile(id);
    },
    [manager],
  );

  const getSyncProfiles = useCallback(() => {
    return manager.getSyncProfiles();
  }, [manager]);

  return {
    manager,
    status,
    isInitializing,
    isReady: status?.isInitialized || false,
    isOnline: status?.isOnline || false,
    isSyncing: status?.isSyncing || false,
    pendingChanges: status?.pendingChanges || 0,
    lastSync: status?.lastSync || null,
    storageUsed: status?.storageUsed || 0,
    storageAvailable: status?.storageAvailable || 0,
    activeProfile: status?.activeProfile || null,
    // Operations
    createDocument,
    updateDocument,
    markSynced,
    syncNow,
    selectiveSyncNow,
    createCRDTDocument,
    exportData,
    downloadExport,
    importData,
    exportGDPR,
    downloadGDPR,
    createSyncProfile,
    setActiveSyncProfile,
    getSyncProfiles,
    // Sub-components
    rxdb: manager.getRxDB(),
    db: manager.getDatabase(),
    syncEngine: manager.getSyncEngine(),
    selectiveSync: manager.getSelectiveSync(),
    dataPortability: manager.getDataPortability(),
    crdtManager: manager.getCRDTManager(),
    conflictEngine: manager.getConflictEngine(),
  };
}

// ==================== Default Export ====================

export default {
  getOfflineFirstManager,
  initializeOfflineFirst,
  useOfflineFirst,
  OfflineFirstManager,
};

export { OfflineFirstConfig, OfflineFirstStatus };
