"use client";

import { useState } from 'react';
import { Search, Database, RefreshCw, Download, Upload, ExternalLink, Zap, Server } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { classNames } from "@/lib/utils";

interface FeatureView {
  id: string;
  name: string;
  features: string[];
}

interface OnlineStorePanelProps {
  featureViews: FeatureView[];
  selectedFeatureView: string | null;
  setSelectedFeatureView: (id: string) => void;
  onRead: (featureViewId: string, entityIds: string[]) => Promise<any>;
  onGetFeatures: (featureViewId: string, entityIds: string[]) => Promise<any>;
}

export function OnlineStorePanel({ 
  featureViews, 
  selectedFeatureView, 
  setSelectedFeatureView, 
  onRead, 
  onGetFeatures 
}: OnlineStorePanelProps) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [entityIds, setEntityIds] = useState('');
  const [error, setError] = useState<string | null>(null);

  const filteredViews = featureViews.filter(v => v.features.length > 0);

  const handleRead = async () => {
    if (!selectedFeatureView || !entityIds.trim()) {
      setError('Please select a feature view and provide entity IDs');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const ids = entityIds.split(',').map(id => id.trim()).filter(Boolean);
      const result = await onRead(selectedFeatureView, ids);
      setResults(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Read failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGetFeatures = async () => {
    if (!selectedFeatureView || !entityIds.trim()) {
      setError('Please select a feature view and provide entity IDs');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const ids = entityIds.split(',').map(id => id.trim()).filter(Boolean);
      const result = await onGetFeatures(selectedFeatureView, ids);
      setResults(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Get features failed');
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
            value={selectedFeatureView || ''}
            onChange={(e) => setSelectedFeatureView(e.target.value)}
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
        
        {selectedFeatureView && (
          <div className="mt-3 p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">{featureViews.find(v => v.id === selectedFeatureView)?.name}</span>
              <Badge variant="outline" className="text-xs">
                {featureViews.find(v => v.id === selectedFeatureView)?.features.length || 0} features
              </Badge>
            </div>
            <div className="flex flex-wrap gap-1">
              {featureViews.find(v => v.id === selectedFeatureView)?.features.slice(0, 5).map((f, i) => (
                <Badge key={i} variant="secondary" className="text-xs">{f}</Badge>
              ))}
              {featureViews.find(v => v.id === selectedFeatureView)?.features.length > 5 && (
                <Badge variant="outline" className="text-xs">
                  +{featureViews.find(v => v.id === selectedFeatureView)!.features.length - 5} more
                </Badge>
              )}
            </div>
          </div>
        )}
      </Card>

      {/* Entity ID Input */}
      <Card className="p-4">
        <div className="mb-4">
          <label className="block text-sm font-medium text-ink mb-2">Entity IDs (comma-separated)</label>
          <textarea
            value={entityIds}
            onChange={(e) => setEntityIds(e.target.value)}
            placeholder="entity_1, entity_2, entity_3..."
            rows={3}
            className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
            placeholder="Enter entity IDs separated by commas"
          />
          <p className="text-xs text-muted mt-1">
            Enter comma-separated entity IDs to fetch features for
          </p>
        </div>
        
        <div className="flex gap-2">
          <Button 
            onClick={handleRead} 
            disabled={loading || !selectedFeatureView || !entityIds.trim()}
            className="flex-1"
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
                <Database className="h-4 w-4" />
                Read from Online Store
              </span>
            )}
          </Button>
          <Button 
            variant="outline"
            onClick={handleGetFeatures} 
            disabled={loading || !selectedFeatureView || !entityIds.trim()}
          >
            <Zap className="h-4 w-4 mr-1" />
            Get Features
          </Button>
        </div>
      </Card>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm" role="alert">
          {error}
        </div>
      )}

      {/* Results */}
      {results && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium">Results</h3>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(JSON.stringify(results, null, 2))}>
                <Download className="h-4 w-4 mr-1" />
                Copy JSON
              </Button>
              <Button variant="outline" size="sm" onClick={() => setResults(null)}>
                <X className="h-4 w-4" />
                Clear
              </Button>
            </div>
          </div>
          <div className="bg-muted/50 p-4 rounded-lg max-h-96 overflow-auto font-mono text-xs">
            <pre>{JSON.stringify(results, null, 2)}</pre>
          </div>
        </Card>
      )}
    </div>
  );
}