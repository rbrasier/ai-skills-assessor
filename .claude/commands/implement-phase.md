You are helping the user implement a build phase for the Orchestra project. This command is designed to work autonomously — read documents yourself rather than asking the user if they have. Follow this process exactly, in order. Do not skip steps.

---

## Step 1: Identify the phase

The user has specified: $ARGUMENTS

- If a phase number or name was given, find and read the matching file in `docs/development/to-be-implemented`
- If nothing was specified, list all phases in `docs/development/to-be-implemented/` with their names and ask which one to implement
- Read `docs/development/prd/PRD-000-product-overview.md` for product context

---

## Step 2: Check for existing implementation and revisions

Before proceeding, check `docs/developement/implementated/` to see if:
- An implementation document already exists for this phase (e.g., `PHASE-X-implementation-*.md`)
- Any revision documents exist (e.g., `PHASE-X-Revision-Y-*.md`)

If an implementation document exists:
- Read it to understand prior decisions
- Read any revision documents to understand amendments
- Show the user a summary of what was planned and what revisions have been made
- Ask the user: "Implementation notes already exist for this phase. Would you like to:
  1. Review and amend the existing implementation (create a revision)
  2. Restart the implementation from scratch (create a new implementation document)"
- If they choose "amend", switch to the revision workflow (see Step 7)

---

## Step 3: Auto-verify document approval status

**Do not ask the user if they have read documents. Read and verify them yourself.**

### 3a. Read and verify all PRDs in scope

Read the phase document to identify all PRD references. Then, for each PRD referenced:

1. Read the file at `docs/development/prd/PRD-XXX-*.md`
2. Extract the `## Status` value from the header

Apply this gate:

| Status | Action |
|--------|--------|
| 🟢 Approved | ✅ Continue |
| ⚫ Complete | ✅ Continue (historical — confirm scope still applies) |
| 🟡 Review | ❌ **STOP** |
| 🔴 Draft | ❌ **STOP** |
| 🔵 Planned | ❌ **STOP** |

If **any PRD is not 🟢 Approved or ⚫ Complete**, stop immediately and report:

```
⛔ Cannot proceed: the following PRDs are not approved:
  - PRD-XXX (Status: 🟡 Review) — needs sign-off before implementation begins
  - PRD-YYY (Status: 🔴 Draft) — needs to be completed and approved

Ask the product owner to approve these PRDs, or run /review-prd to complete them.
```

Do not continue until all referenced PRDs are approved.

### 3b. Read and verify all ADRs in scope

Check CLAUDE.md for the mandatory ADR list for this type of work. Also check if the phase document references specific ADRs. For each ADR:

1. Read the file at `docs/development/adr/ADR-XXX-*.md`
2. Extract the `## Status` value

Apply this gate:

| Status | Action |
|--------|--------|
| Accepted | ✅ Continue |
| Superseded | ⚠️ Warn — note which ADR supersedes it and confirm the right one is in scope |
| Proposed | ❌ **STOP** — ADR is not yet accepted |
| Deprecated | ❌ **STOP** — flag to user, do not build against a deprecated ADR |

If any ADR is Proposed or Deprecated, stop and report the issue before continuing.

### 3c. Version bump check

If the phase includes any new Prisma migrations or new API endpoints:

1. Read `package.json` at the project root and extract the current `version` field
2. Check `git log --oneline -5` to see if a version bump commit already exists for this phase
3. If no bump has been done yet, **stop** and tell the user:

```
⛔ This phase includes a DB migration / new API endpoint — a MINOR version bump is required before you start.

Run /bump-version now, then return to /implement-phase.
```

If a bump has been done, note the version number — migration names must include it:
```
prisma migrate dev --name v{MAJOR}_{MINOR}_0_{describe_change}
```

See `docs/guides/managing-versions.md` for full rules.

---

### 3d. Confirmation summary

After reading all documents, print a confirmation block like:

```
✅ Document verification complete

PRDs verified:
  ✅ PRD-001: Authentication & OAuth (Approved)
  ✅ PRD-014: Onboarding (Approved)

ADRs verified:
  ✅ ADR-001: Hexagonal Architecture (Accepted)
  ✅ ADR-007: Authentication (Accepted)

All documents approved. Proceeding.
```

---

## Step 4: Extract and summarise phase content

Read the phase document thoroughly and extract:
- **Phase title and number** (e.g., "Phase 2a: Authentication")
- **Phase goals** — What should be accomplished
- **Deliverables** — What gets shipped
- **PRDs in scope** — List all PRD-XXX references
- **ADRs in scope** — List all ADR references
- **Dependencies** — What prior phases must be complete first
- **Open questions or unknowns** noted in the phase

Also read the key sections of each PRD in scope to understand acceptance criteria and scope boundaries.

Print this summary for the user to confirm before proceeding.

---

## Step 5: Gather implementation context

Ask the user **only** for information you cannot determine from the documents. Keep this to a single message with focused questions. Prefer to infer from the phase and PRD documents where possible.

Ask:

**Q1:** "What is your implementation strategy for this phase? (e.g., 'build all APIs first, then UI', 'do one PRD at a time', 'horizontal slices'). If you have no preference, I'll use the order in the phase document."

**Q2:** "Are there any scope clarifications or amendments — things you plan to do differently from what's written in the phase document?"

**Q3:** "What are the main risks or unknowns you're aware of going in? (Skip if none.)"

If the user has already provided this context in the conversation, do not re-ask — use what they said.

---

## Step 6: Generate and save the implementation document

Using all the information gathered, create an implementation document with this structure:

```markdown
# PHASE-X Implementation: [Phase Title]

## Reference
- **Phase Document:** `docs/development/to-be-implemented/PHASE-X.md`
- **Implementation Date:** [Today's date]
- **Status:** In Progress

---

## Verification Record

### PRDs Approved
| PRD | Title | Status | Verified |
|-----|-------|--------|---------|
| PRD-XXX | [Title] | 🟢 Approved | [Date] |

### ADRs Accepted
| ADR | Title | Status | Verified |
|-----|-------|--------|---------|
| ADR-001 | Hexagonal Architecture | Accepted | [Date] |

---

## Phase Summary
[1-2 sentence summary of what this phase accomplishes]

---

## Phase Scope

### Deliverables
- [Deliverable 1]
- [Deliverable 2]

### External Dependencies
- [Prior phase or integration that must be ready first]

---

## Implementation Strategy

### Approach
[User's strategy from Q1, or order from the phase document if none given]

### Build Sequence
1. [First workstream or PRD]
2. [Second workstream or PRD]
3. [Continue as needed]

---

## Known Risks and Unknowns

### Risks
- [Risk]: [Mitigation strategy if known]

### Unknowns
- [Unknown going into implementation]

### Scope Clarifications
[From Q2 — any deviations from the phase document. "None" if not applicable.]

---

## Implementation Notes

### Part 1: [PRD-XXX — Short title]
- **Goal:** [What this part accomplishes]
- **Acceptance criteria:** [Directly from the PRD where possible]
- **Key decisions going in:**
  - [Any architectural or technical choices already known]
- **Blockers:** [What must exist before this starts]

### Part 2: [PRD-YYY — Short title]
- **Goal:** [What this part accomplishes]
- **Acceptance criteria:** [From the PRD]
- **Key decisions going in:**
  - [Known choices]

### Part 3: [Continue as needed]

---

## Decisions Log

> This section is the living record of decisions made **during** implementation.
> Update it as you go — before moving to the next part, record any significant choices you made.
> Do not leave it empty by the end of the phase.

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| [Today] | — | Initial implementation plan created | — | This document |

**How to add entries:**
- Whenever you make a non-obvious technical choice, record it here
- Include: what options you considered, which you chose, and why
- Link to the file(s) where the decision landed
- Examples: schema field choices, API contract decisions, library selections, pattern deviations

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| [Today] | — | Initial implementation plan | In Progress |

---

## Related Documents
- Phase: `docs/development/implemented/*/*PHASE-X.md`
- PRDs: [Link each PRD in scope]
- ADRs: [Link each ADR in scope]
```

Save this file to: `docs/development/implementated/v{MAJOR}.{MINOR}/PHASE-X-implementation-[kebab-case-title].md`

Where:
- X = phase number
- [kebab-case-title] = the phase title in lowercase with hyphens (e.g., `authentication`)

After saving, tell the user:
- The filename it was saved to
- Which PRD or part to start with based on their strategy
- To update the **Decisions Log** section as they work — before finishing each part, add a row for every significant decision made
- How to use `/document-phase-revision` if the strategy changes mid-phase

---

## Step 7: Revision workflow (if amending existing implementation)

If the user chose to amend an existing implementation in Step 2:

**Q1:** "What changes or amendments are you making to the implementation strategy?"

**Q2:** "What was the outcome or learning that prompted this revision?"

Then:
- Identify the next revision number (Y) by counting existing `PHASE-X-Revision-*.md` files
- Call the `/document-phase-revision` command to create the revision document
- Reference the original implementation in the new revision

---

## Step 8: Validation and integrity checks

After implementing each major part (PRD or workstream), **and before finalizing the phase**, run the validation suite to maintain app integrity:

### 8a. Run validation
Execute `./validate.sh` from the project root. This script runs:
- `pnpm install` — Verify all dependencies are correct
- `pnpm build` — Ensure no TypeScript errors and all packages compile
- `pnpm test` — Run all unit tests (should all pass)
- `pnpm lint` — Check code style and consistency
- ESLint boundary rules — Verify architecture rules (core→adapter imports)

### 8b. Handle validation failures

If `validate.sh` reports failures:

1. **Identify which checks failed** — The script outputs which of the 5 checks failed
2. **Fix issues systematically:**
   - **Build errors:** Review TypeScript compilation errors and fix type issues
   - **Test failures:** Run `pnpm test` in verbose mode to identify failing tests; fix test or implementation
   - **Lint violations:** Run `pnpm lint` and auto-fix where possible (`pnpm lint --fix`), manually fix the rest
   - **Boundary rule violations:** Check for any `packages/core/` imports from `packages/adapters/` or `packages/api/` and restructure to use port interfaces
3. **Re-run** `./validate.sh` after each fix to confirm resolution
4. **Document the fixes** in the implementation document's Decisions Log

### 8c. Final validation record

Once all validation passes, add a row to the implementation document:

```markdown
| [Date] | Validation | All checks passed: install, build, test, lint, boundary rules | Ensures app integrity before phase completion | validate.sh |
```

Update the implementation document's **Status** field to `Completed` only after validation passes.

---

## Notes for You

- **The Decisions Log is the most important long-term output.** It is what future maintainers and reviewers read to understand *why* things were built the way they were. Encourage the user to fill it in as they work, not at the end.
- Each significant decision should answer: what options were considered, what was chosen, why, and where in the codebase it landed.
- If a decision later turns out to be wrong, a revision document should explain what changed and why.
- Link to this document in commit messages: `feat(PHASE-2a): Implement Google OAuth - see PHASE-2a-implementation-authentication.md Part 1`
- If priorities or scope change mid-phase, create a revision via `/document-phase-revision` rather than editing this document directly — that preserves the decision history.
