import type { OutcomeBucket } from "@ai-skills-assessor/shared-types";

interface Props {
  buckets: OutcomeBucket[];
}

export default function OutcomesDonut({ buckets }: Props) {
  const total = buckets.reduce((s, b) => s + b.count, 0);

  if (total === 0) {
    return (
      <div className="chart-card">
        <div className="chart-head"><b>Call outcomes</b></div>
        <div style={{ height: 120, display: "flex", alignItems: "center", color: "var(--ink-4)", fontSize: 13 }}>No data yet</div>
      </div>
    );
  }

  const R = 54, cx = 70, cy = 70, sw = 14;
  let angle = -Math.PI / 2;
  const paths: string[] = [];

  buckets.forEach((b) => {
    const a = (b.count / total) * 2 * Math.PI;
    const x1 = cx + R * Math.cos(angle);
    const y1 = cy + R * Math.sin(angle);
    const x2 = cx + R * Math.cos(angle + a);
    const y2 = cy + R * Math.sin(angle + a);
    const large = a > Math.PI ? 1 : 0;
    paths.push(
      `<path d="M${x1.toFixed(2)} ${y1.toFixed(2)} A${R} ${R} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}" fill="none" stroke="${b.color}" stroke-width="${sw}" stroke-linecap="round"/>`,
    );
    angle += a + 0.04;
  });

  return (
    <div className="chart-card">
      <div className="chart-head"><b>Call outcomes</b><span className="sub">this month</span></div>
      <div className="donut-wrap">
        <svg width="140" height="140" viewBox="0 0 140 140" dangerouslySetInnerHTML={{ __html: `
          <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="var(--paper-2)" stroke-width="${sw}"/>
          ${paths.join("")}
          <text x="${cx}" y="${cy - 4}" text-anchor="middle" font-size="22" font-weight="500" fill="var(--ink)" font-family="Inter Tight,sans-serif" letter-spacing="-1">${total}</text>
          <text x="${cx}" y="${cy + 14}" text-anchor="middle" font-size="10" fill="var(--ink-4)" font-family="Inter Tight,sans-serif">calls</text>
        ` }} />
        <div className="donut-legend">
          {buckets.map((b) => (
            <div key={b.label} className="legend-row">
              <div className="legend-dot" style={{ background: b.color }} />
              <span>{b.label}</span>
              <span className="legend-val">{b.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
