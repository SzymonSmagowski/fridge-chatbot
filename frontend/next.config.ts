import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the production Docker build — emits .next/standalone/ with
  // only the files actually imported. Run with `node .next/standalone/server.js`,
  // NOT `next start` (Next.js 16 explicitly warns about that combination).
  output: "standalone",
};

export default nextConfig;
