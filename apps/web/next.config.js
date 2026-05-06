// next/font/google fetches font manifests at build time. In environments that
// use a self-signed CA (e.g. this CI/dev sandbox), the fetch fails unless TLS
// verification is relaxed. Applied unconditionally since next build sets
// NODE_ENV=production and would otherwise skip this in the same sandbox.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@ai-skills-assessor/shared-types"],
  // Phase 3: enable Next.js standalone output so the Railway Docker image
  // ships just the compiled server + required node_modules (~150MB) rather
  // than the full monorepo (~1GB). See
  // docs/guides/deployed-setup.md §2.
  output: "standalone",
};

module.exports = nextConfig;
