/**
 * Data Portability & Export/Import Module
 * Supports JSON, CSV, Parquet formats + GDPR-compliant data export
 */

import { RxDBManager } from "./rxdb-manager";
import { OfflineDatabase } from "./offline-db";
import {
  convertToParquet,
  createZipPackage,
  extractZipPackage,
  convertToCSV,
  parseCSV,
  downloadBlob,
  downloadData,
  getMimeType,
  getFileExtension,
  generateExportFilename,
  StreamExportOptions,
  streamExport,
  ProgressTracker,
  createProgressTracker,
} from "./data-formats";

export type ExportFormat = "json" | "csv" | "parquet" | "zip";
export type CompressionLevel = "none" | "fast" | "best";

export interface ExportOptions {
  format: ExportFormat;
  collections?: string[];
  filter?: {
    ownerId?: string;
    organizationId?: string;
    dateRange?: { start: number; end: number };
    tags?: string[];
    synced?: boolean;
  };
  includeMetadata?: boolean;
  includeAttachments?: boolean;
  compression?: CompressionLevel;
  encrypt?: boolean;
  encryptionPassword?: string;
}

export interface ImportOptions {
  format: ExportFormat;
  overwrite?: boolean;
  validateOnly?: boolean;
  conflictStrategy?: "skip" | "overwrite" | "merge" | "rename";
  mapping?: Record<string, string>; // Field mapping for CSV
  batchSize?: number;
}

export interface ExportResult {
  success: boolean;
  format: ExportFormat;
  size: number;
  itemCount: number;
  collections: string[];
  data?: string | Uint8Array | Blob;
  filename: string;
  checksum: string;
  exportedAt: number;
  error?: string;
}

export interface ImportResult {
  success: boolean;
  format: ExportFormat;
  imported: number;
  skipped: number;
  failed: number;
  collections: string[];
  errors: Array<{ item: any; error: string }>;
  duration: number;
}

export interface GDPRExportOptions {
  userId: string;
  format?: ExportFormat;
  includeDeleted?: boolean;
  includeAuditLog?: boolean;
  includeConsentRecords?: boolean;
  anonymizeReferences?: boolean;
}

export interface GDPRExportResult extends ExportResult {
  userId: string;
  dataCategories: string[];
  retentionInfo: Record<string, { retentionDays: number; legalBasis: string }>;
  consentRecords: any[];
  processingActivities: any[];
}

export interface DataPackage {
  version: number;
  exportedAt: number;
  exportedBy: string;
  format: ExportFormat;
  collections: Record<string, any[]>;
  metadata: {
    totalItems: number;
    totalSize: number;
    collections: Record<string, { count: number; size: number }>;
  };
  checksum: string;
}

export class DataPortabilityManager {
  private rxdb: RxDBManager;
  private db: OfflineDatabase;

  constructor(rxdb: RxDBManager, db: OfflineDatabase) {
    this.rxdb = rxdb;
    this.db = db;
  }

  // ==================== Export ====================

  async exportData(options: ExportOptions): Promise<ExportResult> {
    const startTime = Date.now();
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");

    try {
      // Determine collections to export
      const collectionsToExport = options.collections || [
        "documents",
        "changes",
        "presence",
        "notifications",
        "syncQueue",
        "settings",
        "searchIndex",
      ];

      const collections: Record<string, any[]> = {};
      let totalItems = 0;
      const collectionStats: Record<string, { count: number; size: number }> =
        {};

      for (const name of collectionsToExport) {
        const collection = this.rxdb.getCollection(name);
        if (!collection) continue;

        // Build query
        let query = collection.find();

        if (options.filter) {
          if (options.filter.ownerId) {
            query = query.where("ownerId").eq(options.filter.ownerId);
          }
          if (options.filter.organizationId) {
            query = query
              .where("organizationId")
              .eq(options.filter.organizationId);
          }
          if (options.filter.dateRange) {
            query = query
              .where("lastModified")
              .gte(options.filter.dateRange.start);
            query = query
              .where("lastModified")
              .lte(options.filter.dateRange.end);
          }
          if (options.filter.tags && options.filter.tags.length > 0) {
            query = query
              .where("tags")
              .elemMatch((tag) => options.filter!.tags!.includes(tag));
          }
          if (options.filter.synced !== undefined) {
            query = query.where("synced").eq(options.filter.synced);
          }
        }

        const docs = await query.exec();
        const data = docs.map((doc) => (doc.toJSON ? doc.toJSON() : doc));

        collections[name] = data;
        totalItems += data.length;
        collectionStats[name] = {
          count: data.length,
          size: JSON.stringify(data).length,
        };
      }

      // Create package
      const pkg: DataPackage = {
        version: 1,
        exportedAt: Date.now(),
        exportedBy: "vcos-data-portability",
        format: options.format,
        collections,
        metadata: {
          totalItems,
          totalSize: JSON.stringify(collections).length,
          collections: collectionStats,
        },
        checksum: "",
      };

      // Calculate checksum
      pkg.checksum = await this.calculateChecksum(JSON.stringify(pkg));

      // Format output
      let output: string | Uint8Array | Blob;
      let filename = `vcos-export-${timestamp}.${options.format}`;
      let mimeType = "application/json";

      switch (options.format) {
        case "json":
          output = JSON.stringify(pkg, null, options.includeMetadata ? 2 : 0);
          mimeType = getMimeType("json");
          break;
        case "csv":
          output = await convertToCSV(collections);
          filename = generateExportFilename("vcos-export", "csv", {
            date: true,
          });
          mimeType = getMimeType("csv");
          break;
        case "parquet":
          output = await convertToParquet(collections, {
            compression: options.compression || "SNAPPY",
          });
          filename = generateExportFilename("vcos-export", "parquet", {
            date: true,
          });
          mimeType = getMimeType("parquet");
          break;
        case "zip":
          output = await createZipPackage(collections, {
            compression: options.compression === "best" ? "DEFLATE" : "STORE",
            compressionLevel: options.compression === "best" ? 9 : 6,
          });
          filename = generateExportFilename("vcos-export", "zip", {
            date: true,
          });
          mimeType = getMimeType("zip");
          break;
      }

      // Encrypt if requested
      if (options.encrypt && options.encryptionPassword) {
        output = await this.encryptData(output, options.encryptionPassword);
        filename += ".enc";
      }

      const blob =
        output instanceof Blob
          ? output
          : new Blob([output], { type: mimeType });

      return {
        success: true,
        format: options.format,
        size: blob.size,
        itemCount: totalItems,
        collections: Object.keys(collections),
        data: blob,
        filename,
        checksum: pkg.checksum,
        exportedAt: pkg.exportedAt,
      };
    } catch (error) {
      return {
        success: false,
        format: options.format,
        size: 0,
        itemCount: 0,
        collections: [],
        filename: "",
        checksum: "",
        exportedAt: Date.now(),
        error: error instanceof Error ? error.message : "Export failed",
      };
    }
  }

  async downloadExport(options: ExportOptions): Promise<void> {
    const result = await this.exportData(options);
    if (!result.success || !result.data) {
      throw new Error(result.error || "Export failed");
    }

    const blob =
      result.data instanceof Blob
        ? result.data
        : new Blob([result.data], { type: this.getMimeType(result.format) });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ==================== Import ====================

  async importData(
    data: string | Uint8Array | Blob | File,
    options: ImportOptions,
  ): Promise<ImportResult> {
    const startTime = Date.now();
    const errors: Array<{ item: any; error: string }> = [];
    let imported = 0;
    let skipped = 0;
    let failed = 0;
    const collectionsImported: string[] = [];

    try {
      let pkg: DataPackage;

      // Parse input based on format
      if (options.format === "json") {
        const text = await this.readAsText(data);
        pkg = JSON.parse(text);
      } else if (options.format === "csv") {
        const collections = await parseCSV(await this.readAsText(data));
        pkg = {
          version: 1,
          exportedAt: Date.now(),
          exportedBy: "vcos-data-portability",
          format: "csv",
          collections,
          metadata: {
            totalItems: Object.values(collections).reduce(
              (sum, arr) => sum + arr.length,
              0,
            ),
            totalSize: 0,
            collections: {},
          },
          checksum: "",
        };
      } else if (options.format === "parquet") {
        // Parquet import would use apache-arrow/parquetjs
        // For now, throw not implemented
        throw new Error("Parquet import not yet implemented - use JSON or ZIP");
      } else if (options.format === "zip") {
        const collections = await extractZipPackage(
          data instanceof Blob ? data : new Blob([data]),
        );
        pkg = {
          version: 1,
          exportedAt: Date.now(),
          exportedBy: "vcos-data-portability",
          format: "zip",
          collections,
          metadata: {
            totalItems: Object.values(collections).reduce(
              (sum, arr) => sum + arr.length,
              0,
            ),
            totalSize: 0,
            collections: {},
          },
          checksum: "",
        };
      } else {
        throw new Error(`Unsupported import format: ${options.format}`);
      }

      // Validate package
      if (!pkg || pkg.version !== 1) {
        throw new Error("Invalid data package format");
      }

      // Verify checksum (skip for CSV/ZIP as they don't have checksums)
      if (options.format === "json" || options.format === "parquet") {
        const calculatedChecksum = await this.calculateChecksum(
          JSON.stringify(pkg),
        );
        if (calculatedChecksum !== pkg.checksum) {
          throw new Error(
            "Checksum verification failed - data may be corrupted",
          );
        }
      }

      // Import collections
      for (const [name, items] of Object.entries(pkg.collections)) {
        const collection = this.rxdb.getCollection(name);
        if (!collection) {
          errors.push({
            item: { collection: name },
            error: "Collection not found in database",
          });
          continue;
        }

        collectionsImported.push(name);

        await this.rxdb.getDatabase()?.transaction(async () => {
          for (const item of items) {
            try {
              // Check if exists
              const primaryKey = collection.schema.primaryKey;
              const existing = await collection
                .findOne(item[primaryKey])
                .exec();

              if (existing) {
                if (options.overwrite === false) {
                  skipped++;
                  continue;
                }

                if (options.conflictStrategy === "merge" && existing) {
                  // Merge logic
                  const merged = { ...existing.toJSON(), ...item };
                  await existing.atomicPatch(merged);
                } else if (options.conflictStrategy === "rename") {
                  // Generate new ID
                  item[primaryKey] = crypto.randomUUID();
                  await collection.insert(item);
                } else {
                  // Overwrite
                  await existing.remove();
                  await collection.insert(item);
                }
              } else {
                await collection.insert(item);
              }

              imported++;
            } catch (error) {
              failed++;
              errors.push({
                item,
                error: error instanceof Error ? error.message : "Import failed",
              });
            }
          }
        });
      }

      return {
        success: failed === 0,
        format: options.format,
        imported,
        skipped,
        failed,
        collections: collectionsImported,
        errors,
        duration: Date.now() - startTime,
      };
    } catch (error) {
      return {
        success: false,
        format: options.format,
        imported: 0,
        skipped: 0,
        failed: 0,
        collections: [],
        errors: [
          {
            item: null,
            error: error instanceof Error ? error.message : "Import failed",
          },
        ],
        duration: Date.now() - startTime,
      };
    }
  }

  // ==================== GDPR Export ====================

  async exportUserDataGDPR(
    options: GDPRExportOptions,
  ): Promise<GDPRExportResult> {
    const startTime = Date.now();

    try {
      // Collect all user data
      const userData: Record<string, any[]> = {};
      const dataCategories: string[] = [];
      const retentionInfo: Record<
        string,
        { retentionDays: number; legalBasis: string }
      > = {};
      const consentRecords: any[] = [];
      const processingActivities: any[] = [];

      // Define data categories and their retention
      const categoryConfig = {
        documents: { retentionDays: 2555, legalBasis: "Legitimate interest" }, // 7 years
        changes: { retentionDays: 2555, legalBasis: "Legal obligation" },
        presence: { retentionDays: 30, legalBasis: "Legitimate interest" },
        notifications: { retentionDays: 365, legalBasis: "Consent" },
        syncQueue: { retentionDays: 90, legalBasis: "Technical necessity" },
        settings: { retentionDays: 2555, legalBasis: "Contract performance" },
        searchIndex: { retentionDays: 2555, legalBasis: "Legitimate interest" },
      };

      for (const [name, config] of Object.entries(categoryConfig)) {
        const collection = this.rxdb.getCollection(name);
        if (!collection) continue;

        let query = collection.find();

        // Filter by userId or ownerId
        try {
          query = query.where("ownerId").eq(options.userId);
        } catch {
          try {
            query = query.where("userId").eq(options.userId);
          } catch {
            continue;
          }
        }

        if (options.includeDeleted) {
          query = query.where("_deleted").eq(false).or("_deleted").eq(true);
        }

        const docs = await query.exec();
        const data = docs.map((doc) => {
          const json = doc.toJSON ? doc.toJSON() : doc;
          if (options.anonymizeReferences) {
            return this.anonymizeData(json);
          }
          return json;
        });

        if (data.length > 0) {
          userData[name] = data;
          dataCategories.push(name);
          retentionInfo[name] = config;
        }
      }

      // Get consent records (would come from a consent collection)
      // consentRecords = await this.getConsentRecords(options.userId);

      // Get processing activities (would come from a processing activities log)
      // processingActivities = await this.getProcessingActivities(options.userId);

      // Create GDPR package
      const pkg: DataPackage = {
        version: 1,
        exportedAt: Date.now(),
        exportedBy: "vcos-gdpr-export",
        format: options.format || "json",
        collections: userData,
        metadata: {
          totalItems: Object.values(userData).reduce(
            (sum, arr) => sum + arr.length,
            0,
          ),
          totalSize: JSON.stringify(userData).length,
          collections: Object.fromEntries(
            Object.entries(userData).map(([k, v]) => [
              k,
              { count: v.length, size: JSON.stringify(v).length },
            ]),
          ),
        },
        checksum: "",
      };

      pkg.checksum = await this.calculateChecksum(JSON.stringify(pkg));

      let output: string | Uint8Array | Blob;
      const format = options.format || "json";
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const filename = `gdpr-export-${options.userId}-${timestamp}.${format}`;

      switch (format) {
        case "json":
          output = JSON.stringify(
            {
              ...pkg,
              userId: options.userId,
              dataCategories,
              retentionInfo,
              consentRecords,
              processingActivities,
            },
            null,
            2,
          );
          break;
        case "csv":
          output = await this.convertToCSV(userData);
          break;
        case "parquet":
          output = await this.convertToParquet(userData);
          break;
        case "zip":
          output = await this.createZipPackage({
            ...pkg,
            userId: options.userId,
            dataCategories,
            retentionInfo,
            consentRecords,
            processingActivities,
          });
          break;
      }

      const blob =
        output instanceof Blob
          ? output
          : new Blob([output], { type: this.getMimeType(format) });

      return {
        success: true,
        format,
        size: blob.size,
        itemCount: pkg.metadata.totalItems,
        collections: Object.keys(userData),
        data: blob,
        filename,
        checksum: pkg.checksum,
        exportedAt: pkg.exportedAt,
        userId: options.userId,
        dataCategories,
        retentionInfo,
        consentRecords,
        processingActivities,
      };
    } catch (error) {
      return {
        success: false,
        format: options.format || "json",
        size: 0,
        itemCount: 0,
        collections: [],
        filename: "",
        checksum: "",
        exportedAt: Date.now(),
        error: error instanceof Error ? error.message : "GDPR export failed",
        userId: options.userId,
        dataCategories: [],
        retentionInfo: {},
        consentRecords: [],
        processingActivities: [],
      };
    }
  }

  async downloadGDPRExport(options: GDPRExportOptions): Promise<void> {
    const result = await this.exportUserDataGDPR(options);
    if (!result.success || !result.data) {
      throw new Error(result.error || "GDPR export failed");
    }

    const blob =
      result.data instanceof Blob
        ? result.data
        : new Blob([result.data], { type: this.getMimeType(result.format) });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ==================== Helpers ====================

  private async calculateChecksum(data: string): Promise<string> {
    const encoder = new TextEncoder();
    const buffer = await crypto.subtle.digest("SHA-256", encoder.encode(data));
    return Array.from(new Uint8Array(buffer))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  private async encryptData(
    data: string | Uint8Array | Blob,
    password: string,
  ): Promise<Uint8Array> {
    // In production, use Web Crypto API with PBKDF2 + AES-GCM
    // This is a placeholder
    const encoder = new TextEncoder();
    const dataBuffer =
      typeof data === "string"
        ? encoder.encode(data)
        : data instanceof Uint8Array
          ? data
          : new Uint8Array(await data.arrayBuffer());
    return dataBuffer; // Placeholder - not actually encrypted
  }

  private anonymizeData(data: any): any {
    const anonymized = { ...data };
    const piiFields = ["email", "phone", "address", "ssn", "ip", "userAgent"];

    for (const field of piiFields) {
      if (field in anonymized) {
        anonymized[field] = "[REDACTED]";
      }
    }

    // Recursively anonymize nested objects
    for (const key of Object.keys(anonymized)) {
      if (typeof anonymized[key] === "object" && anonymized[key] !== null) {
        anonymized[key] = this.anonymizeData(anonymized[key]);
      }
    }

    return anonymized;
  }

  private async readAsText(
    data: string | Uint8Array | Blob | File,
  ): Promise<string> {
    if (typeof data === "string") return data;
    if (data instanceof Uint8Array) return new TextDecoder().decode(data);
    if (data instanceof Blob) return data.text();
    if (data instanceof File) return data.text();
    throw new Error("Unsupported data type");
  }

  private getMimeType(format: ExportFormat): string {
    switch (format) {
      case "json":
        return "application/json";
      case "csv":
        return "text/csv";
      case "parquet":
        return "application/octet-stream";
      case "zip":
        return "application/zip";
      default:
        return "application/octet-stream";
    }
  }

  // ==================== Utility ====================

  async getExportPreview(options: ExportOptions): Promise<{
    estimatedSize: number;
    estimatedItems: number;
    collections: Record<string, { count: number; estimatedSize: number }>;
  }> {
    const collectionsToExport = options.collections || [
      "documents",
      "changes",
      "presence",
      "notifications",
      "syncQueue",
      "settings",
      "searchIndex",
    ];

    const preview: Record<string, { count: number; estimatedSize: number }> =
      {};
    let totalItems = 0;
    let totalSize = 0;

    for (const name of collectionsToExport) {
      const collection = this.rxdb.getCollection(name);
      if (!collection) continue;

      let query = collection.find();
      if (options.filter?.ownerId) {
        query = query.where("ownerId").eq(options.filter.ownerId);
      }
      if (options.filter?.organizationId) {
        query = query.where("organizationId").eq(options.filter.organizationId);
      }

      const count = await query.count().exec();
      const estimatedSize = count * 1000; // Rough estimate

      preview[name] = { count, estimatedSize };
      totalItems += count;
      totalSize += estimatedSize;
    }

    return {
      estimatedSize: totalSize,
      estimatedItems: totalItems,
      collections: preview,
    };
  }
}

// ==================== React Hook ====================

import { useState, useCallback } from "react";

export function useDataPortability(rxdb: RxDBManager, db: OfflineDatabase) {
  const [manager] = useState(() => new DataPortabilityManager(rxdb, db));
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [importProgress, setImportProgress] = useState(0);

  const exportData = useCallback(
    async (options: ExportOptions) => {
      setIsExporting(true);
      setExportProgress(0);

      try {
        const result = await manager.exportData(options);
        setExportProgress(100);
        return result;
      } finally {
        setIsExporting(false);
        setExportProgress(0);
      }
    },
    [manager],
  );

  const downloadExport = useCallback(
    async (options: ExportOptions) => {
      setIsExporting(true);
      try {
        await manager.downloadExport(options);
      } finally {
        setIsExporting(false);
      }
    },
    [manager],
  );

  const importData = useCallback(
    async (data: string | Uint8Array | Blob | File, options: ImportOptions) => {
      setIsImporting(true);
      setImportProgress(0);

      try {
        const result = await manager.importData(data, options);
        setImportProgress(100);
        return result;
      } finally {
        setIsImporting(false);
        setImportProgress(0);
      }
    },
    [manager],
  );

  const exportGDPR = useCallback(
    async (options: { userId: string; format?: ExportFormat }) => {
      setIsExporting(true);
      try {
        const result = await manager.exportUserDataGDPR(options);
        return result;
      } finally {
        setIsExporting(false);
      }
    },
    [manager],
  );

  const downloadGDPR = useCallback(
    async (options: { userId: string; format?: ExportFormat }) => {
      setIsExporting(true);
      try {
        await manager.downloadGDPRExport(options);
      } finally {
        setIsExporting(false);
      }
    },
    [manager],
  );

  const getPreview = useCallback(
    async (options: ExportOptions) => {
      return manager.getExportPreview(options);
    },
    [manager],
  );

  return {
    exportData,
    downloadExport,
    importData,
    exportGDPR,
    downloadGDPR,
    getPreview,
    isExporting,
    isImporting,
    exportProgress,
    importProgress,
  };
}

// ==================== Default Instance ====================

let _dataPortabilityManager: DataPortabilityManager | null = null;

export function getDataPortabilityManager(
  rxdb: RxDBManager,
  db: OfflineDatabase,
): DataPortabilityManager {
  if (!_dataPortabilityManager) {
    _dataPortabilityManager = new DataPortabilityManager(rxdb, db);
  }
  return _dataPortabilityManager;
}

export default DataPortabilityManager;
