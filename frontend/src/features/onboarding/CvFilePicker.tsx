import { useRef } from "react";
import { UploadIcon } from "../../components/icons";

export const CV_ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];
export const CV_MAX_BYTES = 5 * 1024 * 1024;

/** Shared so both CvUpload (uploads immediately) and SignupWizard (stages
 * the file until an account exists) reject the same files for the same
 * reason, worded the same way. */
export function validateCvFile(file: File): string | null {
  const extension = "." + file.name.split(".").pop()?.toLowerCase();
  if (!CV_ACCEPTED_EXTENSIONS.includes(extension)) {
    return "Upload a PDF, Word (.docx) or plain text CV.";
  }
  if (file.size > CV_MAX_BYTES) {
    return "That file is too big. Keep it under 5MB.";
  }
  return null;
}

/** The "choose a file" button, by itself -- no upload, no validation
 * feedback beyond displaying whatever error string it's handed. What
 * happens to the file once chosen is entirely up to the caller. */
export function CvFilePicker({
  onFileSelected,
  error,
}: {
  onFileSelected: (file: File) => void;
  error?: string | null;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept={CV_ACCEPTED_EXTENSIONS.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelected(file);
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
  );
}
