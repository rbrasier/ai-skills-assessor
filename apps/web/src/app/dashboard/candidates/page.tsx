"use client";

import { useCallback, useEffect, useState } from "react";
import type { AdminSessionSummary, CandidateDirectoryRow } from "@ai-skills-assessor/shared-types";
import AdminSidebar from "@/components/admin-shell/AdminSidebar";
import AssessmentReviewModal from "@/components/review-modal/AssessmentReviewModal";
import { mapVoiceEngineClaim, mapVoiceEngineReport } from "@/lib/map-assessment-report";
import type { AssessmentReport } from "@ai-skills-assessor/shared-types";

export default function CandidatesPage() {
  const [rows, setRows] = useState<CandidateDirectoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [restrictOpen, setRestrictOpen] = useState<CandidateDirectoryRow | null>(null);
  const [restrictData, setRestrictData] = useState<{
    noRestrictions: boolean;
    cooldownOverrideGrantedAt: string | null;
    cooldownOverrideExpiresAt: string | null;
    auditLog: Array<{ action: string; grantedBy: string; expiresAt?: string | null; reason?: string | null; createdAt: string }>;
  } | null>(null);
  const [grantDays, setGrantDays] = useState(7);
  const [grantReason, setGrantReason] = useState("");
  const [actor, setActor] = useState("Admin");
  const [modalSession, setModalSession] = useState<AdminSessionSummary | null>(null);
  const [reportData, setReportData] = useState<AssessmentReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/candidates", { cache: "no-store" });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setRows((await res.json()) as CandidateDirectoryRow[]);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const origin = typeof window !== "undefined" ? window.location.origin : "";

  async function openRestrictions(r: CandidateDirectoryRow) {
    setRestrictOpen(r);
    const res = await fetch(`/api/admin/candidates/${encodeURIComponent(r.email)}/restrictions`, { cache: "no-store" });
    if (res.ok) {
      const d = (await res.json()) as {
        no_restrictions: boolean;
        cooldown_override_granted_at: string | null;
        cooldown_override_expires_at: string | null;
        audit_log: Array<{ action: string; granted_by: string; expires_at?: string | null; reason?: string | null; created_at: string }>;
      };
      setRestrictData({
        noRestrictions: d.no_restrictions,
        cooldownOverrideGrantedAt: d.cooldown_override_granted_at,
        cooldownOverrideExpiresAt: d.cooldown_override_expires_at,
        auditLog: (d.audit_log ?? []).map((a) => ({
          action: a.action,
          grantedBy: a.granted_by,
          expiresAt: a.expires_at ?? null,
          reason: a.reason ?? null,
          createdAt: a.created_at,
        })),
      });
    } else {
      setRestrictData(null);
    }
  }

  async function grantOverride() {
    if (!restrictOpen) return;
    const res = await fetch(`/api/admin/candidates/${encodeURIComponent(restrictOpen.email)}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        grantedBy: actor,
        expiresInDays: grantDays,
        reason: grantReason || null,
      }),
    });
    if (res.ok) void openRestrictions(restrictOpen);
  }

  async function revokeOverride() {
    if (!restrictOpen) return;
    const res = await fetch(
      `/api/admin/candidates/${encodeURIComponent(restrictOpen.email)}/override?revokedBy=${encodeURIComponent(actor)}`,
      { method: "DELETE" },
    );
    if (res.ok) void openRestrictions(restrictOpen);
  }

  async function toggleNoRestrictions(enabled: boolean) {
    if (!restrictOpen) return;
    await fetch(`/api/admin/candidates/${encodeURIComponent(restrictOpen.email)}/no-restrictions`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, updatedBy: actor }),
    });
    void openRestrictions(restrictOpen);
  }

  async function openSession(s: AdminSessionSummary) {
    setModalSession(s);
    setReportLoading(true);
    try {
      const adminRes = await fetch(`/api/admin/sessions/${encodeURIComponent(s.sessionId)}/report`, { cache: "no-store" });
      if (adminRes.ok) {
        const raw = (await adminRes.json()) as Record<string, unknown>;
        setReportData(mapVoiceEngineReport(raw));
        return;
      }
      if (s.expertReviewToken) {
        const res = await fetch(`/api/review/expert/${s.expertReviewToken}`, { cache: "no-store" });
        if (res.ok) {
          setReportData((await res.json()) as AssessmentReport);
          return;
        }
      }
      setReportData(null);
    } finally {
      setReportLoading(false);
    }
  }

  async function handleAdminClaimsSave(payload: {
    adminActor: string;
    claims: Array<{ id: string; adminDecision?: "verified" | "rejected" | "flagged"; adminComment?: string }>;
  }) {
    if (!modalSession) return;
    const res = await fetch(`/api/admin/sessions/${encodeURIComponent(modalSession.sessionId)}/claims`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Save failed (${res.status})`);
    const updated = (await res.json()) as { claims: Record<string, unknown>[] };
    setReportData((r) => {
      if (!r) return r;
      return { ...r, claimsJson: updated.claims.map((c) => mapVoiceEngineClaim(c)) };
    });
  }

  return (
    <div className="shell">
      <AdminSidebar />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Candidates</span>
          <div className="sp" />
          <a href="/dashboard" className="btn">← Dashboard</a>
        </div>
        <div className="page">
          <div className="page-head">
            <h1>Candidate directory</h1>
            <p>Most recent activity first · expand rows to see call history</p>
          </div>
          {error && (
            <div style={{ background: "var(--danger-2)", border: "1px solid var(--danger)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "var(--danger)", marginBottom: 20 }}>
              {error}
            </div>
          )}
          <div className="table-card">
            <div className="table-toolbar">
              <b>Candidates</b>
              <div className="sp" />
              <button type="button" className="btn" onClick={() => void load()} disabled={loading}>Refresh</button>
            </div>
            <div className="thead" style={{ gridTemplateColumns: "28px 2fr 1fr 0.8fr 1fr 120px 36px" }}>
              <div />
              <div>Name</div>
              <div>Email</div>
              <div>Calls</div>
              <div>Last call</div>
              <div>Settings</div>
              <div />
            </div>
            {loading ? (
              <div style={{ padding: 24, color: "var(--ink-4)" }}>Loading…</div>
            ) : rows.map((r) => (
              <div key={r.email}>
                <div
                  className="trow"
                  style={{ gridTemplateColumns: "28px 2fr 1fr 0.8fr 1fr 120px 36px", cursor: "default" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    className="btn-ghost"
                    style={{ padding: 4 }}
                    aria-label="Expand"
                    onClick={() => setExpanded((x) => ({ ...x, [r.email]: !x[r.email] }))}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" style={{ transform: expanded[r.email] ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>
                      <path d="M9 18l6-6-6-6"/>
                    </svg>
                  </button>
                  <div style={{ fontWeight: 500 }}>{r.firstName} {r.lastName}</div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{r.email}</div>
                  <div>{r.totalCalls}</div>
                  <div style={{ fontSize: 12 }}>{r.lastCallAt ? new Date(r.lastCallAt).toLocaleString("en-AU", { dateStyle: "medium" }) : "—"}</div>
                  <div>
                    <button type="button" className="btn" onClick={() => void openRestrictions(r)}>Call settings</button>
                  </div>
                  <div />
                </div>
                {expanded[r.email] && (
                  <div style={{ background: "var(--paper-2)", borderBottom: "1px solid var(--line-2)" }}>
                    {r.sessions.map((s) => (
                      <div
                        key={s.sessionId}
                        className="trow"
                        style={{ gridTemplateColumns: "28px 2fr 1fr 0.8fr 1fr 120px 36px", paddingLeft: 36, cursor: "pointer" }}
                        onClick={() => void openSession(s)}
                      >
                        <div />
                        <div style={{ fontWeight: 500 }}>{s.candidateName ?? "Session"}</div>
                        <div className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>{s.sessionId.slice(0, 8)}…</div>
                        <div>{s.status}</div>
                        <div style={{ fontSize: 12 }}>{new Date(s.createdAt).toLocaleDateString("en-AU")}</div>
                        <div />
                        <div>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M9 18l6-6-6-6"/></svg>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {restrictOpen && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) { setRestrictOpen(null); setRestrictData(null); } }}>
          <div className="modal" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-meta" style={{ flex: 1 }}>
                <div className="modal-name">Call settings</div>
                <div className="modal-facts">
                  <span><b>{restrictOpen.email}</b></span>
                </div>
              </div>
              <button type="button" className="modal-close" onClick={() => { setRestrictOpen(null); setRestrictData(null); }} aria-label="Close">×</button>
            </div>
            <div className="modal-body">
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, color: "var(--ink-3)" }}>Actor name (audit)</label>
                <input value={actor} onChange={(e) => setActor(e.target.value)} style={{ display: "block", width: "100%", marginTop: 4, padding: 8, borderRadius: 6, border: "1px solid var(--line)" }} />
              </div>
              {restrictData && (
                <>
                  <p style={{ fontSize: 13, color: "var(--ink-3)" }}>
                    Cooldown override: {restrictData.cooldownOverrideExpiresAt
                      ? `active until ${new Date(restrictData.cooldownOverrideExpiresAt).toLocaleString("en-AU")}`
                      : "none"}
                  </p>
                  <p style={{ fontSize: 13 }}>No restrictions flag: <b>{restrictData.noRestrictions ? "on" : "off"}</b></p>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                    <input type="number" min={1} max={365} value={grantDays} onChange={(e) => setGrantDays(Number(e.target.value))} style={{ width: 72, padding: 6 }} />
                    <input placeholder="Reason" value={grantReason} onChange={(e) => setGrantReason(e.target.value)} style={{ flex: 1, minWidth: 120, padding: 6 }} />
                    <button type="button" className="btn btn-primary" onClick={() => void grantOverride()}>Grant bypass</button>
                    <button type="button" className="btn" onClick={() => void revokeOverride()}>Revoke bypass</button>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <button type="button" className="btn" onClick={() => void toggleNoRestrictions(!restrictData.noRestrictions)}>
                      Toggle no-restrictions
                    </button>
                  </div>
                  <div style={{ marginTop: 16, maxHeight: 200, overflow: "auto", fontSize: 12, color: "var(--ink-3)" }}>
                    {(restrictData.auditLog ?? []).map((a, i) => (
                      <div key={i} style={{ borderTop: "1px solid var(--line-2)", padding: "6px 0" }}>
                        {a.createdAt} — {a.action} by {a.grantedBy}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {modalSession && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) { setModalSession(null); setReportData(null); } }}>
          {reportLoading || !reportData ? (
            <div className="modal" style={{ padding: 48, textAlign: "center", color: "var(--ink-4)" }}>Loading…</div>
          ) : (
            <AssessmentReviewModal
              variant="operator-read-only"
              report={reportData}
              onClose={() => { setModalSession(null); setReportData(null); }}
              expertReviewUrl={modalSession.expertReviewToken ? `${origin}/review/expert/${modalSession.expertReviewToken}` : undefined}
              supervisorReviewUrl={modalSession.supervisorReviewToken ? `${origin}/review/supervisor/${modalSession.supervisorReviewToken}` : undefined}
              showReviewLinksInHeader
              onAdminClaimsSave={handleAdminClaimsSave}
            />
          )}
        </div>
      )}
    </div>
  );
}
