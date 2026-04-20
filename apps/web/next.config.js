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
