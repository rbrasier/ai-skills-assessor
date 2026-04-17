You are helping the user review Architecture Decision Records (ADRs) for the Orchestra project. Your goals are to:

1. Check a specific ADR (or all ADRs) for completeness and internal consistency
2. Cross-reference ADRs against PRDs and phase plans to catch alignment gaps
3. Identify database schema proliferation risks across the full PRD set
4. Verify CLAUDE.md accurately reflects the ADR rules

The user has specified: $ARGUMENTS

---

## Step 1: Identify scope

- If a specific ADR number or name was given, focus the review on that ADR (but still read all PRDs for cross-referencing)
- If `--all` or nothing was specified, review all ADRs holistically
- If `--schema` or `--database` was specified, skip to the Database Bloat Check (Step 4) and run only that

Read all files in `docs/development/adr/`, `docs/development/prd/`, `docs/development/implemeted/*PHASE*.md`, and `CLAUDE.md` before proceeding.

---

## Step 2: ADR Completeness Check

For each ADR being reviewed, check:

| Section | What to look for |
|---------|-----------------|
| **Status** | Is it Proposed, Accepted, Deprecated, or Superseded? Flag any that are Proposed but appear to be in active use. |
| **Context** | Does it explain WHY the decision was needed, not just what was decided? |
| **Options Considered** | Are alternatives documented? A decision with no alternatives listed is harder to revisit later. |
| **Decision** | Is the rule precise enough to be unambiguous? Could two developers read this and disagree on what it requires? |
| **Consequences** | Are both positive AND negative consequences listed? Missing negatives is a warning sign. |
| **Enforcement** | Is there a concrete mechanism (ESLint rule, CLAUDE.md entry, test requirement)? "Code review" alone is not sufficient enforcement. |

Report findings before moving on. Flag any ADR that has gaps.

---

## Step 3: ADR vs PRD Cross-Reference

For each ADR, identify which PRDs are affected by its rules. Then check whether those PRDs acknowledge the constraint in their Technical Constraints section.

Work through these specific pairings:

| ADR | PRDs it governs |
|-----|----------------|
| ADR-001 (Hexagonal Architecture) | All PRDs — every feature must follow ports & adapters |
| ADR-002 (Database) | Any PRD that introduces a new entity or data model |
| ADR-003 (Monorepo) | Any PRD that requires a new package |
| ADR-004 (Desktop/Mobile) | PRD-010 (Mobile), any PRD with platform-specific behaviour |
| ADR-005 (Realtime) | Any PRD involving live updates, sync status, or notifications |
| ADR-006 (AI Pipeline) | PRD-003, PRD-005, PRD-006, PRD-011 |
| ADR-007 (Auth) | PRD-001, and any PRD with access control or token handling |
| ADR-008 (Calendar) | PRD-007, any PRD referencing calendar data |

For each pairing, report one of:
- **OK** — PRD mentions the relevant ADR constraint
- **Gap** — PRD is silent on an ADR constraint that applies to it
- **Conflict** — PRD specifies something that contradicts the ADR

For gaps and conflicts, quote the specific PRD section and the relevant ADR rule so the user can see exactly what needs fixing.

---

## Step 4: Database Bloat Check

This check identifies whether the PRD set is introducing more data entities than necessary.

Read all PRDs and for each one, extract:
- What **new database tables or entities** the feature implies (even if not stated explicitly — infer from user stories and acceptance criteria)
- What **existing tables** it reads from or writes to
- Any **data that could be derived** rather than stored (e.g. counts, aggregates, status fields that are computed from other data)

Then produce a **Data Model Map** in this format:

```
Entity: User
  Introduced by: PRD-001 (Auth)
  Referenced by: PRD-002, PRD-003, PRD-004, PRD-005, PRD-006, PRD-007, PRD-008, PRD-009, PRD-010, PRD-011

Entity: EmailThread
  Introduced by: PRD-002 (Email Sync)
  Referenced by: PRD-004, PRD-006, PRD-011

Entity: [name]
  Introduced by: PRD-XXX
  Referenced by: ...
```

After building the map, flag:

**Redundancy risks** — Two PRDs that appear to store the same logical data in different shapes (e.g. "user preferences" in PRD-001 and "assistant settings" in PRD-005 — are these the same table?)

**Single-use entities** — Tables introduced by one PRD and referenced by no others. These are fine if deliberate, but flag them for confirmation.

**Derived data stored as columns** — Fields like `email_count`, `last_seen_at`, `unread_count` that could be computed queries instead of stored values. Stored counts get out of sync; queries don't.

**Audit/log table sprawl** — If more than 2 PRDs introduce separate audit or event log tables, flag this — a single unified `audit_events` table is almost always better.

Present the map and flags as a summary. Do not make changes to any PRD — ask the user which flags to act on before changing anything.

---

## Step 5: CLAUDE.md Alignment Check

Read `CLAUDE.md` and verify:

1. **Mandatory ADR Reads table** — Is every ADR listed against at least one task type? Are the task types accurate?
2. **Architecture Rules section** — Does each rule in CLAUDE.md trace back to an ADR? Are there ADR rules that are NOT in CLAUDE.md (and should be)?
3. **Adding New Things table** — Does it reflect all the patterns defined in the ADRs?

Report any gaps. For example: "ADR-005 says no polling, but CLAUDE.md's Common Pitfalls section says 'Don't poll' without linking to ADR-005 — consider adding the reference."

Do NOT update CLAUDE.md automatically. List proposed changes and ask the user to confirm.

---

## Step 6: Summary and recommended actions

Produce a final summary with three sections:

**ADR gaps to fix** — List by ADR number with the specific gap

**PRD updates needed** — List by PRD number, what constraint needs to be added to Technical Constraints

**Database model flags** — List each flag with a recommended action (merge tables, convert to derived query, etc.)

Ask the user which items to act on. Only make changes when explicitly confirmed.
