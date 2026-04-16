# To Be Implemented — Voice-AI SFIA Skills Assessment Platform

## Overview

This directory contains the phased implementation plan for the Voice-AI SFIA Skills Assessment Platform. Each phase document is a self-contained specification with deliverables, acceptance criteria, dependencies, and risks.

## Document Map

### Product Requirements
| Document | Location | Description |
|----------|----------|-------------|
| PRD-001 | `docs/development/prd/PRD-001-voice-ai-sfia-assessment-platform.md` | Master product requirements document |

### Architecture Decision Records
| Document | Location | Description |
|----------|----------|-------------|
| ADR-001 | `docs/development/adr/ADR-001-hexagonal-architecture.md` | Hexagonal Architecture (Ports & Adapters) |
| ADR-003 | `docs/development/adr/ADR-002-monorepo-structure.md` | Monorepo with pnpm + Turborepo |
| ADR-004 | `docs/development/adr/ADR-004-voice-engine-technology.md` | Voice Engine: Pipecat, Daily, FastAPI |
| ADR-005 | `docs/development/adr/ADR-005-rag-vector-store-strategy.md` | RAG: pgvector with framework_type metadata |

### Contracts
| Document | Location | Description |
|----------|----------|-------------|
| Assessment Report Contract | `docs/development/contracts/assessment-report-contract.md` | Shared data types (JSON Schema + TypeScript) |

### Implementation Phases

| Phase | Document | Depends On | Key Deliverables |
|-------|----------|------------|------------------|
| **Phase 1** | `phase-1-foundation-monorepo-scaffold.md` | — | Monorepo config, DB schema, port interfaces, CI/CD |
| **Phase 2** | `phase-2-voice-engine-core.md` | Phase 1 | Pipecat pipeline, Daily transport, flow controller, interjection |
| **Phase 3** | `phase-3-rag-knowledge-base.md` | Phase 1, 2 | pgvector setup, SFIA ingestion, SkillRetriever, prompt injection |
| **Phase 4** | `phase-4-claim-extraction-pipeline.md` | Phase 1, 2, 3 | Claude claim extraction, SFIA mapping, report generation, NanoID links |
| **Phase 5** | `phase-5-sme-review-portal.md` | Phase 1, 4 | Admin dashboard, SME review UI, claim approval workflow |
| **Phase 6** | `phase-6-integration-deployment.md` | Phase 1–5 | End-to-end wiring, Sydney deployment, latency optimisation, observability |

## Dependency Graph

```
Phase 1 ──────────────────────────────────────────────┐
  │                                                    │
  ├──▶ Phase 2 ──────┐                                │
  │                    │                                │
  ├──▶ Phase 3 ◀──────┘                                │
  │       │                                            │
  │       ▼                                            │
  ├──▶ Phase 4 ◀─── Phase 2, Phase 3                   │
  │       │                                            │
  │       ▼                                            │
  ├──▶ Phase 5 ◀─── Phase 4                            │
  │       │                                            │
  │       ▼                                            │
  └──▶ Phase 6 ◀─── All phases                         │
                                                       │
```

## How to Use These Documents

1. **Start with PRD-001** for the full product vision and requirements.
2. **Read the ADRs** to understand architectural constraints and technology choices.
3. **Review the Contract spec** before working on any data-producing or data-consuming component.
4. **Implement phases in order** — each phase's acceptance criteria must be met before moving to the next.
5. **Move completed phase docs** from `to-be-implemented/` to `implemented/{version}/` when all acceptance criteria are met.
