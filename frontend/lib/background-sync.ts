"use client";

import { useEffect } from "react";

/**
 * Registers the background sync for offline operations
 * This should be called once during app initialization
 */
export async function registerBackgroundSync(): Promise<void> {
  if (!("serviceWorker" in navigator)) {
    console.warn("[BackgroundSync] Service Worker not supported");
    return;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    // Register for background sync with 'offline-operations' tag
    // This will trigger the 'sync' event in the service worker when online
    if ("sync" in registration) {
      await registration.sync.register("offline-operations");
      console.log("[BackgroundSync] Registered for offline-operations");
    }

    // Also register for push subscription sync if needed
    if ("pushManager" in registration) {
      const subscription = await navigator.serviceWorker.ready.then((reg) =>
        reg.pushManager.getSubscription(),
      );
      if (subscription) {
        await registration.sync.register("push-subscription-sync");
        console.log("[BackgroundSync] Registered for push-subscription-sync");
      }
    }

    console.log("[BackgroundSync] Background sync registered successfully");
  } catch (error) {
    console.warn("[BackgroundSync] Failed to register background sync:", error);
  }
}

/**
 * Registers periodic background sync (requires periodic background sync API)
 * This is for periodic sync even when the app is not open
 */
export async function registerPeriodicBackgroundSync(
  intervalHours: number = 24,
): Promise<void> {
  if (!("serviceWorker" in navigator)) return;

  try {
    const registration = await navigator.serviceWorker.ready;

    if ("periodicSync" in registration) {
      await (registration as any).periodicSync.register("content-sync", {
        minInterval: intervalHours * 60 * 60 * 1000, // Convert hours to milliseconds
      });
      console.log(
        `[BackgroundSync] Periodic sync registered (${intervalHours}h interval)`,
      );
    }
  } catch (error) {
    console.warn("[BackgroundSync] Periodic sync not supported:", error);
  }
}

/**
 * Triggers an immediate sync by triggering the background sync event
 * Can be called manually when user wants to sync now
 */
export async function triggerBackgroundSync(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;

  try {
    const registration = await navigator.serviceWorker.ready;
    if ("sync" in registration) {
      await (registration as any).sync.register("offline-operations");
      console.log("[BackgroundSync] Manual sync triggered");
    }
  } catch (error) {
    console.warn("[BackgroundSync] Failed to trigger sync:", error);
  }
}

/**
 * Checks if background sync is supported
 */
export function isBackgroundSyncSupported(): boolean {
  return (
    "serviceWorker" in navigator &&
    "sync" in (navigator as any).serviceWorker.prototype
  );
}

/**
 * Gets the registration for the service worker
 */
export async function getSWRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.ready;
  } catch {
    return null;
  }
}

/**
 * Hook to register background sync on app initialization
 */
export function useBackgroundSyncRegistration(): void {
  useEffect(() => {
    registerBackgroundSync();

    // Also register periodic sync for periodic updates
    registerPeriodicBackgroundSync(24); // Daily sync
  }, []);
}
