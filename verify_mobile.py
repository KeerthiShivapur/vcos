import os

print("=== Mobile/PWA Implementation Verification ===")
print()

checks = [
    ("Service Worker", "D:/vcos1/workspace/vcos/frontend/public/sw.js"),
    ("Offline Page", "D:/vcos1/workspace/vcos/frontend/public/offline.html"),
    ("PWA Manifest", "D:/vcos1/workspace/vcos/frontend/public/manifest.json"),
    ("Capacitor Config", "D:/vcos1/workspace/vcos/frontend/capacitor.config.ts"),
    ("PWA Install Prompt", "D:/vcos1/workspace/vcos/frontend/components/pwa/PWAInstallPrompt.tsx"),
    ("Mobile App Shell", "D:/vcos1/workspace/vcos/frontend/components/layout/MobileAppShell.tsx"),
    ("Native Bridge", "D:/vcos1/workspace/vcos/frontend/lib/native-bridge.ts"),
    ("Native Bridge Hook", "D:/vcos1/workspace/vcos/frontend/hooks/useNativeBridge.ts"),
    ("Push Notification Hook", "D:/vcos1/workspace/vcos/frontend/hooks/usePushNotifications.ts"),
    ("PWA Asset Generator", "D:/vcos1/workspace/vcos/frontend/scripts/generate-pwa-assets.js"),
]

all_passed = True
for name, path in checks:
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"[OK] {name}: {path} ({size} bytes)")
    else:
        print(f"[MISSING] {name}: {path}")
        all_passed = False

print()
if all_passed:
    print("=== ALL CHECKS PASSED ===")
else:
    print("=== SOME CHECKS FAILED ===")