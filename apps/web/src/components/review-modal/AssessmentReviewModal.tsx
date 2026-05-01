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
  /** For operator: copy-link helpers */
  expertReviewUrl?: string;
  supervisorReviewUrl?: string;
  /** Callbacks for expert/supervisor submit */
  onExpertSubmit?: (payload: {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; expertLevel: number }>;
  }) => Promise<void>;
  onSupervisorSubmit?: (payload: {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; supervisorDecision: "verified" | "rejected"; supervisorComment?: string }>;
  }) => Promise<void>;
}

export default function AssessmentReviewModal({
  variant,
  report,
  onClose,
  expertReviewUrl,
  supervisorReviewUrl,
  onExpertSubmit,
  onSupervisorSubmit,
}: AssessmentReviewModalProps) {
  const [tab, setTab] = useState<"claims" | "transcript">("claims");

  // Expert state
  const [expertState, setExpertState] = useState<ExpertState>({});
  const [identity, setIdentity] = useState<ReviewerIdentity>({ fullName: "", email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Supervisor state
  const [supervisorState, setSupervisorState] = useState<SupervisorState>({});

  const claims = report.claimsJson ?? [];

  function handleExpertLevelChange(claimId: string, level: number) {
    setExpertState((s) => ({ ...s, [claimId]: level }));
  }

  function handleSupervisorChange(claimId: string, decision: "verified" | "rejected", comment: string) {
    setSupervisorState((s) => ({ ...s, [claimId]: { decision, comment } }));
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
        const claimsPayload = claims.map((c) => ({
          id: c.id,
          supervisorDecision: supervisorState[c.id]?.decision ?? c.supervisorDecision ?? "verified",
          supervisorComment: supervisorState[c.id]?.comment || c.supervisorComment || undefined,
        }));
        await onSupervisorSubmit({
          reviewerFullName: identity.fullName,
          reviewerEmail: identity.email,
          claims: claimsPayload as Array<{ id: string; supervisorDecision: "verified" | "rejected"; supervisorComment?: string }>,
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

  const identityValid = Object.keys(validateIdentity(identity)).length === 0;
  const canSubmit = identityValid && !submitting && !submitted;

  const transcript = (report as unknown as { transcriptJson?: unknown })?.transcriptJson;

  return (
    <div className="modal">
      <ModalHeader report={report} onClose={onClose} />

      <div className="modal-tabs">
        <button className={`mtab ${tab === "claims" ? "on" : ""}`} onClick={() => setTab("claims")}>
          Claims register <span className="tc">{claims.length}</span>
        </button>
        <button className={`mtab ${tab === "transcript" ? "on" : ""}`} onClick={() => setTab("transcript")}>
          Transcript
        </button>
      </div>

      <div className="modal-body">
        <ScoreStrip report={report} />
        <AiSummaryPanel />

        {tab === "claims" && (
          <ClaimsRegisterTable
            claims={claims}
            variant={variant}
            expertState={expertState}
            onExpertChange={handleExpertLevelChange}
            supervisorState={supervisorState}
            onSupervisorChange={handleSupervisorChange}
          />
        )}
        {tab === "transcript" && (
          <TranscriptPanel transcriptJson={transcript as { turns?: Array<{ speaker: string; text: string; timestamp?: string | number }> } | null} />
        )}

        {variant === "operator-read-only" && (expertReviewUrl || supervisorReviewUrl) && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {expertReviewUrl && (
              <button
                type="button"
                className="btn"
                onClick={() => void navigator.clipboard.writeText(expertReviewUrl)}
              >
                Copy expert review URL
              </button>
            )}
            {supervisorReviewUrl && (
              <button
                type="button"
                className="btn"
                onClick={() => void navigator.clipboard.writeText(supervisorReviewUrl)}
              >
                Copy supervisor review URL
              </button>
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
