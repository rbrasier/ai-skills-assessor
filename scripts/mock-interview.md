# Mock Interview Test

Runs an AI-to-AI SFIA skills assessment to validate the end-to-end pipeline without voice infrastructure. One Claude instance plays the candidate; the live `SfiaFlowController` conducts the interview as Noa. The full pipeline runs after the call: transcript → claim extraction → assessment report → accuracy score.

## Purpose

- Verify the assessment flow works end-to-end at the transcript level
- Test how well the pipeline maps skills at different SFIA levels
- Simulate dishonest candidates to see whether fabricated claims inflate scores
- Compare candidate intelligence (model choice) against assessment accuracy

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
| **Honesty (1–10)** | How truthfully they represent that level — 10 is fully honest, 1 fabricates entirely |
| **Intelligence (1–3)** | Haiku / Sonnet / Opus — proxy for how articulate and convincing the candidate is |
| **Target skills (3 codes)** | The SFIA skill areas they want to be assessed on. An honest candidate has real experience here; a dishonest one will fabricate it |

The key distinction: **role is the persona, target skills are what they want credit for**. A dishonest candidate can have a genuine role but be seeking assessment on skills they don't actually hold.

Output is written to `./mock-results/mock-interview-{timestamp}.json` (configurable with `--output-dir`).

## Expected output

A summary is printed at the end:

```
──────────────────────────────────────────────────────────
  RESULTS
──────────────────────────────────────────────────────────
  Turns            : 22
  Elapsed          : 68.4s
  Claims found     : 6
  Configured level : 5
  Mean assessed    : 4.8
  Mean delta       : 0.3
  Accuracy         : 95.0%
  Mean confidence  : 0.81

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
| Honest candidate (honesty 8–10) | `mean_accuracy_pct` ≥ 75% is a healthy pipeline. Lower suggests the claim extraction or SFIA mapping needs tuning. |
| Dishonest candidate (honesty 1–3) | `mean_assessed_level` should be noticeably higher than `configured_level` — the pipeline is being fooled. This is expected behaviour, not a bug. |
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

| Role | Level | Honesty | Intelligence | What it tests |
|------|-------|---------|--------------|---------------|
| Mid-level engineer | 4 | 9 | Haiku | Happy path — honest, simple |
| Senior architect | 6 | 9 | Sonnet | High-level candidate accuracy |
| Junior dev | 2 | 2 | Opus | Fabrication detection — smart liar |
| Mid-level engineer | 4 | 9 | Opus | Does higher intelligence improve extraction? |
| Senior architect | 6 | 3 | Sonnet | Partial dishonesty — exaggeration detection |
