import { api } from "./api";
import type { TailoredDocumentOut, TailoredDocumentStatus } from "../types/api";

const POLL_INTERVAL_MS = 2000;
const TERMINAL: TailoredDocumentStatus[] = ["ready", "failed", "cancelled"];

/**
 * Same shape as onboarding/cvPolling.ts's pollCvVersionUntilTerminal --
 * polls GET /tailored-documents/{id} until a terminal status, retrying
 * silently on a transient network error, with a cancel() for a caller that
 * backs out mid-generation (the apply-flow CV-choice modal, when the user
 * taps "back" while a tailored CV is still being generated).
 */
export function pollTailoredDocumentUntilTerminal(
  documentId: string,
  onStatusChange?: (status: TailoredDocumentStatus) => void,
): { promise: Promise<TailoredDocumentOut>; cancel: () => void } {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const promise = new Promise<TailoredDocumentOut>((resolve) => {
    const tick = () => {
      timer = setTimeout(async () => {
        if (cancelled) return;
        try {
          const document = await api.get<TailoredDocumentOut>(`/tailored-documents/${documentId}`);
          if (cancelled) return;
          if (TERMINAL.includes(document.status)) {
            resolve(document);
            return;
          }
          onStatusChange?.(document.status);
        } catch {
          // transient -- keep polling on the same schedule
        }
        if (!cancelled) tick();
      }, POLL_INTERVAL_MS);
    };
    tick();
  });

  return {
    promise,
    cancel: () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    },
  };
}
