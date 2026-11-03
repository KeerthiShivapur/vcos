"use client";

import { useState, useCallback, useRef, useEffect } from 'react';
import { 
  Monitor, 
  MonitorOff, 
  Mic, 
  MicOff, 
  X, 
  Maximize2, 
  Minimize2,
  Share2,
  AlertCircle,
  CheckCircle
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface ScreenSharePreviewProps {
  stream: MediaStream | null;
  isSharing: boolean;
  onStop: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
  isMinimized?: boolean;
  className?: string;
}

function ScreenSharePreviewContent({
  stream,
  isMinimized,
  onStop,
  onMinimize,
  onMaximize,
  className,
}: ScreenSharePreviewProps & { stream: MediaStream }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>
      {/* Preview Header */}
      <div className={classNames(
        "flex items-center justify-between px-3 py-2 bg-black/80 text-white border-b border-line",
        isMinimized && "px-2 py-1"
      )}>
        <div className="flex items-center gap-2">
          <span className={classNames(
            "flex items-center gap-1.5 text-xs font-medium",
            "text-green-400"
          )}>
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Sharing Screen
          </span>
        </div>
        <div className="flex items-center gap-1">
          {!isMinimized && (
            <button
              onClick={onMinimize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Minimize"
            >
              <Minimize2 className="h-4 w-4" />
            </button>
          )}
          {isMinimized && (
            <button
              onClick={onMaximize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Maximize"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onStop}
            className="p-1.5 rounded hover:bg-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors"
            aria-label="Stop sharing"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Video Preview */}
      <div className={classNames(
        "relative w-full h-full bg-black",
        isMinimized ? "h-20" : "h-full"
      )}>
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="w-full h-full object-cover"
        />
      </div>
    </div>
  );
}

export function ScreenSharePreview({
  stream,
  isSharing,
  onStop,
  onMinimize,
  onMaximize,
  className,
}: ScreenSharePreviewProps) {
  const [isMinimized, setIsMinimized] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  if (!isSharing || !stream) return null;

  return (
    <ScreenSharePreviewContent
      stream={stream}
      isSharing={true}
      isMinimized={isMinimized}
      onStop={onStop}
      onMinimize={onMinimize}
      onMaximize={onMaximize}
      className={className}
    />
  );
}

// Main Screen Share Button Component
export function ScreenShareButton({
  onStart,
  onStop,
  isSharing,
  disabled = false,
  className,
}: {
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  isSharing: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <button
      onClick={isSharing ? onStop : onStart}
      disabled={disabled}
      className={classNames(
        "flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200",
        "focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2",
        disabled ? "opacity-50 cursor-not-allowed" : "",
        isSharing 
          ? "bg-red-100 text-red-600 hover:bg-red-200 border border-red-200 animate-pulse" 
          : "bg-brand text-white hover:bg-brand-strong",
        className
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      aria-label={isSharing ? "Stop screen sharing" : "Start screen sharing"}
    >
      <Share2 className={classNames("h-4 w-4", isHovered && "animate-pulse")} />
      <span className="font-medium">
        {isSharing ? "Stop Sharing" : "Share Screen"}
      </span>
      {isSharing && (
        <span className="flex items-center gap-1 text-xs animate-pulse">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
          LIVE
        </span>
      )}
    </button>
  );
}

// Screen Share Selector Modal
interface ScreenShareSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (sourceId: string, displaySurface: string) => void;
}

export function ScreenShareSelector({ isOpen, onClose, onSelect }: ScreenShareSelectorProps) {
  const [sources, setSources] = useState<Array<{
    id: string;
    name: string;
    thumbnail: string;
    displaySurface: string;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const loadSources = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const mediaDevices = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: false,
        });
        
        mediaDevices.getTracks().forEach(track => track.stop());

        const allSources = await navigator.mediaDevices.enumerateDevices();
        const videoSources = allSources.filter(device => device.kind === 'videoinput');
        
        const sourceData = await Promise.all(
          videoSources.map(async (device) => {
            try {
              const stream = await navigator.mediaDevices.getUserMedia({
                video: { deviceId: { exact: device.deviceId } },
              });
              const video = document.createElement('video');
              video.srcObject = stream;
              video.play();
              await new Promise(resolve => {
                video.onloadeddata = resolve;
              });
              const canvas = document.createElement('canvas');
              canvas.width = 160;
              canvas.height = 90;
              canvas.getContext('2d')?.drawImage(video, 0, 0, 160, 90);
              const thumbnail = canvas.toDataURL('image/jpeg', 0.8);
              stream.getTracks().forEach(track => track.stop());
              
              return {
                id: device.deviceId,
                name: device.label || `Screen ${videoSources.indexOf(device) + 1}`,
                thumbnail,
                displaySurface: 'window',
              };
            } catch {
              return null;
            }
          })
        );
        
        setSources(sourceData.filter(Boolean) as Array<{ id: string; name: string; thumbnail: string; displaySurface: string }>);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load screen sources');
      } finally {
        setLoading(false);
      }
    };

    loadSources();
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold">Select Screen to Share</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        
        <div className="p-4 max-h-[60vh] overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
            </div>
          )}
          
          {error && (
            <div className="text-center text-red-500 py-8">
              <AlertCircle className="h-12 w-12 mx-auto mb-2" />
              <p>{error}</p>
              <button
                onClick={() => onClose()}
                className="mt-4 px-4 py-2 bg-brand text-white rounded-lg hover:bg-brand-strong"
              >
                Close
              </button>
            </div>
          )}
          
          {!loading && !error && sources.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {sources.map((source) => (
                <button
                  key={source.id}
                  onClick={() => {
                    onSelect(source.id, source.displaySurface);
                    onClose();
                  }}
                  className="relative group cursor-pointer rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700 hover:border-brand transition-all"
                >
                  <div className="aspect-video relative">
                    <img
                      src={source.thumbnail}
                      alt={source.name}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <span className="px-4 py-2 bg-brand text-white rounded-lg font-medium">
                        Share
                      </span>
                    </div>
                    <div className="absolute bottom-2 left-2 right-2">
                      <div className="bg-black/70 text-white px-3 py-1 rounded text-sm truncate">
                        {source.name}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
          
          {!loading && !error && sources.length === 0 && (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
              <MonitorOff className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No screens available to share</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}