# Phase 1: Foundation & Monorepo Scaffold

## Status
To Be Implemented

## Date
2026-04-16

## References
- PRD-001: Voice-AI SFIA Skills Assessment Platform
- ADR-001: Hexagonal Architecture
- ADR-003: Monorepo Structure (pnpm + Turborepo)

## Objective

Establish the monorepo foundation, CI/CD skeleton, database schema, shared type contracts, and project tooling so that all subsequent phases can build on a stable, consistent base.

---

## 1. Deliverables

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

**API route stub (`apps/web/src/app/api/assessment/trigger/route.ts`):**

```typescript
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { phoneNumber, candidateId } = body;

  // Validate Australian phone number format
  if (!phoneNumber?.match(/^\+61\d{9}$/)) {
    return NextResponse.json(
      { error: "Invalid Australian phone number format. Expected +61XXXXXXXXX" },
      { status: 400 }
    );
  }

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

### 1.4 `packages/database` — PostgreSQL Schema

**Structure:**
```
packages/database/
├── package.json               ← @ai-skills-assessor/database
├── drizzle.config.ts
├── src/
│   ├── index.ts               ← Schema exports
│   ├── schema/
│   │   ├── candidates.ts
│   │   ├── assessment-sessions.ts
│   │   ├── transcripts.ts
│   │   ├── claims.ts
│   │   ├── assessment-reports.ts
│   │   ├── sfia-skills.ts
│   │   └── sfia-levels.ts
│   └── migrations/
└── seed/
    └── sfia-9-skills.ts       ← SFIA 9 skill definitions seed data
```

**Core schema (Drizzle ORM):**

```typescript
// candidates.ts
export const candidates = pgTable("candidates", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull(),
  phone: text("phone").notNull(),
  organisationId: uuid("organisation_id"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

// assessment-sessions.ts
export const assessmentSessions = pgTable("assessment_sessions", {
  id: uuid("id").defaultRandom().primaryKey(),
  candidateId: uuid("candidate_id").references(() => candidates.id).notNull(),
  status: text("status", { 
    enum: ["pending", "dialling", "in_progress", "completed", "failed", "cancelled"] 
  }).notNull().default("pending"),
  triggeredBy: uuid("triggered_by"),
  dailyRoomUrl: text("daily_room_url"),
  recordingUrl: text("recording_url"),
  startedAt: timestamp("started_at"),
  endedAt: timestamp("ended_at"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

// claims.ts
export const claims = pgTable("claims", {
  id: uuid("id").defaultRandom().primaryKey(),
  sessionId: uuid("session_id").references(() => assessmentSessions.id).notNull(),
  verbatimQuote: text("verbatim_quote").notNull(),
  interpretedClaim: text("interpreted_claim").notNull(),
  sfiaSkillCode: text("sfia_skill_code").notNull(),
  sfiaLevel: integer("sfia_level").notNull(),
  confidence: real("confidence").notNull(),
  smeStatus: text("sme_status", {
    enum: ["pending", "approved", "adjusted", "rejected"]
  }).notNull().default("pending"),
  smeAdjustedLevel: integer("sme_adjusted_level"),
  smeNotes: text("sme_notes"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

// assessment-reports.ts
export const assessmentReports = pgTable("assessment_reports", {
  id: uuid("id").defaultRandom().primaryKey(),
  sessionId: uuid("session_id").references(() => assessmentSessions.id).notNull(),
  reviewToken: text("review_token").notNull().unique(),
  status: text("status", {
    enum: ["generated", "sent", "in_review", "completed"]
  }).notNull().default("generated"),
  generatedAt: timestamp("generated_at").defaultNow().notNull(),
  smeReviewedAt: timestamp("sme_reviewed_at"),
  expiresAt: timestamp("expires_at").notNull(),
});
```

### 1.5 `packages/shared-types` — Assessment Report Contract

**Structure:**
```
packages/shared-types/
├── package.json               ← @ai-skills-assessor/shared-types
├── tsconfig.json
├── src/
│   ├── index.ts               ← Re-exports
│   ├── assessment-report.ts   ← TypeScript types
│   ├── assessment-trigger.ts  ← Trigger request/response types
│   └── schemas/
│       ├── assessment-report.schema.json   ← JSON Schema (language-agnostic)
│       └── assessment-trigger.schema.json
```

See the contract specification document for full type definitions.

---

## 2. Port Interface Definitions (Python)

These are created as stubs in Phase 1 and implemented in subsequent phases.

```python
# domain/ports/assessment_trigger.py
from abc import ABC, abstractmethod
from domain.models.assessment import AssessmentSession

class AssessmentTrigger(ABC):
    @abstractmethod
    async def trigger(self, phone_number: str, candidate_id: str) -> AssessmentSession:
        """Initiate an assessment call."""
        ...

# domain/ports/voice_transport.py
from abc import ABC, abstractmethod
from domain.models.assessment import CallConfig, CallConnection

class VoiceTransport(ABC):
    @abstractmethod
    async def dial(self, phone_number: str, config: CallConfig) -> CallConnection:
        """Place an outbound call."""
        ...
    
    @abstractmethod
    async def hangup(self, connection: CallConnection) -> None:
        """End an active call."""
        ...

# domain/ports/knowledge_base.py
from abc import ABC, abstractmethod
from domain.models.skill import SkillDefinition

class KnowledgeBase(ABC):
    @abstractmethod
    async def query(
        self, text: str, framework_type: str = "sfia-9", top_k: int = 5
    ) -> list[SkillDefinition]:
        """Query the knowledge base for relevant skill definitions."""
        ...

# domain/ports/persistence.py
from abc import ABC, abstractmethod
from domain.models.assessment import AssessmentSession
from domain.models.transcript import Transcript
from domain.models.claim import Claim

class Persistence(ABC):
    @abstractmethod
    async def save_session(self, session: AssessmentSession) -> None: ...
    
    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None: ...
    
    @abstractmethod
    async def save_claims(self, session_id: str, claims: list[Claim]) -> None: ...
    
    @abstractmethod
    async def get_session(self, session_id: str) -> AssessmentSession | None: ...

# domain/ports/llm_provider.py
from abc import ABC, abstractmethod
from domain.models.claim import Claim

class LLMProvider(ABC):
    @abstractmethod
    async def extract_claims(self, transcript: str) -> list[Claim]:
        """Extract structured claims from a transcript."""
        ...
```

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

## 4. Acceptance Criteria

- [ ] `pnpm install` at root succeeds with all workspaces resolved.
- [ ] `pnpm build` completes for all packages (even if outputs are stubs).
- [ ] `pnpm lint` passes across all TypeScript packages.
- [ ] `ruff check .` passes in `apps/voice-engine`.
- [ ] All port interfaces are defined as Python ABCs in `apps/voice-engine/src/domain/ports/`.
- [ ] All domain models are defined as Pydantic models in `apps/voice-engine/src/domain/models/`.
- [ ] Database schema is defined in `packages/database/` with all core entities.
- [ ] Shared types are defined in `packages/shared-types/` with both TypeScript types and JSON Schema.
- [ ] Next.js app runs with `pnpm dev --filter @ai-skills-assessor/web`.
- [ ] FastAPI app runs with `uvicorn src.main:app` in `apps/voice-engine/`.
- [ ] CI workflow is defined and would pass on push.

## 5. Dependencies on Other Phases

- **None** — Phase 1 is the foundation. All other phases depend on it.

## 6. Estimated Complexity

- **Monorepo config**: Low — standard pnpm + Turborepo setup.
- **Next.js shell**: Low — scaffold + stub routes.
- **Python service shell**: Medium — port/model definitions require careful domain modelling.
- **Database schema**: Medium — schema design for all core entities.
- **Shared types**: Low-Medium — TypeScript types + JSON Schema generation.
- **CI/CD**: Low — standard GitHub Actions.
