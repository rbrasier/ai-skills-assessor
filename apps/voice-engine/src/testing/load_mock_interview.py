"""Load a mock-interview JSON export back into Postgres.

Usage:
  python -m src.testing.load_mock_interview /path/to/mock-interview-....json

Reuses the same persistence wiring as ``src.testing.cli`` (DATABASE_URL).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.domain.models.assessment import AssessmentSession, AssessmentStatus


def _build_persistence():  # pragma: no cover — CLI helper
    from src.testing.cli import _build_persistence as cli_build

    return cli_build()


async def _load(path: Path) -> str:
    raw = json.loads(path.read_text())
    report_obj: dict = raw.get("report") or {}
    transcript = raw.get("transcript") or {"turns": []}
    meta: dict = raw.get("meta") or {}
    persona: dict = meta.get("persona") or {}

    email = "mock@test.local"
    first = str(persona.get("first_name", "Mock"))
    last = str(persona.get("last_name", "Candidate"))
    employee_id = str(persona.get("employee_id", "MOCK-001"))

    persistence, _is_pg = _build_persistence()
    try:
        await persistence.get_or_create_candidate(
            email=email,
            first_name=first,
            last_name=last,
            employee_id=employee_id,
        )

        session_id = str(report_obj.get("session_id") or "")
        if not session_id:
            raise SystemExit("JSON missing report.session_id")

        cand_name = str(report_obj.get("candidate_name") or "Mock Candidate")
        await persistence.create_session(
            AssessmentSession(
                id=session_id,
                candidate_id=email,
                phone_number="",
                status=AssessmentStatus.PROCESSED,
                candidate_name=cand_name,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
            )
        )

        claims = report_obj.get("claims") or []
        holistic = report_obj.get("holistic_assessment") or []
        expert_tok = str(report_obj.get("expert_review_token") or "")
        sup_tok = str(report_obj.get("supervisor_review_token") or "")
        if not expert_tok or not sup_tok:
            raise SystemExit(
                "JSON missing expert_review_token / supervisor_review_token — "
                "re-export from a current mock run (see scripts/mock-interview.md).",
            )

        overall = float(report_obj.get("overall_confidence") or 0.0)
        expires_raw = report_obj.get("expires_at")
        if isinstance(expires_raw, str):
            exp_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        else:
            exp_at = datetime.now(UTC) + timedelta(days=30)

        await persistence.save_report(
            session_id=session_id,
            claims=claims,
            expert_review_token=expert_tok,
            supervisor_review_token=sup_tok,
            overall_confidence=overall,
            expires_at=exp_at,
            holistic_assessment=holistic,
        )

        await persistence.save_transcript(session_id, transcript)
        await persistence.update_session_status(session_id, "processed")
        return session_id
    finally:
        close = getattr(persistence, "close", None)
        if callable(close):
            await close()


def main() -> None:
    p = argparse.ArgumentParser(description="Reload mock interview JSON into the database")
    p.add_argument("json_file", type=Path, help="Path to mock-interview-*.json")
    args = p.parse_args()
    if not args.json_file.is_file():
        print(f"ERROR: not a file: {args.json_file}", file=sys.stderr)
        sys.exit(1)
    session_id = asyncio.run(_load(args.json_file))
    print(f"Loaded session {session_id}. Open the admin dashboard to inspect.")


if __name__ == "__main__":
    main()
