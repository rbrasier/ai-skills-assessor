You are helping the user document an amendment or revision to an existing phase implementation plan for the Orchestra project. Follow this process exactly, in order. Do not skip steps.

---

## Step 1: Identify the phase and implementation to revise

The user has specified: $ARGUMENTS

- If a phase number was given, find the corresponding implementation document within subfolders under `docs/development/implementated/*/*PHASE-X-implementation-*.md`
- If nothing was specified, list all implementation documents found and ask which one to revise
- Read the existing implementation document thoroughly to understand prior decisions and strategy

---

## Step 2: Determine revision number

Check `docs/development/implementated/` for existing revision documents:
- Look for files matching `PHASE-X-*.md`
- Find the highest revision number (Y) that exists
- The new revision will be Y+1
- If no revisions exist yet, this is Revision-1

Tell the user what revision number will be assigned (e.g., "This will be Revision-2 for Phase 3").

---

## Step 3: Understand the revision context

Ask these questions in sequence. Wait for each answer before proceeding:

**Q1:** "What are you revising? (e.g., 'implementation strategy changed', 'PRD scope expanded', 'discovered technical blocker', 'performance issues found during initial build')"

**Q2:** "What was the original plan or decision (from the implementation document) that is now being amended?"

**Q3:** "What is the new plan or decision? What changed and why?"

**Q4:** "What is the impact of this change? (e.g., 'adds 2 PRDs to scope', 'delays timeline', 'requires new ADR review', 'affects architecture')"

**Q5:** "Is this revision due to: Learning from implementation, stakeholder feedback, scope change, technical discovery, risk mitigation, or something else?"

---

## Step 3b: Version bump check

Before generating the revision document, check whether the revision introduces any new Prisma migrations or new API endpoints.

If yes, add a prominent note to the revision document under `## Impact`:

```
⚠️ **Version bump required:** This revision includes a DB migration / new API endpoint.
Run `/bump-version` (MINOR) before implementing. Migration names must include the version:
`prisma migrate dev --name v{MAJOR}_{MINOR}_0_{describe_change}`
See `docs/guides/managing-versions.md`.
```

Also flag this to the user after saving: "This revision includes a DB change — remember to run `/bump-version` before implementing."

---

## Step 4: Generate and save the revision document

Using all the information gathered, create a revision document with this structure:

```markdown
# PHASE-X Revision-Y: [Short title describing the revision]

## Reference
- **Original Implementation:** `docs/development/implementation/*/*PHASE-X-implementation-[title].md`
- **Original Phase Document:** `docs/development/implementation/*/*PHASE-X.md`
- **Revision Date:** [Today's date]
- **Revision Reason:** [From Q5 above]

## What Changed

### Original Plan (From Implementation Notes)
[From Q2 - summarize the original decision/strategy]

### New Plan (Revised)
[From Q3 - describe the new decision/strategy]

### Why This Revision
[From Q1 - what prompted this revision]

### Impact
[From Q4 - what changes as a result]

---

## Detailed Changes

### Changes to Scope
- [List any PRDs added/removed]
- [List any deliverables added/removed]
- [List any ADRs that now apply]

### Changes to Strategy
[From the original implementation strategy, what changes?]
- **Original approach:** [Quote or summarize the original strategy]
- **Revised approach:** [Describe the new approach]

### Changes to Technical Decisions
[List any architectural or technical decisions that changed]
- **Original decision:** [Decision and rationale]
- **Revised decision:** [New decision and rationale]

### Changes to Risk/Unknowns
[What risks were mitigated, new risks identified, or unknowns clarified?]
- **Resolved:** [Unknown that is now clear]
- **New risk:** [Risk discovered]
- **Mitigation:** [How we're handling it]

---

## Revised Implementation Parts

### Part [X.Y]: [Updated part name or new part]
- **Goal:** [What this part now accomplishes]
- **Key decisions:**
  - [Revised or new decision]
- **Acceptance criteria:** [Updated success criteria if changed]
- **Affected by this revision:** Yes / No

[Include only parts that changed. Reference the implementation document for unchanged parts]

---

## Next Steps
[What happens next? Which part resumes, which PRD to tackle, etc.]

---

## Revision Chain
- **Base Implementation:** `PHASE-X-implementation-*.md`
- **Previous Revisions:** [List any prior revisions that led to this one, e.g., "Revision-1: Added caching layer"]
- **This Revision:** Revision-Y - [Title]

---

## Related Documents
- Phase: `docs/development/implementation/*/*PHASE-X.md`
- Implementation: `ddocs/development/implementation/*/*HASE-X-implementation-[title].md`
- Prior Revisions: [List any]
- PRDs: [Links to relevant PRDs]
- ADRs: [Links to relevant ADRs]
```

Save this file to: `docs/development/to-be-implemented/PHASE-X-Revision-Y-[kebab-case-title].md`

Where:
- X = phase number
- Y = revision number
- [kebab-case-title] = short title in lowercase with hyphens (e.g., `caching-strategy-change`)

Tell the user:
- The filename it was saved to
- Whether this changes any PRD scope (they may need to review those PRDs)
- Whether any ADRs need to be reviewed
- What to do next (continue implementation, review other docs, etc.)

---

## Step 5: Recommend updates to existing docs

After saving the revision, check if updates are needed:

- **Update the implementation document?** Ask: "Should I add a note to the main implementation document linking to this revision?"
  - If yes, append a row to the Revision History table in `PHASE-X-implementation-*.md` referencing this revision

- **Update affected PRDs?** If scope changed, ask: "Should I mark related PRDs that are affected by this revision?"

- **Git commit?** Suggest: "Consider committing this revision with message: `docs(PHASE-X): Add Revision-Y - [reason]`"

---

## Notes for You

- A revision document preserves the history of how a phase implementation evolved
- Link to relevant revision documents in commit messages (e.g., "fix(PHASE-3): Update API contract per PHASE-3-Revision-2-api-scope-expansion.md")
- If multiple revisions accumulate, they form a chain showing learning and adaptation over time
- The revision chain helps future maintainers understand why decisions were made and how they evolved
- Revisions that significantly change scope may require updating the original phase document itself (discuss with user)

---

## Common Revision Reasons

These are common reasons phases get revised. Use them to help the user if they're unsure:

- **Learning:** Discovered new technical requirements during initial implementation
- **Scope expansion:** Stakeholder feedback or additional features requested
- **Scope reduction:** Prioritization or timeline constraints required cutting scope
- **Risk mitigation:** Identified risk that requires strategy change
- **Performance:** Initial implementation revealed performance needs not anticipated
- **Architecture:** ADR review or dependency clarification changed approach
- **Dependency blocking:** External service or prior phase delayed, affecting timeline
- **Stakeholder feedback:** Product owner or user research surfaced changes
