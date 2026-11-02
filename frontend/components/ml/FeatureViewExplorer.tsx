"use client";

import { useState } from 'react';
import { Plus, Search, Filter, Edit, Trash2, Eye, ChevronDown, ChevronUp, Code, Database, Layers } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { classNames } from "@/lib/utils";

interface FeatureView {
  id: string;
  name: string;
  description: string;
  entityId: string;
  entityName: string;
  features: string[];
  transformation: string;
  createdAt: string;
  updatedAt: string;
}

interface FeatureViewExplorerProps {
  featureViews: FeatureView[];
  entities: { id: string; name: string }[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  loading: boolean;
  onCreate: () => void;
  onRefresh: () => void;
}

export function FeatureViewExplorer({ 
  featureViews, 
  entities, 
  searchQuery, 
  setSearchQuery, 
  loading, 
  onCreate, 
  onRefresh 
}: FeatureViewExplorerProps) {
  const [expandedViews, setExpandedViews] = useState<Set<string>>(new Set());
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newView, setNewView] = useState({ 
    name: '', 
    description: '', 
    entityId: '', 
    features: [] as string[],
    transformation: ''
  });

  const entityMap = new Map(entities.map(e => [e.id, e.name]));
  
  const filteredViews = featureViews.filter(view => 
    view.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    view.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    entityMap.get(view.entityId)?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const entityName = (entityId: string) => entityMap.get(entityId) || 'Unknown';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search feature views..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-xs"
            placeholder="Search feature views..."
          />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <svg className="h-4 w-4 mr-1 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M23 4v6h-6" />
              <path d="M1 20v-6h6" />
            </svg>
            Refresh
          </Button>
          <Button onClick={() => setShowCreateModal(true)} className="ml-2">
            <Plus className="h-4 w-4 mr-1" />
            New Feature View
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
          <span className="ml-3 text-muted">Loading feature views...</span>
        </div>
      ) : filteredViews.length === 0 ? (
        <div className="text-center py-12 text-muted">
          <Layers className="h-12 w-12 mx-auto mb-3 opacity-50" />
          <h3 className="text-lg font-medium mb-1">No feature views found</h3>
          <p className="text-sm text-muted mb-4">Create your first feature view to get started</p>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="h-4 w-4 mr-1" />
            Create Feature View
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredViews.map(view => (
            <FeatureViewCard 
              key={view.id} 
              view={view} 
              entityName={entityName(view.entityId)}
              isExpanded={expandedViews.has(view.id)}
              onToggleExpand={() => toggleExpand(view.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FeatureViewCard({ 
  view, 
  entityName, 
  isExpanded, 
  onToggleExpand 
}: { 
  view: any; 
  entityName: string; 
  isExpanded: boolean; 
  onToggleExpand: () => void; 
}) {
  return (
    <Card className="overflow-hidden transition-all">
      <div 
        className="p-4 cursor-pointer hover:bg-muted/50 transition-colors" 
        onClick={onToggleExpand}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-ink truncate">{view.name}</h3>
              <Badge variant="outline" className="text-xs">{view.features.length} features</Badge>
            </div>
            <p className="text-sm text-muted truncate">{view.description}</p>
          </div>
          <div className="flex items-center gap-2 text-muted text-xs">
            <span>Entity: {entityName}</span>
            <span className="mx-1">•</span>
            <span>Updated: {new Date(view.updatedAt).toLocaleDateString()}</span>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-3 pt-3 border-t border-line">
          <button 
            className="text-muted hover:text-brand text-xs font-medium transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="flex items-center gap-1">
              <span>View</span>
            </span>
          </button>
          <button 
            className="text-muted hover:text-brand text-xs font-medium transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="flex items-center gap-1">
              <span>Edit</span>
            </span>
          </button>
          <button 
            className="text-muted hover:text-red-500 text-xs font-medium transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="flex items-center gap-1">
              <span>Delete</span>
            </span>
          </button>
          <button 
            className="text-muted" 
            onClick={onToggleExpand}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>
      
      {expanded && (
        <div className="border-t border-line p-4 bg-muted/30">
          <div className="mb-3">
            <h4 className="font-medium text-sm mb-2">Features</h4>
            <div className="flex flex-wrap gap-2">
              {view.features.map((feature, index) => (
                <span key={index} className="text-xs px-2 py-1 bg-muted rounded border border-line">
                  {feature}
                </span>
              )}
            </div>
          </div>
          <div className="mb-3">
            <h4 className="font-medium text-sm mb-2">Transformation</h4>
            <pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-32 overflow-y-auto">
              {view.transformation}
            </pre>
          </div>
          <div className="text-xs text-muted">
            ID: {view.id}
          </div>
        </div>
      )}
    </Card>
  );
}