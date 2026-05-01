import type { AdminStats } from "@ai-skills-assessor/shared-types";

interface Props {
  stats: AdminStats | null;
}

export default function StatsRow({ stats }: Props) {
  if (!stats) {
    return (
      <div className="stats">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="stat">
            <div className="stat-label" style={{ background: "var(--paper-2)", borderRadius: 4, height: 10, width: 80 }} />
            <div className="stat-val" style={{ background: "var(--paper-2)", borderRadius: 4, height: 28, width: 60, marginTop: 8 }} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="stats">
      <div className="stat">
        <div className="stat-label">Total calls</div>
        <div className="stat-val">{stats.totalCalls}</div>
      </div>
      <div className="stat">
        <div className="stat-label">Avg duration</div>
        <div className="stat-val">{stats.avgDurationMinutes}<small>min</small></div>
      </div>
      <div className="stat">
        <div className="stat-label">Completion rate</div>
        <div className="stat-val">{stats.completionRatePct}<small>%</small></div>
      </div>
      <div className="stat">
        <div className="stat-label">Awaiting review</div>
        <div className="stat-val">{stats.awaitingReviewCount}<small>reports</small></div>
      </div>
      <div className="stat">
        <div className="stat-label">Avg SFIA level</div>
        <div className="stat-val">{stats.avgSfiaLevel || "—"}<small>/7</small></div>
      </div>
    </div>
  );
}
