/**
 * Enhanced Sync Engine with Exponential Backoff
 * Provides robust background synchronization for offline-first data
 */

import {
  OfflineDatabase,
  SyncQueueItem,
  OfflineDocument,
  OfflineChange,
} from "./offline-db";

export interface SyncConfig {
  baseDelay: number; // Base delay in ms (default: 1000)
  maxDelay: number; // Max delay in ms (default: 300000 = 5 min)
  maxRetries: number; // Max retry attempts (default: 10)
  backoffMultiplier: number; // Exponential backoff multiplier (default: 2)
  jitter: boolean; // Add jitter to prevent thundering herd
  batchSize: number; // Items per sync batch (default: 50)
  syncInterval: number; // Periodic sync interval (default: 30000)
  priorityWeights: {
    // Priority-based scheduling
    high: number;
    normal: number;
    low: number;
  };
}

export interface SyncStats {
  totalSynced: number;
  totalFailed: number;
  totalPending: number;
  lastSyncTime: number | null;
  averageSyncTime: number;
  currentBackoff: number;
  isSyncing: boolean;
}

export interface SyncResult {
  success: boolean;
  synced: number;
  failed: number;
  errors: Array<{ itemId: string; error: string }>;
  duration: number;
}

export type SyncOperation = (
  item: SyncQueueItem,
  db: OfflineDatabase,
) => Promise<void>;

export type ConflictResolver = (
  local: OfflineDocument,
  remote: OfflineDocument,
  db: OfflineDatabase,
) => Promise<OfflineDocument>;

export type SelectiveSyncFilter = {
  collections?: string[];
  tags?: string[];
  dateRange?: { start: number; end: number };
  userIds?: string[];
  organizationIds?: string[];
  maxSize?: number; // in bytes
};

export class SyncEngine {
  private db: OfflineDatabase;
  private config: SyncConfig;
  private operation: SyncOperation;
  private conflictResolver?: ConflictResolver;
  private selectiveFilter?: SelectiveSyncFilter;

  private syncIntervalId: ReturnType<typeof setInterval> | null = null;
  private backoffTimerId: ReturnType<typeof setTimeout> | null = null;
  private currentBackoff = 0;
  private retryCount = 0;
  private isSyncing = false;
  private isOnline = navigator.onLine;
  private abortController: AbortController | null = null;

  // Stats
  private stats: SyncStats = {
    totalSynced: 0,
    totalFailed: 0,
    totalPending: 0,
    lastSyncTime: null,
    averageSyncTime: 0,
    currentBackoff: 0,
    isSyncing: false,
  };

  private syncTimes: number[] = [];
  private listeners: Set<(stats: SyncStats) => void> = new Set();

  constructor(
    db: OfflineDatabase,
    operation: SyncOperation,
    config: Partial<SyncConfig> = {},
  ) {
    this.db = db;
    this.operation = operation;

    this.config = {
      baseDelay: config.baseDelay ?? 1000,
      maxDelay: config.maxDelay ?? 300000,
      maxRetries: config.maxRetries ?? 10,
      backoffMultiplier: config.backoffMultiplier ?? 2,
      jitter: config.jitter ?? true,
      batchSize: config.batchSize ?? 50,
      syncInterval: config.syncInterval ?? 30000,
      priorityWeights: config.priorityWeights ?? { high: 3, normal: 2, low: 1 },
    };

    // Listen for online/offline events
    window.addEventListener("online", this.handleOnline.bind(this));
    window.addEventListener("offline", this.handleOffline.bind(this));
  }

  // ==================== Public API ====================

  /**
   * Start the sync engine
   */
  start(): void {
    this.schedulePeriodicSync();
    this.updateStats();
  }

  /**
   * Stop the sync engine
   */
  stop(): void {
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
      this.syncIntervalId = null;
    }
    if (this.backoffTimerId) {
      clearTimeout(this.backoffTimerId);
      this.backoffTimerId = null;
    }
    if (this.abortController) {
      this.abortController.abort();
    }
  }

  /**
   * Trigger immediate sync
   */
  async syncNow(): Promise<SyncResult> {
    if (this.isSyncing || !this.isOnline) {
      return { success: false, synced: 0, failed: 0, errors: [], duration: 0 };
    }
    return this.performSync();
  }

  /**
   * Set selective sync filter
   */
  setSelectiveFilter(filter: SelectiveSyncFilter | undefined): void {
    this.selectiveFilter = filter;
  }

  /**
   * Set conflict resolver
   */
  setConflictResolver(resolver: ConflictResolver | undefined): void {
    this.conflictResolver = resolver;
  }

  /**
   * Subscribe to sync stats updates
   */
  subscribe(listener: (stats: SyncStats) => void): () => void {
    this.listeners.add(listener);
    listener(this.stats); // Initial call
    return () => this.listeners.delete(listener);
  }

  /**
   * Get current stats
   */
  getStats(): SyncStats {
    return { ...this.stats };
  }

  /**
   * Force retry failed items
   */
  async retryFailed(): Promise<void> {
    // Reset failed items to pending
    const failedItems = await this.db.syncQueue
      .where("status")
      .equals("failed")
      .toArray();

    for (const item of failedItems) {
      await this.db.markSyncItemFailed(item.id, "");
    }

    await this.syncNow();
  }

  // ==================== Private Methods ====================

  private handleOnline(): void {
    this.isOnline = true;
    this.currentBackoff = 0;
    this.retryCount = 0;
    this.scheduleImmediateSync();
  }

  private handleOffline(): void {
    this.isOnline = false;
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
      this.syncIntervalId = null;
    }
  }

  private schedulePeriodicSync(): void {
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
    }
    this.syncIntervalId = setInterval(() => {
      if (this.isOnline && !this.isSyncing) {
        this.performSync();
      }
    }, this.config.syncInterval);
  }

  private scheduleImmediateSync(): void {
    // Sync immediately with small delay to let UI settle
    setTimeout(() => this.performSync(), 100);
  }

  private calculateBackoff(): number {
    const { baseDelay, maxDelay, backoffMultiplier, jitter } = this.config;

    // Exponential backoff: baseDelay * (multiplier ^ retryCount)
    let delay = Math.min(
      baseDelay * Math.pow(backoffMultiplier, this.retryCount),
      maxDelay,
    );

    // Add jitter (±25%)
    if (jitter) {
      const jitterAmount = delay * 0.25;
      delay = delay + (Math.random() * 2 - 1) * jitterAmount;
    }

    return Math.max(0, Math.floor(delay));
  }

  private async performSync(): Promise<SyncResult> {
    if (this.isSyncing || !this.isOnline) {
      return { success: false, synced: 0, failed: 0, errors: [], duration: 0 };
    }

    this.isSyncing = true;
    this.abortController = new AbortController();
    const startTime = Date.now();
    const errors: Array<{ itemId: string; error: string }> = [];
    let synced = 0;
    let failed = 0;

    try {
      this.updateStats({ isSyncing: true });

      // Get pending items with priority ordering
      const pendingItems = await this.getPrioritizedPendingItems(
        this.config.batchSize,
      );

      if (pendingItems.length === 0) {
        // Also check for unsynced documents
        await this.syncUnsyncedDocuments();
        this.onSyncSuccess();
        return {
          success: true,
          synced,
          failed: 0,
          errors: [],
          duration: Date.now() - startTime,
        };
      }

      // Process items in priority order
      for (const item of pendingItems) {
        if (this.abortController?.signal.aborted) break;

        await this.db.markSyncItemSyncing(item.id);

        try {
          await this.operation(item, this.db);
          await this.db.markSyncItemCompleted(item.id);
          synced++;
        } catch (error) {
          console.error(`Sync failed for item ${item.id}:`, error);
          await this.db.markSyncItemFailed(
            item.id,
            error instanceof Error ? error.message : "Unknown error",
          );
          failed++;
          errors.push({
            itemId: item.id,
            error: error instanceof Error ? error.message : "Unknown error",
          });
        }
      }

      // Sync unsynced documents
      await this.syncUnsyncedDocuments();

      this.onSyncSuccess();
    } catch (error) {
      console.error("Sync failed:", error);
      this.onSyncError();
      errors.push({
        itemId: "sync-engine",
        error: error instanceof Error ? error.message : "Unknown error",
      });
    }

    const duration = Date.now() - startTime;
    this.syncTimes.push(duration);
    if (this.syncTimes.length > 100) this.syncTimes.shift();

    return { success: failed === 0, synced, failed, errors, duration };
  }

  private async getPrioritizedPendingItems(
    limit: number,
  ): Promise<SyncQueueItem[]> {
    const items = await this.db.syncQueue
      .where("status")
      .anyOf(["pending", "syncing"])
      .limit(limit * 2) // Get more to allow sorting
      .toArray();

    // Sort by priority weight and timestamp
    return items
      .sort((a, b) => {
        const weightA = this.config.priorityWeights[a.priority] || 1;
        const weightB = this.config.priorityWeights[b.priority] || 1;

        // Higher priority first, then older first
        if (weightA !== weightB) return weightB - weightA;
        return a.timestamp - b.timestamp;
      })
      .slice(0, limit);
  }

  private async syncUnsyncedDocuments(): Promise<void> {
    const unsyncedDocs = await this.db.getUnsyncedDocuments();

    for (const doc of unsyncedDocs) {
      if (this.abortController?.signal.aborted) break;

      try {
        // Apply selective filter if set
        if (
          this.selectiveFilter &&
          !this.matchesFilter(doc, this.selectiveFilter)
        ) {
          continue;
        }

        // Check for conflicts if resolver is set
        if (this.conflictResolver) {
          // In production, fetch remote version and resolve
          // For now, just sync
        }

        await this.syncDocumentToServer(doc);
      } catch (error) {
        console.error(`Failed to sync document ${doc.documentId}:`, error);
      }
    }
  }

  private matchesFilter(
    doc: OfflineDocument,
    filter: SelectiveSyncFilter,
  ): boolean {
    if (
      filter.collections &&
      !filter.collections.includes(doc.metadata?.collection || "default")
    ) {
      return false;
    }
    if (filter.tags && doc.metadata?.tags) {
      const hasTag = doc.metadata.tags.some((t: string) =>
        filter.tags!.includes(t),
      );
      if (!hasTag) return false;
    }
    if (filter.dateRange) {
      if (
        doc.lastModified < filter.dateRange.start ||
        doc.lastModified > filter.dateRange.end
      ) {
        return false;
      }
    }
    if (filter.maxSize && JSON.stringify(doc).length > filter.maxSize) {
      return false;
    }
    return true;
  }

  private async syncDocumentToServer(doc: OfflineDocument): Promise<void> {
    // Call actual API endpoint
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
      // Mark as synced
      await this.db.documents.update(doc.id, {
        synced: true,
        version: result.server_version,
      });
    } else {
      throw new Error(result.error || "Document sync failed");
    }
  }

  private onSyncSuccess(): void {
    this.retryCount = 0;
    this.currentBackoff = 0;
    this.stats.lastSyncTime = Date.now();
    this.stats.totalSynced += 1;
    this.updateStats({ isSyncing: false, currentBackoff: 0 });
    this.schedulePeriodicSync();
  }

  private onSyncError(): void {
    this.retryCount++;
    this.currentBackoff = this.calculateBackoff();

    this.stats.totalFailed += 1;
    this.updateStats({
      isSyncing: false,
      currentBackoff: this.currentBackoff,
    });

    // Schedule retry with backoff
    if (this.backoffTimerId) {
      clearTimeout(this.backoffTimerId);
    }

    if (this.retryCount < this.config.maxRetries) {
      this.backoffTimerId = setTimeout(() => {
        if (this.isOnline) {
          this.performSync();
        }
      }, this.currentBackoff);
    } else {
      console.error("Max retries exceeded, stopping sync");
    }
  }

  private updateStats(partial: Partial<SyncStats> = {}): void {
    this.stats = {
      ...this.stats,
      ...partial,
      totalPending: this.stats.totalPending,
      averageSyncTime:
        this.syncTimes.length > 0
          ? this.syncTimes.reduce((a, b) => a + b, 0) / this.syncTimes.length
          : 0,
    };

    this.listeners.forEach((listener) => listener(this.stats));
  }

  // ==================== Selective Sync ====================

  /**
   * Get items matching selective sync criteria
   */
  async getSelectiveSyncItems(
    filter: SelectiveSyncFilter,
  ): Promise<OfflineDocument[]> {
    let docs = await this.db.documents.where("synced").equals(false).toArray();

    return docs.filter((doc) => this.matchesFilter(doc, filter));
  }

  /**
   * Get sync size estimate
   */
  async getSyncSizeEstimate(filter?: SelectiveSyncFilter): Promise<{
    itemCount: number;
    estimatedSize: number;
    estimatedTime: number;
  }> {
    const docs = filter
      ? await this.getSelectiveSyncItems(filter)
      : await this.db.getUnsyncedDocuments();

    const totalSize = docs.reduce(
      (sum, doc) => sum + JSON.stringify(doc).length,
      0,
    );
    const avgItemTime =
      this.stats.averageSyncTime > 0 ? this.stats.averageSyncTime : 100;

    return {
      itemCount: docs.length,
      estimatedSize: totalSize,
      estimatedTime: docs.length * avgItemTime,
    };
  }

  // ==================== Conflict Resolution ====================

  /**
   * Resolve conflict between local and remote versions
   */
  async resolveConflict(
    local: OfflineDocument,
    remote: OfflineDocument,
  ): Promise<OfflineDocument> {
    if (this.conflictResolver) {
      return this.conflictResolver(local, remote, this.db);
    }

    // Default: Last-write-wins based on lastModified
    return local.lastModified > remote.lastModified ? local : remote;
  }

  /**
   * Three-way merge for text documents (using CRDT)
   */
  async threeWayMerge(
    base: OfflineDocument,
    local: OfflineDocument,
    remote: OfflineDocument,
  ): Promise<OfflineDocument> {
    // This would use Yjs or similar CRDT for proper merging
    // For now, return the latest version
    const latest = [base, local, remote].sort(
      (a, b) => b.lastModified - a.lastModified,
    )[0];
    return {
      ...latest,
      version: Math.max(base.version, local.version, remote.version) + 1,
    };
  }
}

/**
 * Factory function to create sync engine with default API operations
 */
export function createSyncEngine(
  db: OfflineDatabase,
  apiClient: {
    syncDocument: (doc: OfflineDocument) => Promise<void>;
    syncOperation: (item: SyncQueueItem) => Promise<void>;
  },
  config?: Partial<SyncConfig>,
): SyncEngine {
  return new SyncEngine(
    db,
    async (item, db) => {
      switch (item.type) {
        case "document":
          await apiClient.syncDocument(item.payload as OfflineDocument);
          break;
        default:
          await apiClient.syncOperation(item);
      }
    },
    config,
  );
}

/**
 * Default conflict resolver: Server wins for system data, local wins for user content
 */
export const defaultConflictResolver: ConflictResolver = async (
  local,
  remote,
  db,
) => {
  // System fields: server wins
  const systemFields = ["id", "documentId", "version", "createdAt", "synced"];

  // User content: local wins (user's edits are precious)
  const userFields = ["content", "title", "metadata"];

  const merged = { ...remote };

  // Preserve user content from local
  for (const field of userFields) {
    if (local[field as keyof OfflineDocument] !== undefined) {
      merged[field as keyof OfflineDocument] =
        local[field as keyof OfflineDocument];
    }
  }

  // Take higher version
  merged.version = Math.max(local.version, remote.version) + 1;
  merged.lastModified = Math.max(local.lastModified, remote.lastModified);

  return merged;
};

export default SyncEngine;
