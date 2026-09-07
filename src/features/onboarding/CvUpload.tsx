import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppHeader } from "../../components/AppHeader";
import { Button } from "../../components/Button";
import { CheckIcon, SpinnerIcon, UploadIcon } from "../../components/icons";
import { api } from "../../lib/api";
import { ApiError } from "../../lib/apiError";
import { useAuthStore } from "../../store/authStore";
import type { CvUploadOut, CvVersionOut, CvVersionStatus } from "../../types/api";

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED = [".pdf", ".docx", ".txt"];
const POLL_INTERVAL_MS = 2000;

type FlowState =
  | { phase: "picking" }
  | { phase: "uploading" }
  | { phase: "polling"; cvVersionId: string; status: CvVersionStatus }
  | { phase: "done"; status: "ready" | "failed"; failureCode: string | null };

export function CvUpload() {
  const navigate = useNavigate();
  const reloadProfile = useAuthStore((s) => s.reloadProfile);
  const [flow, setFlow] = useState<FlowState>({ phase: "picking" });
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  const pollStatus = useCallback(
    (cvVersionId: string) => {
      pollTimer.current = setTimeout(async () => {
        try {
          const version = await api.get<CvVersionOut>(`/profile/cv-versions/${cvVersionId}`);
          if (version.status === "ready" || version.status === "failed") {
            setFlow({ phase: "done", status: version.status, failureCode: version.failure_code });
            if (version.status === "ready") await reloadProfile();
            return;
          }
          setFlow({ phase: "polling", cvVersionId, status: version.status });
          pollStatus(cvVersionId);
        } catch {
          // A transient network hiccup while polling shouldn't kill the
          // flow -- keep trying on the same schedule rather than failing
          // a CV that's still being processed server-side.
          pollStatus(cvVersionId);
        }
      }, POLL_INTERVAL_MS);
    },
    [reloadProfile],
  );

  async function handleFile(file: File) {
    setError(null);
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED.includes(extension)) {
      setError("Upload a PDF, Word (.docx) or plain text CV.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("That file is too big. Keep it under 5MB.");
      return;
    }

    setFlow({ phase: "uploading" });
    const body = new FormData();
    body.append("file", file);
    try {
      const result = await api.post<CvUploadOut>("/profile/cv-upload", body);
      if (result.status === "ready") {
        setFlow({ phase: "done", status: "ready", failureCode: null });
        await reloadProfile();
        return;
      }
      setFlow({ phase: "polling", cvVersionId: result.cv_version_id, status: result.status });
      pollStatus(result.cv_version_id);
    } catch (err) {
      setFlow({ phase: "picking" });
      setError(err instanceof ApiError ? err.displayMessage : "Upload failed. Try again.");
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppHeader />
      <main className="mx-auto max-w-md px-5 py-12 sm:px-8">
        <div className="mb-8 flex justify-end">
          <button
            onClick={() => navigate("/home", { replace: true })}
            className="font-body text-sm font-medium text-ink/50 hover:text-ink"
          >
            Skip for now
          </button>
        </div>

        <h1 className="font-display text-2xl font-black tracking-tight text-ink">Add your CV</h1>
        <p className="mt-1.5 font-body text-[15px] text-ink/60">
          We'll use it to match you to jobs and tailor it for each one you apply to.
        </p>

        <div className="mt-8">
          {flow.phase === "picking" && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED.join(",")}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFile(file);
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-hairline px-6 py-12 text-center transition-colors hover:border-phanda-green"
              >
                <UploadIcon className="h-8 w-8 text-ink/40" />
                <span className="font-body text-[15px] font-semibold text-ink">Choose a file to upload</span>
                <span className="font-body text-sm text-ink/50">PDF, Word or plain text -- up to 5MB</span>
              </button>
              {error && (
                <p role="alert" className="mt-4 rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
                  {error}
                </p>
              )}
            </>
          )}

          {flow.phase === "uploading" && <ProgressState label="Uploading your CV..." />}

          {flow.phase === "polling" && (
            <ProgressState
              label={flow.status === "extracting" ? "Reading your CV..." : "Getting things ready..."}
            />
          )}

          {flow.phase === "done" && flow.status === "ready" && (
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-hairline px-6 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-phanda-green text-white">
                <CheckIcon className="h-6 w-6" />
              </span>
              <p className="font-body text-[15px] font-semibold text-ink">Your CV is ready</p>
              <Button className="mt-2 w-full" onClick={() => navigate("/home", { replace: true })}>
                Continue to Phanda
              </Button>
            </div>
          )}

          {flow.phase === "done" && flow.status === "failed" && (
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-hairline px-6 py-12 text-center">
              <p className="font-body text-[15px] font-semibold text-ink">We couldn't read that file</p>
              <p className="font-body text-sm text-ink/60">
                Try a different file, or a PDF exported directly from Word rather than a scan.
              </p>
              <Button className="mt-2 w-full" variant="secondary" onClick={() => setFlow({ phase: "picking" })}>
                Try another file
              </Button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function ProgressState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-hairline px-6 py-12 text-center">
      <SpinnerIcon className="h-8 w-8 text-phanda-green" />
      <p className="font-body text-[15px] font-semibold text-ink">{label}</p>
      <p className="font-body text-sm text-ink/50">This usually takes a few seconds.</p>
    </div>
  );
}
