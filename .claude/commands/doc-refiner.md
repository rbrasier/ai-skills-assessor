You are helping the user improve the quality of an existing Orchestra document — a PRD, an ADR, or a Phase plan. Your goal is NOT just to fill in blanks. Your goal is to make the document precise enough that a developer could build from it without guessing, and clear enough that a reviewer could verify it is complete.

The user has specified: $ARGUMENTS

---

## Step 1: Identify and load the document

Parse `$ARGUMENTS` to determine what to refine:

- A PRD reference (e.g. `PRD-003`, `prd 3`, `email sync`) → find and read the matching file in `docs/development/prd/`
- An ADR reference (e.g. `ADR-001`, `adr 1`, `hexagonal`) → find and read the matching file in `docs/development/adr/`
- A Phase reference (e.g. `phase-2a`, `phase 3`) → find and read the matching file within subfolders `docs/development/`
- If nothing was specified, list all documents across all three directories with their type and status, and ask the user which one to refine

Always read these for context before starting your audit:
- `docs/development/prd/PRD-000-product-overview.md` — product vision and goals
- `CLAUDE.md` — architecture rules and conventions

If refining a PRD, also read:
- The phase document it belongs to (from the "Build Phase" section)
- Any ADRs listed as mandatory for its task type (from CLAUDE.md's Mandatory ADR Reads table)

If refining a Phase, also read:
- All PRDs referenced in the phase
- All ADRs referenced in the phase

If refining an ADR, also read:
- Any PRDs that the ADR governs (cross-reference the ADR-vs-PRD table in `review-adr.md` for guidance)

---

## Step 2: Run the quality audit

Before asking any questions, perform a silent quality audit of the document. This is different from a completeness check — you are looking for **vagueness, ambiguity, and gaps that would force a developer to guess**.

### For PRDs, check every section against these criteria:

**Problem Statement**
- Is the problem stated as a user need, not as a solution?
- Does it explain why this matters now, not just that it matters?
- Flag: vague statements like "users want better email management"

**Goals**
- Are goals measurable or testable? ("Users can reply to email within 3 taps" is testable. "Improve email UX" is not.)
- Flag: goals with no clear success signal

**Non-Goals**
- Are non-goals specific enough to settle disputes? ("We will not support rich text formatting in v1" is specific. "We won't over-engineer this" is not.)
- Flag: thin or absent non-goals section

**User Stories**
- Does each story follow "As a [user], I want [feature], so that [benefit]"?
- Is the benefit (so that...) filled in, not left vague?
- Are there stories for the unhappy path — what happens when things fail?
- Flag: stories that describe UI steps rather than user goals

**Acceptance Criteria**
- Is each criterion written as a verifiable statement, not a wish? ("The system sends a confirmation email within 5 seconds" is verifiable. "Email confirmation should be fast" is not.)
- Could you write a failing test for each criterion right now?
- Are error states and edge cases covered? (empty states, network failure, invalid input, concurrent access)
- Flag: criteria using "should", "ideally", "approximately", "as needed", "where possible"

**Minimum Viable Version**
- Is the MVP scope tight enough to ship in one phase?
- Does it clearly describe what is NOT in the MVP?
- Could a developer tell exactly when the MVP is done?
- Flag: MVP sections that are just a shorter version of Goals with no real cuts

**Technical Constraints**
- Are the relevant ADRs listed by number, not just vague references to "the architecture"?
- Are constraints specific? ("Must use IRealtimeTransport interface — see ADR-005" is specific. "Should be real-time" is not.)
- Flag: any implicit ADR dependency that isn't called out

**Dependencies**
- Are upstream dependencies listed with their current status?
- If a dependency is 🔵 Planned, is there a note about what happens if it isn't ready?
- Flag: dependencies listed without status

**Open Questions**
- Are open questions specific enough to have a clear owner and resolution path?
- Flag: open questions that are really just TODOs in disguise

---

### For ADRs, check:

**Context**
- Does it explain the forces and constraints that made this decision necessary?
- Is it clear why "doing nothing" or using a simpler approach wouldn't work?
- Flag: context that just describes the chosen solution rather than the problem

**Options Considered**
- Are there at least 2 alternatives documented?
- Is each alternative rejected for a concrete reason, not just "we preferred X"?
- Flag: single-option ADRs (a decision with no alternatives is harder to revisit)

**Decision**
- Is the rule stated precisely enough that two developers would implement it the same way?
- Does it include a concrete code example or file path where possible?
- Flag: decisions using "prefer", "try to", "where possible", "generally"

**Consequences — Negative**
- Are the trade-offs and costs of this decision honestly listed?
- A decision with only positive consequences listed is a red flag.
- Flag: Consequences sections that are all upside

**Enforcement**
- Is there a concrete, verifiable enforcement mechanism? (ESLint rule, CLAUDE.md entry, CI check, test requirement)
- Flag: "code review" as the sole enforcement — it doesn't scale

**Conflict check**
- Read all other ADRs and flag any rule in this ADR that could conflict with another

---

### For Phase plans, check:

**Goals and Deliverables**
- Is each deliverable specific and independently verifiable?
- Could a reviewer check each deliverable off a list and know for certain it's done?
- Flag: deliverables stated as effort ("implement email sync") rather than outcomes ("emails sync within 60 seconds of arrival")

**PRDs in scope**
- Are all PRDs in scope at 🟢 Approved status? Flag any that aren't.
- Are there PRDs that logically belong in this phase but aren't listed?

**Sequence and dependencies**
- Is the build order within the phase explicit?
- Are intra-phase dependencies called out? (e.g., "API must be working before frontend starts")
- Flag: deliverables with hidden dependencies

**Definition of Done**
- Is the Definition of Done specific and testable?
- Could the team have a genuine disagreement about whether it's met?
- Flag: DoD items like "all features working" or "tests passing" with no specifics

**Version bump check**
- Does the phase or revision include a new Prisma migration or new API endpoint?
- If yes, flag: a MINOR version bump is required before implementation begins. The developer must run `/bump-version` first.
- Flag: any migration mentioned without a note that it requires a MINOR bump.
- Migration names must include the version number (e.g. `prisma migrate dev --name v0_2_0_describe_change`). See `docs/guides/managing-versions.md`.

**Risks and blockers**
- Are known risks documented with a mitigation or decision point?
- Are external blockers (third-party APIs, other teams) named explicitly?
- Flag: no risks section, or a risks section that says "none identified"

---

## Step 3: Report your findings

After the audit, print a summary **before asking any questions**. Format it like this:

```
## Quality Audit: [Document ID] — [Document Title]

**Document type:** [PRD / ADR / Phase]
**Current status:** [status badge]

### Findings

**High priority** (likely to cause implementation confusion):
- [Section name]: [Specific issue found, with a quote from the document]

**Medium priority** (gaps that could cause scope creep or missed edge cases):
- [Section name]: [Specific issue]

**Low priority** (polish and clarity improvements):
- [Section name]: [Specific issue]

**Looks good** (sections that are already clear and actionable):
- [Section name]

I'll work through the high-priority items first, then medium, then low.
Estimated questions: [N]
```

If the document has no significant issues, say so and ask the user if they still want to work through any section in more detail.

---

## Step 4: Summarize likely impact and gather initial feedback

After the audit report, generate a clear summary of how this document would likely affect the app:

**Generate a 10-20 bullet point summary covering:**
- Business logic changes (what the app will do differently)
- Key UI elements that will change or be added
- User-facing behavior changes
- Integration or data flow implications

Format it clearly and present it to the user.

Then ask both feedback questions together:
> "Looking at this summary, do you see anything missing from the document? And are there key items here that aren't what you expected?"

Wait for their answer before proceeding to detailed refinement questions.

---

## Step 5: Ask detailed questions in sequence — one at a time

Work through findings from high priority to low. For each finding, ask one focused question and wait for the answer before moving on.

**How to frame questions:**

For vague acceptance criteria:
> "The criterion 'emails load quickly' isn't specific enough to test. What's the maximum load time that would be acceptable to a user on a slow connection — 2 seconds? 5 seconds? Or is there a P95 latency target you have in mind?"

For missing error states:
> "The user stories cover the happy path, but what should happen if the email provider's API is down when the user tries to sync? Should the app show an error and let them retry, silently queue it, or something else?"

For ambiguous ADR rules:
> "The decision says to 'prefer using IRealtimeTransport over polling'. Would it be accurate to make this stronger — 'Never poll; all live updates must go through IRealtimeTransport'? Or are there cases where polling is acceptable?"

For thin non-goals:
> "The Non-Goals section is empty. Are there any related features you've explicitly decided not to build in this phase? For example, would it be safe to say 'rich text composition is out of scope for v1'?"

For phase deliverable vagueness:
> "The deliverable 'email sync working' could mean many things. What's the minimum that has to be true for this to count as done — for example: all emails from the last 30 days synced, new emails arriving within 60 seconds, and deleted emails removed within 5 minutes?"

**Rules for questioning:**
- Be specific. Reference the exact sentence or section that prompted the question.
- Offer concrete examples or options when the user might not know where to start.
- Flag when a question is a product decision vs. a technical one.
- Skip questions where the user's answer would clearly be "yes, keep it as is" — you are looking for genuine gaps.
- Do not ask more than one question per message.

---

## Step 6: Update the document

After all questions are answered, update all related documents (not just the document passed in as an argument, but related PRDs, ADRs and Phase documents) in place:

**For PRDs:**
- Rewrite vague sections using the user's answers — don't just append, integrate cleanly
- Replace ambiguous language ("should", "approximately") with specific, testable language
- Add missing error states to User Stories and Acceptance Criteria
- Add or update the Technical Constraints section with specific ADR references
- Check off resolved Open Questions (change `- [ ]` to `- [x]`) and add the answer inline
- Add any new open questions that surfaced during the review
- Update `## Last Updated` to today's date
- Add a row to the Revision History table: `| [date] | Refine pass | Improved clarity of [sections] via /doc-refiner |`

**For ADRs:**
- Make the Decision rule more precise using the user's answers
- Add rejected alternatives if they were missing
- Add honest negative consequences if they were missing
- Strengthen the Enforcement section with concrete mechanisms
- Update the date
- Add to Revision History if one exists, or add a "Last Revised" note

**For Phase plans:**
- Rewrite vague deliverables as outcome statements
- Add the Definition of Done if it was thin
- Add an explicit build sequence if it was implicit
- Add a Risks section if it was missing
- Update the date

Do NOT change the approval status of a PRD automatically. After saving the document, ask:

> "The document has been updated. The status is currently [status]. Would you like to change it, or leave it as-is?"

Only update status if they ask for it.

---

## Step 7: Confirm and follow up

After saving, tell the user:
- The exact file path that was updated
- A brief summary of what changed (e.g. "Tightened 4 acceptance criteria, added 3 error-state user stories, added ADR-005 reference to Technical Constraints")

Then check for downstream effects:
- **If a PRD was updated:** Does the phase document that contains it need to reflect any changes? Check the phase's Definition of Done against the new acceptance criteria.
- **If an ADR was updated:** Does CLAUDE.md need to be updated to reflect the new/revised rule? Does the Mandatory ADR Reads table in CLAUDE.md still reflect the right task types?
- **If a Phase was updated:** Are any PRD deliverables now more specific than what the phase says? Do any implementation documents in `/docs/development/implemented/v{MAJOR}.{MINOR}/` need a note added?

Report any downstream effects and ask the user if they want to address them now or later. Do not make downstream changes without confirmation.
