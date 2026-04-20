# Phase 1: Foundation & Monorepo Scaffold

## Status
To Be Implemented

## Date
2026-04-19 (Last Updated)

## References
- PRD-001: Voice-AI SFIA Skills Assessment Platform
- ADR-001: Hexagonal Architecture
- ADR-003: Monorepo Structure (pnpm + Turborepo)

## Objective

Establish the monorepo foundation, CI/CD skeleton, database schema, shared type contracts, and project tooling so that all subsequent phases can build on a stable, consistent base.

---

## 0. Prerequisite: Version Bump

Before starting Phase 1 implementation, a **MINOR version bump** is required (this phase includes database migrations):

1. Run `/bump-version` in Claude Code to bump from v0.1.0 → v0.2.0
2. Create a new migration file using the version number: `v0_2_0_init_schema.ts`
3. Update CHANGELOG.md with v0.2.0 entry
4. Commit the version bump before implementing Phase 1 deliverables

---

## 1. Deliverables

**Build in this order to avoid re-work:**
1. **1.1 Monorepo Root Configuration** — pnpm-workspace.yaml, turbo.json, tsconfig.base.json, shared configs
2. **1.2 apps/web & apps/voice-engine scaffolds** — create package structures and basic imports
3. **1.3 packages/database schema** — Prisma schema, migrations, and basic models
4. **1.4 packages/shared-types** — TypeScript types (minimal: AssessmentTrigger types only)
5. **1.5 Port definitions** — Python ABC interfaces in voice-engine/src/domain/

---

### 1.1 Monorepo Root Configuration

**Files to create:**

```
ai-skills-assessor/
├── pnpm-workspace.yaml
├── turbo.json
├── package.json              ← Root scripts, devDependencies
├── tsconfig.base.json        ← Shared TypeScript config
├── .eslintrc.base.js         ← Shared ESLint config
├── .prettierrc               ← Prettier config
├── .gitignore
├── .nvmrc                    ← Node version pin (20 LTS)
└── .python-version           ← Python version pin (3.11+)
```

**`pnpm-workspace.yaml`:**

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

**`turbo.json`:**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**"]
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

**Root `package.json` scripts:**

```json
{
  "scripts": {
    "dev": "turbo dev",
    "build": "turbo build",
    "test": "turbo test",
    "lint": "turbo lint",
    "typecheck": "turbo typecheck",
    "db:generate": "pnpm --filter @ai-skills-assessor/database generate",
    "db:migrate": "pnpm --filter @ai-skills-assessor/database migrate",
    "db:seed": "pnpm --filter @ai-skills-assessor/database seed"
  }
}
```

### 1.2 `apps/web` — Next.js Frontend Shell

**Scaffold with:**
```bash
pnpm create next-app apps/web --typescript --tailwind --app --src-dir --eslint
```

**Additional dependencies:**
- `lucide-react` — Icon library
- `@ai-skills-assessor/shared-types` — Internal shared types package

**Key files:**
```
apps/web/
├── package.json               ← @ai-skills-assessor/web
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json              ← extends ../../tsconfig.base.json
├── src/
│   ├── app/
│   │   ├── layout.tsx         ← Root layout with Tailwind
│   │   ├── page.tsx           ← Landing/dashboard stub
│   │   ├── (dashboard)/
│   │   │   └── page.tsx       ← Admin dashboard stub
│   │   ├── (review)/
│   │   │   └── [token]/
│   │   │       └── page.tsx   ← SME review page stub
│   │   └── api/
│   │       └── assessment/
│   │           └── trigger/
│   │               └── route.ts  ← POST: trigger assessment call
│   ├── components/
│   │   └── ui/                ← Shared UI components
│   └── lib/
│       ├── api-client.ts      ← Voice engine API client
│       └── types.ts           ← Re-exports from shared-types
```

**API route stubs:**

`apps/web/src/app/api/health/route.ts`:
```typescript
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ status: "ok" });
}
```

`apps/web/src/app/api/assessment/trigger/route.ts`:
```typescript
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { phoneNumber, candidateId } = body;

  // Forward to voice engine
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL || "http://localhost:8000";
  const response = await fetch(`${voiceEngineUrl}/api/v1/assessment/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phoneNumber, candidate_id: candidateId }),
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
```

### 1.3 `apps/voice-engine` — Python Service Shell

**Note:** The voice engine uses Prisma (via TypeScript adapters) to query the database. Phase 1 scaffolds the Python structure with port definitions; actual port implementations and integrations happen in later phases.

**Project structure:**
```
apps/voice-engine/
├── pyproject.toml
├── Dockerfile
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI app entry point
│   ├── config.py                  ← Pydantic Settings
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── ports/
│   │   │   ├── __init__.py
│   │   │   ├── assessment_trigger.py    ← AssessmentTrigger port
│   │   │   ├── voice_transport.py       ← VoiceTransport port
│   │   │   ├── knowledge_base.py        ← KnowledgeBase port
│   │   │   ├── persistence.py           ← Persistence port
│   │   │   └── llm_provider.py          ← LLMProvider port
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── assessment.py            ← AssessmentSession, CallConfig
│   │   │   ├── claim.py                 ← Claim, ClaimMapping
│   │   │   ├── skill.py                 ← SkillDefinition, SFIALevel
│   │   │   └── transcript.py            ← Transcript, TranscriptSegment
│   │   └── services/
│   │       ├── __init__.py
│   │       └── assessment_orchestrator.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── daily_transport.py           ← DailyTransport adapter (stub)
│   │   ├── pgvector_knowledge_base.py   ← PgVectorKnowledgeBase adapter (stub)
│   │   ├── postgres_persistence.py      ← PostgresPersistence adapter (stub)
│   │   └── anthropic_llm_provider.py    ← AnthropicLLMProvider adapter (stub)
│   ├── flows/
│   │   ├── __init__.py
│   │   └── sfia_flow_controller.py      ← Pipecat Flows state machine (stub)
│   └── api/
│       ├── __init__.py
│       └── routes.py                    ← FastAPI routes
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── domain/
│       └── __init__.py
```

**`pyproject.toml` dependencies:**

```toml
[project]
name = "voice-engine"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.30.0",
    "pipecat-ai[daily,openai,anthropic,deepgram]>=0.0.47",
    "asyncpg>=0.29.0",
    "pgvector>=0.3.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "anthropic>=0.30.0",
    "nanoid>=2.0.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0",
    "ruff>=0.5.0",
    "mypy>=1.10",
]
```

### 1.4 `packages/database` — PostgreSQL Schema with Prisma

**Structure:**
```
packages/database/
├── package.json               ← @ai-skills-assessor/database
├── prisma/
│   ├── schema.prisma          ← Schema definition
│   └── migrations/
│       └── v0_2_0_init_schema/
│           └── migration.sql
├── src/
│   ├── index.ts               ← Generated Prisma client exports
│   └── seed.ts                ← Empty seed file (populated in later phases)
└── .env.example
```

**Core schema (Prisma):**

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Candidate {
  id        String   @id @default(uuid())
  firstName String   @db.VarChar(255)
  lastName  String   @db.VarChar(255)
  email     String   @unique @db.VarChar(255)
  phoneNumber String @db.VarChar(20)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  assessmentSessions AssessmentSession[]

  @@index([email])
  @@index([createdAt])
}

model AssessmentSession {
  id            String   @id @default(uuid())
  candidateId   String
  candidate     Candidate @relation(fields: [candidateId], references: [id], onDelete: Cascade)
  phoneNumber   String   @db.VarChar(20)
  status        String   @default("pending") // pending, dialling, in_progress, completed, failed, cancelled
  dailyRoomUrl  String?
  recordingUrl  String?
  startedAt     DateTime?
  endedAt       DateTime?
  createdAt     DateTime @default(now())

  @@index([candidateId])
  @@index([candidateId, createdAt])
  @@index([status])
}
```

**Notes:**
- `candidates.email` is **unique** per business requirement
- `assessment_sessions.phone_number` is **denormalized** for easy access during calls (not indexed unless queries by phone are needed)
- **Cascade delete** on candidate ensures sessions are cleaned up if candidate is deleted
- Indexes recommended on `candidateId` (foreign key) and `(candidateId, createdAt)` for "latest assessment" queries
- **No SFIA-specific tables** in Phase 1 — schema is generic to support any framework
- **No claims or assessment_reports** in Phase 1 — moved to appropriate phase when claim extraction PRD is defined

### 1.5 `packages/shared-types` — Minimal Shared Types

**Structure:**
```
packages/shared-types/
├── package.json               ← @ai-skills-assessor/shared-types
├── tsconfig.json
└── src/
    └── index.ts               ← Assessment trigger types only
```

**Minimal types for Phase 1:**

```typescript
// packages/shared-types/src/index.ts

export interface AssessmentTriggerRequest {
  phoneNumber: string;     // +61XXXXXXXXX format
  candidateId: string;
}

export interface AssessmentTriggerResponse {
  sessionId: string;
  status: "pending" | "dialling" | "in_progress" | "completed" | "failed" | "cancelled";
  createdAt: string;
}
```

**Note:** Full Assessment Report Contract (including Claim, SkillLevel types) is deferred to the phase where claim extraction is implemented.

---

## 2. Domain Models & Port Interfaces (Python)

### 2.1 Domain Models

Phase 1 defines minimal domain models in `apps/voice-engine/src/domain/models/`:

```python
# domain/models/assessment.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class AssessmentStatus(str, Enum):
    PENDING = "pending"
    DIALLING = "dialling"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class CallConfig:
    phone_number: str
    candidate_id: str
    timeout_seconds: int = 300

@dataclass
class CallConnection:
    connection_id: str
    room_url: str
    is_active: bool

@dataclass
class AssessmentSession:
    id: str
    candidate_id: str
    phone_number: str
    status: AssessmentStatus
    daily_room_url: str | None = None
    recording_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

# domain/models/transcript.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TranscriptSegment:
    timestamp: datetime
    speaker: str  # "candidate" or "bot"
    text: str
    duration_seconds: float

@dataclass
class Transcript:
    id: str
    session_id: str
    raw_text: str
    segments: list[TranscriptSegment]
    language: str = "en"
    created_at: datetime = None
```

### 2.2 Port Interfaces (Minimal Set)

Three port interfaces in Phase 1 (`apps/voice-engine/src/domain/ports/`):

```python
# domain/ports/assessment_trigger.py
from abc import ABC, abstractmethod
from domain.models.assessment import AssessmentSession, CallConfig

class IAssessmentTrigger(ABC):
    @abstractmethod
    async def trigger(self, config: CallConfig) -> AssessmentSession:
        """Initiate an assessment call and return session metadata."""
        ...

# domain/ports/voice_transport.py
from abc import ABC, abstractmethod
from domain.models.assessment import CallConfig, CallConnection

class IVoiceTransport(ABC):
    @abstractmethod
    async def dial(self, config: CallConfig) -> CallConnection:
        """Place an outbound call and return connection details."""
        ...

    @abstractmethod
    async def hangup(self, connection: CallConnection) -> None:
        """End an active call."""
        ...

# domain/ports/persistence.py
from abc import ABC, abstractmethod
from domain.models.assessment import AssessmentSession
from domain.models.transcript import Transcript

class IPersistence(ABC):
    @abstractmethod
    async def save_session(self, session: AssessmentSession) -> None:
        """Save assessment session to storage."""
        ...

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None:
        """Save transcript to storage."""
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> AssessmentSession | None:
        """Retrieve session by ID."""
        ...
```

**Note:** `IKnowledgeBase` and `ILLMProvider` are deferred to the phase where claim extraction and SFIA mapping are implemented.

---

## 3. CI/CD Skeleton

### GitHub Actions Workflows

**`.github/workflows/ci.yml`:**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck

  test-typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm test

  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e "apps/voice-engine[dev]"
      - run: cd apps/voice-engine && pytest
      - run: cd apps/voice-engine && ruff check .
      - run: cd apps/voice-engine && mypy src/
```

---

## 3. Prisma Database Setup

In `apps/voice-engine/` or at the root (to be determined), create a `.env.example`:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/ai_skills_assessor?schema=public
```

The Prisma client is generated after `pnpm install` and migrations are applied before the voice engine starts.

---

## 4. Acceptance Criteria

**Monorepo & Tooling**
- [ ] `pnpm install` at root succeeds with all workspaces resolved (no unmet dependencies).
- [ ] `turbo run build` completes for all packages without errors (next-app, web, and voice-engine stubs).
- [ ] `pnpm lint` passes across all TypeScript packages.
- [ ] `ruff check .` passes in `apps/voice-engine/`.
- [ ] `pnpm typecheck` passes across all TypeScript packages.

**Database Schema**
- [ ] Prisma schema is defined in `packages/database/prisma/schema.prisma` with `Candidate` and `AssessmentSession` models.
- [ ] Migration file `v0_2_0_init_schema/migration.sql` is generated and applies cleanly.
- [ ] Schema includes indexes on `candidates(email)`, `assessment_sessions(candidateId)`, and `assessment_sessions(candidateId, createdAt)`.
- [ ] Foreign key cascade rules are correctly defined (candidate deletion cascades to sessions).

**Domain Models & Ports (Python)**
- [ ] Domain models are defined as dataclasses in `apps/voice-engine/src/domain/models/` (AssessmentSession, CallConfig, CallConnection, Transcript, TranscriptSegment).
- [ ] Port interfaces are defined as ABCs in `apps/voice-engine/src/domain/ports/` (IAssessmentTrigger, IVoiceTransport, IPersistence).
- [ ] All domain models and port signatures match the requirements in this document.

**Shared Types**
- [ ] `packages/shared-types/src/index.ts` exports `AssessmentTriggerRequest` and `AssessmentTriggerResponse` types.

**Application Stubs**
- [ ] Next.js app starts with `pnpm dev --filter @ai-skills-assessor/web` and responds at `http://localhost:3000/api/health` with `{"status":"ok"}`.
- [ ] FastAPI app starts with `uvicorn src.main:app` in `apps/voice-engine/` and responds with `{"status":"ok"}` on GET `/health`.
- [ ] Both apps run without errors for at least 10 seconds.

**CI/CD**
- [ ] `.github/workflows/ci.yml` is defined and all jobs (lint-and-typecheck, test-typescript, test-python) pass on a test PR.
- [ ] CI confirms TypeScript packages build, lint, and typecheck without errors.
- [ ] CI confirms Python package lints with ruff and typechecks with mypy without errors.

## 5. Dependencies on Other Phases

- **None** — Phase 1 is the foundation. All other phases depend on it being complete and correct.

## 6. Estimated Complexity

- **Monorepo config**: Low — standard pnpm + Turborepo setup.
- **Next.js shell**: Low — scaffold + health/trigger route stubs.
- **Python service shell**: Medium — domain models and port definitions require careful typing.
- **Database schema (Prisma)**: Medium — schema design for candidates and assessment sessions, with proper indexes and constraints.
- **Shared types**: Low — minimal, assessment trigger types only.
- **Domain models & ports**: Medium — 5 dataclasses, 3 port ABCs with clear contracts.
- **CI/CD**: Low — standard GitHub Actions with TypeScript and Python jobs.

## 7. Revision History

| Date | Change | Notes |
|------|--------|-------|
| 2026-04-19 | Refine pass | Tightened acceptance criteria, switched to Prisma, added version bump prerequisite, removed SFIA/claims/reports (defer to appropriate phase), reduced ports to minimal set (3), simplified schema to candidates + sessions only, added explicit build sequence. |
