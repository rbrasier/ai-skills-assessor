"""CLI entry point for the AI mock interview test.

Run interactively:
    python -m src.testing.cli
    ./scripts/mock-interview.sh
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Noa and post-call models are fixed — latest available, not user-configurable
_NOA_MODEL = "claude-sonnet-4-6"
_POST_CALL_MODEL = "claude-sonnet-4-6"

_SFIA_LEVEL_DESCRIPTIONS = {
    1: "Follow           — performs routine tasks under close supervision",
    2: "Assist           — supports others, works under direction",
    3: "Apply            — works without close supervision on routine problems",
    4: "Enable           — influences small teams, manages own work",
    5: "Ensure/Advise    — accountable for outcomes, advises teams, sets standards",
    6: "Initiate/Influence — shapes organisational direction",
    7: "Set Strategy     — sets strategy at the highest organisational level",
}

_HONESTY_DESCRIPTIONS = [
    ("1–2",  "Fabricate   — invents projects/outcomes, claims 2–3 levels above reality"),
    ("3–5",  "Exaggerate  — claims others' work, overstates impact"),
    ("6–8",  "Truthful    — mostly honest with minor embellishment"),
    ("9–10", "Accurate    — fully honest and specific"),
]

_ARTICULATION_DESCRIPTIONS = [
    ("1–2",  "Very poor   — lots of um/uh, rambling, sentences trail off"),
    ("3–4",  "Below avg   — frequent fillers, loosely organised"),
    ("5–6",  "Average     — occasional fillers, gets to the point eventually"),
    ("7–8",  "Good        — clear and structured, rare fillers"),
    ("9–10", "Polished    — articulate, precise, well-structured"),
]

# Grouped by category for the skills prompt
_SKILL_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Development & Implementation", [
        ("PROG", "Programming / software development"),
        ("DENG", "Data engineering"),
        ("TEST", "Testing"),
        ("SINT", "Systems integration and testing"),
        ("DESN", "Systems design"),
    ]),
    ("Delivery & Operation", [
        ("CLOP", "Cloud operations"),
        ("DBAD", "Database administration"),
        ("NTAS", "Network administration"),
        ("HSIN", "Hardware / infrastructure"),
    ]),
    ("Strategy & Architecture", [
        ("ARCH", "Solution architecture"),
        ("SCTY", "Information security"),
    ]),
    ("Business Change", [
        ("BUAN", "Business analysis"),
    ]),
    ("Management & Governance", [
        ("ITMG", "IT management"),
        ("PRMG", "Project management"),
        ("DLMG", "Delivery management"),
    ]),
]

_ALL_SKILL_CODES: set[str] = {
    code for _, skills in _SKILL_GROUPS for code, _ in skills
}


def _hr(char: str = "─", width: int = 58) -> str:
    return char * width


def _prompt_text(label: str, description: str, example: str = "") -> str:
    print(f"\n{label}")
    print(f"  {description}")
    if example:
        print(f'  e.g. "{example}"')
    while True:
        value = input("> ").strip()
        if value:
            return value
        print("  (required — please enter a value)")


def _prompt_int(label: str, options: dict[str, str], lo: int, hi: int) -> int:
    print(f"\n{label}")
    for key, desc in options.items():
        print(f"  {key:>4}  {desc}")
    while True:
        raw = input(f"\n  Enter {lo}–{hi}: ").strip()
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"  Please enter a number between {lo} and {hi}.")


def _prompt_model() -> str:
    from src.testing.candidate_bot import CANDIDATE_MODELS

    print("\nCandidate intelligence  (affects how articulate and convincing the candidate is)")
    print(f"  1  Haiku   — straightforward, concise answers")
    print(f"  2  Sonnet  — articulate, well-structured responses")
    print(f"  3  Opus    — sophisticated, nuanced, highly convincing")
    while True:
        raw = input("\n  Enter 1–3: ").strip()
        if raw == "1":
            return CANDIDATE_MODELS["haiku"]
        if raw == "2":
            return CANDIDATE_MODELS["sonnet"]
        if raw == "3":
            return CANDIDATE_MODELS["opus"]
        print("  Please enter 1, 2, or 3.")


def _prompt_skills() -> list[str]:
    print("\nTarget SFIA skills  (3 skills the candidate wants to be assessed on)")
    print("  An honest candidate has genuine experience in these areas.")
    print("  A dishonest candidate may have the role but fabricate experience in them.\n")
    for group_name, skills in _SKILL_GROUPS:
        print(f"  {group_name}:")
        for code, name in skills:
            print(f"    {code:6}  {name}")
    print()
    while True:
        raw = input("  Enter 3 codes separated by spaces (e.g. PROG ARCH CLOP): ").strip().upper()
        codes = [c.strip(",") for c in raw.split() if c.strip(",")]
        unknown = [c for c in codes if c not in _ALL_SKILL_CODES]
        if len(codes) != 3:
            print(f"  Please enter exactly 3 codes (you entered {len(codes)}).")
        elif unknown:
            print(f"  Unknown code(s): {', '.join(unknown)}. Check the list above.")
        else:
            return codes


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _to_json_safe(obj: object) -> object:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_json_safe(v) for k, v in dataclasses.asdict(obj).items()}
    if hasattr(obj, "model_dump"):
        return _to_json_safe(obj.model_dump())
    if isinstance(obj, list):
        return [_to_json_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _model_label(model_id: str) -> str:
    from src.testing.candidate_bot import CANDIDATE_MODELS
    for label, mid in CANDIDATE_MODELS.items():
        if mid == model_id:
            return label
    return model_id


def _collect_inputs() -> tuple[str, int, int, int, str, list[str]]:
    print(f"\n{_hr('═')}")
    print("  AI Mock Interview Test")
    print(_hr("═"))
    print("  Simulates a full SFIA skills assessment interview.")
    print("  One AI plays the candidate; Noa (the AI interviewer) conducts the call.")
    print("  The full pipeline runs: conversation → claim extraction → scored report.")

    role = _prompt_text(
        "Candidate role / persona",
        "Describe the candidate's job title and context.",
        "Senior Software Engineer at a fintech startup, 8 years experience",
    )

    sfia_level = _prompt_int(
        "SFIA Responsibility Level  (candidate's genuine capability)",
        _SFIA_LEVEL_DESCRIPTIONS,
        lo=1,
        hi=7,
    )

    honesty = _prompt_int(
        "Honesty  (how truthfully the candidate represents their capability)",
        dict(_HONESTY_DESCRIPTIONS),
        lo=1,
        hi=10,
    )

    articulation = _prompt_int(
        "Articulation  (how fluently the candidate speaks — 1=very inarticulate, 10=polished)",
        dict(_ARTICULATION_DESCRIPTIONS),
        lo=1,
        hi=10,
    )

    model = _prompt_model()

    target_skills = _prompt_skills()

    return role, sfia_level, honesty, articulation, model, target_skills


async def _run(
    role: str,
    sfia_level: int,
    honesty: int,
    articulation: int,
    model: str,
    target_skills: list[str],
    output_dir: str,
) -> None:
    from src.testing.candidate_bot import SFIA_SKILL_NAMES, CandidatePersona
    from src.testing.mock_interview_runner import run_mock_interview
    from src.testing.scorer import score

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("\nERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    persona = CandidatePersona(
        role=role,
        sfia_level=sfia_level,
        honesty=honesty,
        articulation=articulation,
        target_skills=target_skills,
        model=model,
    )

    skills_display = ", ".join(
        f"{c} ({SFIA_SKILL_NAMES.get(c, c)})" for c in target_skills
    )
    level_label = _SFIA_LEVEL_DESCRIPTIONS[sfia_level].split("—")[1].strip()

    print(f"\n{_hr()}")
    print("  Running interview  (this takes 1–2 minutes)")
    print(_hr())
    print(f"  Role           : {persona.role}")
    print(f"  SFIA level     : {persona.sfia_level}  —  {level_label}")
    print(f"  Honesty        : {persona.honesty}/10")
    print(f"  Articulation   : {persona.articulation}/10")
    print(f"  Intelligence   : {_model_label(model)} ({model})")
    print(f"  Target skills  : {skills_display}")
    print(_hr())
    print()

    result = await run_mock_interview(
        persona=persona,
        api_key=api_key,
        noa_model=_NOA_MODEL,
        post_call_model=_POST_CALL_MODEL,
    )

    score_result = score(persona, result.report)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"mock-interview-{ts}.json"

    payload = {
        "meta": {
            "timestamp": datetime.now(UTC).isoformat(),
            "persona": dataclasses.asdict(persona),
            "noa_model": _NOA_MODEL,
            "post_call_model": _POST_CALL_MODEL,
            "turn_count": result.turn_count,
            "elapsed_seconds": round(result.elapsed_seconds, 1),
        },
        "transcript": result.transcript,
        "report": _to_json_safe(result.report),
        "score": _to_json_safe(score_result),
    }

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\n{_hr()}")
    print("  RESULTS")
    print(_hr())
    print(f"  Turns            : {result.turn_count}")
    print(f"  Elapsed          : {result.elapsed_seconds:.1f}s")
    print(f"  Claims found     : {score_result.total_claims}")
    print(f"  Configured level : {score_result.configured_level}")
    print(f"  Mean assessed    : {score_result.mean_assessed_level}")
    print(f"  Mean delta       : {score_result.mean_level_delta}")
    print(f"  Accuracy         : {score_result.mean_accuracy_pct:.1f}%")
    print(f"  Mean confidence  : {score_result.mean_confidence:.2f}")

    if score_result.per_skill:
        print(f"\n  Per-skill breakdown  (from claims):")
        for s in score_result.per_skill:
            tag = " ✓" if s.skill_code in target_skills else ""
            print(
                f"    {s.skill_code:6}  {s.skill_name[:28]:28}  "
                f"assessed={s.mean_assessed_level:.1f}  "
                f"acc={s.mean_accuracy_pct:.0f}%  "
                f"conf={s.mean_confidence:.2f}  "
                f"({s.claim_count} claim{'s' if s.claim_count != 1 else ''}){tag}"
            )
        print("         ✓ = targeted skill")

    if score_result.holistic_profiles:
        print(f"\n  Holistic skill profile  (full-transcript view, top {len(score_result.holistic_profiles)}):")
        for h in score_result.holistic_profiles:
            tag = " ✓" if h.skill_code in target_skills else ""
            bar = "█" * round(h.prominence * 10)
            print(
                f"    {h.skill_code:6}  {h.skill_name[:28]:28}  "
                f"level={h.estimated_level}  "
                f"prominence={h.prominence:.2f} {bar}{tag}"
            )
            print(f"           {h.evidence_summary[:80]}")
        print("         ✓ = targeted skill")

    print(f"\n  Output: {out_path}")
    print(_hr())
    print()


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    output_dir = "./mock-results"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--output-dir" and i < len(sys.argv) - 1:
            output_dir = sys.argv[i + 1]

    _setup_logging(verbose)

    try:
        role, sfia_level, honesty, articulation, model, target_skills = _collect_inputs()
    except (KeyboardInterrupt, EOFError):
        print("\n\nCancelled.")
        sys.exit(0)

    print(f"\n  Ready to run? (y/n) ", end="")
    try:
        confirm = input().strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)

    if confirm not in ("y", "yes"):
        print("Cancelled.")
        sys.exit(0)

    asyncio.run(_run(role, sfia_level, honesty, articulation, model, target_skills, output_dir))


if __name__ == "__main__":
    main()
