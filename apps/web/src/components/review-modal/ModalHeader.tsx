import type { AssessmentReport } from "@ai-skills-assessor/shared-types";

const COLORS = [
  "#e8d7c2","#d7e2d0","#d5d7e8","#e8d0d5","#e0dccf","#d0e2e2","#e8e0d0","#e2d0e8",
];

function initials(name: string | null): string {
  if (!name) return "?";
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function avatarColor(name: string | null): string {
  if (!name) return COLORS[0]!;
  const code = name.charCodeAt(0) + (name.charCodeAt(1) || 0);
  return COLORS[code % COLORS.length]!;
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" });
}

interface Props {
  report: AssessmentReport;
  onClose?: () => void;
  expertReviewUrl?: string;
  supervisorReviewUrl?: string;
}

async function copyText(label: string, text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    window.prompt(`Copy ${label}:`, text);
  }
}

export default function ModalHeader({ report, onClose, expertReviewUrl, supervisorReviewUrl }: Props) {
  const name = report.candidateName ?? report.sessionId.slice(0, 8);
  const bg = avatarColor(report.candidateName);

  return (
    <div className="modal-header">
      <div className="modal-av" style={{ background: bg, color: "#1b1a17" }}>
        {initials(report.candidateName)}
      </div>
      <div className="modal-meta">
        <div className="modal-name">{name}</div>
        <div className="modal-facts">
          <span>Session <b>{report.sessionId.slice(0, 8)}</b></span>
          <span>Generated <b>{fmt(report.reportGeneratedAt)}</b></span>
          {report.expertSubmittedAt && (
            <span>Expert reviewed <b>{fmt(report.expertSubmittedAt)}</b></span>
          )}
          {report.supervisorSubmittedAt && (
            <span>Supervisor reviewed <b>{fmt(report.supervisorSubmittedAt)}</b></span>
          )}
          {report.reportStatus && (
            <span>Status <b>{report.reportStatus.replace(/_/g, " ")}</b></span>
          )}
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8, flex: "none" }}>
        {(expertReviewUrl || supervisorReviewUrl) && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end", maxWidth: 360 }}>
            {expertReviewUrl && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                <span style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  SME review
                </span>
                <a href={expertReviewUrl} className="mono" style={{ fontSize: 11.5, wordBreak: "break-all", color: "var(--accent-ink)" }}>
                  {expertReviewUrl}
                </a>
                <button type="button" className="btn" style={{ padding: "3px 8px", fontSize: 11 }} onClick={() => void copyText("SME URL", expertReviewUrl)}>
                  Copy
                </button>
              </div>
            )}
            {supervisorReviewUrl && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                <span style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Supervisor review
                </span>
                <a href={supervisorReviewUrl} className="mono" style={{ fontSize: 11.5, wordBreak: "break-all", color: "var(--accent-ink)" }}>
                  {supervisorReviewUrl}
                </a>
                <button type="button" className="btn" style={{ padding: "3px 8px", fontSize: 11 }} onClick={() => void copyText("Supervisor URL", supervisorReviewUrl)}>
                  Copy
                </button>
              </div>
            )}
          </div>
        )}
        {onClose && (
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
