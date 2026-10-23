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
