import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const PDF = path.resolve(__dirname, "../../data/synthetic/cedar_hill_2025_26.pdf");

test("list-style calendar: bulk 'treat as all-day' is explicit, then export", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Calendar PDF").setInputFiles(PDF);
  await page.getByLabel("School name").fill("Cedar Hill School");
  await page.getByLabel("Timezone").fill("Asia/Kolkata");
  await page.getByRole("button", { name: "Upload and analyse" }).click();
  await expect(page.getByRole("heading", { name: "Review events" })).toBeVisible();

  const summary = page.getByRole("status").filter({ hasText: "13 events" });
  await expect(summary).toContainText("7 ready");
  await expect(summary).toContainText("6 need attention");
  await expect(page.getByText(/Audience \(EY\/PY\)/)).toBeVisible();

  // Nothing is assumed: the 6 unknown-duration events wait for an explicit user action.
  await expect(page.getByRole("heading", { name: "No stated duration" })).toBeVisible();
  let dialogText = "";
  page.once("dialog", async (d) => {
    dialogText = d.message();
    await d.accept();
  });
  await page.getByRole("button", { name: /Treat 6 as all-day/ }).click();
  await expect(page.getByText("6 event(s) marked all-day by you.")).toBeVisible();
  expect(dialogText).toContain("Mark 6 event(s) as all-day");
  await expect(summary).toContainText("13 ready");
  await expect(page.getByRole("heading", { name: "No stated duration" })).toHaveCount(0);

  // The change is auditable on each event.
  await page.getByRole("button", { name: "Book Fair" }).click();
  await page.getByText(/Edit history/).click();
  await expect(page.getByText(/bulk_all_day/)).toBeVisible();

  await page.getByLabel("I have checked that this legend mapping is correct.").check();
  await page.getByRole("link", { name: /Continue to export/ }).click();
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download ICS (13)" }).click(),
  ]);
  const ics = await fs.readFile(await dl.path(), "utf8");
  expect(ics).toContain("SUMMARY:Book Fair");
  expect(ics).toContain("DTSTART;VALUE=DATE:20250908");
  expect(ics).toContain("DTEND;VALUE=DATE:20250913"); // Sep 8-12 inclusive -> exclusive end
  expect(ics).toContain("DTSTART;TZID=Asia/Kolkata:20250926T163000"); // timed event keeps its zone
});

