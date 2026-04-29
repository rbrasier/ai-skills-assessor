# syntax=docker/dockerfile:1.6
#
# AI Skills Assessor — Next.js web image (Phase 3, v0.4.0).
#
# Multi-stage build:
#   1. `deps`     — install the pnpm workspace (Prisma client included).
#   2. `builder`  — generate the Prisma client and run `next build` with
#                   Next.js `output: "standalone"` so the runtime image is
#                   small (~150MB vs ~1GB for the full workspace).
#   3. `runner`   — minimal image; runs the standalone server as a
#                   non-root user, exposes port 3000 (Railway injects
#                   $PORT, the server respects it).
#
# This Dockerfile is monorepo-aware: build from the repo root so the
# pnpm workspace + shared-types + database packages are in scope.
#   docker build -f apps/web/Dockerfile .

ARG NODE_VERSION=20-alpine

# ─── Stage 1: deps ────────────────────────────────────────────────
FROM node:${NODE_VERSION} AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /repo

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY pnpm-workspace.yaml pnpm-lock.yaml package.json tsconfig.base.json turbo.json ./
COPY apps/web/package.json                 ./apps/web/package.json
COPY apps/voice-engine/pyproject.toml      ./apps/voice-engine/pyproject.toml
COPY packages/shared-types/package.json    ./packages/shared-types/package.json
COPY packages/database/package.json        ./packages/database/package.json

RUN pnpm install --frozen-lockfile

# ─── Stage 2: builder ─────────────────────────────────────────────
FROM node:${NODE_VERSION} AS builder
WORKDIR /repo

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY --from=deps /repo/node_modules                      ./node_modules
COPY --from=deps /repo/apps/web/node_modules             ./apps/web/node_modules
COPY --from=deps /repo/packages/shared-types/node_modules ./packages/shared-types/node_modules
COPY --from=deps /repo/packages/database/node_modules    ./packages/database/node_modules

COPY pnpm-workspace.yaml pnpm-lock.yaml package.json tsconfig.base.json turbo.json ./
COPY apps/web                 ./apps/web
COPY packages/shared-types    ./packages/shared-types
COPY packages/database        ./packages/database

# Prisma client is imported by @ai-skills-assessor/database; generate
# before the Next.js build.
RUN pnpm --filter @ai-skills-assessor/database run generate
RUN pnpm --filter @ai-skills-assessor/shared-types run build
RUN pnpm --filter @ai-skills-assessor/web run build

# ─── Stage 3: runner ──────────────────────────────────────────────
FROM node:${NODE_VERSION} AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 --ingroup nodejs nextjs

# Next.js `standalone` output bundles everything required to run the
# server under `apps/web/.next/standalone/` (preserving the monorepo
# paths). Copy that tree, the static assets, and the public folder.
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static    ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/public          ./apps/web/public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget --quiet --spider "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["node", "apps/web/server.js"]
