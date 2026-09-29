import { api } from "../../lib/api";
import type { CvVersionOut, CvVersionStatus } from "../../types/api";

const POLL_INTERVAL_MS = 2000;

/**
 * Polls GET /profile/cv-versions/{id} until it reaches a terminal status,
 * retrying silently on a transient network error -- the CV is still being
 * processed server-side regardless of one dropped poll.
 *
 * Returns a cancel() alongside the promise so a caller whose component
 * unmounts mid-poll (the user clicked "Skip for now" on the CV screen
 * while it was still extracting) can stop the chain rather than leaving it
 * running against an unmounted component.
 *
 * onStatusChange fires on every non-terminal tick, letting a caller show
 * the intermediate "uploaded" -> "extracting" transition; callers that
 * don't need that nuance (the combined signup wizard just shows one
 * "setting things up" label throughout) can omit it.
 */
export function pollCvVersionUntilTerminal(
  cvVersionId: string,
  onStatusChange?: (status: CvVersionStatus) => void,
): { promise: Promise<CvVersionOut>; cancel: () => void } {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const promise = new Promise<CvVersionOut>((resolve) => {
    const tick = () => {
      timer = setTimeout(async () => {
        if (cancelled) return;
        try {
          const version = await api.get<CvVersionOut>(`/profile/cv-versions/${cvVersionId}`);
          if (cancelled) return;
          if (version.status === "ready" || version.status === "failed") {
            resolve(version);
            return;
          }
          onStatusChange?.(version.status);
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
