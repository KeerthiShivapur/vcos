"use client";

import { useEffect, useState } from "react";

interface EmbeddedDashboardProps {
  dashboardId: string;
  token: string;
  baseUrl?: string;
  width?: string;
  height?: string;
  className?: string;
  onLoad?: () => void;
  onError?: (error: Error) => void;
  allowFullscreen?: boolean;
}

export function EmbeddedDashboard({
  dashboardId,
  token,
  baseUrl,
  width = "100%",
  height = "600px",
  className = "",
  onLoad,
  onError,
  allowFullscreen = true,
}: EmbeddedDashboardProps) {
  const [iframeSrc, setIframeSrc] = useState<string>("");

  useEffect(() => {
    const base = baseUrl || window.location.origin;
    const src = `${base}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
    setIframeSrc(src);
  }, [dashboardId, token, baseUrl]);

  return (
    <iframe
      src={iframeSrc}
      width={width}
      height={height}
      className={`vcos-embed-iframe ${className}`}
      frameBorder="0"
      allowFullScreen={allowFullscreen}
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
      style={{ border: "none", width, height, minHeight: "400px" }}
      onLoad={onLoad}
      onError={(e) => onError?.(new Error("Failed to load embedded dashboard"))}
      title="VCOS Embedded Analytics"
    />
  );
}