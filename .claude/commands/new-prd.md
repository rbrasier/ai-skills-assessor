You are helping the user create a new Product Requirements Document (PRD) for the Orchestra project. Follow this process exactly, in order. Do not skip steps.

---

## Step 1: Read existing PRDs and phases

Before asking any questions, read all files in `docs/development/prd/` and `docs/development/implemented/*/*PHASE*.md` to:
- Understand what is already defined
- Avoid creating a duplicate
- Identify which PRD number to assign next (find the highest existing number and add 1)
- Understand the phase structure and timeline
- See which phases are active and which are planned

If the user's request overlaps significantly with an existing PRD, tell them which one and ask if they want to extend the existing PRD instead of creating a new one.

Also read `docs/development/prd/PRD-000-overview.md` for overall product context.

---

## Step 2: Ask these questions in sequence

Ask each question and wait for the answer before moving to the next. Do not batch them all at once.

**Q1:** "What is the name of this feature? (This will become the PRD title)"

**Q2:** "What problem does this solve for the user? Describe it in 1-3 sentences from the user's perspective — not a technical description."

**Q3:** "Who is the primary user of this feature? (e.g. individual user, org admin, all users)"

**Q4:** "Walk me through the core user journey — what does the user do, step by step, to complete the main task this feature enables?"

**Q5:** "What is the minimum viable version of this feature? What can we cut to ship something useful sooner?"

**Q6:** "What is explicitly OUT of scope for this feature? What might people assume is included but isn't?"

**Q7:** "Are there any known technical constraints or dependencies on other PRDs? (e.g. 'requires billing to be done first', 'must work offline on mobile')"

**Q8:** "Which build phase does this belong to? Check `docs/development/to-be-implemented` for the phase list and what work is in each phase. Or say 'unknown' if unsure."

---

## Step 3: Generate and save the PRD

Using the answers, generate a complete PRD using the template below. Then save it to `docs/development/prd/PRD-XXX-feature-name.md` where XXX is the next available number (zero-padded to 3 digits).

After saving, tell the user:
- The filename it was saved to
- That the status is set to 🔴 Draft
- That they should review and edit it, then change the status to 🟡 Review when ready for sign-off, and 🟢 Approved when ready to build

---

## Step 4: Read the corresponding phase

If Q8 specified a phase (e.g., "Phase 2"), find and read `docs/development/*PHASE-X.md` to:
- Understand what work is planned in that phase
- Verify this PRD aligns with the phase's scope
- Identify what other PRDs are in the same phase

Tell the user:
- Which phase this PRD belongs to
- What other work is in that phase
- Whether this PRD should be reviewed alongside other phase PRDs

---

## PRD Template

```markdown
# PRD-XXX: [Feature Name]

## Status
🔴 Draft

## Last Updated
[Today's date]

## Problem Statement
[What problem does this solve? From the user's perspective.]

## Goals
- [Goal 1]
- [Goal 2]
- [Goal 3]

## Non-Goals (Out of Scope)
- [What this PRD explicitly does NOT cover]

## Users
**Primary:** [Who uses this most]
**Secondary:** [Who else is affected]

## User Stories

### Core Journey
**As a** [user type],
**I want to** [action],
**so that** [outcome].

### Additional Stories
- As a [user], I want to [action] so that [outcome].
- As a [user], I want to [action] so that [outcome].

## Acceptance Criteria
- [ ] [Specific, testable criterion]
- [ ] [Specific, testable criterion]
- [ ] [Specific, testable criterion]

## Minimum Viable Version
[What is the smallest thing we can ship that is useful?]

## Technical Constraints
- [Any architectural constraints from ADRs that apply]
- [Dependencies on other systems or PRDs]
- [Platform requirements: web only / mobile / all platforms]

## Dependencies
- **Requires:** [PRD-XXX] to be complete first
- **Blocks:** [PRD-XXX] (this must be done before that)
- **Related:** [PRD-XXX]

## Build Phase
Phase X — [Phase name]

## Open Questions
- [ ] [Unresolved decision or unknown]
- [ ] [Unresolved decision or unknown]

## Revision History
| Date | Change | Author |
|------|--------|--------|
| [Today] | Initial draft | Claude |
```
