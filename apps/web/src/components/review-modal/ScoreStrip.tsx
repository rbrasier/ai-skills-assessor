import type { AssessmentReport, Claim } from "@ai-skills-assessor/shared-types";

function derivedMaxLevel(claims: Claim[], field: "level" | "expertLevel"): number | null {
  const vals = claims.map((c) => (field === "expertLevel" ? c.expertLevel : c.level)).filter(
    (v): v is number => typeof v === "number",
  );
  return vals.length ? Math.max(...vals) : null;
}

function fmt(n: number | null, suffix = ""): string {
  if (n === null || n === undefined) return "—";
  return `${n}${suffix}`;
}

interface Props {
  report: AssessmentReport;
}

export default function ScoreStrip({ report }: Props) {
  const claims = report.claimsJson ?? [];
  const originalMax = derivedMaxLevel(claims, "level");
  const currentMax = derivedMaxLevel(claims, "expertLevel") ?? originalMax;
  const avgConf =
    claims.length > 0
      ? Math.round((claims.reduce((s, c) => s + (c.confidence ?? 0), 0) / claims.length) * 100)
      : null;

  return (
    <div className="score-strip">
      <div className="score-cell">
        <div className="sc-label">AI max level</div>
        <div className="sc-val">{fmt(originalMax)}<small>/7</small></div>
        <div className="sc-sub">From extraction</div>
      </div>
      <div className="score-cell">
        <div className="sc-label">Current max level</div>
        <div className="sc-val">{fmt(currentMax)}<small>/7</small></div>
        <div className="sc-sub">After reviews</div>
      </div>
      <div className="score-cell">
        <div className="sc-label">Avg confidence</div>
        <div className="sc-val">{fmt(avgConf)}<small>%</small></div>
        <div className="sc-sub">Across claims</div>
      </div>
      <div className="score-cell">
        <div className="sc-label">Claims</div>
        <div className="sc-val">{claims.length}</div>
        <div className="sc-sub">Evidence items</div>
      </div>
      <div className="score-cell">
        <div className="sc-label">Overall conf.</div>
        <div className="sc-val">
          {report.overallConfidence != null
            ? Math.round(report.overallConfidence * 100)
            : "—"}
          {report.overallConfidence != null && <small>%</small>}
        </div>
        <div className="sc-sub">Pipeline score</div>
      </div>
    </div>
  );
}
