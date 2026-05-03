// next/font/google fetches font manifests at build time. In environments that
// use a self-signed CA (e.g. this CI/dev sandbox), the fetch fails unless TLS
// verification is relaxed. This is scoped to the Next.js build process only.
if (process.env.NODE_ENV !== "production") {
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
}

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
