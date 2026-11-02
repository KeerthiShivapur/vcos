"use client";

import { Plus, Edit, Trash2, Eye, Copy, ExternalLink, Box, Monitor, Smartphone, Tablet, Palette, Shield, Key, Copy as CopyIcon, Globe, Code, Zap, Layers, Settings, HelpCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/DropdownMenu";
import { Modal } from "@/components/ui/Modal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Label } from "@/components/ui/Label";
import { useState } from "react";

export interface EmbeddedDashboard {
  id: string;
  name: string;
  description?: string;
  dashboard_id?: string;
  embedding_mode: "iframe" | "web_component" | "javascript_sdk";
  allowed_origins: string[];
  theme: string;
  branding?: {
    primary_color?: string;
    logo_url?: string;
    company_name?: string;
  };
  features: {
    fullscreen: boolean;
    export: boolean;
    share: boolean;
    drill_down: boolean;
    filtering: boolean;
  };
  dimensions: {
    width: string;
    height: string;
    min_height: string;
    responsive: boolean;
  };
  allowed_referrers: string[];
  csp_policy?: string;
  created_at: string;
  updated_at: string;
}

export function AccessDenied() {
  return <ErrorState
    title="Access Denied"
    message="You don't have permission to view embedded analytics dashboards."
    action={{ label: "Go Home", onClick: () => window.location.href = "/app" }}
  />;
}

export function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

export function ErrorStateComponent({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <ErrorState
      title="Failed to load dashboards"
      message={error}
      action={{ label: "Retry", onClick: onRetry }}
    />
  );
}

export function EmptyStateComponent({ onCreate, disabled }: { onCreate: () => void; disabled: boolean }) {
  return (
    <EmptyState
      icon={<Box className="h-12 w-12 text-muted" />}
      title="No dashboards yet"
      description="Create your first embedded dashboard to get started"
      action={{
        label: "Create Dashboard",
        onClick: onCreate,
        disabled,
      }}
    />
  );
}