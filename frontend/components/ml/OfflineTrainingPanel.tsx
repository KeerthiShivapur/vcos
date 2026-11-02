"use client";

import { useState } from 'react';
import { Search, Database, RefreshCw, Download, Upload, ExternalLink, Zap, Server, Play, Pause, Stop, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { classNames } from "@/lib/utils";

interface FeatureView {
  id: string;
  name: string;
  features: string[];
}

interface OfflineTrainingPanelProps {
  featureViews: FeatureView[];
  onBatchWrite: (featureViewId: string, data: any[]) => Promise<any>;
  onGetTrainingData: (featureViewId: string, options: { limit?: number; offset?: number; format?: string }) => Promise<any>;
  onMaterialize: (featureViewId: string, options: { outputPath?: string; format?: string }) => Promise<any>;
}

export function OfflineTrainingPanel({ 
  featureViews, 
  onBatchWrite, 
  onGetTrainingData, 
  onMaterialize 
}: OfflineTrainingPanelProps) {
  const [selectedView, setSelectedView] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'write' | 'read' | 'materialize'>('write');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any>(null);

  // Write tab state
  const [batchData, setBatchData] = useState('');
  const [batchOptions, setBatchOptions] = useState({
    format: 'parquet',
    includeMetadata: true,
    overwrite: false,
  });

  // Read tab state
  const [readOptions, setReadOptions] = useState({
    limit: 1000,
    offset: 0,
    format: 'parquet',
    filters: '',
  });

  // Materialize state
  const [materializeOptions, setMaterializeOptions] = useState({
    outputPath: '',
    format: 'parquet',
    compress: true,
    partitionBy: '',
  });

  const filteredViews = featureViews.filter(v => v.features.length > 0);

  const handleBatchWrite = async () => {
    if (!selectedView || !batchData.trim()) {
      setError('Please select a feature view and provide data');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      let data;
      try {
        data = JSON.parse(batchData);
      } catch {
        setError('Invalid JSON data');
        return;
      }

      if (!Array.isArray(data)) {
        setError('Data must be a JSON array');
        return;
      }

      const result = await onBatchWrite(selectedView, data);
      setResults({ success: true, written: data.length, ...result });
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Batch write failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRead = async () => {
    if (!selectedView) {
      setError('Please select a feature view');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await onGetTrainingData(selectedView, readOptions);
      setResults(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Read failed');
    } finally {
      setLoading(false);
    }
  };

  const handleMaterialize = async () => {
    if (!selectedView) {
      setError('Please select a feature view');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await onMaterialize(selectedView, materializeOptions);
      setResults({ success: true, ...result });
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Materialize failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Feature View Selector */}
      <Card className="p-4">
        <div className="mb-4">
          <label className="block text-sm font-medium text-ink mb-2">Select Feature View</label>
          <select
            value={selectedView || ''}
            onChange={(e) => setSelectedView(e.target.value)}
            className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
          >
            <option value="">Select a feature view...</option>
            {featureViews.map(view => (
              <option key={view.id} value={view.id}>
                {view.name} ({view.features.length} features)
              </option>
            )}
          </select>
        </div>
        
        {selectedView && (
          <div className="mt-3 p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">
                {featureViews.find(v => v.id === selectedView)?.name}
              </span>
              <Badge variant="outline" className="text-xs">
                {featureViews.find(v => v.id === selectedView)?.features.length || 0} features
              </Badge>
            </div>
            <div className="flex flex-wrap gap-1">
              {featureViews.find(v => v.id === selectedView)?.features.slice(0, 5).map((f, i) => (
                <Badge key={i} variant="secondary" className="text-xs">{f}</Badge>
              ))}
              {featureViews.find(v => v.id === selectedView)?.features.length > 5 && (
                <Badge variant="outline" className="text-xs">
                  +{featureViews.find(v => v.id === selectedView)!.features.length - 5} more
                </Badge>
              )}
            </div>
          </div>
        )}
      </Card>

      {/* Tabs */}
      <div className="border-b border-line">
        <nav className="flex gap-4" role="tablist">
          {[
            { id: 'write', label: 'Batch Write', icon: Upload },
            { id: 'read', label: 'Read Data', icon: Download },
            { id: 'materialize', label: 'Materialize', icon: Server },
          ].map(tab => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={classNames(
                "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
                activeTab === tab.id
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-ink"
              )}
            >
              <tab.icon className="h-4 w-4 mr-1.5" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="pt-6 space-y-6">
        {/* Write Tab */}
        {activeTab === 'write' && (
          <Card className="p-4">
            <h3 className="font-medium mb-4">Batch Write to Offline Store</h3>
            
            <div className="mb-4">
              <label className="block text-sm font-medium text-ink mb-2">Data (JSON Array)</label>
              <textarea
                value={batchData}
                onChange={(e) => setBatchData(e.target.value)}
                rows={8}
                placeholder='[{"entity_id": "1", "feature_1": 0.5, "feature_2": "value"}, ...]'
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
                placeholder='[{"entity_id": "1", "feature_1": 0.5, "feature_2": "value"}, {"entity_id": "2", "feature_1": 0.3, "feature_2": "other"}]'
              />
              <p className="text-xs text-muted mt-1">Enter JSON array of feature vectors. Each object must have an entity_id field.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Output Format</label>
                <Select
                  value={batchOptions.format}
                  onValueChange={(v) => setBatchOptions(prev => ({ ...prev, format: v }))}
                >
                  <option value="parquet">Parquet</option>
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="includeMetadata"
                  checked={batchOptions.includeMetadata}
                  onChange={(e) => setBatchOptions(prev => ({ ...prev, includeMetadata: e.target.checked }))}
                  className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                />
                <label htmlFor="includeMetadata" className="text-sm text-ink">Include Metadata</label>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="overwrite"
                  checked={batchOptions.overwrite}
                  onChange={(e) => setBatchOptions(prev => ({ ...prev, overwrite: e.target.checked }))}
                  className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                />
                <label htmlFor="overwrite" className="text-sm text-ink">Overwrite Existing</label>
              </div>
            </div>

            <Button 
              onClick={handleBatchWrite} 
              disabled={loading || !selectedView || !batchData.trim()}
              className="w-full"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                    <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeDasharray="31.4 31.4" />
                  </svg>
                  Writing...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <Upload className="h-4 w-4" />
                  Write Batch to Offline Store
                </span>
              )}
            </Button>
          </Card>
        )}

        {/* Read Tab */}
        {activeTab === 'read' && (
          <Card className="p-4">
            <h3 className="font-medium mb-4">Read Training Data</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Limit</label>
                <Input
                  type="number"
                  value={readOptions.limit}
                  onChange={(e) => setReadOptions(prev => ({ ...prev, limit: parseInt(e.target.value) || 0 }))}
                  min={1}
                  max={100000}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Offset</label>
                <Input
                  type="number"
                  value={readOptions.offset}
                  onChange={(e) => setReadOptions(prev => ({ ...prev, offset: parseInt(e.target.value) || 0 }))}
                  min={0}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Format</label>
                <Select
                  value={readOptions.format}
                  onValueChange={(v) => setReadOptions(prev => ({ ...prev, format: v }))}
                >
                  <option value="parquet">Parquet</option>
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                </Select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Filters (JSON)</label>
                <Input
                  value={readOptions.filters}
                  onChange={(e) => setReadOptions(prev => ({ ...prev, filters: e.target.value }))}
                  placeholder='{"feature_1": {">": 0.5}}'
                  className="w-full"
                />
              </div>
            </div>

            <Button 
              onClick={handleRead} 
              disabled={loading || !selectedView}
              className="w-full"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                    <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeDasharray="31.4 31.4" />
                  </svg>
                  Reading...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <Download className="h-4 w-4" />
                  Read Training Data
                </span>
              )}
            </Button>
          </Card>
        )}

        {/* Materialize Tab */}
        {activeTab === 'materialize' && (
          <Card className="p-4">
            <h3 className="font-medium mb-4">Materialize Feature View</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">Output Path</label>
                <Input
                  value={materializeOptions.outputPath}
                  onChange={(e) => setMaterializeOptions(prev => ({ ...prev, outputPath: e.target.value }))}
                  placeholder="s3://bucket/path/ or /local/path/"
                  className="w-full"
                />
                <p className="text-xs text-muted mt-1">S3 path (s3://bucket/path/) or local file path</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">Format</label>
                  <Select
                    value={materializeOptions.format}
                    onValueChange={(v) => setMaterializeOptions(prev => ({ ...prev, format: v }))}
                  >
                    <option value="parquet">Parquet</option>
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </Select>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="compress"
                    checked={materializeOptions.compress}
                    onChange={(e) => setMaterializeOptions(prev => ({ ...prev, compress: e.target.checked }))}
                    className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                  />
                  <label htmlFor="compress" className="text-sm text-ink">Compress Output</label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-ink mb-1">Partition By (Optional)</label>
                <Input
                  value={materializeOptions.partitionBy}
                  onChange={(e) => setMaterializeOptions(prev => ({ ...prev, partitionBy: e.target.value }))}
                  placeholder="feature_name or date_column"
                  className="w-full"
                />
                <p className="text-xs text-muted mt-1">Column name to partition output by</p>
              </div>

              <Button 
                onClick={handleMaterialize} 
                disabled={loading || !selectedView}
                className="w-full"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                      <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeDasharray="31.4 31.4" />
                    </svg>
                    Materializing...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <Server className="h-4 w-4" />
                    Materialize to Offline Store
                  </span>
                )}
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}