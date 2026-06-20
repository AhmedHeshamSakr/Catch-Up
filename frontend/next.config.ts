import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: `next build` emits `out/`, which FastAPI serves at / alongside
  // /api in single-port desktop mode. No dynamic route segments remain (digest
  // detail is /digests?run=<id>), so the export is clean.
  output: "export",
};

export default nextConfig;
