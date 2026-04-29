# Voice-AI SFIA Skills Assessment Platform

An automated, voice-driven system that conducts real-time skills assessments against the [SFIA 9 framework](https://sfia-online.org/en/sfia-9). A phone call from an AI bot conducts a structured interview, uses RAG to retrieve relevant SFIA definitions, extracts verifiable claims from the transcript, maps claims to SFIA skill codes, and produces a structured report for SME review.

**Status**: Planning/Documentation phase — active implementation in progress.

**Geographic Focus**: Australian market (+61 numbers, `ap-southeast-2` Sydney region).

---

## How It Works

1. **Administrator** triggers an assessment call for a candidate via the web dashboard.
2. **AI bot** conducts a structured interview (Skill Discovery → Evidence Gathering), dynamically adapting questions based on stated skills and evidence.
3. **Post-call**, the system extracts verifiable work claims and maps them to SFIA skill codes and levels.
4. **SME Reviewer** receives a structured report with transcript excerpts, confidence scores, and an approval workflow.
5. **Final assessment** is signed off and stored.

---

## Architecture

This is a **pnpm monorepo** using Turborepo for build orchestration, following **Hexagonal Architecture** (Ports & Adapters).

```
ai-skills-assessor/
├── apps/
│   ├── voice-engine/     ← Python/FastAPI + Pipecat voice AI (telephony via Daily)
│   ├── web/              ← Next.js frontend (dashboard, SME review portal)
│   ├── database/         ← PostgreSQL + pgvector migrations
│   └── shared-types/     ← Shared TypeScript types
│
├── packages/
│   ├── core/             ← Business logic (zero runtime external deps)
│   ├── adapters/         ← Port implementations (DB, vector store, voice)
│   └── api/              ← Express API server
│
└── docs/
    ├── adr/              ← Architecture Decision Records
    ├── prd/              ← Product Requirements Documents
    ├── contracts/        ← Shared data type contracts (JSON Schema + TypeScript)
    └── to-be-implemented/ ← Phased implementation plan
```

**Key architectural decisions:**

- **[ADR-001](docs/development/adr/ADR-001-hexagonal-architecture.md)** — Hexagonal Architecture: core business logic has zero runtime external dependencies; external systems accessed through port interfaces.
- **[ADR-002](docs/development/adr/ADR-002-monorepo-structure.md)** — pnpm workspaces + Turborepo for build orchestration.
- **[ADR-004](docs/development/adr/ADR-004-voice-engine-technology.md)** — Voice engine: Pipecat (Python) + Daily (WebRTC/PSTN) + FastAPI.
- **[ADR-005](docs/development/adr/ADR-005-rag-vector-store-strategy.md)** — RAG: pgvector (PostgreSQL) with per-skill-level chunks and metadata filtering.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Voice AI framework | [Pipecat](https://github.com/pipecat-ai/pipecat) (Python) |
| Telephony / WebRTC | [Daily](https://www.daily.co/) |
| Voice API server | FastAPI |
| Frontend | Next.js (TypeScript) |
| API server | Express (TypeScript) |
| Database | PostgreSQL + pgvector |
| Package manager | pnpm |
| Build orchestration | Turborepo |
| Skills framework | SFIA 9 |

---

## Development

### Prerequisites

- Node.js 20+
- pnpm 9+
- Python 3.11+ (for voice engine)

### Setup

```bash
pnpm install
```

### Common Commands

```bash
# Build all packages
pnpm run build

# Build a specific package
pnpm --filter @ai-skills-assessor/core run build

# Run all tests
pnpm run test

# Lint
pnpm run lint

# Dev mode (watch)
pnpm run dev

# Clean build artifacts
pnpm run clean
```

---

## Documentation

- **[PRD-001](docs/development/prd/PRD-001-voice-ai-sfia-assessment-platform.md)** — Master product requirements
- **[PRD-002](docs/development/prd/PRD-002-assessment-interview-workflow.md)** — Assessment interview workflow
- **[Assessment Report Contract](docs/development/contracts/assessment-report-contract.md)** — Shared data types (JSON Schema + TypeScript)
- **[Implementation Phases](docs/development/to-be-implemented/)** — Phased build plan
