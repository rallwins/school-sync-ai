import { expect, test } from "@playwright/test";
import path from "node:path";

const PDF = path.resolve(__dirname, "../../data/synthetic/maple_grove_2025_26.pdf");

test("upload, review, resolve ambiguous events, sync gate", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Calendar PDF").setInputFiles(PDF);
  await page.getByRole("button", { name: "Upload and analyse" }).click();

  await expect(page.getByRole("heading", { name: "Review events" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "8 events" })).toContainText("6 ready");
  await expect(page.getByRole("status").filter({ hasText: "8 events" })).toContainText("2 need attention");

  // Legend mapping is shown with the printed labels.
  await expect(page.getByRole("cell", { name: "Half Day (Early Dismissal)", exact: true })).toBeVisible();
  await expect(page.getByText("matches no legend entry")).toBeVisible();

  // Half day without time cannot be confirmed until the user supplies a time.
  await page.getByRole("button", { name: "Half Day", exact: true }).click();
  const confirm = page.getByRole("button", { name: "Confirm this event" });
  await expect(confirm).toBeDisabled();
  await expect(page.getByText("Enter the dismissal time (not assumed).")).toBeVisible();
  await page.getByLabel("Dismissal time").fill("11:45");
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText("You confirmed this event.")).toBeVisible();

  // Colour-only unlisted event stays blocked until title + duration are provided.
  await page.getByLabel("Needs attention only").check();
  await page.getByRole("button", { name: /untitled/ }).click();
  await expect(page.getByRole("button", { name: "Confirm this event" })).toBeDisabled();
  await page.getByRole("complementary").getByLabel("Title").fill("Staff Development Day");
  await page.getByRole("complementary").getByLabel("Duration").selectOption("all_day");
  await page.getByRole("button", { name: "Confirm this event" }).click();
  await expect(page.getByText("You confirmed this event.")).toBeVisible();
  await page.getByLabel("Needs attention only").uncheck();

  // Calendar view renders month grids.
  await page.getByRole("button", { name: "Calendar" }).click();
  await expect(page.getByRole("grid", { name: "September 2025" })).toBeVisible();

  // Sync page: legend unconfirmed -> downloads and sync stay disabled.
  await page.getByRole("link", { name: /Continue to export/ }).click();
  await expect(page.getByText("Confirm the legend mapping first")).toBeVisible();
  await expect(page.getByRole("button", { name: /Download ICS/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Preview sync/ })).toBeDisabled();
  await expect(page.getByText(/Google Calendar: unavailable/)).toBeVisible();

  // Confirm legend on review, come back.
  await page.getByRole("link", { name: "Review", exact: true }).click();
  await page.getByLabel("I have checked that this legend mapping is correct.").check();
  await page.getByRole("link", { name: /Continue to export/ }).click();
  await expect(page.getByText("First import for this school and year.")).toBeVisible();

  // ICS download contains the events.
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download ICS (8)" }).click(),
  ]);
  const ics = await (await import("node:fs/promises")).readFile(await dl.path(), "utf8");
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain("SUMMARY:Labor Day");
  expect(ics).toContain("DTSTART;VALUE=DATE:20250901");

  // Preview -> explicit confirm -> report -> second preview shows zero creates.
  await page.getByRole("button", { name: /Preview sync/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "8 create" })).toBeVisible();
  const go = page.getByRole("button", { name: "Confirm and sync" });
  await expect(go).toBeDisabled();
  await page.getByLabel(/I confirm: apply 8 create/).check();
  await go.click();
  await expect(page.getByRole("heading", { name: "Import report" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "8 created" })).toBeVisible();

  await page.getByRole("button", { name: /Preview sync/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "8 skip" })).toBeVisible();
  await expect(page.getByText(/already synced, unchanged/).first()).toBeVisible();
});
