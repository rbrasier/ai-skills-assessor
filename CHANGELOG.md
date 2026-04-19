# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-19

### Added — Phase 1: Foundation & Monorepo Scaffold

- pnpm + Turborepo monorepo structure (`pnpm-workspace.yaml`, `turbo.json`).
- Shared TypeScript, ESLint, and Prettier base configurations.
- `packages/shared-types` with `AssessmentTriggerRequest` / `AssessmentTriggerResponse`.
- `packages/database` with Prisma schema for `Candidate` and `AssessmentSession`,
  plus initial migration `v0_2_0_init_schema/migration.sql`.
- `apps/web` Next.js 14 (App Router) shell with `/api/health`,
  `/api/assessment/trigger`, and stub pages for landing, dashboard, and SME review.
- `apps/voice-engine` FastAPI shell with:
  - Domain models (`AssessmentSession`, `CallConfig`, `CallConnection`,
    `Transcript`, `TranscriptSegment`, plus stub `Claim` / `SkillDefinition` models).
  - Port interfaces (`IAssessmentTrigger`, `IVoiceTransport`, `IPersistence`).
  - Adapter stubs for Daily transport, pgvector knowledge base, Postgres
    persistence, and Anthropic LLM provider.
  - `/health` and `/api/v1/assessment/trigger` endpoints.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) covering lint,
  typecheck, build, TypeScript tests, and Python lint/typecheck/tests.

### Notes

- This is the initial scaffold release; no business logic is implemented yet.
- All adapter implementations are stubs that raise `NotImplementedError`; they
  will be filled in by subsequent phases.

## [0.1.0] - 2026-04-18

### Added

- Initial documentation set: PRDs, ADRs, contract specs, and phase plans.
