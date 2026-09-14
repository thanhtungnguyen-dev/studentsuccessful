import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

test("real registration, refresh, shared tabs, CSRF logout, and login", async ({ page, context }) => {
  const email = `r5-${randomUUID()}@example.com`;
  const password = "Example-browser-password-1";

  const accountEmail = (target: Page) =>
    target.locator(`[title="${email}"]:visible`).first();

  await page.goto("/");

  await expect(
    page.getByRole("link", { name: "Register", exact: true })
  ).toBeVisible();

  await expect(
    page.getByRole("link", { name: "Login", exact: true })
  ).toBeVisible();

  await page.screenshot({
    path: test.info().outputPath("signed-out.png"),
  });

  await page
    .getByRole("link", { name: "Register", exact: true })
    .click();

  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill("mismatch");

  await page
    .getByRole("button", { name: "Register", exact: true })
    .click();

  await expect(
    page.getByRole("main").getByRole("alert")
  ).toHaveText("Passwords do not match.");

  await page.getByLabel("Confirm password").fill(password);

  await page
    .getByRole("button", { name: "Register", exact: true })
    .click();

  await expect(page).toHaveURL(
    "http://localhost:3000/onboarding/review"
  );

  await page
    .getByRole("button", {
      name: "Complete onboarding",
      exact: true,
    })
    .click();

  await expect(page).toHaveURL("http://localhost:3000/");

  // Current UI shows the account email directly instead of
  // rendering "Signed in as <email>".
  await expect(accountEmail(page)).toHaveText(email);

  // Browser automation may inspect HttpOnly metadata;
  // application JS never reads it.
  const cookies = await context.cookies();

  const session = cookies.find(
    (cookie) => cookie.name === "ss_session"
  )!;

  expect(Boolean(session?.httpOnly)).toBe(true);

  expect(
    cookies.some(
      (cookie) =>
        cookie.name === "ss_csrf" &&
        !cookie.httpOnly
    )
  ).toBe(true);

  // Session persists after refresh.
  await page.reload();
  await expect(accountEmail(page)).toHaveText(email);

  // Session is shared across tabs.
  const second = await context.newPage();

  await second.goto("/");
  await expect(accountEmail(second)).toHaveText(email);

  await page.bringToFront();

  // Logout is inside the current desktop account menu.
  await page
    .getByRole("button", {
      name: `Account menu for ${email}`,
      exact: true,
    })
    .click();

  const [request] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.url().endsWith("/api/v1/auth/logout") &&
        request.method() === "POST"
    ),
    page
      .getByRole("menuitem", {
        name: "Logout",
        exact: true,
      })
      .click(),
  ]);

  const csrf = cookies.find(
    (cookie) => cookie.name === "ss_csrf"
  )!;

  expect(
    request.headers()["x-csrf-token"] === csrf.value
  ).toBe(true);

  await expect(
    page.getByRole("link", {
      name: "Login",
      exact: true,
    })
  ).toBeVisible();

  // Logout must invalidate the session in the other tab too.
  await second.reload();

  await expect(
    second.getByRole("link", {
      name: "Login",
      exact: true,
    })
  ).toBeVisible();

  await expect(
    second.locator(`[title="${email}"]:visible`)
  ).toHaveCount(0);

  // A cleared browser cookie alone is insufficient:
  // the old session must be revoked server-side.
  const replay = await context.request.get(
    "/api/v1/auth/me",
    {
      headers: {
        Cookie: `ss_session=${session.value}`,
      },
    }
  );

  expect(replay.status()).toBe(401);

  // Login again.
  await page.bringToFront();

  await page
    .getByRole("link", {
      name: "Login",
      exact: true,
    })
    .click();

  await page.getByLabel("Email", { exact: true }).fill(email);

  await page
    .getByLabel("Password", { exact: true })
    .fill("wrong-password");

  await page
    .getByRole("button", {
      name: "Login",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("main").getByRole("alert")
  ).toHaveText("Invalid email or password.");

  await page
    .getByLabel("Password", { exact: true })
    .fill(password);

  await page
    .getByRole("button", {
      name: "Login",
      exact: true,
    })
    .click();

  await expect(page).toHaveURL("http://localhost:3000/");
  await expect(accountEmail(page)).toHaveText(email);

  // The real backend duplicate-registration response
  // is presented safely.
  await page.screenshot({
    path: test.info().outputPath("signed-in.png"),
  });

  await page.setViewportSize({
    width: 390,
    height: 844,
  });

  await page.screenshot({
    path: test.info().outputPath("signed-in-mobile.png"),
  });

  await page.goto("/register");

  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);

  await page
    .getByRole("button", {
      name: "Register",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("main").getByRole("alert")
  ).toHaveText(
    "An account with this email already exists. Please log in."
  );
});