import { useEffect, useRef, useState } from "react";
import { Button } from "./Button";
import { ProgressState } from "./ProgressState";
import { api, downloadFile } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { pollTailoredDocumentUntilTerminal } from "../lib/tailoringPolling";
import type { TailoredDocumentOut } from "../types/api";

interface ApplyCvChoiceModalProps {
  listingId: string;
  onContinueWithCurrent: () => void;
  onTailoredReady: (tailoredDocumentId: string) => void;
  onClose: () => void;
}

type Phase = "choice" | "generating" | "ready";

/**
 * Shown before every apply action -- both the "Apply" button (email/
 * ats_link listings) and "Mark as applied" (manual/DPSA listings). Never
 * shown at all when the caller has already determined there's no ready CV
 * to choose between (see ListingDetail's cvReady check) -- offering a
 * choice between two options when only the "upload a CV first" path is
 * actually usable would be a broken modal, not a real choice.
 *
 * Generation failure returns to the choice view (with an inline error)
 * rather than falling through to a failed apply call -- the user always
 * lands back on a screen with both options still available, never on a
 * dead end. Reaching "ready" doesn't proceed automatically either: the
 * links here are the only chance to grab the file before the apply call
 * fires (Track has a persistent download link afterward too, but this is
 * the moment someone's actually looking at it).
 */
export function ApplyCvChoiceModal({ listingId, onContinueWithCurrent, onTailoredReady, onClose }: ApplyCvChoiceModalProps) {
  const [phase, setPhase] = useState<Phase>("choice");
  const [error, setError] = useState<string | null>(null);
  const [readyDocument, setReadyDocument] = useState<TailoredDocumentOut | null>(null);
  const cancelPollRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => cancelPollRef.current?.();
  }, []);

  async function handleGenerateTailored() {
    setError(null);
    setPhase("generating");
    try {
      const document = await api.post<TailoredDocumentOut>(
        "/tailored-documents",
        { listing_id: listingId },
        { headers: { "Idempotency-Key": crypto.randomUUID() } },
      );
      const { promise, cancel } = pollTailoredDocumentUntilTerminal(document.id);
      cancelPollRef.current = cancel;
      const finished = await promise;
      cancelPollRef.current = null;
      if (finished.status === "ready") {
        setReadyDocument(finished);
        setPhase("ready");
      } else {
        setPhase("choice");
        setError("Couldn't generate a tailored CV right now. You can try again, or continue with your current CV.");
      }
    } catch (err) {
      setPhase("choice");
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't generate a tailored CV right now.");
    }
  }

  function handleBack() {
    cancelPollRef.current?.();
    cancelPollRef.current = null;
    setPhase("choice");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 px-4 pb-4 sm:items-center sm:pb-0">
      <div className="w-full max-w-sm rounded-2xl bg-paper p-5 shadow-lg">
        {phase === "generating" && (
          <>
            <ProgressState label="Generating your tailored CV..." />
            <button
              onClick={handleBack}
              className="mt-4 w-full font-body text-sm font-semibold text-ink/60 hover:text-ink"
            >
              Back
            </button>
          </>
        )}

        {phase === "ready" && readyDocument && (
          <>
            <h2 className="font-display text-lg font-black tracking-tight text-ink">Your tailored CV is ready</h2>
            <p className="mt-1 font-body text-sm text-ink/60">
              Grab a copy now if you want one, or just continue -- it'll be attached to this application either way.
            </p>
            <div className="mt-4 flex flex-col gap-2">
              <button
                onClick={() => downloadFile(`/tailored-documents/${readyDocument.id}/download?kind=cv`, "Phanda_Tailored_CV.pdf")}
                className="font-body text-sm font-semibold text-phanda-green-dark hover:underline"
              >
                Download your tailored CV
              </button>
              <button
                onClick={() =>
                  downloadFile(`/tailored-documents/${readyDocument.id}/download?kind=cover_letter`, "Cover_Letter.pdf")
                }
                className="font-body text-sm font-semibold text-phanda-green-dark hover:underline"
              >
                Download your cover letter
              </button>
            </div>
            <Button className="mt-5 w-full" onClick={() => onTailoredReady(readyDocument.id)}>
              Continue
            </Button>
          </>
        )}

        {phase === "choice" && (
          <>
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-display text-lg font-black tracking-tight text-ink">Which CV do you want to use?</h2>
              <button
                onClick={onClose}
                aria-label="Close"
                className="shrink-0 font-body text-sm text-ink/40 hover:text-ink/70"
              >
                &times;
              </button>
            </div>

            {error && (
              <div className="mt-3 rounded-[10px] bg-signal-soft px-4 py-3">
                <p className="font-body text-sm font-medium text-signal">{error}</p>
              </div>
            )}

            <div className="mt-4 flex flex-col gap-3">
              <Button variant="secondary" className="w-full" onClick={onContinueWithCurrent}>
                Continue with your current CV
              </Button>

              <div>
                <Button className="w-full" onClick={handleGenerateTailored}>
                  Generate a tailored CV
                </Button>
                <p className="mt-1.5 text-center font-body text-xs text-ink/50">
                  Generating a tailored CV increases your chances of acceptance.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
