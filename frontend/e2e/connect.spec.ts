import { expect, test } from "@playwright/test";
import path from "node:path";

const PDF = path.resolve(__dirname, "../../data/synthetic/maple_grove_2025_26.pdf");

test("Google is honestly 'not configured' on a server without credentials; demo calendar selectable", async ({ page }) => {
  await page.goto("/connect");
  await expect(page.getByRole("heading", { name: "Connect a destination" })).toBeVisible();
  await expect(page.getByText(/Not configured on this server/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Google" })).toHaveCount(0);

  await page.getByRole("button", { name: "Use the demo calendar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Demo: Demo calendar" })).toBeVisible();
});

test("OAuth return codes are shown without leaking anything", async ({ page }) => {
  await page.goto("/connect?google=error&reason=denied");
  await expect(page.getByRole("alert").filter({ hasText: "You cancelled at Google" })).toBeVisible();
  await page.goto("/connect?google=connected");
  await expect(page.getByText("Google connected. Choose a calendar below.")).toBeVisible();
});

test("picking a Google calendar routes the sync to it, with an explicit REAL-calendar warning", async ({ page }) => {
  // Import first (real backend) so there are events to sync.
  await page.goto("/");
  await page.getByLabel("Calendar PDF").setInputFiles(PDF);
  await page.getByLabel("School name").fill("Connect Test School");
  await page.getByRole("button", { name: "Upload and analyse" }).click();
  await expect(page.getByRole("heading", { name: "Review events" })).toBeVisible();
  await page.getByLabel("I have checked that this legend mapping is correct.").check();

  // Pretend Google is configured and connected (network mocked; no Google call is made).
  const providers = [
    { id: "file", label: "File export (ICS/CSV)", available: true, reason: null },
    { id: "mock", label: "Demo calendar (in-memory)", available: true, reason: null },
    { id: "google", label: "Google Calendar", available: true, reason: null },
    { id: "microsoft", label: "Microsoft Outlook", available: false, reason: "not configured" },
  ];
  await page.route("**/api/providers", (r) => r.fulfill({ json: providers }));
  await page.route("**/api/providers/google/calendars", (r) =>
    r.fulfill({ json: [{ id: "work@example.com", name: "Work" }, { id: "test-cal-id", name: "SchoolSync TEST" }] }),
  );
  let previewBody: { provider?: string; calendar_id?: string } = {};
  await page.route("**/api/sync/preview", async (r) => {
    previewBody = JSON.parse(r.request().postData() ?? "{}");
    await r.fulfill({
      json: {
        items: [{ action: "create", stable_id: "s1", title: "Labor Day", start_date: "2025-09-01", end_date: "2025-09-01", reason: "new event", matched_title: null }],
        counts: { create: 1, update: 0, skip: 0, conflict: 0, propose_remove: 0 },
        plan_token: "tok",
      },
    });
  });

  await page.getByRole("link", { name: "Connect", exact: true }).click();
  await expect(page.getByText("Connected.")).toBeVisible();
  await page.getByLabel("Calendar to write to").selectOption("test-cal-id");
  await page.getByRole("button", { name: "Use this calendar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Google: SchoolSync TEST" })).toBeVisible();

  await page.getByRole("link", { name: "Export & sync", exact: true }).click();
  await expect(page.getByText(/writes to a real Google Calendar after you confirm/)).toBeVisible();
  await page.getByRole("button", { name: /Preview sync to SchoolSync TEST/ }).click();
  await expect(page.getByText(/your REAL Google calendar “SchoolSync TEST”/)).toBeVisible();

  // The request targets exactly the chosen calendar, and the sync button stays locked until confirmed.
  expect(previewBody.provider).toBe("google");
  expect(previewBody.calendar_id).toBe("test-cal-id");
  await expect(page.getByRole("button", { name: "Confirm and sync" })).toBeDisabled();
});

test("sync page explains exactly why it cannot preview yet, then clears", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Calendar PDF").setInputFiles(PDF);
  await page.getByLabel("School name").fill("Checklist Test School");
  await page.getByRole("button", { name: "Upload and analyse" }).click();
  await expect(page.getByRole("heading", { name: "Review events" })).toBeVisible();

  await page.getByRole("link", { name: "Export & sync", exact: true }).click();
  const box = page.getByRole("status").filter({ hasText: "Before you can preview a sync" });
  await expect(box).toContainText("Legend mapping is not confirmed.");
  await expect(page.getByRole("button", { name: /Preview sync/ })).toBeDisabled();

  // The legend is shown right here and can be confirmed in place (no trip back to Review).
  await expect(box.getByText("Legend as read from your PDF")).toBeVisible();
  await expect(box.getByText("Holiday / No School")).toBeVisible();
  await box.getByLabel("I have checked that this legend mapping is correct.").click(); // box disappears once confirmed
  await expect(page.getByText(/✓ Ready to preview/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Preview sync/ })).toBeEnabled();
});

