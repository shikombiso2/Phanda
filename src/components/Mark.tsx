/** The brand mark: same blocky slab "P" as the app icons, plus the
 * wordmark. Used in the header and the auth screens' brand panel. */
export function Mark({ withWordmark = true, size = 28 }: { withWordmark?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
        <rect width="32" height="32" rx="6" fill="#0B8F55" />
        <path fill="#fff" d="M9 5h13v3H9zM9 8h3v19H9zM19 8h3v11h-3zM9 16h13v3H9zM12 11h4v3h-4z" />
      </svg>
      {withWordmark && (
        <span className="font-display text-xl font-black tracking-tight text-ink">Phanda</span>
      )}
    </span>
  );
}
