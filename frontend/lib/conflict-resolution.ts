/**
 * Enhanced Conflict Resolution for Offline-First Data Layer
 * 
 * Provides multiple conflict resolution strategies:
 * - Last-Write-Wins (LWW) with vector clocks
 * - Operational Transformation (OT) for text
 * - CRDT-based automatic merging
 * - Application-level semantic merging
 * - Custom resolver functions
 * - Conflict-free replicated data types
 */

import { OfflineDatabase, OfflineDocument, OfflineChange } from './offline-db';
import { RxDBManager } from './rxdb-manager';
import { CRDTManager } from './crdt-integration';

export type ConflictType = 
  | 'version'           // Concurrent version updates
  | 'concurrent-edit'   // Same field edited by multiple users
  | 'delete-modify'     // One user deletes, another modifies
  | 'move'              // Concurrent move operations
  | 'schema'            // Schema evolution conflicts
  | 'semantic';         // Business logic conflicts

export type ResolutionStrategy = 
  | 'lww'               // Last-Write-Wins (timestamp-based)
  | 'lww-field'         // LWW per field
  | 'crdt'              // CRDT automatic merge
  | 'ot'                // Operational Transformation
  | 'semantic'          // Application-specific logic
  | 'manual'            // User intervention required
  | 'server-wins'       // Server authority
  | 'client-wins'       // Client authority
  | 'merge'             // Three-way merge
  | 'custom';           // Custom resolver function

export interface VectorClock {
  [nodeId: string]: number;
}

export interface ConflictContext {
  conflictId: string;
  type: ConflictType;
  documentId: string;
  collection: string;
  localVersion: number;
  remoteVersion: number;
  localVectorClock: VectorClock;
  remoteVectorClock: VectorClock;
  localData: any;
  remoteData: any;
  baseData?: any;          // For three-way merge
  fieldPath?: string;      // Specific field in conflict
  timestamp: number;
  metadata: Record<string, any>;
}

export interface ResolutionResult {
  resolved: boolean;
  strategy: ResolutionStrategy;
  resolvedData: any;
  newVersion: number;
  newVectorClock: VectorClock;
  conflictsResolved: string[];  // Field paths resolved
  requiresManualReview: boolean;
  auditInfo: {
    strategy: ResolutionStrategy;
    resolvedAt: number;
    resolvedBy: string;  // 'system' | 'user' | 'custom'
    details: Record<string, any>;
  };
}

export interface ConflictResolver {
  (context: ConflictContext): Promise<ResolutionResult>;
}

export interface ResolutionRule {
  id: string;
  name: string;
  description: string;
  appliesTo: {
    collections?: string[];
    conflictTypes?: ConflictType[];
    fieldPaths?: string[];
  };
  strategy: ResolutionStrategy;
  priority: number;  // Higher = more specific
  customResolver?: ConflictResolver;
  enabled: boolean;
}

export interface ConflictAuditEntry {
  id: string;
  conflictId: string;
  documentId: string;
  collection: string;
  type: ConflictType;
  strategy: ResolutionStrategy;
  status: 'detected' | 'resolved' | 'escalated' | 'ignored';
  localUser: string;
  remoteUser?: string;
  timestamp: number;
  resolvedAt?: number;
  resolvedBy?: string;
  resolution?: ResolutionResult;
  metadata: Record<string, any>;
}

export class ConflictResolutionEngine {
  private rxdb: RxDBManager;
  private db: OfflineDatabase;
  private crdtManager: CRDTManager;
  
  private rules: Map<string, ResolutionRule> = new Map();
  private customResolvers: Map<string, ConflictResolver> = new Map();
  private conflictCache: Map<string, ConflictContext> = new Map();
  private auditLog: ConflictAuditEntry[] = [];
  
  private defaultStrategy: ResolutionStrategy = 'crdt';
  private escalationThreshold = 3;  // Max auto-retries before escalation

  constructor(
    rxdb: RxDBManager,
    db: OfflineDatabase,
    crdtManager: CRDTManager
  ) {
    this.rxdb = rxdb;
    this.db = db;
    this.crdtManager = crdtManager;
    
    this.initializeDefaultRules();
  }

  private initializeDefaultRules(): void {
    // CRDT types - automatic merge
    this.addRule({
      id: 'crdt-auto',
      name: 'CRDT Automatic Merge',
      description: 'Automatic conflict resolution for CRDT data types',
      appliesTo: { 
        collections: ['documents'], 
        conflictTypes: ['concurrent-edit', 'version'] 
      },
      strategy: 'crdt',
      priority: 100,
      enabled: true,
    });

    // Text content - OT for rich text
    this.addRule({
      id: 'text-ot',
      name: 'Operational Transformation for Text',
      description: 'Operational transformation for concurrent text edits',
      appliesTo: { 
        collections: ['documents'],
        fieldPaths: ['content'],
        conflictTypes: ['concurrent-edit']
      },
      strategy: 'ot',
      priority: 90,
      enabled: true,
    });

    // Metadata - LWW per field
    this.addRule({
      id: 'metadata-lww-field',
      name: 'LWW per Field for Metadata',
      description: 'Last-write-wins per field for metadata',
      appliesTo: { 
        collections: ['documents'],
        fieldPaths: ['metadata', 'tags', 'title'],
        conflictTypes: ['concurrent-edit', 'version']
      },
      strategy: 'lww-field',
      priority: 80,
      enabled: true,
    });

    // Delete-modify - Server wins for deletes
    this.addRule({
      id: 'delete-modify-server',
      name: 'Server Wins for Delete-Modify',
      description: 'Server authority for delete vs modify conflicts',
      appliesTo: { conflictTypes: ['delete-modify'] },
      strategy: 'server-wins',
      priority: 95,
      enabled: true,
    });

    // System fields - Server wins
    this.addRule({
      id: 'system-fields-server',
      name: 'Server Wins for System Fields',
      description: 'Server authority for version, createdAt, etc.',
      appliesTo: { 
        fieldPaths: ['version', 'createdAt', 'synced', '_rev', '_id']
      },
      strategy: 'server-wins',
      priority: 100,
      enabled: true,
    });

    // User content - Client wins
    this.addRule({
      id: 'user-content-client',
      name: 'Client Wins for User Content',
      description: 'Local user edits take precedence for content',
      appliesTo: { 
        fieldPaths: ['content', 'yjsState'],
        conflictTypes: ['concurrent-edit']
      },
      strategy: 'client-wins',
      priority: 85,
      enabled: true,
    );
  }

  addRule(rule: Omit<ResolutionRule, 'id'> & { id?: string }): ResolutionRule {
    const newRule: ResolutionRule = {
      id: rule.id || crypto.randomUUID(),
      name: rule.name,
      description: rule.description,
      appliesTo: rule.appliesTo,
      strategy: rule.strategy,
      priority: rule.priority,
      customResolver: rule.customResolver,
      enabled: rule.enabled ?? true,
    };
    this.rules.set(newRule.id, newRule);
    return newRule;
  }

  removeRule(ruleId: string): boolean {
    return this.rules.delete(ruleId);
  }

  getRules(): ResolutionRule[] {
    return Array.from(this.rules.values()).sort((a, b) => b.priority - a.priority);
  }

  registerCustomResolver(name: string, resolver: ConflictResolver): void {
    this.customResolvers.set(name, resolver);
  }

  // ==================== Conflict Detection ====================

  /**
   * Detect conflicts between local and remote versions
   */
  async detectConflicts(
    documentId: string,
    localData: any,
    remoteData: any,
    baseData?: any
  ): Promise<ConflictContext[]> {
    const conflicts: ConflictContext[] = [];
    const collection = this.getCollectionForDocument(documentId);

    // Check version conflict
    if (localData.version !== remoteData.version) {
      conflicts.push(this.createConflictContext({
        type: 'version',
        documentId,
        collection,
        localData,
        remoteData,
        baseData,
        localVersion: localData.version,
        remoteVersion: remoteData.version,
      }));
    }

    // Check field-level conflicts
    const fieldConflicts = this.detectFieldConflicts(localData, remoteData, baseData);
    for (const fieldConflict of fieldConflicts) {
      conflicts.push(this.createConflictContext({
        ...fieldConflict,
        documentId,
        collection,
        localVersion: localData.version,
        remoteVersion: remoteData.version,
      }));
    }

    // Check delete-modify
    if ((localData._deleted && !remoteData._deleted) || 
        (!localData._deleted && remoteData._deleted)) {
      conflicts.push(this.createConflictContext({
        type: 'delete-modify',
        documentId,
        collection,
        localData,
        remoteData,
        baseData,
        localVersion: localData.version,
        remoteVersion: remoteData.version,
      }));
    }

    return conflicts;
  }

  private detectFieldConflicts(localData: any, remoteData: any, baseData?: any): ConflictContext[] {
    const conflicts: ConflictContext[] = [];
    const allKeys = new Set([...Object.keys(localData), ...Object.keys(remoteData)]);

    for (const key of allKeys) {
      if (key.startsWith('_') || key === 'id' || key === 'version') continue;
      
      const localVal = localData[key];
      const remoteVal = remoteData[key];
      const baseVal = baseData?.[key];

      // Skip if both same
      if (this.deepEqual(localVal, remoteVal)) continue;
      
      // Skip if one matches base (no conflict)
      if (baseVal !== undefined) {
        if (this.deepEqual(localVal, baseVal) || this.deepEqual(remoteVal, baseVal)) {
          continue;
        }
      }

      // Detect conflict type
      let type: ConflictType = 'concurrent-edit';
      if (localVal === undefined && remoteVal !== undefined) type = 'concurrent-edit';
      else if (localVal !== undefined && remoteVal === undefined) type = 'concurrent-edit';
      else if (Array.isArray(localVal) && Array.isArray(remoteVal)) type = 'concurrent-edit';
      else if (typeof localVal === 'object' && typeof remoteVal === 'object') type = 'concurrent-edit';

      conflicts.push(this.createConflictContext({
        type,
        fieldPath: key,
        localData: localVal,
        remoteData: remoteVal,
        baseData: baseVal,
      }));
    }

    return conflicts;
  }

  private createConflictContext(partial: Partial<ConflictContext> & { 
    type: ConflictType; 
    documentId: string; 
    collection: string;
    localVersion: number;
    remoteVersion: number;
  }): ConflictContext {
    const conflictId = `${partial.documentId}-${partial.type}-${partial.fieldPath || 'root'}-${Date.now()}`;
    
    return {
      conflictId,
      type: partial.type,
      documentId: partial.documentId,
      collection: partial.collection,
      localVersion: partial.localVersion,
      remoteVersion: partial.remoteVersion,
      localVectorClock: this.extractVectorClock(partial.localData),
      remoteVectorClock: this.extractVectorClock(partial.remoteData),
      localData: partial.localData,
      remoteData: partial.remoteData,
      baseData: partial.baseData,
      fieldPath: partial.fieldPath,
      timestamp: Date.now(),
      metadata: {},
    };
  }

  private extractVectorClock(data: any): VectorClock {
    if (!data) return {};
    const clock: VectorClock = {};
    if (data._vectorClock) return data._vectorClock;
    if (data.vectorClock) return data.vectorClock;
    // Extract from version if available
    if (data.version) clock['local'] = data.version;
    return clock;
  }

  private deepEqual(a: any, b: any): boolean {
    if (a === b) return true;
    if (a === null || b === null) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    
    return keysA.every(key => this.deepEqual(a[key], b[key]));
  }

  private getCollectionForDocument(documentId: string): string {
    // In production, this would look up the collection
    return 'documents';
  }

  // ==================== Conflict Resolution ====================

  /**
   * Resolve conflicts using applicable rules
   */
  async resolveConflicts(
    conflicts: ConflictContext[],
    userId: string
  ): Promise<ResolutionResult[]> {
    const results: ResolutionResult[] = [];

    for (const conflict of conflicts) {
      // Find applicable rule
      const rule = this.findApplicableRule(conflict);
      if (!rule) {
        // No rule found - escalate
        results.push(await this.escalateConflict(conflict, userId));
        continue;
      }

      // Apply resolution strategy
      let result: ResolutionResult;
      
      switch (rule.strategy) {
        case 'crdt':
          result = await this.resolveWithCRDT(conflict);
          break;
        case 'ot':
          result = await this.resolveWithOT(conflict);
          break;
        case 'lww':
          result = await this.resolveLWW(conflict);
          break;
        case 'lww-field':
          result = await this.resolveLWWField(conflict);
          break;
        case 'server-wins':
          result = await this.resolveServerWins(conflict);
          break;
        case 'client-wins':
          result = await this.resolveClientWins(conflict);
          break;
        case 'merge':
          result = await this.resolveThreeWayMerge(conflict);
          break;
        case 'semantic':
          result = await this.resolveSemantic(conflict, rule);
          break;
        case 'custom':
          result = await this.resolveCustom(conflict, rule);
          break;
        case 'manual':
        default:
          result = await this.escalateConflict(conflict, userId);
          break;
      }

      // Audit log
      this.auditConflict(conflict, rule.strategy, result, userId);
      results.push(result);
    }

    return results;
  }

  private findApplicableRule(conflict: ConflictContext): ResolutionRule | null {
    let bestRule: ResolutionRule | null = null;
    let bestPriority = -1;

    for (const rule of this.rules.values()) {
      if (!rule.enabled) continue;

      const applies = this.ruleApplies(rule, conflict);
      if (applies && rule.priority > bestPriority) {
        bestRule = rule;
        bestPriority = rule.priority;
      }
    }

    return bestRule;
  }

  private ruleApplies(rule: ResolutionRule, conflict: ConflictContext): boolean {
    const { appliesTo } = rule;

    // Check collection
    if (appliesTo.collections && !appliesTo.collections.includes(conflict.collection)) {
      return false;
    }

    // Check conflict type
    if (appliesTo.conflictTypes && !appliesTo.conflictTypes.includes(conflict.type)) {
      return false;
    }

    // Check field path
    if (appliesTo.fieldPaths && conflict.fieldPath) {
      const matches = appliesTo.fieldPaths.some(fp => 
        conflict.fieldPath!.startsWith(fp) || fp === '*'
      );
      if (!matches) return false;
    }

    return true;
  }

  // ==================== Resolution Strategies ====================

  private async resolveWithCRDT(conflict: ConflictContext): Promise<ResolutionResult> {
    // CRDT automatically merges - use remote state as base and apply local
    // In practice, Yjs handles this automatically
    
    const ydoc = this.crdtManager.getDocument(conflict.documentId);
    if (ydoc) {
      // CRDT already merged - return merged state
      const resolvedData = this.getCRDTMergedState(ydoc);
      
      return {
        resolved: true,
        strategy: 'crdt',
        resolvedData,
        newVersion: conflict.remoteVersion + 1,
        newVectorClock: this.incrementVectorClock(conflict.remoteVectorClock, 'local'),
        conflictsResolved: conflict.fieldPath ? [conflict.fieldPath] : ['all'],
        requiresManualReview: false,
        auditInfo: {
          strategy: 'crdt',
          resolvedAt: Date.now(),
          resolvedBy: 'system',
          details: { method: 'crdt-auto-merge' },
        },
      };
    }

    // Fallback to LWW
    return this.resolveLWW(conflict);
  }

  private async resolveWithOT(conflict: ConflictContext): Promise<ResolutionResult> {
    // Operational Transformation for text
    // In production, this would use a proper OT library
    
    if (conflict.fieldPath === 'content' || conflict.fieldPath === 'yjsState') {
      // Get Yjs document and let it handle OT
      const ydoc = this.crdtManager.getDocument(conflict.documentId);
      if (ydoc) {
        const resolvedData = this.getCRDTMergedState(ydoc);
        return {
          resolved: true,
          strategy: 'ot',
          resolvedData,
          newVersion: conflict.remoteVersion + 1,
          newVectorClock: this.incrementVectorClock(conflict.remoteVectorClock, 'local'),
          conflictsResolved: [conflict.fieldPath || 'content'],
          requiresManualReview: false,
          auditInfo: {
            strategy: 'ot',
            resolvedAt: Date.now(),
            resolvedBy: 'system',
            details: { method: 'yjs-operational-transformation' },
          },
        };
      }
    }

    // Fallback to field-level LWW
    return this.resolveLWWField(conflict);
  }

  private async resolveLWW(conflict: ConflictContext): Promise<ResolutionResult> {
    // Last-Write-Wins based on timestamp
    const localTime = conflict.localData?.lastModified || 0;
    const remoteTime = conflict.remoteData?.lastModified || 0;
    
    const winner = localTime > remoteTime ? 'local' : 'remote';
    const resolvedData = winner === 'local' ? conflict.localData : conflict.remoteData;

    return {
      resolved: true,
      strategy: 'lww',
      resolvedData: { ...resolvedData, version: Math.max(conflict.localVersion, conflict.remoteVersion) + 1 },
      newVersion: Math.max(conflict.localVersion, conflict.remoteVersion) + 1,
      newVectorClock: this.incrementVectorClock(
        winner === 'local' ? conflict.localVectorClock : conflict.remoteVectorClock, 
        'local'
      ),
      conflictsResolved: ['all'],
      requiresManualReview: false,
      auditInfo: {
        strategy: 'lww',
        resolvedAt: Date.now(),
        resolvedBy: 'system',
        details: { winner, localTime, remoteTime },
      },
    };
  }

  private async resolveLWWField(conflict: ConflictContext): Promise<ResolutionResult> {
    // LWW per field
    const resolvedData = { ...conflict.remoteData };
    const resolvedFields: string[] = [];

    const allKeys = new Set([
      ...Object.keys(conflict.localData || {}),
      ...Object.keys(conflict.remoteData || {})
    ]);

    for (const key of allKeys) {
      if (key.startsWith('_') || key === 'version') continue;
      
      const localVal = conflict.localData?.[key];
      const remoteVal = conflict.remoteData?.[key];
      const localTime = conflict.localData?._fieldTimestamps?.[key] || 0;
      const remoteTime = conflict.remoteData?._fieldTimestamps?.[key] || 0;

      if (localVal !== undefined && remoteVal !== undefined && !this.deepEqual(localVal, remoteVal)) {
        // Conflict on this field - use LWW
        if (localTime > remoteTime) {
          resolvedData[key] = localVal;
        } else {
          resolvedData[key] = remoteVal;
        }
        resolvedFields.push(key);
      } else if (localVal !== undefined) {
        resolvedData[key] = localVal;
      } else if (remoteVal !== undefined) {
        resolvedData[key] = remoteVal;
      }
    }

    return {
      resolved: true,
      strategy: 'lww-field',
      resolvedData: { ...resolvedData, version: Math.max(conflict.localVersion, conflict.remoteVersion) + 1 },
      newVersion: Math.max(conflict.localVersion, conflict.remoteVersion) + 1,
      newVectorClock: this.incrementVectorClock(conflict.remoteVectorClock, 'local'),
      conflictsResolved: resolvedFields,
      requiresManualReview: false,
      auditInfo: {
        strategy: 'lww-field',
        resolvedAt: Date.now(),
        resolvedBy: 'system',
        details: { resolvedFields },
      },
    };
  }

  private async resolveServerWins(conflict: ConflictContext): Promise<ResolutionResult> {
    return {
      resolved: true,
      strategy: 'server-wins',
      resolvedData: { ...conflict.remoteData, version: conflict.remoteVersion + 1 },
      newVersion: conflict.remoteVersion + 1,
      newVectorClock: conflict.remoteVectorClock,
      conflictsResolved: conflict.fieldPath ? [conflict.fieldPath] : ['all'],
      requiresManualReview: false,
      auditInfo: {
        strategy: 'server-wins',
        resolvedAt: Date.now(),
        resolvedBy: 'system',
        details: { reason: 'server-authority' },
      },
    };
  }

  private async resolveClientWins(conflict: ConflictContext): Promise<ResolutionResult> {
    return {
      resolved: true,
      strategy: 'client-wins',
      resolvedData: { ...conflict.localData, version: conflict.localVersion + 1 },
      newVersion: conflict.localVersion + 1,
      newVectorClock: this.incrementVectorClock(conflict.localVectorClock, 'local'),
      conflictsResolved: conflict.fieldPath ? [conflict.fieldPath] : ['all'],
      requiresManualReview: false,
      auditInfo: {
        strategy: 'client-wins',
        resolvedAt: Date.now(),
        resolvedBy: 'system',
        details: { reason: 'client-authority' },
      },
    };
  }

  private async resolveThreeWayMerge(conflict: ConflictContext): Promise<ResolutionResult> {
    if (!conflict.baseData) {
      // No base - fallback to LWW
      return this.resolveLWW(conflict);
    }

    // Three-way merge
    const merged = this.threeWayMerge(
      conflict.baseData,
      conflict.localData,
      conflict.remoteData
    );

    return {
      resolved: true,
      strategy: 'merge',
      resolvedData: { ...merged, version: Math.max(conflict.localVersion, conflict.remoteVersion) + 1 },
      newVersion: Math.max(conflict.localVersion, conflict.remoteVersion) + 1,
      newVectorClock: this.incrementVectorClock(conflict.remoteVectorClock, 'local'),
      conflictsResolved: ['all'],
      requiresManualReview: false,
      auditInfo: {
        strategy: 'merge',
        resolvedAt: Date.now(),
        resolvedBy: 'system',
        details: { method: 'three-way-merge' },
      },
    };
  }

  private threeWayMerge(base: any, local: any, remote: any): any {
    const result = { ...remote };
    const allKeys = new Set([...Object.keys(local), ...Object.keys(remote), ...Object.keys(base)]);

    for (const key of allKeys) {
      if (key.startsWith('_') || key === 'version') continue;

      const baseVal = base[key];
      const localVal = local[key];
      const remoteVal = remote[key];

      // If local and remote agree, use that
      if (this.deepEqual(localVal, remoteVal)) {
        result[key] = localVal;
      }
      // If local matches base, remote changed - use remote
      else if (this.deepEqual(localVal, baseVal)) {
        result[key] = remoteVal;
      }
      // If remote matches base, local changed - use local
      else if (this.deepEqual(remoteVal, baseVal)) {
        result[key] = localVal;
      }
      // Both changed - conflict
      else {
        // Use LWW for this field
        const localTime = local._fieldTimestamps?.[key] || 0;
        const remoteTime = remote._fieldTimestamps?.[key] || 0;
        result[key] = localTime > remoteTime ? localVal : remoteVal;
      }
    }

    return result;
  }

  private async resolveSemantic(conflict: ConflictContext, rule: any): Promise<ResolutionResult> {
    // Application-specific semantic resolution
    // Would call custom resolver if provided
    if (rule.customResolver) {
      return rule.customResolver(conflict);
    }

    // Default semantic: merge arrays, LWW for objects
    return this.resolveThreeWayMerge(conflict);
  }

  private async resolveCustom(conflict: ConflictContext, rule: any): Promise<ResolutionResult> {
    if (rule.customResolver) {
      return rule.customResolver(conflict);
    }
    return this.resolveLWW(conflict);
  }

  private async escalateConflict(conflict: ConflictContext, userId: string): Promise<ResolutionResult> {
    // Store for manual resolution
    await this.storeForManualResolution(conflict, userId);

    return {
      resolved: false,
      strategy: 'manual',
      resolvedData: conflict.remoteData,
      newVersion: conflict.remoteVersion,
      newVectorClock: conflict.remoteVectorClock,
      conflictsResolved: [],
      requiresManualReview: true,
      auditInfo: {
        strategy: 'manual',
        resolvedAt: Date.now(),
        resolvedBy: 'user',
        details: { escalated: true, assignedTo: userId },
      },
    };
  }

  private async storeForManualResolution(conflict: ConflictContext, userId: string): Promise<void> {
    // Store in conflict resolution queue
    await this.rxdb.getCollection('conflicts')?.insert({
      id: conflict.conflictId,
      ...conflict,
      assignedTo: userId,
      status: 'pending',
      createdAt: Date.now(),
    });
  }

  // ==================== Helpers ====================

  private getCRDTMergedState(ydoc: any): any {
    // Extract merged state from Yjs document
    // This would depend on the CRDT type
    return {
      content: ydoc.getText('content')?.toString() || '',
      // Add other fields
    };
  }

  private deepEqual(a: any, b: any): boolean {
    if (a === b) return true;
    if (a === null || b === null) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    
    return keysA.every(key => this.deepEqual(a[key], b[key]));
  }

  private incrementVectorClock(clock: VectorClock, nodeId: string): VectorClock {
    return {
      ...clock,
      [nodeId]: (clock[nodeId] || 0) + 1,
    };
  }

  private async auditConflict(
    conflict: ConflictContext,
    strategy: ResolutionStrategy,
    result: ResolutionResult,
    userId: string
  ): Promise<void> {
    const entry: ConflictAuditEntry = {
      id: crypto.randomUUID(),
      conflictId: conflict.conflictId,
      documentId: conflict.documentId,
      collection: conflict.collection,
      type: conflict.type,
      strategy,
      status: result.resolved ? 'resolved' : 'escalated',
      localUser: userId,
      timestamp: Date.now(),
      resolvedAt: result.resolved ? Date.now() : undefined,
      resolvedBy: result.auditInfo.resolvedBy,
      resolution: result,
      metadata: {
        fieldPath: conflict.fieldPath,
        localVersion: conflict.localVersion,
        remoteVersion: conflict.remoteVersion,
      },
    };

    this.auditLog.push(entry);
    
    // Persist to database
    await this.rxdb.getCollection('conflict_audit')?.insert(entry);
  }

  // ==================== Manual Resolution ====================

  async resolveManually(
    conflictId: string,
    userId: string,
    resolution: 'local' | 'remote' | 'merge',
    customData?: any
  ): Promise<ResolutionResult> {
    const conflict = this.conflictCache.get(conflictId);
    if (!conflict) throw new Error('Conflict not found');

    let result: ResolutionResult;
    switch (resolution) {
      case 'local':
        result = await this.resolveClientWins(conflict);
        break;
      case 'remote':
        result = await this.resolveServerWins(conflict);
        break;
      case 'merge':
        result = await this.resolveThreeWayMerge(conflict);
        if (customData) {
          result.resolvedData = { ...result.resolvedData, ...customData };
        }
        break;
    }

    result.auditInfo.resolvedBy = 'user';
    result.auditInfo.details.manualResolution = resolution;

    this.auditConflict(conflict, 'manual', result, userId);
    this.conflictCache.delete(conflictId);

    return result;
  }

  getPendingConflicts(userId?: string): ConflictContext[] {
    let conflicts = Array.from(this.conflictCache.values());
    if (userId) {
      // Filter by assigned user
      conflicts = conflicts.filter(c => c.metadata.assignedTo === userId);
    }
    return conflicts;
  }

  getAuditLog(conflictId?: string, limit = 100): ConflictAuditEntry[] {
    let log = this.auditLog;
    if (conflictId) {
      log = log.filter(e => e.conflictId === conflictId);
    }
    return log.slice(-limit).reverse();
  }
}

// ==================== React Hook ====================

import { useState, useCallback } from 'react';

export function useConflictResolution(
  engine: ConflictResolutionEngine
) {
  const [pendingConflicts, setPendingConflicts] = useState<any[]>([]);
  const [auditLog, setAuditLog] = useState<any[]>([]);
  const [isResolving, setIsResolving] = useState(false);

  const refreshConflicts = useCallback(async (userId?: string) => {
    const conflicts = engine.getPendingConflicts(userId);
    setPendingConflicts(conflicts);
  }, [engine]);

  const resolveConflict = useCallback(async (
    conflictId: string,
    userId: string,
    resolution: 'local' | 'remote' | 'merge',
    customData?: any
  ) => {
    setIsResolving(true);
    try {
      const result = await engine.resolveManually(conflictId, userId, resolution, customData);
      setPendingConflicts(prev => prev.filter(c => c.conflictId !== conflictId));
      return result;
    } finally {
      setIsResolving(false);
    }
  }, [engine]);

  const getAuditLog = useCallback(async (conflictId?: string) => {
    const log = engine.getAuditLog(conflictId);
    setAuditLog(log);
    return log;
  }, [engine]);

  const addRule = useCallback((rule: any) => {
    engine.addRule(rule);
  }, [engine]);

  const getRules = useCallback(() => {
    return engine.getRules();
  }, [engine]);

  return {
    pendingConflicts,
    auditLog,
    isResolving,
    refreshConflicts,
    resolveConflict,
    getAuditLog,
    addRule,
    getRules,
  };
}

// ==================== Default Instance ====================

let _conflictEngine: ConflictResolutionEngine | null = null;

export function getConflictResolutionEngine(
  rxdb: RxDBManager,
  db: OfflineDatabase,
  crdtManager: CRDTManager
): ConflictResolutionEngine {
  if (!_conflictEngine) {
    _conflictEngine = new ConflictResolutionEngine(rxdb, db, crdtManager);
  }
  return _conflictEngine;
}

export default ConflictResolutionEngine;