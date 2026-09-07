import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppHeader } from "../../components/AppHeader";
import { Button } from "../../components/Button";
import { CheckIcon } from "../../components/icons";
import { ProgressState } from "../../components/ProgressState";
import { api } from "../../lib/api";
import { ApiError } from "../../lib/apiError";
import { useAuthStore } from "../../store/authStore";
import type { CvUploadOut, CvVersionStatus } from "../../types/api";
import { CvFilePicker, validateCvFile } from "./CvFilePicker";
import { pollCvVersionUntilTerminal } from "./cvPolling";

type FlowState =
  | { phase: "picking" }
  | { phase: "uploading" }
  | { phase: "polling"; status: CvVersionStatus }
  | { phase: "done"; status: "ready" | "failed" };

export function CvUpload() {
  const navigate = useNavigate();
  const reloadProfile = useAuthStore((s) => s.reloadProfile);
  const [flow, setFlow] = useState<FlowState>({ phase: "picking" });
  const [error, setError] = useState<string | null>(null);
  const cancelPollRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => cancelPollRef.current?.();
  }, []);

  async function handleFile(file: File) {
    setError(null);
    const validationError = validateCvFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setFlow({ phase: "uploading" });
    const body = new FormData();
    body.append("file", file);
    try {
      const result = await api.post<CvUploadOut>("/profile/cv-upload", body);
      if (result.status === "ready") {
        setFlow({ phase: "done", status: "ready" });
        await reloadProfile();
        return;
      }
      setFlow({ phase: "polling", status: result.status });
      const { promise, cancel } = pollCvVersionUntilTerminal(result.cv_version_id, (status) =>
        setFlow({ phase: "polling", status }),
      );
      cancelPollRef.current = cancel;
      const version = await promise;
      setFlow({ phase: "done", status: version.status as "ready" | "failed" });
      if (version.status === "ready") await reloadProfile();
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
          {flow.phase === "picking" && <CvFilePicker onFileSelected={handleFile} error={error} />}

          {flow.phase === "uploading" && <ProgressState label="Uploading your CV..." />}

          {flow.phase === "polling" && (
            <ProgressState label={flow.status === "extracting" ? "Reading your CV..." : "Getting things ready..."} />
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
