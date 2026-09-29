import type { ReactNode } from "react";
import { linkifyText } from "./linkify";

/**
 * A deliberately small Markdown subset renderer for listing descriptions.
 *
 * Vacancy Update listings are now stored as real Markdown (the scraper keeps
 * the page's own "About X" / "Eligibility Criteria" / "Application
 * Instructions" section headings and its <ul>/<ol> criteria -- see
 * app/listings/ingestion/vacancyupdate_adapter.py). DPSA and Adzuna
 * descriptions are still plain prose separated by blank lines, and they must
 * keep rendering exactly as readably as before: plain text is valid Markdown,
 * so it simply falls through as paragraphs.
 *
 * Hand-written rather than pulling in react-markdown: the only constructs
 * that actually occur are headings, bullets, numbered items and paragraphs,
 * and inline text still has to go through linkifyText() for the DPSA Z83
 * form URL, which contains literal spaces and no off-the-shelf parser
 * handles it.
 */

type Block =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "numbers"; items: string[] };

const HEADING_RE = /^#{1,6}\s+(.*)$/;
const BULLET_RE = /^[-*]\s+(.*)$/;
const NUMBERED_RE = /^\d+[.)]\s+(.*)$/;

export function parseMarkdownBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let bullets: string[] = [];
  let numbers: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  const flushBullets = () => {
    if (bullets.length) blocks.push({ kind: "bullets", items: bullets });
    bullets = [];
  };
  const flushNumbers = () => {
    if (numbers.length) blocks.push({ kind: "numbers", items: numbers });
    numbers = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushBullets();
    flushNumbers();
  };

  for (const rawLine of source.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushAll();
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      flushAll();
      blocks.push({ kind: "heading", text: heading[1].trim() });
      continue;
    }

    const bullet = BULLET_RE.exec(line);
    if (bullet) {
      flushParagraph();
      flushNumbers();
      bullets.push(bullet[1].trim());
      continue;
    }

    const numbered = NUMBERED_RE.exec(line);
    if (numbered) {
      flushParagraph();
      flushBullets();
      numbers.push(numbered[1].trim());
      continue;
    }

    flushBullets();
    flushNumbers();
    paragraph.push(line);
  }

  flushAll();
  return blocks;
}

export function renderMarkdown(source: string): ReactNode {
  return parseMarkdownBlocks(source).map((block, index) => {
    if (block.kind === "heading") {
      return (
        <h3 key={index} className="mt-5 font-body text-[15px] font-bold text-ink first:mt-0">
          {block.text}
        </h3>
      );
    }
    if (block.kind === "bullets") {
      return (
        <ul key={index} className="mt-2 list-disc space-y-1 pl-5">
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex} className="font-body text-[15px] leading-relaxed text-ink/75">
              {linkifyText(item)}
            </li>
          ))}
        </ul>
      );
    }
    if (block.kind === "numbers") {
      return (
        <ol key={index} className="mt-2 list-decimal space-y-1 pl-5">
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex} className="font-body text-[15px] leading-relaxed text-ink/75">
              {linkifyText(item)}
            </li>
          ))}
        </ol>
      );
    }
    return (
      <p key={index} className="mt-2 font-body text-[15px] leading-relaxed text-ink/75">
        {linkifyText(block.text)}
      </p>
    );
  });
}
