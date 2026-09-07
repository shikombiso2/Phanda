import { useState } from "react";
import { useInstallPrompt } from "../hooks/useInstallPrompt";
import { DownloadToPhoneIcon } from "./icons";

/** The actual installability affordance the spec calls for -- a manifest
 * and service worker alone leave the feature undiscoverable. Renders
 * nothing once the app is already installed, or on a browser that supports
 * neither the native prompt nor a clear manual path. */
export function InstallButton({ variant = "compact" }: { variant?: "compact" | "hero" }) {
  const { platform, promptInstall } = useInstallPrompt();
  const [showIosSteps, setShowIosSteps] = useState(false);

  if (platform === "unsupported") return null;

  const label = variant === "hero" ? "Install Phanda on your phone" : "Install app";

  if (platform === "ios") {
    return (
      <div className="relative">
        <button
          onClick={() => setShowIosSteps((v) => !v)}
          className="inline-flex items-center gap-2 rounded-[10px] border border-hairline px-4 py-2.5 font-body text-sm font-semibold text-ink hover:border-ink"
        >
          <DownloadToPhoneIcon className="h-4 w-4" />
          {label}
        </button>
        {showIosSteps && (
          <div className="absolute left-0 top-full z-10 mt-2 w-64 rounded-[10px] border border-hairline bg-paper p-4 text-sm text-ink shadow-lg">
            <p className="font-medium">On iPhone or iPad:</p>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-ink/80">
              <li>Tap the Share icon in Safari</li>
              <li>Choose "Add to Home Screen"</li>
            </ol>
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={promptInstall}
      className={
        variant === "hero"
          ? "inline-flex items-center gap-2 rounded-[10px] border border-hairline px-5 py-3 font-body text-[15px] font-semibold text-ink hover:border-ink"
          : "inline-flex items-center gap-2 rounded-[10px] border border-hairline px-4 py-2.5 font-body text-sm font-semibold text-ink hover:border-ink"
      }
    >
      <DownloadToPhoneIcon className="h-4 w-4" />
      {label}
    </button>
  );
}
