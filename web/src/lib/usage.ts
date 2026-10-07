/** How a run's (or a month's) usage reads in the chat: tokens and cost together, and never "0 tokens" beside a cost.
 * A cost with no tokens (a run that recorded only its price) shows the cost alone. */

const fmtTokens = (n: number) => {
  const short = (v: number, unit: string) => `${v >= 10 ? Math.round(v) : Number(v.toFixed(1))}${unit}`;
  if (n >= 999_500) return short(n / 1_000_000, "M");
  if (n >= 1000) return short(n / 1000, "k");
  return String(n);
};
const fmtUsd = (n: number) => (n < 0.01 ? "<$0.01" : `$${n.toFixed(2)}`);

export function usageLine(tokens: number | null | undefined, usd: number | null | undefined): string {
  const parts: string[] = [];
  if (tokens) parts.push(`${fmtTokens(tokens)} tokens`);
  if (usd !== null && usd !== undefined && (usd > 0 || !tokens)) parts.push(fmtUsd(usd));
  return parts.join(" · ");
}
