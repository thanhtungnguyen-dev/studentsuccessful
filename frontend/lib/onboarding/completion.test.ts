import { afterEach, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiClient, type CurrentUser } from "../api/client";
import { postAuthDestination } from "./routing";
import { AuthStatus } from "../../components/auth/AuthStatus";

const state = vi.hoisted(() => ({user: null as CurrentUser | null}));
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: () => ({user: state.user, error: "", refresh: vi.fn()}) }));
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); state.user = null; });
const user = { id: "owner", email: "owner@example.com", is_active: true, created_at: "2026-09-07T00:00:00Z", onboarding_completed_at: "2026-09-07T12:00:00Z" } satisfies CurrentUser;

it("sends only an empty payload, same-origin session and current CSRF cookie", async () => {
  vi.stubGlobal("document", {cookie: "ss_csrf=current-token"});
  const fetch = vi.fn().mockResolvedValue({ok:true, status:200, json:async () => user}); vi.stubGlobal("fetch", fetch);
  expect(await new ApiClient().completeOnboarding()).toEqual(user);
  expect(fetch).toHaveBeenCalledWith("/api/v1/auth/onboarding/complete", expect.objectContaining({method:"POST",body:"{}",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-CSRF-Token":"current-token"}}));
});
it("rejects a missing CSRF cookie before issuing a request", async () => {
  vi.stubGlobal("document", {cookie:""}); const fetch = vi.fn(); vi.stubGlobal("fetch",fetch);
  await expect(new ApiClient().completeOnboarding()).rejects.toMatchObject({status:403});expect(fetch).not.toHaveBeenCalled();
});
it.each([401,403,503])("preserves completion failures (%s) as understandable errors", async status => {
  vi.stubGlobal("document", {cookie:"ss_csrf=token"});vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,status}));
  await expect(new ApiClient().completeOnboarding()).rejects.toMatchObject({status, message:expect.any(String)});
});
it("uses backend completion after a fresh session read, including login and reload", async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,status:200,json:async () => user});vi.stubGlobal("fetch",fetch);
  for(let i=0;i<2;i++) { const current = await new ApiClient().getCurrentUser();expect(postAuthDestination(current!)).toBe("/"); }
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("directs incomplete users into review regardless of other account information", () => {
  expect(postAuthDestination({...user,onboarding_completed_at:null})).toBe("/onboarding/review");
});
it("home offers incomplete users Continue onboarding and keeps all editors accessible", () => {
  state.user = {...user,onboarding_completed_at:null};const html=renderToStaticMarkup(createElement(AuthStatus));
  expect(html).toContain("Continue onboarding");
  for(const route of ["/profile","/education","/employment","/work-authorization","/preferences"]) expect(html).toContain(`href="${route}"`);
});
it("completed home keeps editing and manual review available without forcing onboarding", () => {
  state.user=user;const html=renderToStaticMarkup(createElement(AuthStatus));
  expect(html).not.toContain("Continue onboarding");expect(html).toContain('href="/onboarding/review"');expect(html).toContain('href="/preferences"');
});
