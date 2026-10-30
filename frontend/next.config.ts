import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/health", destination: `${backend}/health` },
            { source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  /* config options here */
  experimental: {
    agentFeedback: true,
    // SAM recovery and video indexing can outlast the rewrite proxy's 30s default.
    proxyTimeout: 600_000,
  },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
