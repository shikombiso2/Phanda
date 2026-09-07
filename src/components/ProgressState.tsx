import { SpinnerIcon } from "./icons";

/** A labelled spinner in a card -- real progress, not a bare spinner with
 * no state, per the CV-upload and account-setup flows' requirement to show
 * what's actually happening while something processes server-side. */
export function ProgressState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-hairline px-6 py-12 text-center">
      <SpinnerIcon className="h-8 w-8 text-phanda-green" />
      <p className="font-body text-[15px] font-semibold text-ink">{label}</p>
      <p className="font-body text-sm text-ink/50">This usually takes a few seconds.</p>
    </div>
  );
}
