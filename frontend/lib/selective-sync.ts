/**
 * Selective Sync Manager
 * Allows users to choose what data to sync offline
 * Supports filtering by collections, tags, date ranges, size limits
 */

import {
  SyncEngine,
  SelectiveSyncFilter,
  SyncConfig,
  SyncResult,
} from "./sync-engine";
import { OfflineDatabase, OfflineDocument } from "./offline-db";
import { RxDBManager } from "./rxdb-manager";

export interface SelectiveSyncOptions {
  // What to sync
  collections?: string[]; // Specific collections to sync
  tags?: string[]; // Tags to include
  dateRange?: { start: number; end: number }; // Date range filter
  userIds?: string[]; // Specific users' data
  organizationIds?: string[]; // Specific organizations
  maxSize?: number; // Max total size in bytes
  maxItems?: number; // Max number of items

  // Sync behavior
  priority?: "high" | "normal" | "low";
  includeAttachments?: boolean;
  onlyUnsynced?: boolean; // Only sync unsynced items

  // Scheduling
  syncOnConnect?: boolean; // Auto-sync when online
  syncInterval?: number; // Periodic sync interval (ms)
  syncOnChanges?: boolean; // Sync immediately on local changes

  // Storage management
  maxOfflineSize?: number; // Max offline storage (bytes)
  evictionPolicy?: "lru" | "lfu" | "fifo" | "priority"; // Eviction policy
  warnAtPercent?: number; // Warn at % of max size (default: 80%)
}

export interface SyncProfile {
  id: string;
  name: string;
  description: string;
  options: SelectiveSyncOptions;
  createdAt: number;
  updatedAt: number;
  isDefault: boolean;
}

export interface SyncStatus {
  profileId: string;
  isOnline: boolean;
  isSyncing: boolean;
  lastSync: number | null;
  nextScheduledSync: number | null;
  syncedItems: number;
  pendingItems: number;
  failedItems: number;
  totalSize: number;
  availableSpace: number;
  error: string | null;
  progress: {
    current: number;
    total: number;
    currentItem?: string;
  };
}

export interface SyncConflict {
  id: string;
  localItem: any;
  remoteItem: any;
  type: "version" | "delete" | "field";
  field?: string;
  detectedAt: number;
  resolved: boolean;
  resolution?: "local" | "remote" | "merge" | "custom";
  resolvedAt?: number;
}

export interface SyncAuditEntry {
  id: string;
  profileId: string;
  action: "start" | "complete" | "error" | "conflict" | "pause" | "resume";
  timestamp: number;
  details: {
    itemsSynced?: number;
    itemsFailed?: number;
    bytesTransferred?: number;
    duration?: number;
    error?: string;
    conflictId?: string;
  };
}

export class SelectiveSyncManager {
  private rxdb: RxDBManager;
  private syncEngine: any; // SyncEngine from sync-engine.ts
  private db: any; // OfflineDatabase

  private profiles: Map<string, SyncProfile> = new Map();
  private activeProfileId: string | null = null;
  private statusSubject = new BehaviorSubject<SyncStatus | null>(null);
  private auditLog: SyncAuditEntry[] = [];
  private conflicts: Map<string, SyncConflict> = new Map();

  private syncIntervalId: ReturnType<typeof setInterval> | null = null;
  private storageCheckIntervalId: ReturnType<typeof setInterval> | null = null;

  private isInitialized = false;
  private abortController: AbortController | null = null;

  constructor(rxdb: RxDBManager, syncEngine: any, db: any) {
    this.rxdb = rxdb;
    this.syncEngine = syncEngine;
    this.db = db;
  }

  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    // Load profiles from storage
    await this.loadProfiles();

    // Create default profile if none exists
    if (this.profiles.size === 0) {
      await this.createDefaultProfile();
    }

    // Set active profile
    const defaultProfile = Array.from(this.profiles.values()).find(
      (p) => p.isDefault,
    );
    if (defaultProfile) {
      await this.setActiveProfile(defaultProfile.id);
    }

    // Start monitoring
    this.startMonitoring();

    this.isInitialized = true;
    console.log("[SelectiveSync] Initialized");
  }

  private async loadProfiles(): Promise<void> {
    try {
      const stored = await this.rxdb.getSetting("syncProfiles");
      if (stored) {
        const profiles = JSON.parse(stored);
        for (const profile of profiles) {
          this.profiles.set(profile.id, profile);
        }
      }
    } catch (e) {
      console.warn("[SelectiveSync] Failed to load profiles:", e);
    }
  }

  private async saveProfiles(): Promise<void> {
    const profiles = Array.from(this.profiles.values());
    await this.rxdb.setSetting("syncProfiles", JSON.stringify(profiles));
  }

  private async createDefaultProfile(): Promise<void> {
    const defaultProfile: SyncProfile = {
      id: "default",
      name: "Default",
      description: "Sync all documents",
      options: {
        collections: [],
        tags: [],
        userIds: [],
        organizationIds: [],
        maxSize: 500 * 1024 * 1024, // 500MB
        maxItems: 10000,
        priority: "normal",
        includeAttachments: true,
        onlyUnsynced: true,
        syncOnConnect: true,
        syncInterval: 30000,
        syncOnChanges: true,
        maxOfflineSize: 1024 * 1024 * 1024, // 1GB
        evictionPolicy: "lru",
        warnAtPercent: 80,
      },
      createdAt: Date.now(),
      updatedAt: Date.now(),
      isDefault: true,
    };

    this.profiles.set(defaultProfile.id, defaultProfile);
    await this.saveProfiles();
  }

  // ==================== Profile Management ====================

  async createProfile(
    profile: Omit<SyncProfile, "id" | "createdAt" | "updatedAt">,
  ): Promise<SyncProfile> {
    const newProfile: SyncProfile = {
      ...profile,
      id: crypto.randomUUID(),
      createdAt: Date.now(),
      updatedAt: Date.now(),
      isDefault: false,
    };

    this.profiles.set(newProfile.id, newProfile);
    await this.saveProfiles();
    return newProfile;
  }

  async updateProfile(
    profileId: string,
    updates: Partial<SyncProfile>,
  ): Promise<SyncProfile | null> {
    const profile = this.profiles.get(profileId);
    if (!profile) return null;

    const updated = {
      ...profile,
      ...updates,
      updatedAt: Date.now(),
    };

    this.profiles.set(profileId, updated);
    await this.saveProfiles();

    // If active profile updated, reapply
    if (this.activeProfileId === profileId) {
      await this.applyProfile(updated);
    }

    return updated;
  }

  async deleteProfile(profileId: string): Promise<boolean> {
    const profile = this.profiles.get(profileId);
    if (!profile) return false;
    if (profile.isDefault) return false; // Can't delete default

    this.profiles.delete(profileId);
    await this.saveProfiles();

    if (this.activeProfileId === profileId) {
      const defaultProfile = Array.from(this.profiles.values()).find(
        (p) => p.isDefault,
      );
      if (defaultProfile) {
        await this.setActiveProfile(defaultProfile.id);
      }
    }

    return true;
  }

  getProfiles(): SyncProfile[] {
    return Array.from(this.profiles.values());
  }

  getProfile(profileId: string): SyncProfile | null {
    return this.profiles.get(profileId) || null;
  }

  async setActiveProfile(profileId: string): Promise<void> {
    const profile = this.profiles.get(profileId);
    if (!profile) throw new Error(`Profile not found: ${profileId}`);

    this.activeProfileId = profileId;
    await this.applyProfile(profile);
    await this.rxdb.setSetting("activeSyncProfile", profileId);
  }

  getActiveProfile(): SyncProfile | null {
    return this.activeProfileId
      ? this.profiles.get(this.activeProfileId) || null
      : null;
  }

  private async applyProfile(profile: SyncProfile): Promise<void> {
    // Update sync engine with new filter
    this.syncEngine.setSelectiveFilter(profile.options);

    // Update sync interval
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
    }

    if (profile.options.syncInterval && profile.options.syncInterval > 0) {
      this.syncIntervalId = setInterval(() => {
        if (navigator.onLine) {
          this.syncNow();
        }
      }, profile.options.syncInterval);
    }

    // Log audit
    this.addAuditEntry(profile.id, "profile_changed", {
      profileName: profile.name,
    });
  }

  // ==================== Sync Operations ====================

  async syncNow(): Promise<SyncResult> {
    if (!this.activeProfileId) {
      return { success: false, synced: 0, failed: 0, errors: [], duration: 0 };
    }

    const profile = this.profiles.get(this.activeProfileId);
    if (!profile) throw new Error("No active profile");

    this.updateStatus({ isSyncing: true, progress: { current: 0, total: 0 } });
    this.addAuditEntry(this.activeProfileId!, "start", {});

    const startTime = Date.now();
    let synced = 0;
    let failed = 0;
    const errors: Array<{ itemId: string; error: string }> = [];

    try {
      // Get items to sync based on filter
      const items = await this.getItemsToSync(profile.options);
      this.updateStatus({ progress: { current: 0, total: items.length } });

      // Check storage space
      const spaceCheck = await this.checkStorageSpace(profile.options);
      if (!spaceCheck.hasSpace) {
        await this.evictItems(
          profile.options.evictionPolicy || "lru",
          spaceCheck.neededSpace,
        );
      }

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        this.updateStatus({
          progress: {
            current: i + 1,
            total: items.length,
            currentItem: item.documentId || item.id,
          },
        });

        try {
          await this.syncItem(item);
          synced++;
        } catch (error) {
          console.error(`Sync failed for ${item.id}:`, error);
          failed++;
          errors.push({
            itemId: item.id,
            error: error instanceof Error ? error.message : "Unknown",
          });

          // Check for conflicts
          if (this.isConflictError(error)) {
            await this.handleConflict(item, error);
          }
        }
      }

      // Update last sync time
      await this.rxdb.setSetting("lastSyncTime", Date.now());

      const result = {
        success: failed === 0,
        synced,
        failed,
        errors,
        duration: Date.now() - startTime,
      };

      this.addAuditEntry(this.activeProfileId!, "complete", {
        itemsSynced: synced,
        itemsFailed: failed,
        duration: result.duration,
      });

      this.updateStatus({
        isSyncing: false,
        lastSync: Date.now(),
        syncedItems: synced,
        failedItems: failed,
        error: failed > 0 ? `${failed} items failed` : null,
      });

      return result;
    } catch (error) {
      const err = error instanceof Error ? error : new Error("Sync failed");
      this.addAuditEntry(this.activeProfileId!, "error", {
        error: err.message,
      });
      this.updateStatus({ isSyncing: false, error: err.message });
      return {
        success: false,
        synced: 0,
        failed: 0,
        errors: [{ itemId: "", error: err.message }],
        duration: Date.now() - startTime,
      };
    }
  }

  private async getItemsToSync(options: SelectiveSyncOptions): Promise<any[]> {
    // This would query RxDB with the selective filter
    // For now, return mock items
    return [];
  }

  private async syncItem(item: any): Promise<void> {
    // Sync individual item
    await new Promise((resolve) => setTimeout(resolve, 50));
  }

  private isConflictError(error: any): boolean {
    return (
      error.message?.includes("conflict") || error.message?.includes("version")
    );
  }

  private async handleConflict(item: any, error: any): Promise<void> {
    const conflict: SyncConflict = {
      id: crypto.randomUUID(),
      localItem: item,
      remoteItem: null, // Would fetch from server
      type: "version",
      detectedAt: Date.now(),
      resolved: false,
    };

    this.conflicts.set(conflict.id, conflict);
    this.addAuditEntry(this.activeProfileId || "", "conflict", {
      conflictId: conflict.id,
    });
  }

  async resolveConflict(
    conflictId: string,
    resolution: "local" | "remote" | "merge",
  ): Promise<void> {
    const conflict = this.conflicts.get(conflictId);
    if (!conflict) throw new Error("Conflict not found");

    conflict.resolved = true;
    conflict.resolution = resolution;
    conflict.resolvedAt = Date.now();

    // Apply resolution
    switch (resolution) {
      case "local":
        // Push local version
        break;
      case "remote":
        // Accept remote version
        break;
      case "merge":
        // Merge both
        break;
    }

    this.conflicts.delete(conflictId);
    this.addAuditEntry(this.activeProfileId || "", "conflict_resolved", {
      conflictId,
      resolution,
    });
  }

  getConflicts(): SyncConflict[] {
    return Array.from(this.conflicts.values());
  }

  // ==================== Storage Management ====================

  private async checkStorageSpace(options: SelectiveSyncOptions): Promise<{
    hasSpace: boolean;
    usedSpace: number;
    availableSpace: number;
    neededSpace: number;
  }> {
    // Estimate current usage
    const docs =
      (await this.rxdb.getCollection("documents")?.find().exec()) || [];
    const usedSpace = docs.reduce(
      (sum, doc) => sum + JSON.stringify(doc).length,
      0,
    );
    const maxSize = options.maxOfflineSize || 1024 * 1024 * 1024; // 1GB default
    const availableSpace = maxSize - usedSpace;

    // Estimate needed space (rough)
    const pendingItems = await this.getItemsToSync(options);
    const neededSpace = pendingItems.length * 10000; // Rough estimate

    return {
      hasSpace: availableSpace > neededSpace,
      usedSpace,
      availableSpace,
      neededSpace,
    };
  }

  private async evictItems(policy: string, neededSpace: number): Promise<void> {
    // Evict items based on policy until enough space
    console.log(
      `[SelectiveSync] Evicting items using ${policy} policy to free ${neededSpace} bytes`,
    );

    // Implementation would remove least recently used / least frequently used items
    // that are already synced and not pinned
  }

  async getStorageStats(): Promise<{
    used: number;
    available: number;
    total: number;
    itemCount: number;
    collections: Record<string, { count: number; size: number }>;
  }> {
    // Calculate storage stats across all collections
    return {
      used: 0,
      available: 0,
      total: 0,
      itemCount: 0,
      collections: {},
    };
  }

  // ==================== Audit Log ====================

  private addAuditEntry(
    profileId: string,
    action: SyncAuditEntry["action"],
    details: SyncAuditEntry["details"],
  ): void {
    const entry: SyncAuditEntry = {
      id: crypto.randomUUID(),
      profileId,
      action,
      timestamp: Date.now(),
      details,
    };

    this.auditLog.push(entry);

    // Keep only last 1000 entries
    if (this.auditLog.length > 1000) {
      this.auditLog = this.auditLog.slice(-1000);
    }
  }

  getAuditLog(profileId?: string, limit = 100): SyncAuditEntry[] {
    let log = this.auditLog;
    if (profileId) {
      log = log.filter((e) => e.profileId === profileId);
    }
    return log.slice(-limit).reverse();
  }

  // ==================== Status ====================

  private updateStatus(partial: Partial<SyncStatus>): void {
    const current = this.statusSubject.value || {
      profileId: this.activeProfileId || "",
      isOnline: navigator.onLine,
      isSyncing: false,
      lastSync: null,
      nextScheduledSync: null,
      syncedItems: 0,
      pendingItems: 0,
      failedItems: 0,
      totalSize: 0,
      availableSpace: 0,
      error: null,
      progress: { current: 0, total: 0 },
    };

    this.statusSubject.next({ ...current, ...partial });
  }

  getStatus$(): Observable<SyncStatus | null> {
    return this.statusSubject.asObservable();
  }

  getStatus(): SyncStatus | null {
    return this.statusSubject.value;
  }

  // ==================== Monitoring ====================

  private startMonitoring(): void {
    // Periodic storage check
    this.storageCheckIntervalId = setInterval(async () => {
      if (this.activeProfileId) {
        const profile = this.profiles.get(this.activeProfileId);
        if (profile) {
          await this.checkStorageSpace(profile.options);
        }
      }
    }, 60000); // Every minute

    // Online/offline handling
    window.addEventListener("online", () => this.handleOnline());
    window.addEventListener("offline", () => this.handleOffline());
  }

  private handleOnline(): void {
    this.updateStatus({ isOnline: true, error: null });

    const profile = this.activeProfileId
      ? this.profiles.get(this.activeProfileId)
      : null;
    if (profile?.options.syncOnConnect) {
      this.syncNow();
    }
  }

  private handleOffline(): void {
    this.updateStatus({ isOnline: false });
  }

  // ==================== Pause/Resume ====================

  pause(): void {
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
      this.syncIntervalId = null;
    }
    this.updateStatus({ isSyncing: false });
    this.addAuditEntry(this.activeProfileId || "", "pause", {});
  }

  resume(): void {
    if (this.activeProfileId) {
      const profile = this.profiles.get(this.activeProfileId);
      if (profile?.options.syncInterval) {
        this.syncIntervalId = setInterval(() => {
          if (navigator.onLine) this.syncNow();
        }, profile.options.syncInterval);
      }
      this.addAuditEntry(this.activeProfileId, "resume", {});
    }
  }

  // ==================== Cleanup ====================

  destroy(): void {
    if (this.syncIntervalId) clearInterval(this.syncIntervalId);
    if (this.storageCheckIntervalId) clearInterval(this.storageCheckIntervalId);
  }
}

// ==================== React Hook ====================

import { useState, useEffect, useCallback } from "react";
import { BehaviorSubject, Observable } from "rxjs";

export function useSelectiveSync(rxdb: RxDBManager, syncEngine: any, db: any) {
  const [manager] = useState(
    () => new SelectiveSyncManager(rxdb, syncEngine, db),
  );
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [profiles, setProfiles] = useState<SyncProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<SyncProfile | null>(null);

  useEffect(() => {
    manager.initialize().then(() => {
      setProfiles(manager.getProfiles());
      setActiveProfile(manager.getActiveProfile());
    });

    const statusSub = manager
      .getStatus$()
      .subscribe((s) => setStatus(s || null));

    return () => {
      statusSub.unsubscribe();
      manager.destroy();
    };
  }, [manager]);

  const createProfile = useCallback(
    async (profile: Omit<SyncProfile, "id" | "createdAt" | "updatedAt">) => {
      const created = await manager.createProfile(profile);
      setProfiles(manager.getProfiles());
      return created;
    },
    [manager],
  );

  const updateProfile = useCallback(
    async (id: string, updates: Partial<SyncProfile>) => {
      const updated = await manager.updateProfile(id, updates);
      if (updated) setProfiles(manager.getProfiles());
      return updated;
    },
    [manager],
  );

  const setActiveProfile = useCallback(
    async (id: string) => {
      await manager.setActiveProfile(id);
      setActiveProfile(manager.getActiveProfile());
    },
    [manager],
  );

  const syncNow = useCallback(async () => {
    return manager.syncNow();
  }, [manager]);

  const pauseSync = useCallback(() => {
    manager.pause();
  }, [manager]);

  const resumeSync = useCallback(() => {
    manager.resume();
  }, [manager]);

  return {
    status,
    profiles,
    activeProfile,
    createProfile,
    updateProfile,
    setActiveProfile,
    syncNow,
    pauseSync,
    resumeSync,
    conflicts: manager.getConflicts(),
    resolveConflict: manager.resolveConflict.bind(manager),
    auditLog: manager.getAuditLog.bind(manager),
    getStorageStats: manager.getStorageStats.bind(manager),
  };
}

// ==================== Default Instance ====================

let _selectiveSyncManager: SelectiveSyncManager | null = null;

export function getSelectiveSyncManager(
  rxdb: RxDBManager,
  syncEngine: any,
  db: any,
): SelectiveSyncManager {
  if (!_selectiveSyncManager) {
    _selectiveSyncManager = new SelectiveSyncManager(rxdb, syncEngine, db);
  }
  return _selectiveSyncManager;
}

import { BehaviorSubject } from "rxjs";
