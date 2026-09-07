import { useId, type InputHTMLAttributes } from "react";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function TextField({ label, error, hint, id, className = "", ...rest }: TextFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="font-body text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={fieldId}
        aria-invalid={Boolean(error)}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        className={`w-full rounded-[10px] border px-4 py-3 font-body text-[15px] text-ink outline-none transition-colors placeholder:text-ink/40 ${
          error ? "border-signal" : "border-hairline focus:border-phanda-green"
        } ${className}`}
        {...rest}
      />
      {hint && !error && (
        <p id={hintId} className="text-sm text-ink/60">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm font-medium text-signal">
          {error}
        </p>
      )}
    </div>
  );
}
