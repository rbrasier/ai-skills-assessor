# ADR-001: Hexagonal Architecture (Ports & Adapters)

## Status
Accepted

## Date
2026-02-18

## Context

The previous codebases had platform-specific code mixed throughout business logic services. This made it impossible to:
- Test business logic without a running database
- Run the same code on web and desktop without conditional branches
- Swap implementations (e.g., replace polling with WebSockets) without touching core logic
- Port to a new platform (Tauri, mobile) without major surgery

## Decision

Use **Hexagonal Architecture** (also called Ports & Adapters) as the foundational structural pattern.

### The Core Rule

`packages/core` contains all business logic and has **zero runtime dependencies on external systems**. It defines what it needs through TypeScript interfaces (Ports). External systems provide implementations (Adapters) that are injected at startup.

```
┌─────────────────────────────────────────────┐
│              packages/core                   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │           Business Logic            │   │
│  │  (EmailService, AIService, etc.)    │   │
│  └──────────────┬──────────────────────┘   │
│                 │ calls                      │
│  ┌──────────────▼──────────────────────┐   │
│  │         Ports (Interfaces)          │   │
│  │  IDatabase, IJobQueue, IEmail...    │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                 ▲ implements
┌────────────────┴────────────────────────────┐
│            packages/adapters                 │
│                 (examples)                   │
│  PostgresAdapter    
│  SqliteAdapter     InMemoryQueueAdapter      │
│  SocketIOAdapter                              │
└─────────────────────────────────────────────┘
                 ▲ wires together
┌────────────────┴────────────────────────────┐
│               apps/                          │
│  web-server/index.ts  (wires Postgres)   │
└─────────────────────────────────────────────┘
```

### Package Structure

```
packages/
├── core/           ← Business logic. No platform deps.
│   └── src/
│       ├── ports/  ← Interfaces only. Written before implementations.
│       └── ...
├── adapters/       ← Platform implementations of ports.
└── api/            ← Express app. Receives adapters as constructor args.

apps/
├── web-server/     ← Wires real adapters. Entry point for web deployment.
```

### What This Means In Practice

**Adding a new external dependency:**
1. Define an interface in `packages/core/src/ports/INewThing.ts`
2. Write business logic against the interface
3. Implement the adapter in `packages/adapters/src/`
4. Wire it in the relevant `apps/` entry point

**Writing tests:**
- Never need a real database or queue
- Create an `InMemoryAdapter` that implements the port
- Tests are fast, isolated, deterministic

**Porting to a new platform:**
- Write new adapters in `packages/adapters/`
- Write a new wire file in `apps/`
- `packages/core` is untouched

## Consequences

**Positive:**
- Business logic is testable without any infrastructure
- Adding a new deployment target requires only new adapters
- Clear, enforced boundary between what the system does vs. how it does it
- Claude can implement adapters from interface alone, without understanding the full system

**Negative:**
- More files than a monolithic approach
- Requires discipline to not cheat (import adapters directly into core)
- Initial setup cost is higher

## Enforcement

- TypeScript path aliases configured to make cross-boundary imports obvious
- ESLint rule: `no-restricted-imports` in `packages/core/` blocking adapter imports
- Code review: any PR that adds a platform import to `packages/core/` is rejected
