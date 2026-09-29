import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari's own flag; not covered by the media query above.
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

function isIos(): boolean {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

/**
 * Chrome/Edge/Samsung Internet fire `beforeinstallprompt` and let a page
 * trigger the native install UI on demand. iOS Safari does neither -- there
 * is no programmatic install prompt there, only the manual Share -> "Add to
 * Home Screen" path -- so this hook also reports `platform: "ios"` so the
 * UI can show instructions instead of a button that would do nothing.
 */
export function useInstallPrompt() {
  const [deferredEvent, setDeferredEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(isStandalone());

  useEffect(() => {
    function onBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      setDeferredEvent(event as BeforeInstallPromptEvent);
    }
    function onInstalled() {
      setInstalled(true);
      setDeferredEvent(null);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const platform: "installable" | "ios" | "unsupported" = installed
    ? "unsupported"
    : deferredEvent
      ? "installable"
      : isIos()
        ? "ios"
        : "unsupported";

  async function promptInstall() {
    if (!deferredEvent) return;
    await deferredEvent.prompt();
    const choice = await deferredEvent.userChoice;
    if (choice.outcome === "accepted") setInstalled(true);
    setDeferredEvent(null);
  }

  return { installed, platform, promptInstall };
}
