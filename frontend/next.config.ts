import type { NextConfig } from "next";

// next build persists rewrite destinations; rebuild to change the backend URL.
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

export const contentSecurityPolicy = (nodeEnv = process.env.NODE_ENV) =>
  "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self' data:; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self' 'unsafe-inline'"
  + (nodeEnv === "development" ? " 'unsafe-eval'" : "")
  + "; style-src 'self' 'unsafe-inline'";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  outputFileTracingRoot: __dirname,
  // CI runs ESLint directly; Next 15 embeds a runner for older ESLint versions.
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: contentSecurityPolicy() },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=()" },
      ],
    }];
  },
  async rewrites() {
    return [
      {
        source: "/health/:path*",
        destination: `${BACKEND_URL}/health/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
      {
        source: "/openapi.json",
        destination: `${BACKEND_URL}/openapi.json`,
      },
      {
        source: "/docs",
        destination: `${BACKEND_URL}/docs`,
      },
    ];
  },
};

export default nextConfig;
