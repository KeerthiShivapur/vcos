"use client";

import { useState, useMemo, useCallback } from "react";
import { ChevronUp, ChevronDown, Search, Filter, ChevronLeft, ChevronRight, MoreHorizontal, Download, Columns } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Checkbox } from "@/components/ui/Checkbox";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { classNames } from "@/lib/utils";
import { ColumnDef, SortingState, PaginationState, RowSelectionState } from "@tanstack/react-table";
import { useReactTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel, getPaginationRowModel, flexRender, createColumnHelper, SortingState, PaginationState, RowSelectionState } from "@tanstack/react-table";

interface DataTableProps<TData> {
  columns: ColumnDef<TData>[];
  data: TData[];
  keyAccessor: (row: TData) => string;
  title?: string;
  description?: string;
  searchable?: boolean;
  filterable?: boolean;
  sortable?: boolean;
  selectable?: boolean;
  onRowClick?: (row: TData) => void;
  onSelectionChange?: (selection: RowSelectionState) => void;
  initialSort?: SortingState;
  initialPageSize?: number;
  pageSizeOptions?: number[];
  striped?: boolean;
  hoverable?: boolean;
  compact?: boolean;
  loading?: boolean;
  emptyMessage?: string;
  actions?: {
    label: string;
    icon?: React.ReactNode;
    onClick: (rows: TData[]) => void;
    variant?: "primary" | "secondary" | "danger";
    disabled?: (rows: TData[]) => boolean;
  }[];
  columnsToggle?: boolean;
  downloadable?: boolean;
  downloadFilename?: string;
  className?: string;
}

export function DataTable<TData extends Record<string, any>>({
  columns,
  data,
  keyAccessor,
  title,
  description,
  searchable = true,
  filterable = true,
  sortable = true,
  selectable = false,
  onRowClick,
  onSelectionChange,
  initialSort,
  initialPageSize = 10,
  pageSizeOptions = [10, 25, 50, 100],
  striped = false,
  hoverable = true,
  compact = false,
  loading = false,
  emptyMessage = "No data available",
  actions = [],
  columnsToggle = true,
  downloadable = false,
  downloadFilename = "export.csv",
  className,
}: DataTableProps<any>) {
  const [sorting, setSorting] = useState<import("@tanstack/react-table").SortingState>(initialSort || []);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: initialPageSize,
  });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});
  const [columnOrder, setColumnOrder] = useState<string[]>([]);

  const columnHelper = createColumnHelper<any>();

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      pagination,
      globalFilter,
      columnVisibility,
      columnOrder,
      rowSelection,
    },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: setColumnOrder,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId: (row) => keyAccessor(row.original),
    manualPagination: false,
    manualSorting: false,
    manualFiltering: false,
  });

  const handleRowClick = useCallback((row: any) => {
    if (onRowClick) {
      onRowClick(row.original);
    }
  }, [onRowClick]);

  const handleSelectionChange = useCallback((updater: any) => {
    setRowSelection(updater);
    if (onSelectionChange) {
      onSelectionChange(typeof updater === "function" ? updater(rowSelection) : updater);
    }
  }, [onSelectionChange]);

  const handleDownload = () => {
    const visibleRows = table.getFilteredRowModel().rows.slice(
      pagination.pageIndex * pagination.pageSize,
      (pagination.pageIndex + 1) * pagination.pageSize
    );
    const csvContent = [
      columns.filter(c => c.id !== "select").map(c => c.header).join(","),
      ...table.getFilteredRowModel().rows.map(row =>
        columns.filter(c => c.id !== "select").map(c => {
          const value = row.getValue(c.id);
          return typeof value === "string" && value.includes(",") ? `"${value}"` : value;
        }).join(",")
      )
    ].join("\n");
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = downloadFilename;
    link.click();
  };

  const selectedRows = table.getSelectedRowModel().rows.map(r => r.original);
  const hasSelection = selectedRows.length > 0;

  const primaryAction = actions.find(a => a.variant === "primary" || !a.variant);
  const secondaryActions = actions.filter(a => a.variant && a.variant !== "primary");

  return (
    <div className={cn("rounded-xl border border-line bg-surface overflow-hidden", className)}>
      {(title || description) && (
        <div className="px-4 py-3 border-b border-line bg-canvas/50">
          {title && <h3 className="text-lg font-semibold text-ink">{title}</h3>}
          {description && <p className="text-sm text-muted mt-0.5">{description}</p>}
        </div>
      )}

      <div className="p-3 border-b border-line bg-canvas/50 flex flex-wrap items-center gap-3">
        {title && <h3 className="font-semibold text-ink">{title}</h3>}
        
        <div className="flex-1" />
        
        <div className="flex items-center gap-2">
          {searchable && (
            <div className="relative hidden sm:block">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                type="search"
                placeholder="Search..."
                value={globalFilter as unknown as string}
                onChange={(e) => setGlobalFilter(e.target.value)}
                className="h-8 w-64 pl-9 pr-3 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                placeholder="Search..."
              />
            </div>
          )}

          {filterable && (
            <Dropdown
              trigger={(open) => (
                <Button variant="outline" size="sm" className="gap-1" onClick={() => {}}>
                  <Filter className="h-4 w-4" />
                  <span className="hidden sm:inline">Filters</span>
                </Button>
              )}
              children={(close) => (
                <div className="p-3 min-w-[200px]">
                  <p className="text-xs font-medium text-muted mb-2">Filters</p>
                  <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" className="rounded border-line" />
                      <span className="text-muted">Active only</span>
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" className="rounded border-line" />
                      <span className="text-muted">Has attachments</span>
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" className="rounded border-line" />
                      <span className="text-muted">Assigned to me</span>
                    </label>
                  </div>
                  <div className="pt-2 border-t border-line">
                    <Button variant="ghost" size="sm" className="w-full" onClick={close}>
                      Clear filters
                    </Button>
                  </div>
                </div>
              )}
            />
          )}

          <Dropdown
            trigger={(open) => (
              <Button variant="outline" size="sm" className="gap-1" onClick={() => {}}>
                <Columns className="h-4 w-4" />
                <span className="hidden sm:inline">Columns</span>
              </Button>
            )}
            children={(close) => (
              <div className="p-3 min-w-[200px]">
                <p className="text-xs font-medium text-muted mb-2">Visible columns</p>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {/* Column visibility toggles would go here */}
                  <p className="text-sm text-muted text-center py-4">Column toggles coming soon</p>
                </div>
              </div>
            )}
          />

          {downloadable && (
            <Button variant="outline" size="sm" className="gap-1" onClick={handleDownload}>
              <Download className="h-4 w-4" />
              <span className="hidden sm:inline">Export</span>
            </Button>
          )}

          {actions.length > 0 && hasSelection && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted">
                {selectedRows.length} selected
              </span>
              {actions.map((action, index) => (
                <Button
                  key={index}
                  variant={action.variant || "secondary"}
                  size="sm"
                  disabled={action.disabled?.(selectedRows)}
                  onClick={() => action.onClick(selectedRows)}
                  className="gap-1"
                >
                  {action.icon && <action.icon className="h-4 w-4" />}
                  {action.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full caption-bottom text-sm">
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="border-b border-line">
                    {headerGroup.headers.map((header) => (
                      <th
                        key={header.id}
                        className={cn(
                          "h-10 px-3 text-left text-xs font-semibold uppercase tracking-wider text-faint",
                          "border-b border-line",
                          header.getCanSort() && "cursor-pointer select-none hover:bg-canvas/50"
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                        style={{ width: header.getSize() }}
                      >
                        <div className="flex items-center gap-2">
                          {header.column.id !== "select" && (
                            <span>{flexRender(header.column.columnDef.header, header.getContext())}</span>
                          )}
                          {header.column.getCanSort() && (
                            <span className="ml-auto">
                              {header.getIsSorted() === "asc" ? (
                                <ChevronUp className="h-4 w-4 text-muted" />
                              ) : header.getIsSorted() === "desc" ? (
                                <ChevronDown className="h-4 w-4 text-muted" />
                              ) : (
                                <span className="h-4 w-4 text-faint">⇅</span>
                              )}
                            </span>
                          )}
                        </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="px-4 py-12 text-center">
                      <div className="flex flex-col items-center gap-2 text-muted">
                        {loading ? (
                          <>
                            <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
                            <p className="text-sm text-muted mt-2">Loading...</p>
                          </>
                        ) : (
                          <>
                            <p className="text-muted">{emptyMessage}</p>
                          </>
                        )}
                      </>
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row, rowIndex) => (
                    <tr
                      key={row.id}
                      className={cn(
                        "border-b border-line transition-colors",
                        "hover:bg-canvas/50",
                        row.getIsSelected() && "bg-brand/5 ring-1 ring-inset ring-brand"
                      )}
                      onClick={() => handleRowClick(row)}
                      style={{ cursor: onRowClick ? "pointer" : "default" }}
                    >
                      {columns.map((column) => {
                        const cell = row.getCell(column.id);
                        return (
                          <td
                            key={column.id}
                            className={cn(
                              "px-4 py-3 text-sm",
                              column.id === "select" && "w-12"
                            )}
                          >
                            {column.id === "select" ? (
                              <Checkbox
                                checked={row.getIsSelected()}
                                onCheckedChange={row.getToggleSelectedHandler()}
                                disabled={!row.getCanSelect()}
                              />
                            ) : (
                              flexRender(row.getCell(column.id).getContext(), column.columnDef.cell)
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="px-4 py-3 border-t border-line bg-canvas/50 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span>
              Showing {pagination.pageIndex * pagination.pageSize + 1} to{" "}
              {Math.min((pagination.pageIndex + 1) * pagination.pageSize, table.getFilteredRowModel().rows.length)}{" "}
              of {table.getFilteredRowModel().rows.length} results
            </span>
            <Select
              value={pagination.pageSize}
              onValueChange={(v) => setPagination({ ...pagination, pageSize: Number(v), pageIndex: 0 })}
              options={pageSizeOptions.map((size) => ({ value: size.toString(), label: `${size} per page` }))}
              className="w-auto"
            />
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted px-2">
              Page {pagination.pageIndex + 1} of {table.getPageCount()}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Select
              value={pagination.pageSize}
              onValueChange={(v) => setPagination({ ...pagination, pageSize: Number(v), pageIndex: 0 })}
              options={pageSizeOptions.map((size) => ({ value: size.toString(), label: `${size} per page` }))}
              className="w-auto hidden sm:block"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export { DataTable };