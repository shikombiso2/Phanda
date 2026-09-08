/** Builds a `?a=1&b=2` query string, dropping undefined/null/empty-string
 * values entirely rather than sending `type=` or `q=` for a filter the
 * user hasn't set -- the backend treats an absent param and an empty one
 * differently in a couple of places (e.g. `remote` is only applied when
 * `True`), so omitting is the correct behaviour, not just tidier. */
export function buildQueryString(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
