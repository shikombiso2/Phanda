const CURRENCY_PREFIX: Record<string, string> = {
  ZAR: "R",
  USD: "US$",
  CAD: "CA$",
};

const PERIOD_SUFFIX: Record<string, string> = {
  hourly: "/hour",
  weekly: "/week",
  fortnightly: "/fortnight",
  monthly: "/month",
  annual: "/year",
};

/**
 * Formats a salary range, or returns null if it can't be shown *safely*.
 *
 * The hard rule this exists to enforce: never render an amount without its
 * period and currency, and never render a period when there's no amount.
 * The data genuinely mixes hourly USD contract postings with annual ZAR
 * ones -- "12 000" alone is meaningless (and actively misleading) without
 * knowing which of those it is. So this only produces a string when it has
 * at least one amount, a period, AND a currency; missing any one of the
 * three means "say nothing" rather than guessing.
 */
export function formatSalary(
  min: number | null | undefined,
  max: number | null | undefined,
  period: string | null | undefined,
  currency: string | null | undefined,
): string | null {
  if (min == null && max == null) return null;
  if (!period || !currency) return null;

  const prefix = CURRENCY_PREFIX[currency] ?? `${currency} `;
  const suffix = PERIOD_SUFFIX[period] ?? `/${period}`;
  const format = (n: number) => `${prefix}${n.toLocaleString("en-ZA")}`;

  if (min != null && max != null && min !== max) {
    return `${format(min)} - ${format(max)}${suffix}`;
  }
  return `${format(min ?? max ?? 0)}${suffix}`;
}
