"use client";

import { createContext, useContext, useEffect, ReactNode } from "react";
import { useOfflineSync } from "@/hooks/useOfflineSync";
import { useOfflineNotifications } from "@/hooks/useOfflineSync";
import { useAuth } from "@/hooks/useAuth";

interface OfflineContextType {
  isOnline: boolean;
  isSyncing: boolean;
  pendingChanges: number;
  pendingSyncItems: number;
  lastSyncTime: number | null;
  syncError: string | null;
  lastSyncStatus: "idle" | "syncing" | "completed" | "failed";
  syncNow: () => void;
  goOffline: () => void;
  goOnline: () => void;
  unreadNotifications: number;
  notifications: any[];
  markNotificationRead: (id: string) => void;
  refreshCounts: () => void;
}

const OfflineContext = createContext<OfflineContextType | null>(null);

export function OfflineProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();

  const {
    isOnline: hookIsOnline,
    isSyncing,
    pendingChanges,
    pendingSyncItems,
    lastSyncTime,
    syncError,
    lastSyncStatus,
    syncNow,
    goOffline,
    goOnline,
    refreshCounts,
  } = useOfflineSync({
    organizationId: "default", // Will be replaced with actual org ID from auth
    autoSync: true,
    syncInterval: 30000,
  });

  const { unreadNotifications, notifications, markNotificationRead } =
    useOfflineNotifications();

  // Register service worker
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js")
        .then((registration) => {
          console.log("[OfflineProvider] SW registered:", registration.scope);

          // Listen for updates
          registration.addEventListener("updatefound", () => {
            const newWorker = registration.installing;
            newWorker?.addEventListener("statechange", () => {
              if (
                newWorker.state === "installed" &&
                navigator.serviceWorker.controller
              ) {
                // New version available - could show update prompt
                console.log("[OfflineProvider] New SW version available");
              }
            });
          });
        })
        .catch((error) => {
          console.error("[OfflineProvider] SW registration failed:", error);
        });
    }
  }, []);

  // Send auth token to Service Worker when it changes
  useEffect(() => {
    if ("serviceWorker" in navigator && accessToken) {
      navigator.serviceWorker.ready.then((registration) => {
        if (registration.active) {
          registration.active.postMessage({
            type: "SET_AUTH_TOKEN",
            token: accessToken,
          });
          console.log("[OfflineProvider] Sent auth token to SW");
        }
      });
    }
  }, [accessToken]);

  // Register background sync for offline operations
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.ready.then((registration) => {
        if ("sync" in registration) {
          registration.sync
            .register("offline-operations")
            .then(() =>
              console.log(
                "[OfflineProvider] Background sync registered for offline-operations",
              ),
            )
            .catch((err) =>
              console.warn(
                "[OfflineProvider] Background sync registration failed:",
                err,
              ),
            );
        }
      });
    }
  }, []);

  // Listen for online/offline events
  useEffect(() => {
    const handleOnline = () => {
      console.log("[OfflineProvider] Online");
    };
    const handleOffline = () => {
      console.log("[OfflineProvider] Offline");
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // Periodically refresh counts
  useEffect(() => {
    const interval = setInterval(() => {
      refreshCounts();
    }, 10000); // Every 10 seconds

    return () => clearInterval(interval);
  }, [refreshCounts]);

  const value = {
    isOnline: navigator.onLine, // Use actual navigator state
    isSyncing,
    pendingChanges,
    pendingSyncItems,
    lastSyncTime,
    syncError,
    lastSyncStatus,
    syncNow,
    goOffline,
    goOnline,
    unreadNotifications,
    notifications,
    markNotificationRead,
    refreshCounts,
  };

  return (
    <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>
  );
}

export function useOffline() {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error("useOffline must be used within an OfflineProvider");
  }
  return context;
}

// Hook for sync status display
export function useSyncStatus() {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error("useSyncStatus must be used within an OfflineProvider");
  }
  return {
    isOnline: context.isOnline,
    isSyncing: context.isSyncing,
    pendingChanges: context.pendingChanges,
    pendingSyncItems: context.pendingSyncItems,
    lastSyncTime: context.lastSyncTime,
    syncError: context.syncError,
    lastSyncStatus: context.lastSyncStatus,
  };
}

// Hook for offline notifications
export function useOfflineNotificationsContext() {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error(
      "useOfflineNotificationsContext must be used within an OfflineProvider",
    );
  }
  return {
    unreadNotifications: context.unreadNotifications,
    notifications: context.notifications,
    markNotificationRead: context.markNotificationRead,
  };
}
