"use client";

import { Plus, Edit, Trash2, Eye, Copy, ExternalLink, Box, Monitor, Smartphone, Tablet, Palette, Shield, Key, Copy as CopyIcon, Globe, Code, Zap, Layers, Settings, HelpCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/DropdownMenu";
import { Modal } from "@/components/ui/Modal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Label } from "@/components/ui/Label";
import { useState } from "react";

import { EmbeddedDashboard } from "./DashboardUIComponents";

export function CreateDashboardModal({ isOpen, onClose, onSubmit, loading, initialData }: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: Partial<EmbeddedDashboard>) => Promise<void>;
  loading?: boolean;
  initialData?: Partial<EmbeddedDashboard>;
}) {
  const [formData, setFormData] = useState<Partial<EmbeddedDashboard>>({
    name: "",
    description: "",
    dashboard_id: "",
    embedding_mode: "iframe",
    allowed_origins: [],
    theme: "light",
    branding: {},
    features: {
      fullscreen: true,
      export: true,
      share: true,
      drill_down: true,
      filtering: true,
    },
    dimensions: {
      width: "100%",
      height: "600px",
      min_height: "400px",
      responsive: true,
    },
    allowed_referrers: [],
    csp_policy: "",
  });

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initialData ? "Edit Dashboard" : "Create Dashboard"}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit(formData);
      }} className="space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" value={formData.name || ""} onChange={e => setFormData({...formData, name: e.target.value})} required />
        </div>
        <div>
          <Label htmlFor="description">Description</Label>
          <Textarea id="description" value={formData.description || ""} onChange={e => setFormData({...formData, description: e.target.value})} />
        </div>
        <div>
          <Label htmlFor="dashboard_id">Dashboard ID</Label>
          <Input id="dashboard_id" value={formData.dashboard_id || ""} onChange={e => setFormData({...formData, dashboard_id: e.target.value})} />
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <Label htmlFor="embedding_mode">Embedding Mode</Label>
            <Select value={formData.embedding_mode || "iframe"} onValueChange={v => setFormData({...formData, embedding_mode: v as any})}>
              <option value="iframe">Iframe</option>
              <option value="web_component">Web Component</option>
              <option value="javascript_sdk">JavaScript SDK</option>
            </Select>
          </div>
          <div className="flex-1">
            <Label htmlFor="theme">Theme</Label>
            <Select value={formData.theme || "light"} onValueChange={v => setFormData({...formData, theme: v})}>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={loading}>{loading ? "Saving..." : initialData ? "Update" : "Create"}</Button>
        </div>
      </form>
    </Modal>
  );
}