"use client";

import { useState } from "react";
import type { AssessmentReport } from "@ai-skills-assessor/shared-types";
import AiSummaryPanel from "./AiSummaryPanel";
import ClaimsRegisterTable, { type ExpertState, type SupervisorState } from "./ClaimsRegisterTable";
import ModalHeader from "./ModalHeader";
import ReviewerIdentityForm, { validateIdentity, type ReviewerIdentity } from "./ReviewerIdentityForm";
import ScoreStrip from "./ScoreStrip";
import TranscriptPanel from "./TranscriptPanel";

export type ModalVariant = "expert" | "supervisor" | "operator-read-only";

export interface AssessmentReviewModalProps {
  variant: ModalVariant;
  report: AssessmentReport;
  onClose?: () => void;
  /** For operator: copy-link helpers (only when variant is operator) */
  expertReviewUrl?: string;
  supervisorReviewUrl?: string;
  showReviewLinksInHeader?: boolean;
  /** Callbacks for expert/supervisor submit */
  onExpertSubmit?: (payload: {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; expertLevel: number }>;
  }) => Promise<void>;
  onSupervisorSubmit?: (payload: {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; supervisorDecision: "verified" | "rejected" | "flagged"; supervisorComment?: string }>;
  }) => Promise<void>;
  /** Operator: persist admin verify/reject/flag */
  onAdminClaimsSave?: (payload: {
    adminActor: string;
    claims: Array<{ id: string; adminDecision?: "verified" | "rejected" | "flagged"; adminComment?: string }>;
  }) => Promise<void>;
}

export default function AssessmentReviewModal({
  variant,
  report,
  onClose,
  expertReviewUrl,
  supervisorReviewUrl,
  showReviewLinksInHeader = false,
  onExpertSubmit,
  onSupervisorSubmit,
  onAdminClaimsSave,
}: AssessmentReviewModalProps) {
  const [tab, setTab] = useState<"sme" | "supervisor" | "transcript">("sme");

  // Expert state
  const [expertState, setExpertState] = useState<ExpertState>({});
  const [identity, setIdentity] = useState<ReviewerIdentity>({ fullName: "", email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Supervisor state
  const [supervisorState, setSupervisorState] = useState<SupervisorState>({});

  // Admin operator state
  const [adminActor, setAdminActor] = useState("");
  const [adminState, setAdminState] = useState<SupervisorState>({});
  const [adminSaving, setAdminSaving] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);

  const claims = report.claimsJson ?? [];
  const holistic = report.holisticAssessmentJson ?? [];

  const smeClaims = claims.filter((c) => (c.claimType ?? "sme") === "sme");
  const supervisorClaims = claims.filter((c) => (c.claimType ?? "sme") === "supervisor");

  function buildAiSummaryText(): string {
    if (!holistic.length) return "";
    const lines = holistic
      .slice()
      .sort((a, b) => b.prominence - a.prominence)
      .slice(0, 8)
      .map(
        (h) =>
          `${h.skillCode} (${h.skillName}) — estimated L${h.estimatedLevel} ` +
          `(weight ${Math.round(h.prominence * 100)}%): ${h.evidenceSummary}`,
      );
    return lines.join("\n\n");
  }

  function handleExpertLevelChange(claimId: string, level: number) {
    setExpertState((s) => ({ ...s, [claimId]: level }));
  }

  function handleSupervisorChange(claimId: string, decision: "verified" | "rejected" | "flagged", comment: string) {
    setSupervisorState((s) => ({ ...s, [claimId]: { decision, comment } }));
  }

  function handleAdminChange(claimId: string, decision: "verified" | "rejected" | "flagged", comment: string) {
    setAdminState((s) => ({ ...s, [claimId]: { decision, comment } }));
  }

  async function handleSubmit() {
    const identityErrs = validateIdentity(identity);
    if (Object.keys(identityErrs).length > 0) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      if (variant === "expert" && onExpertSubmit) {
        const claimsPayload = claims.map((c) => ({
          id: c.id,
          expertLevel: expertState[c.id] ?? c.expertLevel ?? c.level,
        }));
        await onExpertSubmit({
          reviewerFullName: identity.fullName,
          reviewerEmail: identity.email,
          claims: claimsPayload,
        });
        setSubmitted(true);
      } else if (variant === "supervisor" && onSupervisorSubmit) {
        const claimsPayload = claims.map((c) => {
          const raw = supervisorState[c.id]?.decision ?? c.supervisorDecision;
          const decision: "verified" | "rejected" | "flagged" =
            raw === "verified" || raw === "rejected" || raw === "flagged" ? raw : "verified";
          return {
            id: c.id,
            supervisorDecision: decision,
            supervisorComment: supervisorState[c.id]?.comment ?? c.supervisorComment ?? "",
          };
        });
        await onSupervisorSubmit({
          reviewerFullName: identity.fullName,
          reviewerEmail: identity.email,
          claims: claimsPayload,
        });
        setSubmitted(true);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Submission failed. Please try again.";
      setSubmitError(msg.includes("409") || msg.toLowerCase().includes("already")
        ? "You have already submitted your review. No changes were made."
        : msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAdminSave() {
    if (!onAdminClaimsSave) return;
    const actor = adminActor.trim();
    if (!actor) {
      setAdminError("Enter your name or initials for the audit log.");
      return;
    }
    setAdminSaving(true);
    setAdminError(null);
    try {
      const payloadClaims = claims
        .map((c) => {
          const st = adminState[c.id];
          if (!st) return null;
          return {
            id: c.id,
            adminDecision: st.decision,
            adminComment: st.comment,
          };
        })
        .filter((x): x is { id: string; adminDecision: "verified" | "rejected" | "flagged"; adminComment: string } => x != null);
      if (payloadClaims.length === 0) {
        setAdminError("Change at least one claim before saving.");
        setAdminSaving(false);
        return;
      }
      await onAdminClaimsSave({ adminActor: actor, claims: payloadClaims });
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setAdminSaving(false);
    }
  }

  const identityValid = Object.keys(validateIdentity(identity)).length === 0;
  const canSubmit = identityValid && !submitting && !submitted;

  const transcript = report.transcriptJson;

  return (
    <div className="modal">
      <ModalHeader
        report={report}
        onClose={onClose}
        expertReviewUrl={showReviewLinksInHeader ? expertReviewUrl : undefined}
        supervisorReviewUrl={showReviewLinksInHeader ? supervisorReviewUrl : undefined}
      />

      <div className="modal-body">
        <ScoreStrip report={report} />
        <AiSummaryPanel summary={buildAiSummaryText() || null} />

        <div className="modal-tabs">
          <button className={`mtab ${tab === "sme" ? "on" : ""}`} onClick={() => setTab("sme")}>
            SME claims <span className="tc">{smeClaims.length}</span>
          </button>
          <button className={`mtab ${tab === "supervisor" ? "on" : ""}`} onClick={() => setTab("supervisor")}>
            Supervisor claims <span className="tc">{supervisorClaims.length}</span>
          </button>
          <button className={`mtab ${tab === "transcript" ? "on" : ""}`} onClick={() => setTab("transcript")}>
            Transcript
          </button>
        </div>

        {tab === "sme" && (
          <ClaimsRegisterTable
            claims={smeClaims}
            variant={variant}
            expertState={expertState}
            onExpertChange={handleExpertLevelChange}
            supervisorState={supervisorState}
            onSupervisorChange={handleSupervisorChange}
            adminState={adminState}
            onAdminChange={handleAdminChange}
            registerSubView={variant === "supervisor" ? "supervisor" : "sme"}
          />
        )}
        {tab === "supervisor" && (
          <ClaimsRegisterTable
            claims={supervisorClaims}
            variant={variant}
            expertState={expertState}
            onExpertChange={handleExpertLevelChange}
            supervisorState={supervisorState}
            onSupervisorChange={handleSupervisorChange}
            adminState={adminState}
            onAdminChange={handleAdminChange}
            registerSubView="supervisor"
          />
        )}
        {tab === "transcript" && (
          <TranscriptPanel transcriptJson={transcript} />
        )}

        {variant === "operator-read-only" && onAdminClaimsSave && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginTop: 12 }}>
            <input
              type="text"
              placeholder="Your name (audit log)"
              value={adminActor}
              onChange={(e) => setAdminActor(e.target.value)}
              style={{
                flex: "1 1 200px",
                minWidth: 160,
                background: "var(--paper)",
                border: "1px solid var(--line-2)",
                borderRadius: 7,
                padding: "8px 10px",
                fontSize: 13,
              }}
            />
            <button type="button" className="btn btn-primary" disabled={adminSaving} onClick={() => void handleAdminSave()}>
              {adminSaving ? "Saving…" : "Save operator notes"}
            </button>
            {adminError && (
              <span style={{ fontSize: 12, color: "var(--danger)", width: "100%" }}>{adminError}</span>
            )}
          </div>
        )}
      </div>

      {(variant === "expert" || variant === "supervisor") && (
        <div className="review-footer">
          {submitted ? (
            <div style={{ flex: 1, fontSize: 13.5, color: "var(--ok)", fontWeight: 500 }}>
              Review submitted successfully. Thank you.
            </div>
          ) : (
            <>
              <ReviewerIdentityForm value={identity} onChange={setIdentity} disabled={submitting} />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                {submitError && (
                  <div style={{ fontSize: 12, color: "var(--danger)", maxWidth: 260, textAlign: "right" }}>
                    {submitError}
                  </div>
                )}
                <button
                  type="button"
                  className="btn-save"
                  disabled={!canSubmit}
                  onClick={() => void handleSubmit()}
                >
                  {submitting ? "Saving…" : "Save review"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
