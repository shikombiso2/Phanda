/**
 * DPSA-specific: a single circular "POST" is sometimes filled at several
 * named locations at once (e.g. one Deputy Master post with a slot in
 * Pretoria, one in Polokwane, one in Thohoyandou), each carrying its own
 * reference number. Confirmed via a prior read-only investigation that this
 * is genuinely how DPSA structures the source document -- one real post, one
 * `CENTRE:` field listing every location -- not a parser bug, and NOT safe
 * to split into separate listing rows (which location a candidate is
 * applying for isn't reliably inferable at ingestion time). This is a
 * display-only concern: parse the concatenated string just well enough to
 * show something readable, and fall back to the raw string whenever the
 * format doesn't match cleanly rather than show something broken or empty.
 *
 * Confirmed live across a sample of real rows, the common shape is
 * "<place> Ref No: <ref> (X<n> Post(s))" repeated, though the post-count
 * suffix is often missing and one confirmed source spells it "Refno" with
 * no space. A second, rarer shape puts the ref first and the place in
 * parentheses ("Ref No: DEDT 03/09/26 (Maria Moroka Resort)"). Anything
 * else -- and any row where the split doesn't cleanly account for the whole
 * string -- returns null so the caller shows the original text unchanged.
 */

export interface LocationEntry {
  place: string;
  refNo: string;
  postCount: number | null;
}

const REF_NO_RE = /Ref\s*No\.?\s*:?/gi;
const POST_COUNT_RE = /^\(\s*X?\s*(\d+)\s*Posts?\s*\)/i;
const PAREN_RE = /^\(([^)]+)\)/;
const TOKEN_RE = /\S+/g;

function cleanPlace(raw: string): string {
  // Strips stray leading separators left over from the previous unit --
  // confirmed live, e.g. a lone backtick artifact from PDF extraction
  // ("...2026 ` Sekhukhune District...") -- and trailing commas/dashes.
  return raw.replace(/^[\s,`\-]+/, "").replace(/[\s,\-]+$/, "").trim();
}

/**
 * A reference number's LAST token always carries a digit in every real
 * sample seen ("14/08/2026", "DSDFS 76/26", "VOCMA 24", "CARL/FINANCE/10")
 * while a place name's tokens never do -- so the boundary between "this
 * post's ref number" and "the next post's place name" (there is often no
 * other separator between them at all, no comma, no parenthesis) is: keep
 * consuming whitespace-delimited tokens from the start of `remainder` until
 * one contains a digit, then stop. Returns null if no token in `remainder`
 * ever contains a digit -- there's no ref number here to find.
 */
function extractRefValue(remainder: string): { ref: string; end: number } | null {
  TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TOKEN_RE.exec(remainder))) {
    if (/\d/.test(match[0])) {
      const end = match.index + match[0].length;
      return { ref: remainder.slice(0, end).trim(), end };
    }
  }
  return null;
}

export function parseMultiLocation(raw: string | null | undefined): LocationEntry[] | null {
  if (!raw) return null;
  const refMatches = [...raw.matchAll(REF_NO_RE)];
  if (refMatches.length < 2) return null;

  const entries: LocationEntry[] = [];
  let cursor = 0;

  for (let i = 0; i < refMatches.length; i++) {
    const match = refMatches[i];
    const matchIndex = match.index ?? -1;
    if (matchIndex < 0) return null;

    const refValueStart = matchIndex + match[0].length;
    const nextMatchIndex = i + 1 < refMatches.length ? (refMatches[i + 1].index ?? raw.length) : raw.length;
    const remainder = raw.slice(refValueStart, nextMatchIndex);

    const extracted = extractRefValue(remainder);
    if (!extracted) return null;

    let unitEnd = refValueStart + extracted.end;
    let placeFromParen: string | null = null;
    let postCount: number | null = null;

    // Whatever immediately follows the ref value -- if anything -- may be a
    // "(X1 Post)" count, or (rarer) the place name itself in parentheses
    // when the source writes ref-first ("Ref No: DEDT 03/09/26 (Maria
    // Moroka Resort)"). Otherwise it's just the next unit's place name,
    // left untouched for the next loop iteration to pick up.
    const tail = raw.slice(unitEnd, nextMatchIndex);
    const tailLeadingSpace = tail.match(/^\s*/)?.[0].length ?? 0;
    const afterSpace = tail.slice(tailLeadingSpace);
    const countMatch = afterSpace.match(POST_COUNT_RE);
    if (countMatch) {
      postCount = Number(countMatch[1]);
      unitEnd += tailLeadingSpace + countMatch[0].length;
    } else {
      const parenMatch = afterSpace.match(PAREN_RE);
      // Only treat a parenthetical as "the place name" when there's no
      // place text already sitting before this "Ref No" -- otherwise a
      // place's own qualifier in parens (e.g. "Capricorn District
      // (Polokwane)") would be misread as this entry's place all over
      // again on the next iteration.
      if (parenMatch && raw.slice(cursor, matchIndex).trim().length === 0) {
        placeFromParen = parenMatch[1];
        unitEnd += tailLeadingSpace + parenMatch[0].length;
      }
    }

    const place = placeFromParen ?? cleanPlace(raw.slice(cursor, matchIndex));
    const ref = cleanPlace(extracted.ref);

    if (!place || !ref) return null;

    entries.push({ place, refNo: ref, postCount });
    cursor = unitEnd;
  }

  // The whole string must be accounted for by these units -- anything left
  // over (unparsed trailing text) means this isn't the clean shape we know
  // how to summarise.
  if (raw.slice(cursor).trim().length > 0) return null;

  return entries;
}

/** Short label for list-view cards -- never the raw concatenated string. */
export function locationSummaryLabel(location: string | null | undefined): string | null {
  const entries = parseMultiLocation(location);
  if (!entries) return location ?? null;
  return `${entries.length} locations`;
}

// ---------------------------------------------------------------------------
// apply_target: a much less structured field (free-text application
// instructions), so this only recognises one confirmed concrete shape --
// several "<Province>: ..." blocks concatenated together, one per office a
// candidate might need to apply to depending on which location's post they
// want. Anything else falls back to plain length-based truncation in the UI
// rather than attempting a parse that's likely to get it wrong.
// ---------------------------------------------------------------------------

const SA_PROVINCES = [
  "Eastern Cape",
  "Free State",
  "Gauteng",
  "KwaZulu-Natal",
  "Limpopo",
  "Mpumalanga",
  "North West",
  "Northern Cape",
  "Western Cape",
];

const PROVINCE_BLOCK_RE = new RegExp(`\\b(${SA_PROVINCES.join("|")})\\s*:`, "g");

export interface ApplyTargetOffice {
  province: string;
  text: string;
}

export function parseMultiOfficeApplyTarget(raw: string | null | undefined): ApplyTargetOffice[] | null {
  if (!raw) return null;
  const matches = [...raw.matchAll(PROVINCE_BLOCK_RE)];
  if (matches.length < 2) return null;

  const offices: ApplyTargetOffice[] = [];
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i];
    const start = match.index ?? -1;
    if (start < 0) return null;
    const end = i + 1 < matches.length ? (matches[i + 1].index ?? raw.length) : raw.length;
    const text = raw.slice(start, end).trim();
    if (!text) return null;
    offices.push({ province: match[1], text });
  }

  // Anything before the first province label must be empty/whitespace --
  // otherwise this isn't a clean "all-provinces, nothing else" block and a
  // structured split would silently drop real content.
  if (raw.slice(0, matches[0].index ?? 0).trim().length > 0) return null;

  return offices;
}
