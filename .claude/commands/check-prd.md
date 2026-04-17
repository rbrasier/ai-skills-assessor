The user wants to verify whether a feature has a PRD before building it. This is a safety check.

## Your Task

1. Read all files in `docs/development/prd/` to understand what is currently defined
2. The user has provided a feature name or description: $ARGUMENTS
3. Determine whether a PRD exists that covers this feature

## Output

### If a matching PRD exists:
- State which PRD covers it (name + file path)
- State the current PRD status (Draft / Review / Approved / Complete / Planned)
- If status is 🟢 Approved: confirm it is safe to build
- If status is 🔴 Draft or 🟡 Review: warn that it is NOT yet ready to build and must be approved first
- If status is 🔵 Planned: warn that it is a shell only and needs to be written before building

### If no matching PRD exists:
State clearly:

> ⚠️ **No PRD found for "[feature name]".**
>
> Per the PRD-First Development Rule in CLAUDE.md, this feature cannot be built without a PRD.
>
> Run `/new-prd` to create one, or check if it should be added to an existing PRD such as [suggest the closest existing PRD if any].

### If the request is ambiguous:
List the 2-3 most relevant PRDs and ask the user which one applies, then perform the check on the chosen one.
