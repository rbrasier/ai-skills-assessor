"""CLI entry point for the AI mock interview test.

Usage:
    python -m src.testing.cli --role "Senior Software Engineer" --sfia-level 5
    ./scripts/mock-interview.sh --role "..." --sfia-level 5 --honesty 8
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mock-interview",
        description="Run an AI-to-AI mock SFIA skills assessment interview.",
    )
    p.add_argument(
        "--role",
        required=True,
        help='Candidate role/context, e.g. "Senior Software Engineer at a fintech startup"',
    )
    p.add_argument(
        "--sfia-level",
        type=int,
        required=True,
        choices=range(1, 8),
        metavar="1-7",
        help="Candidate's genuine SFIA responsibility level (1–7)",
    )
    p.add_argument(
        "--honesty",
        type=int,
        default=8,
        choices=range(1, 11),
        metavar="1-10",
        help="Honesty scale: 10=fully truthful, 1=heavily fabricates (default: 8)",
    )
    p.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Candidate bot model (default: claude-haiku-4-5-20251001)",
    )
    p.add_argument(
        "--noa-model",
        default=None,
        help="Interviewer (Noa) model. Defaults to --model if not set.",
    )
    p.add_argument(
        "--post-call-model",
        default="claude-sonnet-4-6",
        help="Model for claim extraction (default: claude-sonnet-4-6)",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=40,
        help="Maximum conversation turns before timeout (default: 40)",
    )
    p.add_argument(
        "--output-dir",
        default="./mock-results",
        help="Directory to write output JSON (default: ./mock-results)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return p


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _to_json_safe(obj: object) -> object:
    """Recursively convert dataclasses and Pydantic models to plain dicts."""
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


async def _main(args: argparse.Namespace) -> None:
    from src.testing.candidate_bot import CandidatePersona
    from src.testing.mock_interview_runner import run_mock_interview
    from src.testing.scorer import score

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    persona = CandidatePersona(
        role=args.role,
        sfia_level=args.sfia_level,
        honesty=args.honesty,
        model=args.model,
    )

    print(f"\n{'=' * 60}")
    print(f"  AI Mock Interview")
    print(f"{'=' * 60}")
    print(f"  Role       : {persona.role}")
    print(f"  SFIA Level : {persona.sfia_level}")
    print(f"  Honesty    : {persona.honesty}/10")
    print(f"  Cand. model: {persona.model}")
    print(f"  Noa model  : {args.noa_model or persona.model}")
    print(f"  Post-call  : {args.post_call_model}")
    print(f"{'=' * 60}\n")
    print("Running interview... (this may take a minute)\n")

    result = await run_mock_interview(
        persona=persona,
        api_key=api_key,
        noa_model=args.noa_model,
        post_call_model=args.post_call_model,
        max_turns=args.max_turns,
    )

    score_result = score(persona, result.report)

    # Write output file
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"mock-interview-{ts}.json"

    payload = {
        "meta": {
            "timestamp": datetime.now(UTC).isoformat(),
            "persona": dataclasses.asdict(persona),
            "noa_model": args.noa_model or persona.model,
            "post_call_model": args.post_call_model,
            "turn_count": result.turn_count,
            "elapsed_seconds": round(result.elapsed_seconds, 1),
        },
        "transcript": result.transcript,
        "report": _to_json_safe(result.report),
        "score": _to_json_safe(score_result),
    }

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"  Turns          : {result.turn_count}")
    print(f"  Elapsed        : {result.elapsed_seconds:.1f}s")
    print(f"  Claims found   : {score_result.total_claims}")
    print(f"  Configured level : {score_result.configured_level}")
    print(f"  Mean assessed    : {score_result.mean_assessed_level}")
    print(f"  Mean delta       : {score_result.mean_level_delta}")
    print(f"  Accuracy         : {score_result.mean_accuracy_pct:.1f}%")
    print(f"  Mean confidence  : {score_result.mean_confidence:.2f}")

    if score_result.per_skill:
        print(f"\n  Per-skill breakdown:")
        for s in score_result.per_skill:
            print(
                f"    {s.skill_code:6s} {s.skill_name[:30]:30s} "
                f"assessed={s.mean_assessed_level:.1f} "
                f"acc={s.mean_accuracy_pct:.0f}% "
                f"conf={s.mean_confidence:.2f} "
                f"({s.claim_count} claim{'s' if s.claim_count != 1 else ''})"
            )

    print(f"\n  Output: {output_path}")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _setup_logging(args.verbose)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
