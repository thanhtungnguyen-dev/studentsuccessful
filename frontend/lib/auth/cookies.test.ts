import { afterEach, describe, expect, it, vi } from "vitest";
import { readCsrfCookie } from "./cookies";

afterEach(() => vi.unstubAllGlobals());
describe("current CSRF cookie", () => {
  it("is absent outside the browser", () => { expect(readCsrfCookie()).toBeNull(); });
  it.each(["", "other_ss_csrf=wrong", "ss_csrf=", "ss_csrf=%broken"])("rejects missing or malformed values: %s", (cookie) => {
    vi.stubGlobal("document", { cookie }); expect(readCsrfCookie()).toBeNull();
  });
  it("finds the exact cookie name and decodes its value", () => {
    vi.stubGlobal("document", { cookie: "other=1; ss_csrf=abc%3Ddef; last=2" });
    expect(readCsrfCookie()).toBe("abc=def");
  });
});
