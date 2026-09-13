import { defineConfig } from "vitest/config";

export default defineConfig({ oxc: { jsx: { runtime: "automatic" } }, test: { include: ["lib/**/*.test.ts", "next.config.test.ts"] } });
