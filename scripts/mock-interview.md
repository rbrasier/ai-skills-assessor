# Mock Interview Test

Runs an AI-to-AI SFIA skills assessment to validate the end-to-end pipeline without voice infrastructure. One Claude instance plays the candidate; the live `SfiaFlowController` conducts the interview as Noa. The full pipeline runs after the call: transcript → claim extraction → assessment report → accuracy score.

## Purpose

- Verify the assessment flow works end-to-end at the transcript level
- Test how the pipeline handles different candidate behaviours (honest, evasive, disruptive, over-confident)
- Compare assessment accuracy across SFIA levels and skill areas
- Validate RAG context injection: if SFIA vectors exist in the database, the interviewer uses live pgvector definitions — exactly as in a real voice call

## Prerequisites

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cd apps/voice-engine && pip install -e .[voice]
```

## Usage

```bash
./scripts/mock-interview.sh
```

You will be prompted for five inputs:

| Prompt | Description |
|--------|-------------|
| **Role / persona** | The candidate's job title and context — this is who they genuinely are |
| **SFIA level (1–7)** | Their actual capability level |
| **Behaviour / approach** | Free-text description of how the candidate will behave during the interview |
| **Articulation (1–10)** | How fluently the candidate speaks — 1=very inarticulate, 10=polished |
| **Intelligence (1–3)** | Haiku / Sonnet / Opus — proxy for how articulate and convincing the candidate is |
| **Target skills (3 codes)** | The SFIA skill areas they want to be assessed on |

### Behaviour / approach examples

The approach field is passed directly as the candidate's behaviour instruction. Some useful values:

| Approach description | What it tests |
|----------------------|---------------|
| `"honest and direct, gives accurate concrete examples at their real level"` | Happy path — truthful candidate |
| `"will exaggerate skills and pretend to higher ability with high ego and confidence"` | Fabrication / inflation detection |
| `"anxious and disruptive — loses track, gives vague rambling answers"` | Resilience of pipeline to low-quality transcripts |
| `"mostly honest but occasionally takes credit for team achievements"` | Subtle over-claiming |
| `"refuses to give concrete examples, deflects every question"` | Edge case: evasive candidate |

The key distinction: **role is the persona, behaviour is how they play it**. The same role can be run with different approaches to see how the pipeline responds.

Output is written to `./mock-results/mock-interview-{timestamp}.json` (configurable with `--output-dir`).

## RAG context

When `DATABASE_URL` is set and SFIA vectors exist in `framework_skill_levels`, the interviewer bot receives live skill definitions from pgvector — the same RAG context injection that runs in real voice calls. This is shown in the RESULTS output:

```
  Knowledge base   : pgvector (live SFIA vectors)
```

Without a database (or if the table is empty), the runner falls back to stub in-memory definitions:

```
  Knowledge base   : stub (in-memory definitions)
```

## Expected output

A summary is printed at the end:

```
──────────────────────────────────────────────────────────
  RESULTS
──────────────────────────────────────────────────────────
  Turns            : 22
  Elapsed          : 68.4s
  Knowledge base   : pgvector (live SFIA vectors)
  Claims found     : 6
  Configured level : 5
  Mean assessed    : 4.8
  Mean delta       : 0.3
  Accuracy         : 95.0%
  Mean prominence  : 0.81

  Per-skill breakdown:
    ARCH    Solution architecture         assessed=5.0  acc=100%  conf=0.88  (2 claims) ✓
    CLOP    Cloud operations              assessed=5.0  acc=100%  conf=0.79  (3 claims) ✓
    SCTY    Information security          assessed=4.5  acc=92%   conf=0.76  (1 claim)  ✓
         ✓ = targeted skill
```

The JSON file contains three sections: `transcript`, `report`, and `score`.

## How to analyse

### Accuracy score

`mean_accuracy_pct` is the primary signal. It measures how closely the pipeline's SFIA level assessments matched the configured candidate level, averaged across all claims:

```
accuracy per claim = 1 - (|assessed_level - configured_level| / 6)
```

A delta of 0 scores 100%; a delta of 6 (maximum possible) scores 0%.

**Interpreting results:**

| Scenario | What to look for |
|----------|-----------------|
| Honest candidate | `mean_accuracy_pct` ≥ 75% is a healthy pipeline. Lower suggests the claim extraction or SFIA mapping needs tuning. |
| Over-claiming / ego approach | `mean_assessed_level` should be noticeably higher than `configured_level` — the pipeline is being fooled. This is expected behaviour, not a bug. |
| Targeted vs non-targeted skills | Check whether `✓` skills appear in the report at all. If the candidate successfully steered the conversation, they should dominate the claim list. |
| Confidence scores | Low `mean_confidence` (< 0.5) across an honest candidate suggests the transcript isn't providing enough concrete evidence — the interview prompts may need strengthening. |

### Transcript

Read `transcript.turns` to understand the conversation flow. Each turn has `speaker`, `text`, `phase`, and `timestamp`. Check that:
- All 5 phases appear (`introduction`, `skill_discovery`, `evidence_gathering`, `summary`, `closing`)
- The candidate's target skills are mentioned in `evidence_gathering` turns
- There are no abrupt endings or missing phases (indicates a `max_turns` timeout)

### Report claims

Each claim in `report.claims` has:
- `verbatim_quote` — the exact words from the transcript
- `sfia_skill_code` / `sfia_level` — what the pipeline assessed
- `confidence` — how certain the extractor was
- `reasoning` — the LLM's explanation for its mapping

Low confidence on specific claims often points to vague candidate answers — useful for tuning interview probing prompts.

### Suggested test matrix

Run these scenarios and compare results to build a baseline:

| Role | Level | Approach | Intelligence | What it tests |
|------|-------|----------|--------------|---------------|
| Mid-level engineer | 4 | honest and direct, accurate examples | Haiku | Happy path — honest, simple |
| Senior architect | 6 | honest, well-articulated, specific | Sonnet | High-level candidate accuracy |
| Junior dev | 2 | exaggerates skills with high ego and confidence | Opus | Fabrication detection — smart liar |
| Mid-level engineer | 4 | honest and direct, accurate examples | Opus | Does higher intelligence improve extraction? |
| Senior architect | 6 | mostly honest but takes credit for team work | Sonnet | Partial over-claiming detection |
