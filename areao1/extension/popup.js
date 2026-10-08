import { localApp } from "./shared.js";

const $ = (id) => document.getElementById(id);

async function render() {
  const s = await chrome.storage.local.get(["app", "token", "sources", "last", "share", "status"]);
  if (s.app) $("app").value = s.app;
  $("unpaired").hidden = !!s.token;
  $("paired").hidden = !s.token;
  $("count").textContent = s.token ? `Paired. Watching ${(s.sources || []).length} official pages.` : "";
  $("last").textContent = s.last ? `${s.last.text} (${new Date(s.last.at).toLocaleString()})` : "Nothing saved yet.";
  $("share").checked = !!s.share;
  $("status").textContent = s.status || "";
}

$("pair").addEventListener("click", async () => {
  $("status").textContent = "Pairing…";
  try {
    const app = localApp($("app").value.trim());
    const r = await fetch(`${app}/api/vault/capture/pair`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-AreaO1": "1" },
      body: JSON.stringify({ code: $("code").value.trim() }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || `Area O1 answered ${r.status}`);
    await chrome.storage.local.set({ app, token: body.token, sources: body.sources, sourcesAt: Date.now(), status: "" });
  } catch (e) {
    await chrome.storage.local.set({ status: e.message });
  }
  render();
});

$("unpair").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: null, sources: [], status: "Unpaired." });
  render();
});

$("share").addEventListener("change", (e) => chrome.storage.local.set({ share: e.target.checked }));

render();
