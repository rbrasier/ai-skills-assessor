# ADR-003: Monorepo Structure with pnpm Workspaces + Turborepo

## Status
Accepted

## Date
2026-02-18

## Context

AI Skills Assessor has multiple deployable units that share code:
- `packages/core` — business logic shared by API, and potentially a CLI
- `packages/adapters` — platform implementations
- `packages/api` — Express server
- `packages/web` — Next.js frontend
- `apps/web-server` — wires adapters for web deployment

In a multi-repo setup, sharing `packages/core` would require publishing it to npm (slow, versioning overhead) or using `npm link` (fragile). A monorepo solves this cleanly.

## Decision

Use **pnpm workspaces** for package management and **Turborepo** for build orchestration.

### Why pnpm over npm/yarn workspaces?
- Strict dependency isolation (prevents phantom dependencies)
- Content-addressable store (shared packages, fast installs)
- `--filter` flag makes running scripts on specific packages straightforward
- Better performance than npm/yarn for large monorepos

### Why Turborepo?
- Task graph: knows that `api` depends on `core` being built first
- Remote caching: CI never rebuilds unchanged packages
- Parallel execution with correct ordering
- Simple `turbo.json` config, no complex scripting needed

### Repository Structure

```
orchestra/
├── pnpm-workspace.yaml
├── turbo.json
├── package.json                    ← root scripts only
├── tsconfig.base.json              ← shared TS config
├── .eslintrc.base.js               ← shared ESLint rules
│
├── packages/
│   ├── core/                       ← @orchestra/core
│   │   ├── package.json
│   │   ├── tsconfig.json           ← extends base
│   │   └── src/
│   │       ├── ports/              ← Interfaces
│   │       ├── email/
│   │       ├── ai/
│   │       ├── assistants/
│   │       ├── calendar/
│   │       ├── automation/
│   │       ├── billing/
│   │       ├── organisations/
│   │       └── config/
│   │
│   ├── adapters/                   ← @orchestra/adapters
│   │   ├── package.json
│   │   └── src/
│   │       ├── database/
│   │       └── storage/
│   │
│   ├── api/                        ← @ai-skills-assessor/api
│   │   ├── package.json
│   │   └── src/
│   │       ├── app.ts              ← createApp(adapters)
│   │       ├── routes/
│   │       ├── controllers/
│   │       └── middleware/
│   │
│   └── web/                        ← @ai-skills-assessor/web
│       ├── package.json
│       └── src/
│           ├── app/                ← Next.js App Router
│           ├── components/
│           ├── stores/             ← Zustand
│           └── lib/
│
├── apps/
│   ├── web-server/                 ← Deployable: web + API
│       ├── package.json
│       └── src/index.ts           ← Wires PostgresAdapter + BullMQ + SocketIO
│   
|
│
└── docs/development/
    ├── adr/
    ├── prd/
    ├── to-be-implented/
    └── implemented/
        ├── v0.1/
        └── {other versions}   

```

### turbo.json

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["^build"]
    },
    "lint": {},
    "typecheck": {
      "dependsOn": ["^build"]
    }
  }
}
```

`"^build"` means: build my dependencies first. So `@orchestra/api` will not build until `@orchestra/core` and `@orchestra/adapters` have built successfully.

### Package Naming

All internal packages use the `@orchestra/` scope:
- `@orchestra/core`
- `@orchestra/adapters`
- `@orchestra/api`
- `@orchestra/web`

These are private packages (not published to npm). The scope just provides namespacing.

## Consequences

**Positive:**
- One `pnpm install` at root installs everything
- `pnpm --filter @orchestra/core test` runs tests for a single package
- Turborepo caches build outputs — `pnpm build` only rebuilds what changed
- TypeScript project references give proper cross-package type checking
- Single ESLint and Prettier config across all packages

**Negative:**
- More complex initial setup than a single package
- Developers must understand which package a new file belongs in
- Some tooling (IDE plugins, some test runners) needs monorepo-aware configuration
