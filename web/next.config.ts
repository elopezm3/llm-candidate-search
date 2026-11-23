import type { NextConfig } from "next";

// Static export: the public build is plain HTML + demo.json, no server, no API keys.
const config: NextConfig = { output: "export" };
export default config;
