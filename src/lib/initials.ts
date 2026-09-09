/** Two-letter initials derived from an email's local part, e.g.
 * "jane.doe@x.com" -> "JD", "thabo@x.com" -> "TH". Used anywhere an avatar
 * stands in for a user we only know by email (no display name field exists). */
export function initials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  const pair = parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
  return (pair || "?").toUpperCase();
}
