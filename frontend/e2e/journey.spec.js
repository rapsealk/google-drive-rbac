import { test, expect } from "@playwright/test";

const ADMIN = { username: "e2e-admin", password: "password123", company: "E2E Corp" };
const MEMBER = { username: "e2e-member", password: "password123" };
const OUTSIDER = { username: "e2e-outsider", password: "password123", company: "Other Corp" };
const FILE_NAME = `e2e-report-${Date.now()}.txt`;

async function signup(page, { username, password, company }) {
  await page.goto("/login");
  await page.getByRole("tablist").getByRole("button", { name: "Sign up" }).click();
  await page.getByPlaceholder("Username").fill(username);
  await page.getByPlaceholder("Password (min 8 chars)").fill(password);
  if (company) {
    await page.getByRole("button", { name: "Create company" }).click();
    await page.getByPlaceholder("Company name").fill(company);
  }
  await page.locator("form").getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByRole("link", { name: "My Drive" })).toBeVisible({ timeout: 15_000 });
}

async function logout(page) {
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("tablist").getByRole("button", { name: "Log in" })).toBeVisible();
}

test("full journey: admin seeds via UI, member shares, outsider isolated", async ({ page }) => {
  // --- Admin: create company ---
  await signup(page, ADMIN);

  // --- Admin: create a workspace readable by all employees ---
  await page.getByRole("link", { name: "Workspaces" }).click();
  await page.getByPlaceholder("New workspace name").fill("team-ws");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("team-ws")).toBeVisible();
  await page.getByLabel("Default role for team-ws").selectOption("viewer");

  // --- Admin: generate invite code, remember it for the member ---
  await page.getByRole("link", { name: "Members" }).click();
  await page.getByRole("button", { name: "Generate invite code" }).click();
  const code = await page.locator(".invite-code").first().textContent();
  expect(code).toBeTruthy();

  // --- Admin: upload a file into the workspace ---
  await page.getByRole("link", { name: "My Drive" }).click();
  await page.setInputFiles('input[type="file"]', {
    name: FILE_NAME, mimeType: "text/plain", buffer: Buffer.from("rbac e2e payload"),
  });
  await expect(page.getByText(FILE_NAME)).toBeVisible({ timeout: 15_000 });

  // --- Member: joins via invite code, sees the shared workspace and file ---
  await logout(page);
  await page.goto("/login");
  await page.getByRole("tablist").getByRole("button", { name: "Sign up" }).click();
  await page.getByPlaceholder("Username").fill(MEMBER.username);
  await page.getByPlaceholder("Password (min 8 chars)").fill(MEMBER.password);
  await page.getByRole("button", { name: "Join with code" }).click();
  await page.getByPlaceholder("Invite code").fill(code);
  await page.locator("form").getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByRole("link", { name: "My Drive" })).toBeVisible({ timeout: 15_000 });

  // Member (plain "user") sees no admin nav
  await expect(page.getByRole("link", { name: "Members" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Audit" })).toHaveCount(0);

  // Member sees the workspace (default_role=viewer) and the file
  await expect(page.locator(".file-row", { hasText: FILE_NAME })).toBeVisible({ timeout: 15_000 });

  // Member (viewer) cannot delete the admin's file
  const row = page.locator(".file-row", { hasText: FILE_NAME });
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: `Delete ${FILE_NAME}` }).click();
  await expect(page.getByText(/forbidden|missing content:delete/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".file-row", { hasText: FILE_NAME })).toBeVisible();

  // --- Outsider: another company cannot see anything ---
  await logout(page);
  await signup(page, OUTSIDER);
  await expect(page.getByText("Empty — upload something.")).toBeVisible({ timeout: 15_000 });
});

test("audit log records the journey for the admin", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("Username").fill(ADMIN.username);
  await page.getByPlaceholder("Password (min 8 chars)").fill(ADMIN.password);
  await page.locator("form").getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "My Drive" })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("link", { name: "Audit" }).click();
  // Signup seeded member.add entries — RBAC-affecting actions are audited.
  await expect(page.getByText("Added member").first()).toBeVisible();
});
