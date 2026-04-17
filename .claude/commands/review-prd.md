You are helping the user review and complete an existing PRD for the Orchestra project. Your goal is to turn a shell or draft PRD into something 🟢 Approved and ready to build.

## Step 1: Identify the PRD and its phase

The user has specified: $ARGUMENTS

- If a PRD number or name was given, find and read the matching file in `docs/development/prd/`
- If nothing was specified, list all PRDs with their current status and ask which one to review
- Also read `docs/development/prd/PRD-000-product-overview.md` for product context
- Identify which build phase the PRD belongs to (check the "Build Phase" section)
- Read the corresponding phase document from `docs/development/` (e.g., `PHASE-2.md`)
- Review other PRDs in the same phase to understand the broader context

---

## Step 2: Audit the PRD and check phase alignment

Before asking any questions, read the PRD thoroughly and identify:

1. **Sections that are TBD** — Problem Statement, Goals, Acceptance Criteria, Minimum Viable Version
2. **Open Questions** — the unchecked items in the Open Questions section
3. **Thin sections** — User Stories with only 1-2 entries, or vague Acceptance Criteria
4. **Dependency gaps** — referenced PRDs that are still 🔵 Planned (may block this one)
5. **Missing technical constraints** — anything the ADRs require that isn't mentioned
6. **Phase alignment** — Does the PRD's scope match what's described in the phase document? Are there conflicting assumptions?

Print a brief summary of what you found before asking questions. For example:
> "PRD-003 (AI Pipeline) in Phase 2 has 4 sections that are TBD and 7 open questions. I also found that it references PRD-005 which is still in a later phase. I'll go through them in order. Estimated: 12 questions."

Flag any misalignments between the PRD and its phase immediately so the user can decide how to proceed.

---

## Step 3: Ask questions in sequence

Work through the gaps one at a time. Do not ask multiple questions at once. Wait for the answer before moving to the next question.

**Order:**
1. Problem Statement (if TBD)
2. Goals (if TBD or vague)
3. Core User Stories (if thin)
4. Minimum Viable Version (if TBD — this is critical for scoping)
5. Non-Goals / Out of Scope (if thin)
6. Acceptance Criteria (one question per major story)
7. Open Questions (work through each unchecked one)

**Framing questions well:**
- Be specific: "What is the smallest version of draft generation that would be useful? For example: always generate a draft, or only for emails above a certain priority?"
- Offer options when helpful: "Should acceptance criteria include a latency target for draft generation? If so, what would acceptable be — under 10 seconds? Under 30?"
- Flag when something is contentious: "This one is a product decision: should the redraft loop be unlimited iterations, or capped?"

**Skip questions that are already clearly answered.** Only ask about genuine gaps.

---

## Step 4: Update the PRD file

After all questions are answered, update the PRD file with the new content:
- Fill in all TBD sections with the answers given
- Check off resolved Open Questions (change `- [ ]` to `- [x]` and add the answer inline)
- Add any new open questions that surfaced during the review
- Update the `## Last Updated` date to today
- Add a row to the Revision History table

Do NOT change the status automatically — ask the user first:

> "The PRD now has all sections completed. Would you like to change the status to:
> - 🟡 Review (if you want someone else to sign off before building)
> - 🟢 Approved (if you're ready to build from it now)"

Set the status to whichever they choose.

---

## Step 5: Final check

After saving, confirm:
- Which file was updated and where it lives
- Whether any dependencies (other PRDs) need to be reviewed before this one can be built
- If the PRD is now 🟢 Approved, which build phase it belongs to and what comes before it
- Which other PRDs are in the same phase (they should probably be reviewed together for alignment)
- Whether the phase document needs any updates to align with this PRD
