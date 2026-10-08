// Area O1 capture (ADR 0011 §2). Shared by the background worker and the popup.

export const DEFAULT_APP = "http://127.0.0.1:7777";

/** A URL as Area O1 compares it (areao1/vault/capture.py `key`): host without www, path without a trailing slash,
 * the query, no fragment, lower case. */
export function urlKey(url) {
  let u;
  try {
    u = new URL(url);
  } catch {
    return null;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return null;
  const host = u.hostname.toLowerCase().replace(/^www\./, "");
  const port = u.port ? `:${u.port}` : "";
  const path = u.pathname.replace(/\/+$/, "");
  return `${host}${port}${path}${u.search}`.toLowerCase();
}

/** Only the local app: the extension never sends anything anywhere else. */
export function localApp(app) {
  const u = new URL(app || DEFAULT_APP);
  if (u.hostname !== "127.0.0.1" || u.protocol !== "http:") throw new Error("Area O1 runs on http://127.0.0.1 only");
  return u.origin;
}
