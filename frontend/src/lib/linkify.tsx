import type { ReactNode } from "react";

/**
 * Matches a URL either the normal way (no whitespace) or, lazily extending
 * token-by-token through embedded spaces, until it finds one ending in a
 * document extension. The second form exists for one real, confirmed case:
 * the DPSA adapter's Z83-form link is a literal, unencoded government URL
 * containing spaces --
 * "https://www.dpsa.gov.za/.../editable Approved New Z83 form Gazetted 6 Nov 2020.pdf"
 * -- which a plain `\S+` match would truncate at the first space.
 */
const LINK_RE = /https?:\/\/\S+(?:\s+\S+)*?\.(?:pdf|docx?|xlsx?|pptx?)\b|https?:\/\/\S+/gi;

/** Renders plain text with any URLs turned into real clickable links,
 * preserving line breaks the same way `whitespace-pre-line` does. Used
 * wherever listing description text is shown -- it's stored as plain text,
 * but at least one real source (DPSA) appends a link a user actually needs
 * to open. */
export function linkifyText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  LINK_RE.lastIndex = 0;
  while ((match = LINK_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const url = match[0].replace(/\s+/g, "%20");
    nodes.push(
      <a
        key={key++}
        href={url}
        target="_blank"
        rel="noreferrer"
        className="font-medium text-phanda-green-dark underline underline-offset-2 hover:text-phanda-green"
      >
        {match[0]}
      </a>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}
