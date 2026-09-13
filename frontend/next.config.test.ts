import { describe, expect, it } from "vitest";
import { contentSecurityPolicy } from "./next.config";

describe("Content-Security-Policy", () => {
  it("permits eval required by Next.js development tooling only in development", () => {
    expect(contentSecurityPolicy("development")).toContain("script-src 'self' 'unsafe-inline' 'unsafe-eval'");
  });

  it("does not permit eval in production", () => {
    const policy = contentSecurityPolicy("production");

    expect(policy).toContain("script-src 'self' 'unsafe-inline'");
    expect(policy).not.toContain("'unsafe-eval'");
  });
});
