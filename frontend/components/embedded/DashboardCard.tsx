"use client";

import { Box, Edit, Trash2, Eye, Copy, ExternalLink, Settings } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";

import { EmbeddedDashboard } from "./DashboardUIComponents";

interface DashboardCardProps {
  dashboard: EmbeddedDashboard;
  onEdit: () => void;
  onViewEmbedCode: () => void;
  onPreview: () => void;
  onCopyId: () => void;
  onDelete: () => void;
}

export function DashboardCard({ dashboard, onEdit, onViewEmbedCode, onPreview, onCopyId, onDelete }: {
  dashboard: EmbeddedDashboard;
  onEdit: () => void;
  onViewEmbedCode: () => void;
  onPreview: () => void;
  onCopyId: () => void;
  onDelete: () => void;
}) {
  return (
    <Card key={dashboard.id} className="relative">
      <div className="flex items-start justify-between p-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
              <Box className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white truncate">{dashboard.name}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 truncate max-w-md">
                {dashboard.description || "No description"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="neutral" className="text-xs">
              {dashboard.embedding_mode === "iframe" ? "Iframe" : 
               dashboard.embedding_mode === "web_component" ? "Web Component" : "JS SDK"}
            </Badge>
            <Badge tone="brand" className="text-xs">
              {dashboard.dimensions.width} × {dashboard.dimensions.height}
            </Badge>
          </div>
        </div>
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
            <span>Updated {new Date(dashboard.updated_at).toLocaleDateString()}</span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={onViewEmbedCode}>
                <ExternalLink className="w-4 h-4 mr-1" />
                Embed Code
              </Button>
              <Dropdown
                trigger={(open) => (
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                    <Settings className="w-4 h-4" />
                  </Button>
                )}
              >
                {(close) => (
                  <>
                    <MenuItem label="Edit" onClick={() => { onEdit(); close(); }} />
                    <MenuItem label="Embed Code" icon={ExternalLink} onClick={() => { onViewEmbedCode(); close(); }} />
                    <MenuItem label="Preview" icon={Eye} onClick={() => { onPreview(); close(); }} />
                    <MenuItem label="Copy ID" icon={Copy} onClick={() => { onCopyId(); close(); }} />
                    <MenuItem label="Delete" icon={Trash2} danger onClick={() => { onDelete(); close(); }} />
                  </>
                )}
              </Dropdown>
            </div>
          </div>
        </div>
      </Card>
    );
  }
}