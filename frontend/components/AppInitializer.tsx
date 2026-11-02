"use client";

import { useEffect } from "react";
import {
  registerBackgroundSync,
  registerPeriodicBackgroundSync,
} from "@/lib/background-sync";

/**
 * AppInitializer component
 * Registers background sync and periodic sync on app load
 * Should be rendered once at the root of the app
 */
export function AppInitializer() {
  useEffect(() => {
    // Register background sync for offline operations
    registerBackgroundSync();

    // Register periodic background sync (daily)
    registerPeriodicBackgroundSync(24); // Daily sync

    // Also register for push subscription sync
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.ready.then((registration) => {
        if ("sync" in registration) {
          registration.sync
            .register("push-subscription-sync")
            .then(() =>
              console.log("[AppInit] Push subscription sync registered"),
            )
            .catch((err) =>
              console.warn(
                "[AppInit] Push subscription sync registration failed:",
                err,
              ),
            );
        }
      });
    }
  }, []);

  return null; // This component doesn't render anything
}
