"use client";

import { useState } from 'react';
import { Plus, Search, Filter, Edit, Trash2, Eye, ChevronDown, ChevronUp } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { classNames } from "@/lib/utils";

interface Entity {
  id: string;
  name: string;
  description: string;
  features: string[];
  createdAt: string;
  updatedAt: string;
}

interface EntityExplorerProps {
  entities: Entity[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  loading: boolean;
  onCreate: () => void;
  onRefresh: () => void;
}

export function EntityExplorer({ 
  entities, 
  searchQuery, 
  setSearchQuery, 
  loading, 
  onCreate, 
  onRefresh 
}: EntityExplorerProps) {
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set());
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newEntity, setNewEntity] = useState({ name: '', description: '', features: [] as string[] });
  const [newFeature, setNewFeature] = useState('');

  const filteredEntities = entities.filter(entity => 
    entity.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    entity.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const toggleExpand = (id: string) => {
    setExpandedEntities(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCreateEntity = () => {
    onCreate();
    setShowCreateModal(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <Input
            placeholder="Search entities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-xs"
            placeholder="Search entities..."
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
          <Button onClick={handleCreateEntity} className="ml-2">
            <Plus className="h-4 w-4 mr-1" />
            New Entity
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
          <span className="ml-3 text-muted">Loading entities...</span>
        </div>
      ) : filteredEntities.length === 0 ? (
        <div className="text-center py-12 text-muted">
          <svg className="h-12 w-12 mx-auto mb-3 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          <h3 className="text-lg font-medium mb-1">No entities found</h3>
          <p className="text-sm text-muted mb-4">Create your first entity to get started</p>
          <Button onClick={handleCreateEntity}>
            <Plus className="h-4 w-4 mr-1" />
            Create Entity
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredEntities.map(entity => (
            <EntityCard 
              key={entity.id} 
              entity={entity} 
              isExpanded={expandedEntities.has(entity.id)}
              onToggleExpand={() => toggleExpand(entity.id)}
            />
          ))}
        )}
    </div>
  );
}

function EntityCard({ 
  entity, 
  isExpanded, 
  onToggleExpand 
}: { 
  entity: Entity; 
  isExpanded: boolean; 
  onToggleExpand: () => void; 
}) {
  return (
    <Card className={classNames("overflow-hidden transition-all", isExpanded && "ring-2 ring-brand/20")}>
      <div 
        className="p-4 cursor-pointer hover:bg-muted/50 transition-colors" 
        onClick={onToggleExpand}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-ink truncate">{entity.name}</h3>
              <Badge variant="outline" className="text-xs">{entity.features.length} features</Badge>
            </div>
            <p className="text-sm text-muted truncate">{entity.description}</p>
          </div>
          <div className="flex items-center gap-2 text-muted text-xs">
            <span>Updated: {new Date(entity.updatedAt).toLocaleDateString()}</span>
            <span className="mx-1">•</span>
            <span>Created: {new Date(entity.createdAt).toLocaleDateString()}</span>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-3 pt-3 border-t border-line">
          <Button variant="ghost" size="sm" className="text-muted hover:text-brand">
            <Eye className="h-4 w-4" />
            View
          </Button>
          <Button variant="ghost" size="sm" className="text-muted hover:text-brand">
            <Edit className="h-4 w-4" />
            Edit
          </Button>
          <Button variant="ghost" size="sm" className="text-muted hover:text-red-500">
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
          <Button 
            variant="ghost" 
            size="sm" 
            className="text-muted" 
            onClick={onToggleExpand}
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
      
      {isExpanded && (
        <div className="border-t border-line p-4 bg-muted/30">
          <div className="mb-3">
            <h4 className="font-medium text-sm mb-2">Features</h4>
            <div className="flex flex-wrap gap-2">
              {entity.features.map((feature, index) => (
                <Badge key={index} variant="outline" className="text-xs">
                  {feature}
                </Badge>
              ))}
            </div>
          </div>
          <div className="text-xs text-muted">
            ID: {entity.id}
          </div>
        </div>
      )}
    </Card>
  );
}