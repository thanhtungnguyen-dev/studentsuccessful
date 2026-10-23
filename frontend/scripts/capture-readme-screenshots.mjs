/** Capture screenshots of the actual Next.js UI for the repository README. */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const origin = process.env.SCREENSHOT_BASE_URL || "http://127.0.0.1:3000";
const output = path.resolve(process.cwd(), "../docs/screenshots");
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  reducedMotion: "reduce",
  colorScheme: "light",
});
const page = await context.newPage();

async function capture(route, name, locator) {
  await page.goto(new URL(route, origin).toString(), { waitUntil: "domcontentloaded" });
  await page.locator(locator).first().waitFor({ state: "visible", timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1600);
  const imagePath = path.join(output, `${name}.jpg`);
  await page.screenshot({
    path: imagePath,
    type: "jpeg",
    quality: 85,
    animations: "disabled",
    caret: "hide",
    fullPage: false,
  });
  console.log(`Captured ${route} => ${imagePath}`);
}

try {
  await capture("/", "landing", "h1");
  await capture("/demo", "dashboard", ".desktop-sidebar");
  await capture("/jobs", "jobs", 'h1:has-text("Jobs")');
  await capture("/candidate", "candidate", 'h1:has-text("Candidate Profile")');
} finally {
  await browser.close();
}
