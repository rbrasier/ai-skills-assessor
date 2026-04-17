You are helping the user create a new Architecture Decision Record (ADR) for the Orchestra project. Follow this process exactly, in order. Do not skip steps.

---

## Step 1: Read existing ADRs and CLAUDE.md

Before asking any questions, read all files in `docs/development/adr/` and `CLAUDE.md` to:
- Understand what architectural decisions have already been made
- Avoid creating a duplicate ADR
- Identify which ADR number to assign next (find the highest existing number and add 1)
- Understand existing patterns and rules that the new ADR must be consistent with

If the user's request overlaps significantly with an existing ADR, tell them which one and ask whether they want to supersede it or extend it rather than creating a new one.

---

## Step 2: Ask these questions in sequence

Ask each question and wait for the answer before moving to the next. Do not batch them all at once.

**Q1:** "What architectural decision are you making? Describe it in one sentence."

**Q2:** "What is the context — what problem or set of forces led to this decision? What goes wrong without it?"

**Q3:** "What options did you consider before choosing this approach? (Even a brief comparison — this is important for future readers who might question the choice.)"

**Q4:** "What is the decision itself? Be precise: what is now required, what is now forbidden, or what pattern must be followed?"

**Q5:** "What are the positive consequences of this decision?"

**Q6:** "What are the negative consequences or trade-offs?"

**Q7:** "How will this decision be enforced? (e.g. ESLint rule, CLAUDE.md constraint, test requirement, file size limit, code review checklist)"

**Q8:** "Does this decision affect any existing PRDs, phases, or other ADRs? If so, which ones and how?"

---

## Step 3: Generate and save the ADR

Using the answers, generate a complete ADR using the template below. Save it to `docs/development/adr/ADR-XXX-decision-name.md` where XXX is the next available number (zero-padded to 3 digits).

---

## Step 4: Update CLAUDE.md if needed

After saving the ADR file, check whether CLAUDE.md needs updating:

1. **Architecture Rules section** — If the ADR introduces a new non-negotiable rule (e.g. file size limits, import restrictions, naming patterns), add it as a numbered rule in the "Architecture Rules" section.
2. **Mandatory ADR Reads table** — If the ADR is relevant to a specific task type (database work, auth, real-time, etc.), add it to the table so Claude reads it at the start of relevant sessions.

Do NOT change CLAUDE.md for consequences that are already captured in existing rules.

---

## Step 5: Notify the user

Tell the user:
- The filename the ADR was saved to
- Whether CLAUDE.md was updated and what changed (quote the specific lines added)
- Which PRDs or phases (if any) should be updated to reference this ADR in their Technical Constraints section — do NOT update those files automatically, just flag them
- That the ADR status is **Proposed** until the team accepts it — they should change it to **Accepted** when ready

---

## ADR Template

```markdown
# ADR-XXX: [Decision Title]

## Status
Proposed

## Date
[Today's date]

## Context

[The problem, forces at play, and why a decision was needed here. Include what would happen without this decision. Reference the previous codebase behaviour if relevant.]

## Options Considered

1. **[Option A]** — [Brief description. Why it was rejected or accepted.]
2. **[Option B]** — [Brief description. Why it was rejected or accepted.]
3. **[Option C if applicable]** — [Brief description.]

## Decision

[What was decided. Be precise: what is required, what is forbidden, what pattern must be followed. Include a code example or directory example if it helps clarify the pattern.]

## Consequences

**Positive:**
- [Benefit]
- [Benefit]

**Negative:**
- [Trade-off]
- [Trade-off]

## Enforcement

- [How this is enforced — ESLint rule, CLAUDE.md constraint, test requirement, file structure, etc.]
- [If multiple enforcement mechanisms, list each]
```
