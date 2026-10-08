// Area O1 capture: when you finish loading a page, and only if its URL is one your vault lists, save it to the local
// Area O1. It never opens, reloads or fetches pages itself; it reads the tab you're on.
import { localApp, urlKey } from "./shared.js";

const REFRESH_MS = 60 * 60 * 1000;

async function watched(s) {
  if (s.sources && s.sourcesAt && Date.now() - s.sourcesAt < REFRESH_MS) return s.sources;
  try {
    const r = await fetch(`${localApp(s.app)}/api/vault/capture/sources`, { headers: { Authorization: `Bearer ${s.token}` } });
    if (r.status === 401) {
      await chrome.storage.local.set({ token: null, status: "Pairing expired: pair again from Area O1's Settings > Knowledge." });
      return [];
    }
    if (!r.ok) return s.sources || [];
    const { sources } = await r.json();
    await chrome.storage.local.set({ sources, sourcesAt: Date.now() });
    return sources;
  } catch {
    return s.sources || []; // Area O1 isn't running: keep the last list
  }
}

chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete" || !tab.url) return;
  const key = urlKey(tab.url);
  if (!key) return;
  const s = await chrome.storage.local.get(["app", "token", "sources", "sourcesAt", "share"]);
  if (!s.token) return;
  const hit = (await watched(s)).find((w) => w.keys.includes(key));
  if (!hit) return; // not a vault page: nothing is read or sent
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({ html: document.documentElement.outerHTML, title: document.title }),
  });
  let text;
  try {
    const r = await fetch(`${localApp(s.app)}/api/vault/capture/page`, {
      method: "POST",
      headers: { "content-type": "application/json", Authorization: `Bearer ${s.token}`, "X-AreaO1": "1" },
      body: JSON.stringify({ url: tab.url, title: result.title, html: result.html, share: !!s.share }),
    });
    text = r.ok ? `Saved: ${hit.title}` : `Couldn't save ${hit.title} (${r.status})`;
    chrome.action.setBadgeText({ tabId, text: r.ok ? "OK" : "!" });
  } catch {
    text = `Couldn't reach Area O1 to save ${hit.title}. Is it running?`;
    chrome.action.setBadgeText({ tabId, text: "!" });
  }
  await chrome.storage.local.set({ last: { at: new Date().toISOString(), text } });
});
