You are helping the Orchestra developer decide on and apply a version bump before a MINOR or MAJOR release. Follow these steps exactly.

PATCH versions are handled automatically by CI on every merge to `main` — do not use this skill for patches.

---

## Step 1: Read current version

Read `package.json` from the repo root. Show the user the current version so they can confirm before proceeding.

---

## Step 2: Determine bump type

Ask one question:

> "Is this a **breaking change** (removing or renaming an API field, endpoint, or changing a field's type) — or a **new major milestone**? Or is it a **minor release** (new DB migration, new API endpoint, new feature group)?"

- Breaking change / major milestone → **MAJOR** bump (e.g. `0.1.0 → 1.0.0`)
- Everything else with a DB or API change → **MINOR** bump (e.g. `0.1.0 → 0.2.0`)

If they say "I'm not sure", ask:
- "Does this release include any new Prisma migration files?" → YES → MINOR
- "Does this add new API endpoints or new response fields?" → YES → MINOR
- If neither, remind them that PATCH is handled by CI and they should not be running this skill.

---

## Step 3: Identify what's shipping in this release

Ask:

> "Which PRDs, phases, and implementation documents are shipping in this release? List them by name or number — e.g. PRD-010, PHASE-7, PHASE-7-Revision-1."

Then scan `docs/development/prd/`, `docs/development/to-be-implemented/`, and `docs/phases/implementated/` to find the actual files matching what they listed. Show the user the resolved file list and ask them to confirm it's complete before continuing.

Also check git for any PRD, phase, or implementation docs that have been modified in recent commits (`git log --name-only --oneline -20`) and surface any they may have missed.

**Note:** PRDs will be listed for reference, but only phases and implementation documents will be moved to the version folder in Step 5.

---

## Step 4: Apply the version bump

Compute the new version:
- MAJOR: increment first segment, reset minor and patch to 0
- MINOR: increment second segment, reset patch to 0

Read `package.json`, update the `version` field, write it back.

Confirm the change to the user: "Updated package.json: `OLD → NEW`"

---

## Step 5: Move phase and implementation documents

This step moves phase and implementation documents into the version folder with version-prefixed names. **PRD documents remain in `docs/development/prd/` and are not moved.**

### 5a. Create the version folder

Create the directory `docs/development/implemented/vMAJOR.MINOR/` (e.g. `docs/development/implemented/v0.1/`).

### 5b. Move phase and implementation documents into the version folder

For each phase and implementation document identified in Step 3, move (not copy) the file into the version folder with a version prefix added to the filename.

**Naming convention:** `v{MAJOR}.{MINOR}-{original-filename}`

**Do NOT move PRD documents** — they stay in `docs/development/prd/`.

Examples:
- `docs/docs/development/to-be-implemented/PHASE-7-mobile.md` → `docs/development/implemented/v0.1/v0.1-PHASE-7-mobile.md`

Use `git mv` for each file so that git tracks the rename and preserves history.

**Important:** Before moving, confirm the full list of files (phases and implementation docs only, not PRDs) and their new names with the user. Moving documents is not easily reversible.


---

## Step 6: Confirm and summarise

Tell the user:

```
Done.

Version bumped : {OLD} → {NEW}
Version folder : /docs/development/implemented/v{MAJOR}.{MINOR}/

Phase and implementation files moved:
  {old path} → {new path}
  {old path} → {new path}
  ...

PRD documents remain in docs/development/prd/ (not moved).

Next steps:
1. Review the version index and add any release notes
2. Commit: git commit -am "chore: bump version to {NEW}"
3. Tag:    git tag v{NEW} && git push origin v{NEW}
4. CI will build signed desktop binaries and create the GitHub Release automatically
```

Do NOT commit or push. That is the developer's responsibility.
