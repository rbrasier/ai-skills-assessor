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

# Latest models — not user-configurable
_CANDIDATE_MODEL = "claude-haiku-4-5-20251001"   # fast, many turns
_NOA_MODEL = "claude-sonnet-4-6"                 # capable interviewer
_POST_CALL_MODEL = "claude-sonnet-4-6"            # accurate claim extraction

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
    (range(1, 3),  "Fabricate   — invents projects/outcomes, claims 2–3 levels above reality"),
    (range(3, 6),  "Exaggerate  — claims others' work, overstates impact"),
    (range(6, 9),  "Truthful    — mostly honest with minor embellishment"),
    (range(9, 11), "Accurate    — fully honest and specific"),
]


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


def _prompt_int(label: str, options: dict, lo: int, hi: int) -> int:
    print(f"\n{label}")
    for k, v in options.items():
        print(f"  {k}  {v}")
    while True:
        raw = input(f"\n  Enter {lo}–{hi}: ").strip()
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"  Please enter a number between {lo} and {hi}.")


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


def _collect_inputs() -> tuple[str, int, int]:
    print(f"\n{_hr('═')}")
    print("  AI Mock Interview Test")
    print(_hr("═"))
    print("  Simulates a full SFIA skills assessment interview.")
    print("  One AI plays the candidate; Noa (the AI interviewer) conducts the call.")
    print("  The transcript is processed through claim extraction and scored.")

    role = _prompt_text(
        "Candidate role",
        "Describe the candidate's job title and context.",
        "Senior Software Engineer at a fintech startup, 8 years experience",
    )

    sfia_level = _prompt_int(
        "SFIA Responsibility Level  (candidate's genuine capability)",
        _SFIA_LEVEL_DESCRIPTIONS,
        lo=1,
        hi=7,
    )

    honesty_options: dict[str, str] = {}
    for rng, desc in _HONESTY_DESCRIPTIONS:
        lo, hi = rng.start, rng.stop - 1
        label = f"{lo}" if lo == hi else f"{lo}–{hi}"
        honesty_options[label] = desc

    honesty = _prompt_int(
        "Honesty  (how truthfully the candidate represents their level)",
        honesty_options,
        lo=1,
        hi=10,
    )

    return role, sfia_level, honesty


async def _run(role: str, sfia_level: int, honesty: int, output_dir: str) -> None:
    from src.testing.candidate_bot import CandidatePersona
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
        model=_CANDIDATE_MODEL,
    )

    print(f"\n{_hr()}")
    print("  Running interview  (this takes 1–2 minutes)")
    print(_hr())
    print(f"  Role       : {persona.role}")
    print(f"  SFIA level : {persona.sfia_level}  —  {_SFIA_LEVEL_DESCRIPTIONS[persona.sfia_level].split('—')[1].strip()}")
    print(f"  Honesty    : {persona.honesty}/10")
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
        print(f"\n  Per-skill breakdown:")
        for s in score_result.per_skill:
            print(
                f"    {s.skill_code:6}  {s.skill_name[:28]:28}  "
                f"assessed={s.mean_assessed_level:.1f}  "
                f"acc={s.mean_accuracy_pct:.0f}%  "
                f"conf={s.mean_confidence:.2f}  "
                f"({s.claim_count} claim{'s' if s.claim_count != 1 else ''})"
            )

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
        role, sfia_level, honesty = _collect_inputs()
    except (KeyboardInterrupt, EOFError):
        print("\n\nCancelled.")
        sys.exit(0)

    print(f"\n  Ready to run with the above settings? (y/n) ", end="")
    try:
        confirm = input().strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)

    if confirm not in ("y", "yes"):
        print("Cancelled.")
        sys.exit(0)

    asyncio.run(_run(role, sfia_level, honesty, output_dir))


if __name__ == "__main__":
    main()
