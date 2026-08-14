import { expect, test, type Page } from "@playwright/test";

/**
 * The journey the phase's definition of done describes: create a project
 * through the wizard, draft and approve a narrative, run validation, then
 * build and download a package.
 *
 * It drives the real backend rather than mocking it, because almost every
 * bug this phase actually surfaced -- missing CORS, an API bound to the
 * wrong IP stack, a mislabelled button, a status enum compared in the
 * wrong case -- was invisible to unit tests by construction. A mocked
 * version of this test would have passed straight through all of them.
 *
 * WHY it creates and then deletes its own project instead of borrowing
 * the EXAMOX seed: an earlier version overrode the seed's validation
 * rules to get a build through, which permanently mutated shared demo
 * data (overrides have no DELETE endpoint and accumulated on every run)
 * and destroyed the seed's whole point -- it is *deliberately* buggy, so
 * making it exportable removes the thing it teaches. A test that needs
 * mutable state should own that state.
 */

const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const EMAIL = "e2e@example.com";
const PASSWORD = "e2e-password";

let token = "";
let createdProjectId: string | null = null;
let createdProductId: string | null = null;

function authHeaders() {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

test.beforeAll(async () => {
  let reachable = false;
  try {
    reachable = (await fetch(`${API}/health`)).ok;
  } catch {
    reachable = false;
  }
  test.skip(
    !reachable,
    `API not reachable at ${API} — start Postgres and the API first (see frontend/README.md)`,
  );

  // A second run gets 409 from register, which is fine; the sign-in below
  // is what actually matters.
  await fetch(`${API}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  }).catch(() => undefined);

  const login = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: EMAIL, password: PASSWORD }),
  });
  token = (await login.json()).access_token;
});

test.afterAll(async () => {
  // Leave the database as we found it. Deleting the project cascades to
  // its validation overrides.
  if (createdProjectId) {
    await fetch(`${API}/projects/${createdProjectId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).catch(() => undefined);
  }
  if (createdProductId) {
    await fetch(`${API}/products/${createdProductId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).catch(() => undefined);
  }
});

async function signIn(page: Page) {
  await page.goto("/login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/projects");
}

test("wizard to download: capture data, review a narrative, validate, build", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(String(error)));

  await signIn(page);

  // ---- the wizard: capture data, never upload a dossier ----------------
  await page.click('a:has-text("New product")');
  await page.waitForURL("**/products/new");

  // Dropdowns come from GET /enums, so the UI cannot offer a value the
  // database would reject.
  await page.waitForSelector("#field-dosage_form");
  expect(await page.locator("#field-dosage_form option").count()).toBeGreaterThan(30);

  const brand = `E2E-${Date.now().toString().slice(-6)}`;
  await page.fill("#field-brand_name", brand);
  await page.fill("#field-generic_name", "Amoxicillin");
  await page.selectOption("#field-dosage_form", "hard gelatin capsule");
  await page.fill("#field-shelf_life_months", "24");
  await page.fill("#field-storage_condition", "Store below 30 C.");
  await page.selectOption("#field-registration_type", "new");
  await page.click('button:has-text("Save and continue")');

  // manufacturer
  await page.fill("#field-name", "E2E Plant");
  await page.selectOption("#field-role", "finished product");
  await page.selectOption("#field-gmp_status", "certified");
  await page.click('button:has-text("Add manufacturer")');
  await expect(page.getByText("E2E Plant — finished product")).toBeVisible();
  await page.click('button:has-text("Next")');

  // two actives, each with its own strength (the combination-product case)
  for (const [inn, strength] of [
    ["Ampicillin", "250"],
    ["Cloxacillin", "250"],
  ]) {
    await page.fill("#field-inn_name", inn);
    await page.fill("#field-strength_value", strength);
    await page.fill("#field-strength_unit", "mg");
    await page.fill("#field-specifications", "Assay 95.0-105.0% per BP.");
    await page.click('button:has-text("Add active ingredient")');
    // Wait for the row before filling the next one: the draft clears
    // after the save resolves, which would otherwise wipe the new input.
    await expect(page.getByText(`${inn} ${strength} mg`)).toBeVisible();
  }

  // skip excipients and packaging; add the stability study that supports
  // the 24-month shelf life claimed on step 1
  await page.click('button:has-text("Next")');
  await page.click('button:has-text("Next")');
  await page.click('button:has-text("Next")');
  await page.selectOption("#field-study_type", "long-term");
  await page.fill("#field-condition", "30 C / 65 % RH");
  await page.fill("#field-duration_months", "24");
  await page.fill("#field-result_summary", "Within specification through 24 months.");
  await page.click('button:has-text("Add stability study")');
  await expect(page.getByText(/long-term — 30 C/)).toBeVisible();
  await page.click('button:has-text("Next")');

  // ---- create the project ----------------------------------------------
  await page.fill("#field-name", `${brand} filing`);
  await page.selectOption("#field-region", "NAFDAC");
  await page.click('button:has-text("Create project")');
  await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/);

  createdProjectId = page.url().split("/").pop() ?? null;
  // Capture the product id too, or afterAll would delete the project and
  // leave its product orphaned in the database.
  createdProductId = (
    await (
      await fetch(`${API}/projects/${createdProjectId}`, { headers: authHeaders() })
    ).json()
  ).product.id;

  // The derived strength proves both actives survived the round trip --
  // strength lives per active ingredient, not on the product.
  await expect(
    page.getByText("Ampicillin 250 mg + Cloxacillin 250 mg"),
  ).toBeVisible();

  // ---- narrative: generate, then approve --------------------------------
  await page.click('button:has-text("Narratives")');
  const generate = page.locator('button:has-text("Generate draft")').first();
  await expect(generate).toBeVisible();
  await generate.click();

  // An unreviewed draft must be visibly marked as not yet usable: only
  // approve/edit set final_text on the backend, and only final_text ever
  // reaches a rendered document.
  await expect(page.getByText("awaiting review").first()).toBeVisible();
  await page.locator('button:has-text("Approve")').first().click();
  await expect(page.getByText("APPROVED").first()).toBeVisible();

  // ---- validation: errors are visible, and provenance is shown ----------
  await page.click('button:has-text("Validation")');
  // "Blocked" appears twice by design (page header and the report), so
  // scope to the first rather than loosening the assertion.
  await expect(page.getByText("Blocked").first()).toBeVisible();
  await expect(page.getByText("data rule").first()).toBeVisible();

  // ---- build: refused while errors are unresolved -----------------------
  await page.click('button:has-text("Build")');
  // NAFDAC files a CTD, so the eCTD builder must not be offered. Match the
  // badge exactly so the "Build CTD package" button doesn't satisfy it.
  await expect(page.getByText("CTD package", { exact: true })).toBeVisible();
  await expect(
    page.locator('button:has-text("Build next eCTD sequence")'),
  ).toHaveCount(0);

  await page.click('button:has-text("Build CTD package")');
  // Unresolved ERROR findings mean the API answers 409, and the UI must
  // say so rather than pretend it built something.
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator('button:has-text("Download .zip")')).toHaveCount(0);

  // ---- override with a logged reason, the documented escape hatch -------
  const readiness = await (
    await fetch(`${API}/projects/${createdProjectId}/readiness`, {
      headers: authHeaders(),
    })
  ).json();
  const blocking: string[] = Array.from(
    new Set(
      readiness.findings
        .filter((f: { severity: string }) => f.severity === "ERROR")
        .map((f: { rule_id: string }) => f.rule_id),
    ),
  );
  expect(blocking.length).toBeGreaterThan(0);
  for (const ruleId of blocking) {
    await fetch(`${API}/projects/${createdProjectId}/validation-overrides`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        rule_id: ruleId,
        reason: "End-to-end test: exercising the documented override path.",
      }),
    });
  }

  // ---- now it builds, and downloads --------------------------------------
  await page.reload();
  await page.click('button:has-text("Build")');
  await page.click('button:has-text("Build CTD package")');

  const download = page.waitForEvent("download", { timeout: 120_000 });
  await page.locator('button:has-text("Download .zip")').click();
  const file = await download;
  expect(file.suggestedFilename()).toContain(".zip");

  // The blocked-build step deliberately provokes a 409, and browsers log
  // every failed fetch to the console -- so filter that one out rather
  // than dropping the guard, which still has to catch anything else.
  const unexpected = consoleErrors.filter(
    (message) => !message.includes("409"),
  );
  expect(unexpected).toEqual([]);
});
