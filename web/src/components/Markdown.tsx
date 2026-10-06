import type { ReactNode } from "react";

/** Tiny, safe Markdown subset for agent replies: paragraphs, - lists, **bold**, `code`, [links](https://…).
 *  Builds React nodes; never injects HTML. Only http(s) and in-app (#/...) links are rendered as links. */
export default function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={blocks.length} className="my-1 list-disc space-y-0.5 pl-5">
          {list.map((li, i) => (
            <li key={i}>{inline(li)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    blocks.push(
      heading ? (
        <p key={blocks.length} className="mt-2 font-semibold">
          {inline(heading[1])}
        </p>
      ) : (
        <p key={blocks.length} className="my-1">
          {inline(line)}
        </p>
      ),
    );
  }
  flush();
  return <div className="text-sm leading-relaxed">{blocks}</div>;
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={out.length}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`"))
      out.push(
        <code key={out.length} className="rounded bg-zinc-100 px-1 text-[12px] dark:bg-zinc-800">
          {tok.slice(1, -1)}
        </code>,
      );
    else {
      const [, label, href] = tok.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)!;
      const safe = /^(https?:\/\/|#\/)/.test(href);
      out.push(
        safe ? (
          <a key={out.length} href={href} className="link" target={href.startsWith("#") ? undefined : "_blank"} rel="noreferrer">
            {label}
          </a>
        ) : (
          label
        ),
      );
    }
    last = m.index! + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
