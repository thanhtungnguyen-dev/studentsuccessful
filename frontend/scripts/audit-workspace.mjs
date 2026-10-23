/** Browser smoke audit of the real frontend-only workspace at desktop and mobile sizes. */
import { chromium } from "@playwright/test";

const origin = process.env.SCREENSHOT_BASE_URL || "http://127.0.0.1:3000";
const routes = [
  "/demo", "/jobs", "/applications", "/candidate", "/profile", "/education",
  "/employment", "/work-authorization", "/preferences", "/skills", "/projects",
  "/resumes", "/artifacts", "/alerts",
];
const browser = await chromium.launch({ channel: "chrome", headless: true });
const failures = [];

for (const width of [1440, 390]) {
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    reducedMotion: "reduce",
    colorScheme: "light",
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    // /demo activates a browser-local session; never use production authentication.
    await page.goto(new URL("/demo", origin).toString(), { waitUntil: "domcontentloaded" });
    await page.locator('.workspace-nav a[href="/jobs"]').first().waitFor({ state: "attached", timeout: 20000 });

    for (const route of routes) {
      const before = pageErrors.length;
      try {
        await page.goto(new URL(route, origin).toString(), { waitUntil: "domcontentloaded" });
        await page.locator("main").first().waitFor({ state: "attached", timeout: 20000 });
        await page.waitForTimeout(550);

        const details = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          viewport: window.innerWidth,
          title: document.querySelector("h1")?.textContent?.trim() || "",
          broken: Boolean(document.querySelector(".next-error-h1")),
        }));
        if (details.scrollWidth > details.viewport + 4) {
          failures.push(`${width}px ${route}: horizontal overflow (${details.scrollWidth}px > ${details.viewport}px)`);
        }
        if (!details.title || details.broken) {
          failures.push(`${width}px ${route}: missing page heading or route error`);
        }
        for (const message of pageErrors.slice(before)) {
          failures.push(`${width}px ${route}: JavaScript error: ${message}`);
        }
        console.log(`PASS ${width}px ${route} — ${details.title}`);
      } catch (error) {
        failures.push(`${width}px ${route}: ${error.message}`);
      }
    }
    // Exercise representative interactions, not just the ability to render routes.
    try {
      await page.goto(new URL("/jobs", origin).toString(), { waitUntil: "domcontentloaded" });
      await page.locator(".job-card").first().waitFor({ state: "visible", timeout: 15000 });
      if (width === 390) {
        await page.getByRole("button", { name: /^Filter jobs/ }).click();
        await page.locator(".job-filter-toolbar.filters-open").waitFor({ state: "visible" });
        await page.getByRole("button", { name: "Apply filters" }).click();
        await page.locator(".job-filter-toolbar:not(.filters-open)").waitFor({ state: "attached" });
        console.log("PASS mobile job filter toggle and Apply flow");
      }
      const firstJob = page.locator(".job-card .job-result-select").first();
      await firstJob.click();
      await page.locator(".job-detail").first().waitFor({ state: "visible", timeout: 15000 });
      const advanced = page.locator(".job-advanced-analysis").first();
      await advanced.locator("summary").click();
      await advanced.getByRole("link", { name: "View skill gap analysis" }).waitFor({ state: "visible" });
      const fitLink = page.getByRole("link", { name: "View fit analysis" }).first();
      await fitLink.click();
      await page.getByRole("navigation", { name: "Compare this job" }).waitFor({ state: "visible" });
      if (!await page.getByRole("link", { name: "Resume coverage" }).isVisible()) {
        failures.push(width + "px: analysis navigation missing");
      }
      console.log("PASS " + width + "px job selection, progressive tools and analysis navigation");
    } catch (error) { failures.push(width + "px job interaction: " + error.message); }

    try {
      await page.goto(new URL("/resumes", origin).toString(), { waitUntil: "domcontentloaded" });
      const more = page.locator(".resume-version .resume-more-menu").first();
      await more.locator("summary").waitFor({ state: "visible", timeout: 15000 });
      await more.locator("summary").click();
      await more.getByRole("button", { name: /Check evidence|Retry check/ }).waitFor({ state: "visible" });
      console.log("PASS " + width + "px resume version advanced controls");
    } catch (error) { failures.push(width + "px resume advanced controls: " + error.message); }

    try {
      await page.goto(new URL("/candidate", origin).toString(), { waitUntil: "domcontentloaded" });
      const search = page.getByPlaceholder("Find a skill");
      await search.waitFor({ state: "visible", timeout: 15000 });
      await search.fill("Python");
      await page.locator(".candidate-skill-chip").first().waitFor({ state: "visible", timeout: 15000 });
      const names = await page.locator(".candidate-skill-chip").allTextContents();
      if (!names.length || names.some(name => !name.toLowerCase().includes("python"))) {
        failures.push(width + "px candidate search did not filter skills");
      } else console.log("PASS " + width + "px candidate skill search");
      await search.fill("");
    } catch (error) { failures.push(width + "px candidate search: " + error.message); }

    try {
      await page.goto(new URL("/applications", origin).toString(), { waitUntil: "domcontentloaded" });
      const select = page.locator('select[aria-label^="Update status for"]').first();
      await select.waitFor({ state: "visible", timeout: 15000 });
      const before = await select.inputValue();
      const after = before === "INTERVIEW" ? "APPLIED" : "INTERVIEW";
      await select.selectOption(after);
      const beforeSave = await page.locator(".application-card .application-status").first().textContent();
      if (beforeSave?.trim().toUpperCase() !== before) {
        failures.push(width + "px application status changed before the Save action");
      }
      await page.getByRole("button", { name: "Save status" }).first().click();
      await page.waitForFunction(expected => {
        const element = document.querySelector('select[aria-label^="Update status for"]');
        return element && element.value === expected;
      }, after, { timeout: 15000 });
      await page.waitForTimeout(500);
      await page.reload({ waitUntil: "domcontentloaded" });
      await select.waitFor({ state: "visible", timeout: 15000 });
      if (await select.inputValue() !== after) failures.push(width + "px application status did not persist after refresh");
      else console.log("PASS " + width + "px application status persists");
    } catch (error) { failures.push(width + "px application status update: " + error.message); }
  } finally {
    await context.close();
  }
}
await browser.close();

if (failures.length) {
  console.error("Browser UX smoke issues:\n" + failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log("Browser UX smoke passed: 14 routes at desktop and mobile widths.");
}
