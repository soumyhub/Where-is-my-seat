import type { NextConfig } from "next";

// Where the FastAPI backend runs. Read when the server starts (dev) or builds (prod).
const API_URL = process.env.WIMS_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // On Vercel, vercel.json sends /api/* to the backend service before it reaches Next.js.
    if (process.env.VERCEL) return [];
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
