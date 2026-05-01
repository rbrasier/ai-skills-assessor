"use client";

import { useState } from "react";
import type { AdminSessionSummary } from "@ai-skills-assessor/shared-types";
import AssessmentReviewModal from "@/components/review-modal/AssessmentReviewModal";
import type { AssessmentReport } from "@ai-skills-assessor/shared-types";

type Filter = "all" | "complete" | "review" | "incomplete";

interface Props {
  sessions: AdminSessionSummary[];
  loading?: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  filter: Filter;
  onFilterChange: (f: Filter) => void;
  onPrev?: () => void;
  onNext?: () => void;
  canPrev?: boolean;
  canNext?: boolean;
}

function statusFilter(s: AdminSessionSummary, f: Filter): boolean {
  if (f === "all") return true;
  if (f === "complete") return s.status === "completed" || s.reportStatus === "reviews_complete";
  if (f === "review") return s.reportStatus === "awaiting_expert" || s.reportStatus === "awaiting_supervisor" || s.reportStatus === "in_review";
  if (f === "incomplete") return ["failed", "cancelled", "pending"].includes(s.status);
  return true;
}

function StatusChip({ status, reportStatus }: { status: string; reportStatus: string | null }) {
  const rs = reportStatus;
  if (rs === "reviews_complete") return <span className="chip chip-ok">Reviews complete</span>;
  if (rs === "awaiting_expert" || rs === "awaiting_supervisor" || rs === "in_review")
    return <span className="chip chip-warn">{rs.replace(/_/g, " ")}</span>;
  if (status === "completed") return <span className="chip chip-ok">Completed</span>;
  if (status === "in_progress") return <span className="chip chip-accent">In progress</span>;
  if (status === "failed") return <span className="chip chip-danger">Failed</span>;
  if (status === "cancelled") return <span className="chip chip-neutral">Cancelled</span>;
  return <span className="chip chip-neutral">{status}</span>;
}

function fmt(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

function fmtDuration(secs: number): string {
  if (!secs || secs <= 0) return "—";
  return `${Math.floor(secs / 60)}:${String(Math.floor(secs % 60)).padStart(2, "0")}`;
}

export default function AssessmentsTable({
  sessions, loading, search, onSearchChange, filter, onFilterChange,
  onPrev, onNext, canPrev, canNext,
}: Props) {
  const [modalSession, setModalSession] = useState<AdminSessionSummary | null>(null);
  const [reportData, setReportData] = useState<AssessmentReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const visible = sessions.filter((s) => statusFilter(s, filter));

  async function openRow(s: AdminSessionSummary) {
    setModalSession(s);
    if (s.expertReviewToken) {
      setReportLoading(true);
      try {
        const res = await fetch(`/api/review/expert/${s.expertReviewToken}`, { cache: "no-store" });
        if (res.ok) setReportData((await res.json()) as AssessmentReport);
      } finally {
        setReportLoading(false);
      }
    } else {
      setReportData({
        sessionId: s.sessionId,
        candidateName: s.candidateName ?? null,
        expertReviewToken: s.expertReviewToken ?? null,
        supervisorReviewToken: s.supervisorReviewToken ?? null,
        overallConfidence: s.overallConfidence ?? null,
        reportStatus: s.reportStatus ?? null,
        claimsJson: [],
        reportGeneratedAt: null,
        expiresAt: null,
        expertSubmittedAt: null,
        expertReviewerName: null,
        expertReviewerEmail: null,
        supervisorSubmittedAt: null,
        supervisorReviewerName: null,
        supervisorReviewerEmail: null,
        reviewsCompletedAt: null,
      });
    }
  }

  const origin = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <>
      <div className="table-card">
        <div className="table-toolbar">
          <b>All assessments</b>
          <div className="filter-tabs">
            {(["all", "complete", "review", "incomplete"] as Filter[]).map((f) => (
              <button key={f} className={`ftab${filter === f ? " on" : ""}`} onClick={() => onFilterChange(f)}>
                {f === "all" ? "All" : f === "complete" ? "Complete" : f === "review" ? "Awaiting review" : "Incomplete"}
              </button>
            ))}
          </div>
          <div className="sp" />
          <div className="search-box">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
            </svg>
            <input
              type="text"
              placeholder="Search name, email, skill…"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
            />
          </div>
        </div>

        <div className="thead">
          <div>Candidate</div>
          <div>Email</div>
          <div>Date</div>
          <div>Duration</div>
          <div>Top skills</div>
          <div>Max level</div>
          <div>Confidence</div>
          <div />
        </div>

        {loading ? (
          <div style={{ padding: "24px 16px", fontSize: 13, color: "var(--ink-4)" }}>Loading…</div>
        ) : visible.length === 0 ? (
          <div style={{ padding: "24px 16px", fontSize: 13, color: "var(--ink-4)", textAlign: "center" }}>
            No sessions match the current filters.
          </div>
        ) : (
          visible.map((s) => (
            <div key={s.sessionId} className="trow" onClick={() => void openRow(s)}>
              <div style={{ fontWeight: 500 }}>{s.candidateName ?? s.candidateEmail.split("@")[0]}</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{s.candidateEmail}</div>
              <div style={{ fontSize: 12 }}>{fmt(s.createdAt)}</div>
              <div style={{ fontSize: 12, fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{fmtDuration(s.durationSeconds)}</div>
              <div>
                <div className="skill-pills">
                  {(s.topSkillCodes ?? []).slice(0, 4).map((code) => (
                    <span key={code} className="sp-pill">{code}</span>
                  ))}
                </div>
              </div>
              <div>
                {s.maxSfiaLevel != null ? (
                  <span style={{ fontWeight: 600 }}>{s.maxSfiaLevel}<small style={{ fontWeight: 400, color: "var(--ink-4)" }}>/7</small></span>
                ) : (
                  <StatusChip status={s.status} reportStatus={s.reportStatus ?? null} />
                )}
              </div>
              <div>
                {s.overallConfidence != null ? (
                  <div className="conf-bar">
                    <div className="track">
                      <div className="fill" style={{
                        width: `${Math.round(s.overallConfidence * 100)}%`,
                        background: s.overallConfidence >= 0.75 ? "var(--ok)" : s.overallConfidence >= 0.5 ? "var(--warn)" : "var(--danger)"
                      }} />
                    </div>
                    <span className="pct">{Math.round(s.overallConfidence * 100)}%</span>
                  </div>
                ) : "—"}
              </div>
              <div>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                  <path d="M9 18l6-6-6-6"/>
                </svg>
              </div>
            </div>
          ))
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
        <button className="btn" disabled={!canPrev} onClick={onPrev}>← Previous</button>
        <button className="btn" disabled={!canNext} onClick={onNext}>Next →</button>
      </div>

      {modalSession && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) { setModalSession(null); setReportData(null); } }}>
          {reportLoading || !reportData ? (
            <div className="modal" style={{ padding: 48, textAlign: "center", color: "var(--ink-4)" }}>Loading report…</div>
          ) : (
            <AssessmentReviewModal
              variant="operator-read-only"
              report={reportData}
              onClose={() => { setModalSession(null); setReportData(null); }}
              expertReviewUrl={modalSession.expertReviewToken ? `${origin}/review/expert/${modalSession.expertReviewToken}` : undefined}
              supervisorReviewUrl={modalSession.supervisorReviewToken ? `${origin}/review/supervisor/${modalSession.supervisorReviewToken}` : undefined}
            />
          )}
        </div>
      )}
    </>
  );
}
