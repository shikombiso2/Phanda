/** Two-letter initials derived from an email's local part, e.g.
 * "jane.doe@x.com" -> "JD", "thabo@x.com" -> "TH". Used anywhere an avatar
 * stands in for a user we only know by email (no display name field exists). */
export function initials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  const pair = parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
  return (pair || "?").toUpperCase();
}

/** A plausible first name from an email's local part, e.g.
 * "thabo.dlamini@x.com" -> "Thabo". There's no display-name field on the
 * profile, so this is a best-effort guess -- returns null (rather than
 * something like "Xk29" or "Info") when the first token isn't alphabetic,
 * so callers can fall back to a nameless greeting instead of an odd one. */
export function firstName(email: string): string | null {
  const name = email.split("@")[0] ?? "";
  const first = name.split(/[._-]+/).filter(Boolean)[0] ?? "";
  if (!/^[a-zA-Z]{2,}$/.test(first)) return null;
  return first[0].toUpperCase() + first.slice(1).toLowerCase();
}
