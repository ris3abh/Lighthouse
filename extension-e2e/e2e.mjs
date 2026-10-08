// usage: node e2e.mjs <app-url> <listed-page-url> <unlisted-page-url> <extension-dir> [chrome-path]
// Loads the extension into Chrome, pairs it with the running app, visits an unlisted then a listed page, and prints
// a JSON report. Never visits anything but the two given pages.
import puppeteer from "puppeteer-core";

const [app, listed, unlisted, extDir, chromePath] = process.argv.slice(2);
const executablePath = chromePath || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await puppeteer.launch({ executablePath, headless: true, pipe: true, enableExtensions: [extDir],
  args: ["--no-first-run", "--no-default-browser-check"] });
const report = { steps: [] };
try {
  const worker = await browser.waitForTarget((t) => t.type() === "service_worker" && t.url().endsWith("background.js"), { timeout: 15000 });
  const id = new URL(worker.url()).host;
  report.extension = id;
  const code = (await (await fetch(`${app}/api/vault/capture/code`, { method: "POST", headers: { "X-AreaO1": "1" } })).json()).code;
  const popup = await browser.newPage();
  await popup.goto(`chrome-extension://${id}/popup.html`);
  await popup.$eval("#app", (el, v) => (el.value = v), app);
  await popup.type("#code", code);
  await popup.click("#pair");
  await popup.waitForFunction(() => !document.getElementById("paired").hidden, { timeout: 10000 });
  report.paired = await popup.$eval("#count", (el) => el.textContent);
  const tab = await browser.newPage();
  for (const [name, url] of [["unlisted", unlisted], ["listed", listed]]) {
    await tab.goto(url, { waitUntil: "load" });
    await new Promise((r) => setTimeout(r, 2500));
    report.steps.push({ name, url });
  }
  await popup.reload();
  report.last = await popup.$eval("#last", (el) => el.textContent);
} finally {
  await browser.close();
}
console.log(JSON.stringify(report));
