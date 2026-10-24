// Records a real run of the UI (synthetic PDF only) to ../video/schoolsync-demo.webm
// Usage (servers on :8000 and :3000, fresh data dir): node e2e/record-demo.mjs
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PDF = path.resolve(here, "../../data/synthetic/maple_grove_2025_26.pdf");
const OUT = path.resolve(here, "../../video");
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
fs.mkdirSync(OUT, { recursive: true });
const tmp = fs.mkdtempSync(path.join(OUT, "tmp-"));

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
  acceptDownloads: true,
});
await ctx.addInitScript(() => {
  const render = () => {
    let el = document.getElementById("__cap");
    const t = sessionStorage.getItem("__cap") || "";
    if (!el) {
      el = document.createElement("div");
      el.id = "__cap";
      el.style.cssText =
        "position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:14px 24px;font:600 20px system-ui;" +
        "color:#fff;background:rgba(15,23,42,.92);text-align:center;pointer-events:none;white-space:pre-line";
      (document.body || document.documentElement).appendChild(el);
    }
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  };
  window.__renderCap = render;
  document.addEventListener("DOMContentLoaded", render);
});
const page = await ctx.newPage();
const t0 = Date.now();
const timeline = [];
const SPEED = 1.9; // pacing factor so captions are readable
const SHOT_DIR = process.env.SHOT_DIR;
let shotN = 0;
async function cap(text, ms) {
  timeline.push({ at: ((Date.now() - t0) / 1000).toFixed(1), caption: text });
  await page.evaluate((t) => { sessionStorage.setItem("__cap", t); window.__renderCap?.(); }, text);
  if (SHOT_DIR) await page.screenshot({ path: path.join(SHOT_DIR, `s${String(++shotN).padStart(2, "0")}.png`) });
  await page.waitForTimeout(ms * SPEED);
}

// 1. Upload
await page.goto(BASE + "/");
await cap("SchoolSync AI: upload a school calendar PDF (synthetic, fictional school)", 3000);
await page.getByLabel("Calendar PDF").setInputFiles(PDF);
await cap("Set school, academic year and timezone", 2500);
await page.getByRole("button", { name: "Upload and analyse" }).click();
await page.getByRole("heading", { name: "Review events" }).waitFor();

// 2. Legend
await page.locator("#h-legend").scrollIntoViewIfNeeded();
await cap("Legend read from the PDF itself: colours are matched to its labels,\nnothing is hard-coded (no 'red = holiday')", 5500);
await cap("One cell uses a colour that is NOT in the legend:\nflagged for review, not guessed", 4000);

// 3. Events
await page.getByRole("heading", { name: "Review events" }).scrollIntoViewIfNeeded();
await cap("Each event shows duration, category, source page and status;\nuncertainty is explicit, not a single score", 4500);
await page.getByRole("button", { name: "Half Day", exact: true }).click();
await cap("Half day with NO printed time: the app will not assume noon.\nConfirm is blocked", 5500);
await page.getByLabel("Dismissal time").fill("11:45");
await cap("You supply the dismissal time; the edit is logged in history", 2500);
await page.getByRole("button", { name: "Confirm this event" }).click();
await page.waitForTimeout(800);

await page.getByLabel("Needs attention only").check();
await page.getByRole("button", { name: /untitled/ }).click();
await cap("Colour-only cell with no text: needs a title and duration from you", 4500);
const side = page.getByRole("complementary");
await side.getByLabel("Title").fill("Staff Development Day");
await side.getByLabel("Duration").selectOption("all_day");
await page.getByRole("button", { name: "Confirm this event" }).click();
await page.getByLabel("Needs attention only").uncheck();
await cap("Resolved by a person, with source evidence kept", 2500);

await page.getByRole("button", { name: "Calendar" }).click();
await cap("Month-calendar view of the same events", 4000);
await page.getByRole("button", { name: "Table" }).click();
await page.locator("#h-legend").scrollIntoViewIfNeeded();
await page.getByLabel("I have checked that this legend mapping is correct.").check();
await cap("Confirm the legend mapping before export or sync", 2500);
await page.getByRole("link", { name: /Continue to export/ }).click();

// 4. Export + sync
await page.getByRole("heading", { name: "Export & sync" }).waitFor();
await cap("Import history: first import of this school and year", 3000);
const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download ICS (8)" }).click()]);
fs.writeFileSync(path.join(OUT, "sample-export.ics"), fs.readFileSync(await dl.path()));
await cap("ICS downloaded: all-day events are date values,\ntimed events carry a timezone, stable UIDs", 4500);
await page.getByRole("button", { name: /Preview sync/ }).click();
await page.getByRole("status").filter({ hasText: "8 create" }).waitFor();
await page.locator("#h-sync").scrollIntoViewIfNeeded();
await cap("Preview: 8 creates, nothing written yet.\nSync needs your explicit confirmation of this exact plan", 5500);
await page.getByLabel(/I confirm: apply 8 create/).check();
await page.getByRole("button", { name: "Confirm and sync" }).click();
await page.getByRole("heading", { name: "Import report" }).waitFor();
await cap("Report: 8 created in the in-memory demo calendar\n(no real calendar is touched)", 4000);

// 5. Duplicate safety
await page.getByRole("button", { name: /Preview sync/ }).click();
await page.getByRole("status").filter({ hasText: "8 skip" }).waitFor();
await cap("Run it again: 8 skipped, 0 created.\nDuplicate-safe: already synced, unchanged", 5500);
await page.goto(BASE + "/");
await page.getByLabel("Calendar PDF").setInputFiles(PDF);
await cap("Now upload the SAME PDF again", 2500);
await page.getByRole("button", { name: "Upload and analyse" }).click();
await page.getByRole("heading", { name: "Review events" }).waitFor();
await page.getByRole("link", { name: "Export & sync" }).click();
await page.getByRole("heading", { name: "Export & sync" }).waitFor();
await cap("Recognised: this exact PDF was imported before.\nNo new import record, no duplicates", 5500);

// 6. Wrap-up card
await page.evaluate(() => {
  document.body.innerHTML = "";
  document.body.style.cssText = "margin:0;background:#0f172a;color:#e8ebef;font:24px/1.6 system-ui;padding:80px 100px";
  document.body.innerHTML =
    "<h1 style='font-size:44px;margin:0 0 24px'>SchoolSync AI: what is proven, and what is not</h1>" +
    "<ul><li>Backend: 104 automated tests; frontend: 5 unit tests + browser e2e</li>" +
    "<li>Extraction: precision/recall 1.00 on 2 synthetic PDFs (13 events). Synthetic, same author: a baseline, not real-world accuracy</li>" +
    "<li>Not done: scanned PDFs (OCR), Google verified against the real API, Microsoft Graph, user accounts</li>" +
    "<li>Hosted demo: Vercel + AWS Lambda, synthetic data only</li></ul>";
  sessionStorage.removeItem("__cap");
});
timeline.push({ at: ((Date.now() - t0) / 1000).toFixed(1), caption: "closing card" });
await page.waitForTimeout(14000);
const total = (Date.now() - t0) / 1000;

await ctx.close();
const vid = fs.readdirSync(tmp).find((f) => f.endsWith(".webm"));
fs.renameSync(path.join(tmp, vid), path.join(OUT, "schoolsync-demo.webm"));
fs.rmSync(tmp, { recursive: true, force: true });
fs.writeFileSync(path.join(OUT, "timeline.json"), JSON.stringify({ total_seconds: total, scenes: timeline }, null, 2));
await browser.close();
console.log(`recorded ${total.toFixed(0)}s -> video/schoolsync-demo.webm`);
