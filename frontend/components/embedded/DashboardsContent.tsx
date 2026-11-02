"use client";

import { DashboardCard } from "./DashboardCard";
import { LoadingState, ErrorStateComponent, EmptyStateComponent } from "./DashboardUIComponents";
import { EmbeddedDashboard } from "./DashboardUIComponents";

export function DashboardsContent({ 
  filteredDashboards, 
  loading, 
  error, 
  canManage,
  onRefresh,
  onCreate,
  onEdit,
  onViewEmbedCode,
  onPreview,
  onCopyId,
  onDelete
}: {
  filteredDashboards: EmbeddedDashboard[];
  loading: boolean;
  error: string | null;
  canManage: boolean;
  onRefresh: () => void;
  onCreate: () => void;
  onEdit: (dashboard: EmbeddedDashboard) => void;
  onViewEmbedCode: (dashboard: EmbeddedDashboard) => void;
  onPreview: (dashboard: EmbeddedDashboard) => void;
  onCopyId: (id: string) => void;
  onDelete: (dashboard: EmbeddedDashboard) => void;
}) {
  if (loading) return <LoadingState />;
  if (error) return <ErrorStateComponent error={error} onRetry={onRefresh} />;
  if (filteredDashboards.length === 0) return <EmptyStateComponent onCreate={onCreate} disabled={!canManage} />;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {filteredDashboards.map(dashboard => (
        <DashboardCard
          key={dashboard.id}
          dashboard={dashboard}
          onEdit={() => onEdit(dashboard)}
          onViewEmbedCode={() => onViewEmbedCode(dashboard)}
          onPreview={() => onPreview(dashboard)}
          onCopyId={() => onCopyId(dashboard.id)}
          onDelete={() => onDelete(dashboard)}
        />
      ))}
    </div>
  );
}