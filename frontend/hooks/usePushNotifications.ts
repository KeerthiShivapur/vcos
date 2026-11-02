"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

interface PushSubscriptionData {
  endpoint: string;
  p256dh: string;
  auth: string;
  userAgent?: string;
}

interface PushNotificationPayload {
  title: string;
  body: string;
  icon?: string;
  badge?: string;
  image?: string;
  vibrate?: number[];
  data?: Record<string, any>;
  actions?: Array<{ action: string; title: string }>;
  tag?: string;
  renotify?: boolean;
  requireInteraction?: boolean;
  silent?: boolean;
}

interface UsePushNotificationsReturn {
  // State
  isSupported: boolean;
  permission: NotificationPermission;
  isSubscribed: boolean;
  subscription: PushSubscriptionData | null;
  vapidPublicKey: string | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  subscribe: () => Promise<void>;
  unsubscribe: () => Promise<void>;
  requestPermission: () => Promise<NotificationPermission>;
  sendTestNotification: () => Promise<void>;
  refreshSubscription: () => Promise<void>;
}

export function usePushNotifications(): UsePushNotificationsReturn {
  const { user, accessToken } = useAuth();

  const [isSupported, setIsSupported] = useState(false);
  const [permission, setPermission] =
    useState<NotificationPermission>("default");
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [subscription, setSubscription] = useState<PushSubscriptionData | null>(
    null,
  );
  const [vapidPublicKey, setVapidPublicKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize
  useEffect(() => {
    const init = async () => {
      try {
        // Check support
        const supported =
          "serviceWorker" in navigator && "PushManager" in window;
        setIsSupported(supported);

        if (!supported) {
          setError("Push notifications are not supported in this browser");
          setIsLoading(false);
          return;
        }

        // Get permission state
        const perm = await Notification.requestPermission();
        setPermission(perm);

        // Get VAPID public key
        try {
          const response = await fetch("/api/v1/push/vapid-public-key", {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (response.ok) {
            const data = await response.json();
            setVapidPublicKey(data.public_key);
          }
        } catch (e) {
          console.warn("Failed to get VAPID key:", e);
        }

        // Check existing subscription
        if (perm === "granted") {
          const registration = await navigator.serviceWorker.ready;
          const existingSubscription =
            await registration.pushManager.getSubscription();

          if (existingSubscription) {
            setIsSubscribed(true);
            setSubscription({
              endpoint: existingSubscription.endpoint,
              p256dh: arrayBufferToBase64(
                existingSubscription.getKey("p256dh")!,
              ),
              auth: arrayBufferToBase64(existingSubscription.getKey("auth")!),
            });
          }
        }
      } catch (e) {
        console.error("Push init error:", e);
        setError("Failed to initialize push notifications");
      } finally {
        setIsLoading(false);
      }
    };

    init();
  }, [accessToken]);

  // Convert ArrayBuffer to base64
  const arrayBufferToBase64 = useCallback((buffer: ArrayBuffer): string => {
    return btoa(String.fromCharCode(...new Uint8Array(buffer)));
  }, []);

  // Convert base64 to Uint8Array
  const base64ToUint8Array = useCallback((base64: string): Uint8Array => {
    const padding = "=".repeat((4 - (base64.length % 4)) % 4);
    const base64Padded = base64 + padding;
    const binary = atob(base64Padded);
    return new Uint8Array([...binary].map((c) => c.charCodeAt(0)));
  }, []);

  // Request permission
  const requestPermission =
    useCallback(async (): Promise<NotificationPermission> => {
      if (!isSupported) return "denied";

      try {
        const perm = await Notification.requestPermission();
        setPermission(perm);
        return perm;
      } catch (e) {
        setError("Failed to request permission");
        return "denied";
      }
    }, [isSupported]);

  // Subscribe to push
  const subscribe = useCallback(async () => {
    if (!isSupported || !vapidPublicKey) {
      setError("Push not supported or VAPID key not available");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Request permission if needed
      if (permission !== "granted") {
        const perm = await Notification.requestPermission();
        setPermission(perm);
        if (perm !== "granted") {
          setError("Permission denied");
          return;
        }
      }

      const registration = await navigator.serviceWorker.ready;

      // Subscribe with VAPID key
      const pushSubscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64ToUint8Array(vapidPublicKey),
      });

      // Convert keys to base64
      const p256dh = arrayBufferToBase64(pushSubscription.getKey("p256dh")!);
      const auth = arrayBufferToBase64(pushSubscription.getKey("auth")!);

      const subscriptionData: PushSubscriptionData = {
        endpoint: pushSubscription.endpoint,
        p256dh,
        auth,
        userAgent: navigator.userAgent,
      };

      // Send to backend
      const response = await fetch("/api/v1/push/subscribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(subscriptionData),
      });

      if (!response.ok) {
        throw new Error("Failed to register subscription");
      }

      setIsSubscribed(true);
      setSubscription(subscriptionData);

      // Notify service worker
      if (registration.active) {
        registration.active.postMessage({
          type: "SET_AUTH_TOKEN",
          token: accessToken,
        });
      }
    } catch (e) {
      console.error("Subscribe error:", e);
      setError(e instanceof Error ? e.message : "Failed to subscribe");
    } finally {
      setIsLoading(false);
    }
  }, [
    isSupported,
    vapidPublicKey,
    permission,
    accessToken,
    base64ToUint8Array,
  ]);

  // Unsubscribe
  const unsubscribe = useCallback(async () => {
    if (!isSupported || !subscription) return;

    setIsLoading(true);
    setError(null);

    try {
      const registration = await navigator.serviceWorker.ready;
      const pushSubscription = await registration.pushManager.getSubscription();

      if (pushSubscription) {
        await pushSubscription.unsubscribe();
      }

      // Notify backend
      await fetch("/api/v1/push/subscriptions", {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });

      setIsSubscribed(false);
      setSubscription(null);
    } catch (e) {
      console.error("Unsubscribe error:", e);
      setError(e instanceof Error ? e.message : "Failed to unsubscribe");
    } finally {
      setIsLoading(false);
    }
  }, [isSupported, subscription, accessToken]);

  // Send test notification
  const sendTestNotification = useCallback(async () => {
    if (!isSubscribed) return;

    try {
      await fetch("/api/v1/push/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          user_ids: [user?.id],
          title: "VCOS Test Notification",
          body: "Push notifications are working correctly!",
          icon: "/icon-192.png",
          badge: "/icon-72.png",
          data: { test: true },
        }),
      });
    } catch (e) {
      console.error("Test notification error:", e);
    }
  }, [isSubscribed, accessToken, user?.id]);

  // Refresh subscription
  const refreshSubscription = useCallback(async () => {
    if (!isSupported) return;

    try {
      const registration = await navigator.serviceWorker.ready;
      const pushSubscription = await registration.pushManager.getSubscription();

      if (pushSubscription) {
        setIsSubscribed(true);
        setSubscription({
          endpoint: pushSubscription.endpoint,
          p256dh: arrayBufferToBase64(pushSubscription.getKey("p256dh")!),
          auth: arrayBufferToBase64(pushSubscription.getKey("auth")!),
        });
      } else {
        setIsSubscribed(false);
        setSubscription(null);
      }
    } catch (e) {
      console.error("Refresh subscription error:", e);
    }
  }, [isSupported, arrayBufferToBase64]);

  return {
    // State
    isSupported,
    permission,
    isSubscribed,
    subscription,
    vapidPublicKey,
    isLoading,
    error,

    // Actions
    subscribe,
    unsubscribe,
    requestPermission,
    sendTestNotification,
    refreshSubscription,
  };
}

// Helper hook for sending notifications from components
export function useSendNotification() {
  const { accessToken } = useAuth();

  const send = useCallback(
    async (userIds: string[], payload: PushNotificationPayload) => {
      const response = await fetch("/api/v1/push/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ user_ids: userIds, ...payload }),
      });

      return response.json();
    },
    [accessToken],
  );

  return { send };
}

// Hook for organization-wide notifications
export function useOrganizationNotification() {
  const { accessToken } = useAuth();

  const send = useCallback(
    async (payload: PushNotificationPayload, filterRole?: string) => {
      const response = await fetch("/api/v1/push/send/organization", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ ...payload, filter_role: filterRole }),
      });

      return response.json();
    },
    [accessToken],
  );

  return { send };
}
