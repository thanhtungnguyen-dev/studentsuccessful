import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";

describe("ApiClient", () => {
  it("fetches health live status successfully", async () => {
    const mockData = { status: "ok", timestamp: "2026-09-05T00:00:00Z" };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockData,
    } as Response);

    const client = new ApiClient("http://localhost:8000");
    const result = await client.getHealthLive();

    expect(result.status).toBe("ok");
    expect(result.timestamp).toBe("2026-09-05T00:00:00Z");
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/health/live", {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
  });

  it("fetches health ready status correctly even with 503", async () => {
    const mockData = {
      status: "not_ready",
      dependencies: { database: false, storage: true },
      timestamp: "2026-09-05T00:00:00Z",
    };
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => mockData,
    } as Response);

    const client = new ApiClient("http://localhost:8000");
    const result = await client.getHealthReady();

    expect(result.status).toBe("not_ready");
    expect(result.dependencies.database).toBe(false);
  });
});
