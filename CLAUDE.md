# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Voice-AI SFIA Skills Assessment Platform** — An automated, voice-driven system that conducts real-time skills assessments against the SFIA 9 framework. A phone call from an AI bot conducts a structured interview, uses RAG to retrieve relevant SFIA definitions, extracts verifiable claims from the transcript, maps claims to SFIA skill codes, and produces a structured report for SME review.

**Status**: Planning/Documentation phase. No implementation code yet.

## Key Architecture Principles

### Hexagonal Architecture (Ports & Adapters)
Defined in [ADR-001](docs/development/adr/ADR-001-hexagonal-architecture.md). **Critical pattern for all code:**

- `packages/core` contains all business logic with **zero runtime dependencies** on external systems
- External systems (database, API, messaging) are accessed through **interfaces (Ports)** defined in `packages/core/src/ports/`
- Implementations (Adapters) live in `packages/adapters/src/` and are injected at startup
- This allows testing without real databases and swapping implementations without changing core logic

**Practical implication**: When adding a new external dependency:
1. Define an interface in `packages/core/src/ports/INewThing.ts`
2. Write business logic against the interface
3. Implement the adapter in `packages/adapters/src/`
4. Wire it in the relevant `apps/` entry point

### Monorepo Structure (pnpm + Turborepo)
Defined in [ADR-003](docs/development/adr/ADR-002-monorepo-structure.md). The repository uses:

- **pnpm workspaces** for package management (strict dependency isolation, content-addressable store)
- **Turborepo** for build orchestration (task graph, remote caching, parallel execution with correct ordering)

**Repository structure**:
```
ai-skills-assessor/
├── pnpm-workspace.yaml
├── turbo.json
├── package.json              ← root scripts only
├── tsconfig.base.json        ← shared TS config
│
├── packages/
│   ├── core/                 ← @ai-skills-assessor/core (business logic)
│   │   └── src/
│   │       ├── ports/        ← Interfaces
│   │       ├── assessment/
│   │       ├── rag/
│   │       ├── claim-extraction/
│   │       └── ...
│   │
│   ├── adapters/             ← @ai-skills-assessor/adapters (implementations)
│   │   └── src/
│   │       ├── database/
│   │       ├── vector-store/
│   │       └── ...
│   │
│   ├── api/                  ← @ai-skills-assessor/api (Express server)
│   │   └── src/
│   │       ├── app.ts        ← createApp(adapters)
│   │       ├── routes/
│   │       └── ...
│   │
│   └── web/                  ← @ai-skills-assessor/web (Next.js frontend)
│       └── src/
│           ├── app/          ← App Router
│           ├── components/
│           └── ...
│
└── apps/
    └── web-server/           ← Deployable entry point
        └── src/index.ts      ← Wires PostgresAdapter + other adapters

docs/development/
├── adr/                      ← Architecture Decision Records
├── prd/                      ← Product Requirements Documents
├── contracts/                ← Data type contracts (JSON Schema + TypeScript)
├── to-be-implemented/        ← Phase documents (Phases 1–6)
└── implemented/              ← Completed phase docs (versioned)
```

## Voice Engine Architecture

Defined in [ADR-004](docs/development/adr/ADR-004-voice-engine-technology.md):

- **Framework**: Pipecat (Python) — purpose-built for real-time voice AI with declarative state machines (Flows)
- **Telephony/WebRTC**: Daily (ap-southeast-2 Sydney region for +61 Australian numbers)
- **API Framework**: FastAPI (async-native, Pydantic validation, WebSocket support)
- **Assessment Flow State Machine**: Introduction → Skill Discovery → Evidence Gathering

Key architectural choice: Pipecat Flows maps directly to assessment phases, frame-based architecture supports interjections, DailyTransport is first-class.

The voice engine will be a separate deployable in `packages/voice-engine/` (or similar), exposed as FastAPI endpoints that the Next.js frontend and job queue can invoke.

## RAG & Vector Store

Defined in [ADR-005](docs/development/adr/ADR-005-rag-vector-store-strategy.md):

- **Vector Store**: pgvector (PostgreSQL extension) — keeps all data in one database, avoids separate infra
- **Chunking**: Per-skill-level with framework-type metadata (`framework_type`, `skill_code`, `level`)
- **Table**: `skill_embeddings` stores (framework, skill, level) tuples as vectors
- **Future extensibility**: Metadata-based filtering supports adding TOGAF, ITIL, PMBOK frameworks without schema changes
- **KnowledgeBase Port**: Abstracts the implementation — can swap pgvector for Pinecone/Weaviate later if needed

## Development Commands

Once the monorepo is bootstrapped, use:

```bash
# Install dependencies
pnpm install

# Build all packages
pnpm run build

# Build a specific package
pnpm --filter @ai-skills-assessor/core run build

# Run tests (when available)
pnpm run test
pnpm --filter @ai-skills-assessor/core run test

# Lint
pnpm run lint

# Watch mode (for development)
pnpm run dev

# Clean builds
pnpm run clean
```

See each package's `package.json` for specific scripts (e.g., `pnpm --filter @ai-skills-assessor/web run dev` for Next.js dev server).

## Key Documents

- **[PRD-001](docs/development/prd/PRD-001-voice-ai-sfia-assessment-platform.md)** — Master product requirements and system overview
- **[ADR-001](docs/development/adr/ADR-001-hexagonal-architecture.md)** — Hexagonal architecture pattern (read before coding)
- **[ADR-002](docs/development/adr/ADR-002-monorepo-structure.md)** — pnpm + Turborepo structure
- **[ADR-004](docs/development/adr/ADR-004-voice-engine-technology.md)** — Voice engine decisions (Pipecat, Daily, FastAPI)
- **[ADR-005](docs/development/adr/ADR-005-rag-vector-store-strategy.md)** — RAG and vector store (pgvector)
- **[Assessment Report Contract](docs/development/contracts/assessment-report-contract.md)** — Data types (JSON Schema + TypeScript) for assessment outputs
- **[Phase Documents](docs/development/to-be-implemented/)** — Phased implementation plan (6 phases)

## Implementation Workflow

When implementing a phase:

1. **Use `/check-prd`** to verify all PRDs are approved before starting
2. **Use `/implement-phase`** to begin work on a specific phase (command handles document verification)
3. **Refer to the phase document** for acceptance criteria, deliverables, and dependencies
4. **Follow Hexagonal Architecture**: Define ports first, implement adapters, wire in apps
5. **After completion**: Move phase doc from `to-be-implemented/` to `implemented/{version}/` with notes

## Important Patterns

- **Dependency Injection**: All adapters are injected into services at startup. No `new` statements for external dependencies in core logic.
- **Interfaces First**: Define `IDatabase`, `IVectorStore`, `IVoiceEngine` before implementing them.
- **Testing**: Create in-memory adapters for testing (e.g., `InMemoryDatabaseAdapter`). Tests never need real infrastructure.
- **Configuration**: Environment variables should be read at the app entry point (`apps/web-server/src/index.ts`), not scattered throughout core logic.

## Monorepo Workflow Tips

- Use `pnpm --filter [package-name]` to run commands on specific packages
- Turborepo automatically handles build ordering (e.g., builds core before api)
- Use `turbo run build --graph` to visualize the task dependency graph
- `.eslintrc.base.js` and `tsconfig.base.json` are shared; extend them in each package's local config

## Data Contract Compliance

All data structures shared between services (especially between voice engine and claim extraction) must comply with the [Assessment Report Contract](docs/development/contracts/assessment-report-contract.md). This includes:

- `AssessmentReport` — Top-level output structure
- `ExtractedClaim` — Individual claims with SFIA skill mapping
- `SkillLevel` — SFIA responsibility level (1–7)

Generate TypeScript from the contract schema to ensure consistency.

## Future Notes

- **Phase 1** will establish monorepo structure, database schema, port interfaces, and CI/CD
- **Phases 2–3** implement voice engine and RAG knowledge base
- **Phase 4** implements claim extraction and SFIA mapping
- **Phases 5–6** add SME review portal and deployment
