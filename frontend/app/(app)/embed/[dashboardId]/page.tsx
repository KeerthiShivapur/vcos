"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { X, ExternalLink, Download, BarChart2, Share2, Filter, Maximize2, Minimize2, RefreshCw, Settings } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Tooltip } from "@/components/ui/Tooltip";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";

export default function EmbeddedDashboardPage() {
  const [iframeSrc, setIframeSrc] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "auto">("auto");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = searchParams;
    const token = params.get("token");
    const dashboardId = params.get("dashboardId") || "default";

    if (!token) {
      setHasError(true);
      setIsLoading(false);
      return;
    }

    const baseUrl = window.location.origin;
    const src = `${baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
    setIframeSrc(src);
  }, [searchParams]);

  const handleLoad = () => {
    setIsLoading(false);
  };

  const handleError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  const handleMessage = (event: MessageEvent) => {
    if (event.data.type === "vcos:resize" && iframeRef.current) {
      iframeRef.current.style.height = `${event.data.height}px`;
    }
  };

  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  const handleFullscreen = () => {
    if (iframeRef.current) {
      if (!isFullscreen) {
        iframeRef.current.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const handleRefresh = () => {
    if (iframeRef.current) {
      iframeRef.current.src = iframeRef.current.src;
    }
  };

  const exportData = () => {
    if (iframeRef.current) {
      iframeRef.current.contentWindow?.postMessage({ type: "vcos:export" }, "*");
    }
  };

  const shareDashboard = () => {
    const url = window.location.href;
    navigator.clipboard.writeText(url);
  };

  if (hasError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] px-4">
        <div className="text-center p-8 max-w-md">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-danger/10 flex items-center justify-center">
            <svg className="w-8 h-8 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-ink mb-2">Unable to load dashboard</h3>
          <p className="text-sm text-muted mb-6">The embedded dashboard could not be loaded. The token may be invalid or expired.</p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-brand text-white rounded-lg font-medium hover:bg-brand/90 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Bar */}
      <header className="fixed top-0 left-0 right-0 z-40 bg-white border-b border-slate-200 px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div className="min-w-0">
              <h1 className="font-semibold text-slate-900 truncate">Embedded Dashboard</h1>
              <p className="text-xs text-slate-500">VCOS Embedded Analytics</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Tooltip content="Refresh data">
              <button
                onClick={handleRefresh}
                disabled={isLoading}
                className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label="Refresh"
              >
                <RefreshCw className={`w-5 h-5 ${isLoading ? "animate-spin" : ""}`} />
              </button>
            </Tooltip>

            <Tooltip content="Export data">
              <button onClick={exportData} className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors" aria-label="Export">
                <Download className="w-5 h-5" />
              </button>
            </Tooltip>

            <Tooltip content="Share dashboard">
              <button onClick={shareDashboard} className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors" aria-label="Share">
                <Share2 className="w-5 h-5" />
              </button>
            </Tooltip>

            <Tooltip content="Settings">
              <button
                onClick={() => setShowSettings(true)}
                className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label="Settings"
              >
                <Settings className="w-5 h-5" />
              </button>
            </Tooltip>

            <Tooltip content={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}>
              <button
                onClick={handleFullscreen}
                className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              >
                {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
              </button>
            </Tooltip>

            <Tooltip content="Open in new tab">
              <a
                href={window.location.href}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label="Open in new tab"
              >
                <ExternalLink className="w-5 h-5" />
              </a>
            </Tooltip>
          </div>
        </div>
      </header>

      {/* Settings Panel */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowSettings(false)} />
          <div className="relative w-full max-w-md bg-white rounded-t-2xl shadow-xl p-6 animate-slide-up">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-slate-900">Embed Settings</h2>
              <button onClick={() => setShowSettings(false)} className="p-2 text-slate-500 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Theme</label>
                <div className="flex gap-2">
                  {["light", "dark", "auto"].map((t) => (
                    <button
                      key={t}
                      onClick={() => setTheme(t as "light" | "dark" | "auto")}
                      className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                        theme === t
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Height</label>
                <input
                  type="number"
                  min="400"
                  max="2000"
                  step="50"
                  defaultValue={600}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                />
              </div>

              <div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span className="text-sm text-slate-700">Auto-refresh (5 min)</span>
                </label>
              </div>

              <div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span className="text-sm text-slate-700">Allow fullscreen</span>
                </label>
              </div>

              <div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span className="text-sm text-slate-700">Allow export</span>
                </label>
              </div>

              <div className="pt-4 border-t border-slate-200">
                <button
                  onClick={() => setShowSettings(false)}
                  className="w-full py-2 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Save & Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Iframe */}
      <div className="relative">
        {isLoading && (
          <div className="absolute inset-0 bg-slate-50/80 flex items-center justify-center z-10">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-3 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Loading dashboard...</p>
            </div>
          </div>
        )}

        {hasError && (
          <div className="flex items-center justify-center min-h-[60vh] p-4">
            <div className="text-center p-8 max-w-md">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">Unable to load dashboard</h3>
              <p className="text-sm text-slate-500 mb-6">The embedded dashboard could not be loaded. The token may be invalid or expired.</p>
              <button
                onClick={() => window.location.reload()}
                className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        )}

        <iframe
          ref={iframeRef}
          src={iframeSrc}
          width="100%"
          height={isFullscreen ? "100vh" : "calc(100vh - 64px)"}
          className={`vcos-embed-iframe w-full rounded-xl border border-slate-200 bg-white ${
            isFullscreen ? "fixed inset-0 z-50 rounded-none" : ""
          }`}
          frameBorder="0"
          allowFullScreen
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
          onLoad={handleLoad}
          onError={handleError}
          title="VCOS Embedded Analytics"
          allow="fullscreen"
          style={{
            border: "none",
            width: "100%",
            height: isFullscreen ? "100vh" : "calc(100vh - 64px)",
            minHeight: "400px",
            borderRadius: isFullscreen ? "0" : "0.75rem",
          }}
        />

        {isLoading && !hasError && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-10">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-3 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Loading dashboard...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}