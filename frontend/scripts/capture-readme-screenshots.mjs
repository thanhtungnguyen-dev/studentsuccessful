/** Capture screenshots of the actual Next.js UI for the repository README. */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const origin = process.env.SCREENSHOT_BASE_URL || "http://127.0.0.1:3000";
const output = path.resolve(process.cwd(), "../docs/screenshots");
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
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
  // Additional workspace screens used for UX review (actual browser captures).
  await capture("/applications", "applications", 'h1:has-text("Applications")');
  await capture("/resumes", "resumes", 'h1:has-text("Resumes")');
  await capture("/projects", "projects", 'h1:has-text("Projects")');
  await capture("/skills", "skills", 'h1:has-text("Skills")');

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
    colorScheme: "light",
  });
  try {
    const mobilePage = await mobile.newPage();
    await mobilePage.goto(new URL("/demo", origin).toString(), { waitUntil: "domcontentloaded" });
    await mobilePage.locator(".mobile-topbar").first().waitFor({ state: "visible", timeout: 30000 });
    await mobilePage.evaluate(() => document.fonts.ready);
    await mobilePage.waitForTimeout(1200);
    await mobilePage.screenshot({ path: path.join(output, "mobile-workspace.jpg"), type: "jpeg", quality: 86, fullPage: false });
    console.log("Captured mobile workspace");
  } finally {
    await mobile.close();
  }
} finally {
  await browser.close();
}
