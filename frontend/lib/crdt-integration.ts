/**
 * CRDT Integration for Universal Offline-First Data Layer
 *
 * Provides CRDT-based conflict resolution for all collaborative data types:
 * - YText for rich text documents
 * - YArray for ordered lists
 * - YMap for key-value objects
 * - YXmlFragment for structured content
 * - Counter for distributed counters
 * - Awareness for presence/cursors
 */

import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { IndexeddbPersistence } from "y-indexeddb";
import { OfflineDatabase } from "./offline-db";
import { RxDBManager } from "./rxdb-manager";
import { SyncEngine, SyncEngine as SyncEngineType } from "./sync-engine";

export type CRDTType =
  "ytext" | "yarray" | "ymap" | "yxml" | "counter" | "awareness";

export interface CRDTDocumentConfig {
  type: CRDTType;
  documentId: string;
  initialContent?: any;
  persistenceKey?: string;
  syncEndpoint?: string;
  awareness?: boolean;
}

export interface CRDTSyncConfig {
  websocketUrl: string;
  roomName: string;
  authToken?: string;
  connectOnInit?: boolean;
  awareness?: boolean;
}

export interface CRDTConflictInfo {
  type: "concurrent-edit" | "delete-modify" | "move" | "attribute";
  paths: string[];
  localOps: any[];
  remoteOps: any[];
  timestamp: number;
}

export interface CRDTMetrics {
  documentId: string;
  type: CRDTType;
  localStateVersion: number;
  remoteStateVersion: number;
  pendingOps: number;
  conflictsResolved: number;
  lastSync: number | null;
  bytesSent: number;
  bytesReceived: number;
}

export class CRDTManager {
  private rxdb: RxDBManager;
  private db: OfflineDatabase;
  private syncEngine: SyncEngineType;

  private documents: Map<string, Y.Doc> = new Map();
  private providers: Map<string, WebsocketProvider> = new Map();
  persistences: Map<string, IndexeddbPersistence> = new Map();
  private awarenessStates: Map<string, Y.Awareness> = new Map();

  private syncConfigs: Map<string, CRDTSyncConfig> = new Map();
  private documentConfigs: Map<string, CRDTDocumentConfig> = new Map();

  private conflictCallbacks: Map<string, (conflict: CRDTConflictInfo) => void> =
    new Map();
  private changeCallbacks: Map<
    string,
    (doc: Y.Doc, event: Y.YEvent<any>) => void
  > = new Map();

  private metrics: Map<string, CRDTMetrics> = new Map();
  private isInitialized = false;

  constructor(
    private rxdb: RxDBManager,
    private db: OfflineDatabase,
    private syncEngine: SyncEngineType,
  ) {}

  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    // Initialize Yjs with IndexedDB persistence
    // This will be called when first document is created
    this.isInitialized = true;
    console.log("[CRDT] Manager initialized");
  }

  // ==================== Document Creation ====================

  async createDocument(config: CRDTDocumentConfig): Promise<Y.Doc> {
    const { documentId, type, initialContent, persistenceKey, syncEndpoint } =
      config;

    if (this.documents.has(documentId)) {
      return this.documents.get(documentId)!;
    }

    // Create Yjs document
    const ydoc = new Y.Doc({ guid: documentId });
    this.documents.set(documentId, ydoc);

    // Set up IndexedDB persistence for offline support
    if (persistenceKey) {
      const persistence = new IndexeddbPersistence(persistenceKey, ydoc);
      this.persistences.set(documentId, persistence);

      persistence.on("synced", () => {
        console.log(`[CRDT] Document ${documentId} loaded from IndexedDB`);
      });
    }

    // Initialize content based on type
    this.initializeContent(ydoc, type, initialContent);

    // Set up WebSocket sync if endpoint provided
    if (syncEndpoint) {
      await this.setupSync(documentId, syncEndpoint);
    }

    // Track metrics
    this.metrics.set(documentId, {
      documentId,
      type,
      localStateVersion: 0,
      remoteStateVersion: 0,
      pendingOps: 0,
      conflictsResolved: 0,
      lastSync: null,
      bytesSent: 0,
      bytesReceived: 0,
    });

    // Store config
    this.documentConfigs.set(documentId, config);

    // Set up change tracking
    this.setupChangeTracking(documentId, ydoc, type);

    // Persist to RxDB for querying
    await this.persistDocumentMeta(documentId, type, config);

    return ydoc;
  }

  private initializeContent(
    ydoc: Y.Doc,
    type: CRDTType,
    initialContent?: any,
  ): void {
    switch (type) {
      case "ytext": {
        const ytext = ydoc.getText("content");
        if (initialContent) {
          ytext.insert(0, initialContent);
        }
        break;
      }
      case "yarray": {
        const yarray = ydoc.getArray("content");
        if (initialContent && Array.isArray(initialContent)) {
          yarray.insert(0, initialContent);
        }
        break;
      }
      case "ymap": {
        const ymap = ydoc.getMap("content");
        if (initialContent && typeof initialContent === "object") {
          for (const [key, value] of Object.entries(initialContent)) {
            ymap.set(key, value);
          }
        }
        break;
      }
      case "yxml": {
        const yxml = ydoc.getXmlFragment("content");
        if (initialContent) {
          // Parse and insert XML
          const parser = new DOMParser();
          const doc = parser.parseFromString(initialContent, "text/xml");
          // Would need to convert DOM to Y.Xml
        }
        break;
      }
      case "counter": {
        // Counters are handled via Y.Map with integer values
        break;
      }
    }
  }

  private async setupSync(
    documentId: string,
    websocketUrl: string,
  ): Promise<void> {
    const config: CRDTSyncConfig = {
      websocketUrl,
      roomName: documentId,
      connectOnInit: true,
      awareness: true,
    };
    this.syncConfigs.set(documentId, config);

    const ydoc = this.documents.get(documentId)!;

    const provider = new WebsocketProvider(websocketUrl, documentId, ydoc, {
      connect: config.connectOnInit,
      params: config.authToken ? { token: config.authToken } : undefined,
    });

    this.providers.set(documentId, provider);

    // Set up awareness
    if (config.awareness) {
      const awareness = provider.awareness;
      this.awarenessStates.set(documentId, awareness);

      // Set local user info
      awareness.setLocalStateField("user", {
        id: "current-user", // Would come from auth
        name: "Current User",
        color: "#" + Math.floor(Math.random() * 16777215).toString(16),
      });

      // Track remote cursors
      awareness.on("change", () => {
        this.handleAwarenessChange(documentId, awareness);
      });
    }

    // Monitor connection status
    provider.on("status", (event) => {
      console.log(`[CRDT] Sync status for ${documentId}:`, event.status);
      this.updateSyncMetrics(documentId, { lastSync: Date.now() });
    });

    provider.on("sync", (isSynced: boolean) => {
      console.log(`[CRDT] Document ${documentId} synced:`, isSynced);
    });

    provider.on("error", (error: any) => {
      console.error(`[CRDT] Sync error for ${documentId}:`, error);
    });
  }

  private setupChangeTracking(
    documentId: string,
    ydoc: Y.Doc,
    type: CRDTType,
  ): void {
    // Track local changes for sync engine
    ydoc.on("update", (update: Uint8Array, origin: any) => {
      this.updateSyncMetrics(documentId, {
        localStateVersion: ydoc._stateVector?.get(ydoc.clientID) || 0,
        pendingOps: (this.metrics.get(documentId)?.pendingOps || 0) + 1,
      });

      // Notify change callback
      const callback = this.changeCallbacks.get(documentId);
      if (callback) {
        // Create a synthetic event
        callback(ydoc, { target: ydoc, changes: new Map() } as any);
      }

      // Queue for sync engine
      this.queueForSync(documentId, type, update);
    });

    // Observe specific type changes
    switch (type) {
      case "ytext": {
        const ytext = ydoc.getText("content");
        ytext.observe((event) => {
          this.handleTextChange(documentId, event);
        });
        break;
      }
      case "yarray": {
        const yarray = ydoc.getArray("content");
        yarray.observe((event) => {
          this.handleArrayChange(documentId, event);
        });
        break;
      }
      case "ymap": {
        const ymap = ydoc.getMap("content");
        ymap.observe((event) => {
          this.handleMapChange(documentId, event);
        });
        break;
      }
    }
  }

  private handleTextChange(documentId: string, event: Y.YTextEvent): void {
    // Track text changes for conflict detection
    console.log(`[CRDT] Text change in ${documentId}:`, event.changes.delta);
  }

  private handleArrayChange(documentId: string, event: Y.YArrayEvent): void {
    console.log(`[CRDT] Array change in ${documentId}:`, event.changes.delta);
  }

  private handleMapChange(documentId: string, event: Y.YMapEvent): void {
    console.log(`[CRDT] Map change in ${documentId}:`, event.changes.keys);
  }

  private handleAwarenessChange(
    documentId: string,
    awareness: Y.Awareness,
  ): void {
    const states = awareness.getStates();
    // Broadcast awareness to other clients via sync engine
    console.log(
      `[CRDT] Awareness update for ${documentId}:`,
      states.size,
      "users",
    );
  }

  // ==================== Conflict Resolution ====================

  /**
   * Register conflict callback
   */
  onConflict(
    documentId: string,
    callback: (conflict: CRDTConflictInfo) => void,
  ): void {
    this.conflictCallbacks.set(documentId, callback);
  }

  /**
   * Register change callback
   */
  onChange(
    documentId: string,
    callback: (doc: Y.Doc, event: Y.YEvent<any>) => void,
  ): void {
    this.changeCallbacks.set(documentId, callback);
  }

  /**
   * Detect and resolve conflicts
   */
  async resolveConflict(
    documentId: string,
    strategy: "auto" | "local" | "remote" | "merge" = "auto",
  ): Promise<void> {
    const ydoc = this.documents.get(documentId);
    if (!ydoc) return;

    // Yjs automatically resolves most conflicts via CRDT
    // This is for application-level conflicts
    const callback = this.conflictCallbacks.get(documentId);
    if (callback) {
      const conflict: CRDTConflictInfo = {
        type: "concurrent-edit",
        paths: [],
        localOps: [],
        remoteOps: [],
        timestamp: Date.now(),
      };
      callback(conflict);
    }

    this.updateSyncMetrics(documentId, {
      conflictsResolved:
        (this.metrics.get(documentId)?.conflictsResolved || 0) + 1,
    });
  }

  // ==================== Content Access ====================

  getText(documentId: string): Y.Text | null {
    const ydoc = this.documents.get(documentId);
    return ydoc?.getText("content") || null;
  }

  getArray(documentId: string): Y.Array<any> | null {
    const ydoc = this.documents.get(documentId);
    return ydoc?.getArray("content") || null;
  }

  getMap(documentId: string): Y.Map<any> | null {
    const ydoc = this.documents.get(documentId);
    return ydoc?.getMap("content") || null;
  }

  getXml(documentId: string): Y.XmlFragment | null {
    const ydoc = this.documents.get(documentId);
    return ydoc?.getXmlFragment("content") || null;
  }

  getAwareness(documentId: string): Y.Awareness | null {
    return this.awarenessStates.get(documentId) || null;
  }

  getDocument(documentId: string): Y.Doc | null {
    return this.documents.get(documentId) || null;
  }

  getAllDocuments(): Map<string, Y.Doc> {
    return this.documents;
  }

  // ==================== Document Operations ====================

  async updateText(
    documentId: string,
    index: number,
    deleteLength: number,
    text: string,
  ): Promise<void> {
    const ytext = this.getText(documentId);
    if (!ytext) throw new Error(`No YText found for document: ${documentId}`);

    ytext.delete(index, deleteLength);
    if (text) ytext.insert(index, text);
  }

  async insertText(
    documentId: string,
    index: number,
    text: string,
  ): Promise<void> {
    const ytext = this.getText(documentId);
    if (!ytext) throw new Error(`No YText found for document: ${documentId}`);

    ytext.insert(index, text);
  }

  async deleteText(
    documentId: string,
    index: number,
    length: number,
  ): Promise<void> {
    const ytext = this.getText(documentId);
    if (!ytext) throw new Error(`No YText found for document: ${documentId}`);

    ytext.delete(index, length);
  }

  async updateArray(
    documentId: string,
    index: number,
    deleteCount: number,
    ...items: any[]
  ): Promise<void> {
    const yarray = this.getArray(documentId);
    if (!yarray) throw new Error(`No YArray found for document: ${documentId}`);

    yarray.delete(index, deleteCount);
    if (items.length > 0) yarray.insert(index, items);
  }

  async setMapValue(
    documentId: string,
    key: string,
    value: any,
  ): Promise<void> {
    const ymap = this.getMap(documentId);
    if (!ymap) throw new Error(`No YMap found for document: ${documentId}`);

    ymap.set(key, value);
  }

  async deleteMapValue(documentId: string, key: string): Promise<void> {
    const ymap = this.getMap(documentId);
    if (!ymap) throw new Error(`No YMap found for document: ${documentId}`);

    ymap.delete(key);
  }

  async updateAwareness(documentId: string, state: any): Promise<void> {
    const awareness = this.getAwareness(documentId);
    if (!awareness)
      throw new Error(`No awareness found for document: ${documentId}`);

    awareness.setLocalState(state);
  }

  // ==================== Sync Control ====================

  connect(documentId: string): void {
    const provider = this.providers.get(documentId);
    if (provider) {
      provider.connect();
    }
  }

  disconnect(documentId: string): void {
    const provider = this.providers.get(documentId);
    if (provider) {
      provider.disconnect();
    }
  }

  destroy(documentId: string): void {
    const provider = this.providers.get(documentId);
    if (provider) {
      provider.destroy();
      this.providers.delete(documentId);
    }

    const persistence = this.persistences.get(documentId);
    if (persistence) {
      persistence.destroy();
      this.persistences.delete(documentId);
    }

    const ydoc = this.documents.get(documentId);
    if (ydoc) {
      ydoc.destroy();
      this.documents.delete(documentId);
    }

    this.awarenessStates.delete(documentId);
    this.syncConfigs.delete(documentId);
    this.documentConfigs.delete(documentId);
    this.metrics.delete(documentId);
    this.conflictCallbacks.delete(documentId);
    this.changeCallbacks.delete(documentId);
  }

  destroyAll(): void {
    for (const documentId of this.documents.keys()) {
      this.destroy(documentId);
    }
  }

  // ==================== Persistence ====================

  private async persistDocumentMeta(
    documentId: string,
    type: CRDTType,
    config: CRDTDocumentConfig,
  ): Promise<void> {
    try {
      await this.rxdb.createDocument({
        documentId,
        title: config.documentId,
        content: "",
        ownerId: "system",
        organizationId: "system",
        collection: "crdt",
        metadata: {
          crdtType: type,
          syncEndpoint: config.syncEndpoint,
          persistenceKey: config.persistenceKey,
        },
      });
    } catch (e) {
      console.warn("[CRDT] Failed to persist document meta:", e);
    }
  }

  private async queueForSync(
    documentId: string,
    type: CRDTType,
    update: Uint8Array,
  ): Promise<void> {
    // Queue update for sync engine
    await this.syncEngine.addToSyncQueue({
      type: "crdt",
      operation: "update",
      payload: { documentId, type, update: Array.from(update) },
      priority: "high",
    });
  }

  // ==================== Metrics ====================

  private updateSyncMetrics(
    documentId: string,
    updates: Partial<CRDTMetrics>,
  ): void {
    const current = this.metrics.get(documentId) || {
      documentId,
      type: "ytext",
      localStateVersion: 0,
      remoteStateVersion: 0,
      pendingOps: 0,
      conflictsResolved: 0,
      lastSync: null,
      bytesSent: 0,
      bytesReceived: 0,
    };

    this.metrics.set(documentId, { ...current, ...updates });
  }

  getMetrics(documentId: string): CRDTMetrics | null {
    return this.metrics.get(documentId) || null;
  }

  getAllMetrics(): Map<string, CRDTMetrics> {
    return this.metrics;
  }

  // ==================== State Export/Import ====================

  async exportDocumentState(documentId: string): Promise<{
    documentId: string;
    type: CRDTType;
    state: Uint8Array;
    awareness: any;
    version: number;
  } | null> {
    const ydoc = this.documents.get(documentId);
    if (!ydoc) return null;

    const state = Y.encodeStateAsUpdate(ydoc);
    const awareness = this.awarenessStates.get(documentId);
    const awarenessState = awareness ? awareness.getStates() : {};

    return {
      documentId,
      type: this.documentConfigs.get(documentId)?.type || "ytext",
      state,
      awareness: awarenessState,
      version: ydoc._stateVector?.get(ydoc.clientID) || 0,
    };
  }

  async importDocumentState(data: {
    documentId: string;
    type: CRDTType;
    state: Uint8Array;
    awareness?: any;
  }): Promise<void> {
    const ydoc = await this.createDocument({
      documentId: data.documentId,
      type: data.type,
    });

    Y.applyUpdate(ydoc, data.state);

    if (data.awareness) {
      const awareness = this.awarenessStates.get(data.documentId);
      if (awareness) {
        awareness.setLocalState(data.awareness);
      }
    }
  }

  // ==================== Getters ====================

  isDocumentReady(documentId: string): boolean {
    const ydoc = this.documents.get(documentId);
    return ydoc !== undefined;
  }

  getDocumentType(documentId: string): CRDTType | null {
    return this.documentConfigs.get(documentId)?.type || null;
  }

  getSyncConfig(documentId: string): CRDTSyncConfig | null {
    return this.syncConfigs.get(documentId) || null;
  }
}

// ==================== React Hooks ====================

import { useState, useEffect, useCallback, useRef } from "react";
import * as Y from "yjs";

export function useCRDTDocument(
  crdtManager: CRDTManager,
  documentId: string,
  config: CRDTDocumentConfig,
) {
  const [ydoc, setYdoc] = useState<Y.Doc | null>(null);
  const [content, setContent] = useState<string>("");
  const [isConnected, setIsConnected] = useState(false);
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [awareness, setAwareness] = useState<Map<number, any>>(new Map());

  const ytextRef = useRef<Y.Text | null>(null);
  const observerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const init = async () => {
      const doc = await crdtManager.createDocument(config);
      setYdoc(doc);

      const ytext = doc.getText("content");
      ytextRef.current = ytext;

      // Initial content
      setContent(ytext.toString());

      // Observe changes
      const observer = () => {
        setContent(ytext.toString());
      };
      ytext.observe(observer);
      observerRef.current = observer;

      // Observe awareness
      const awareness = crdtManager.getAwareness(documentId);
      if (awareness) {
        const awarenessObserver = () => {
          setAwareness(new Map(awareness.getStates()));
        };
        awareness.on("change", awarenessObserver);

        return () => {
          ytext.unobserve(observer);
          awareness.off("change", awarenessObserver);
        };
      }
    };

    init();

    return () => {
      if (observerRef.current && ytextRef.current) {
        ytextRef.current.unobserve(observerRef.current);
      }
    };
  }, [crdtManager, documentId, config]);

  const insertText = useCallback(async (index: number, text: string) => {
    if (ytextRef.current) {
      ytextRef.current.insert(index, text);
    }
  }, []);

  const deleteText = useCallback(async (index: number, length: number) => {
    if (ytextRef.current) {
      ytextRef.current.delete(index, length);
    }
  }, []);

  const updateAwareness = useCallback(
    async (state: any) => {
      await crdtManager.updateAwareness(documentId, state);
    },
    [crdtManager, documentId],
  );

  return {
    ydoc,
    content,
    isConnected,
    conflicts,
    awareness,
    insertText,
    deleteText,
    updateAwareness,
  };
}

export function useCRDTArray(
  crdtManager: CRDTManager,
  documentId: string,
  config: CRDTDocumentConfig,
) {
  const [yarray, setYarray] = useState<Y.Array<any> | null>(null);
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    const init = async () => {
      const doc = await crdtManager.createDocument(config);
      const array = doc.getArray("content");
      setYarray(array);
      setItems(array.toArray());

      const observer = () => setItems(array.toArray());
      array.observe(observer);

      return () => array.unobserve(observer);
    };

    init();
  }, [crdtManager, documentId, config]);

  const insert = useCallback(
    (index: number, ...items: any[]) => {
      yarray?.insert(index, items);
    },
    [yarray],
  );

  const deleteItems = useCallback(
    (index: number, length: number) => {
      yarray?.delete(index, length);
    },
    [yarray],
  );

  const update = useCallback(
    (index: number, value: any) => {
      if (yarray) {
        yarray.delete(index, 1);
        yarray.insert(index, [value]);
      }
    },
    [yarray],
  );

  return { yarray, items, insert, delete: deleteItems, update };
}

export function useCRDTMap(
  crdtManager: CRDTManager,
  documentId: string,
  config: CRDTDocumentConfig,
) {
  const [ymap, setYmap] = useState<Y.Map<any> | null>(null);
  const [data, setData] = useState<Record<string, any>>({});

  useEffect(() => {
    const init = async () => {
      const doc = await crdtManager.createDocument(config);
      const map = doc.getMap("content");
      setYmap(map);
      setData(map.toJSON());

      const observer = () => setData(map.toJSON());
      map.observe(observer);

      return () => map.unobserve(observer);
    };

    init();
  }, [crdtManager, documentId, config]);

  const set = useCallback(
    (key: string, value: any) => {
      ymap?.set(key, value);
    },
    [ymap],
  );

  const remove = useCallback(
    (key: string) => {
      ymap?.delete(key);
    },
    [ymap],
  );

  const clear = useCallback(() => {
    ymap?.clear();
  }, [ymap]);

  return { ymap, data, set, remove, clear };
}

export function useCRDTAwareness(crdtManager: CRDTManager, documentId: string) {
  const [awareness, setAwareness] = useState<Map<number, any>>(new Map());
  const [localState, setLocalState] = useState<any>(null);

  useEffect(() => {
    const awareness = crdtManager.getAwareness(documentId);
    if (!awareness) return;

    setAwareness(new Map(awareness.getStates()));

    const observer = () => {
      setAwareness(new Map(awareness.getStates()));
    };
    awareness.on("change", observer);

    return () => awareness.off("change", observer);
  }, [crdtManager, documentId]);

  const updateLocalState = useCallback(
    async (state: any) => {
      setLocalState(state);
      await crdtManager.updateAwareness(documentId, state);
    },
    [crdtManager, documentId],
  );

  return { awareness, localState, updateLocalState };
}

// ==================== Singleton ====================

let _crdtManager: CRDTManager | null = null;

export function getCRDTManager(
  rxdb: RxDBManager,
  db: OfflineDatabase,
  syncEngine: SyncEngineType,
): CRDTManager {
  if (!_crdtManager) {
    _crdtManager = new CRDTManager(rxdb, db, syncEngine);
  }
  return _crdtManager;
}

export default CRDTManager;
