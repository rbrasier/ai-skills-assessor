import type { DailyCallCount } from "@ai-skills-assessor/shared-types";

interface Props {
  data: DailyCallCount[];
}

export default function CallsBarChart({ data }: Props) {
  const max = Math.max(...data.map((d) => d.count), 1);
  const visible = data.slice(-27);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="chart-card">
      <div className="chart-head">
        <b>Calls per day</b>
        <span className="sub">last 30 days</span>
      </div>
      {visible.length === 0 ? (
        <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-4)", fontSize: 13 }}>
          No data yet
        </div>
      ) : (
        <div className="bar-chart">
          {visible.map((d) => {
            const pct = ((d.count / max) * 100).toFixed(1);
            const isToday = d.date === today;
            const dayNum = new Date(d.date).getDate();
            return (
              <div key={d.date} className="col" title={`${d.date}: ${d.count} calls`}>
                <div className="bar-wrap">
                  <div className={`bar${isToday ? " accent" : ""}`} style={{ height: `${pct}%` }} />
                </div>
                <div className="xl">{dayNum % 7 === 0 || isToday ? dayNum : ""}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
