"use client";

import { cn } from "@/lib/utils";
import { useMemo } from "react";
import {
  LineChart as RechartsLineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface ChartDataPoint {
  [key: string]: string | number;
}

interface ChartProps {
  data: Record<string, string | number>[];
  type: "line" | "area" | "bar" | "pie";
  xKey: string;
  yKeys: string | string[];
  colors?: string[];
  xAxisKey?: string;
  yAxisLabel?: string;
  xAxisLabel?: string;
  showLegend?: boolean;
  showGrid?: boolean;
  showTooltip?: boolean;
  showLegend?: boolean;
  height?: number;
  width?: string | number;
  className?: string;
  loading?: boolean;
  emptyMessage?: string;
  onClick?: (dataPoint: any) => void;
  colors?: string[];
  animationDuration?: number;
  margin?: { top: number; right: number; left: number; bottom: number };
  stacked?: boolean;
  connectNulls?: boolean;
  dot?: boolean;
  activeDot?: boolean;
  strokeWidth?: number;
  fillOpacity?: number;
  customTooltip?: (
    activePayload: any[],
    activeLabel: string,
  ) => React.ReactNode;
}

const COLORS = [
  "rgb(var(--brand))",
  "rgb(var(--success))",
  "rgb(var(--warning))",
  "rgb(var(--danger))",
  "rgb(99 102 241)",
  "rgb(236 72 153)",
  "rgb(20 184 166)",
  "rgb(249 115 22)",
];

function CustomTooltip({ active, payload, label }: any) {
  if (!payload || !payload.length) return null;

  return (
    <div className="bg-surface border border-line rounded-lg shadow-lg p-3 min-w-[180px] z-50">
      <p className="font-medium text-ink mb-2">
        {payload[0]?.name || payload[0]?.payload?.name || "Data"}
      </p>
      {payload.map((entry: any, index: number) => (
        <div key={index} className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-sm font-medium text-ink">
            {entry.name}:{" "}
            <strong>{entry.value?.toLocaleString?.() ?? entry.value}</strong>
          </span>
        </div>
      ))}
    </div>
  );
}

export function Chart({
  data,
  type,
  xKey,
  yKeys,
  colors = COLORS,
  xAxisKey,
  yAxisLabel,
  xAxisLabel,
  showLegend = true,
  showGrid = true,
  showTooltip = true,
  showLegend: showLegendProp = true,
  height = 300,
  width = "100%",
  className,
  loading = false,
  emptyMessage = "No data available",
  onClick,
  colors = COLORS,
  animationDuration = 300,
  margin = { top: 10, right: 20, left: 20, bottom: 10 },
  stacked = false,
  connectNulls = true,
  dot = true,
  activeDot = true,
  strokeWidth = 2,
  fillOpacity = 0.1,
  customTooltip,
  className: classNameProp,
}: ChartProps) {
  const yKeyArray = Array.isArray(yKeys) ? yKeys : [yKeys];
  const colorArray = Array.isArray(colors) ? colors : [colors];

  const data = useMemo(() => data, [data]);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!payload || !payload.length) return null;

    return (
      <div className="bg-surface border border-line rounded-lg shadow-lg p-3 min-w-[180px] z-50">
        <p className="font-medium text-ink mb-2">
          {payload[0]?.name || payload[0]?.payload?.name || "Data"}
        </p>
        {payload.map((entry: any, index: number) => (
          <div key={index} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-sm font-medium text-ink">
              {entry.name}:{" "}
              <strong>{entry.value?.toLocaleString?.() ?? entry.value}</strong>
            </span>
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return (
      <div
        className={cn("h-[300px] flex items-center justify-center", className)}
      >
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        className={cn("flex items-center justify-center h-[300px]", className)}
      >
        <div className="flex flex-col items-center gap-2 text-muted">
          <svg
            className="h-12 w-12 text-muted/30"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2v2m-4 0h.01M17 13h-8l1.5-4.5 2 2 2-2 2 2 2-2 2 2h8v12H7a2 2 0 00-2 2v6h12v-6a2 2 0 00-2-2z"
              stroke="currentColor"
            />
          </svg>
          <p className="text-muted">No data available</p>
        </div>
      </div>
    );
  }

  const margin = { top: 10, right: 20, left: 20, bottom: 10 };
  const colorArray = Array.isArray(colors) ? colors : [colors];

  if (type === "line") {
    return (
      <div className={cn("w-full", classNameProp)} style={{ width, height }}>
        <ResponsiveContainer width="100%" height={height}>
          <RechartsLineChart data={data} margin={margin} layout="vertical">
            {showGrid && (
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgb(var(--line) / 0.3)"
                vertical={false}
              />
            )}
            <XAxis
              dataKey={xKey}
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            <YAxis
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            {showTooltip && <Tooltip content={<CustomTooltip />} />}
            {showLegend && <Legend />}
            {yKeyArray.map((yKey, index) => (
              <Line
                key={yKey}
                type="monotone"
                dataKey={yKey}
                stroke={colorArray[index % colorArray.length]}
                strokeWidth={strokeWidth}
                dot={dot}
                activeDot={activeDot}
                connectNulls={connectNulls}
                animationDuration={animationDuration}
              />
            ))}
          </RechartsLineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (type === "area") {
    return (
      <div className={cn("w-full", classNameProp)} style={{ width, height }}>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={data} margin={margin}>
            {showGrid && (
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgb(var(--line) / 0.3)"
                vertical={false}
              />
            )}
            <XAxis
              dataKey={xKey}
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            <YAxis
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            {showTooltip && <Tooltip content={<CustomTooltip />} />}
            {showLegend && <Legend />}
            {yKeyArray.map((yKey, index) => (
              <Area
                key={yKey}
                type="monotone"
                dataKey={yKey}
                stroke={colorArray[index % colorArray.length]}
                fill={colorArray[index % colorArray.length]}
                fillOpacity={fillOpacity}
                strokeWidth={strokeWidth}
                connectNulls={connectNulls}
                animationDuration={animationDuration}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (type === "bar") {
    return (
      <div className={cn("w-full", classNameProp)} style={{ width, height }}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={margin} layout="vertical">
            {showGrid && (
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgb(var(--line) / 0.3)"
                vertical={false}
              />
            )}
            <XAxis
              dataKey={xKey}
              type="category"
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            <YAxis
              tick={{ fill: "rgb(var(--muted-foreground))", fontSize: 12 }}
              axisLine={{ stroke: "rgb(var(--line))" }}
              tickLine={{ stroke: "rgb(var(--line))" }}
            />
            {showTooltip && <Tooltip content={<CustomTooltip />} />}
            {showLegend && <Legend />}
            {yKeyArray.map((yKey, index) => (
              <Bar
                key={yKey}
                dataKey={yKey}
                fill={colorArray[index % colorArray.length]}
                stackId={stacked ? "stack" : undefined}
                animationDuration={animationDuration}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (type === "pie") {
    return (
      <div className={cn("w-full", classNameProp)} style={{ width, height }}>
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            {showTooltip && <Tooltip content={<CustomTooltip />} />}
            {showLegend && <Legend />}
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              dataKey={yKeyArray[0]}
              nameKey={xKey}
              label={({ name, percent }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
              labelLine={false}
            >
              {data.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={colorArray[index % colorArray.length]}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return null;
}
