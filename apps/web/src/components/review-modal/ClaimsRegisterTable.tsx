"use client";

import type { Claim } from "@ai-skills-assessor/shared-types";

interface ExpertState {
  [claimId: string]: number;
}

interface SupervisorState {
  [claimId: string]: {
    decision: "verified" | "rejected" | "flagged";
    comment: string;
  };
}

export type ClaimsRegisterSubView = "sme" | "supervisor";

interface Props {
  claims: Claim[];
  variant: "expert" | "supervisor" | "operator-read-only";
  expertState?: ExpertState;
  onExpertChange?: (claimId: string, level: number) => void;
  supervisorState?: SupervisorState;
  onSupervisorChange?: (claimId: string, decision: "verified" | "rejected" | "flagged", comment: string) => void;
  adminState?: SupervisorState;
  onAdminChange?: (claimId: string, decision: "verified" | "rejected" | "flagged", comment: string) => void;
  registerSubView: ClaimsRegisterSubView;
}

function ConfBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 75 ? "var(--ok)" : pct >= 50 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="conf-bar">
      <div className="track">
        <div className="fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="pct">{pct}%</span>
    </div>
  );
}

function LevelLadder({
  aiLevel,
  expertLevel,
  selectable,
  onSelect,
}: {
  aiLevel: number;
  expertLevel?: number | null;
  selectable?: boolean;
  onSelect?: (l: number) => void;
}) {
  const active = expertLevel ?? aiLevel;
  return (
    <div className="ladder">
      {[1, 2, 3, 4, 5, 6, 7].map((l) => {
        const isActive = l === active;
        const isAi = l === aiLevel && !expertLevel;
        const cls = [
          "rung",
          isActive ? (expertLevel ? "selected" : "achieved") : "",
          isAi && !selectable ? "achieved" : "",
          selectable ? "selectable" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <div
            key={l}
            className={cls}
            onClick={() => selectable && onSelect?.(l)}
            title={`SFIA Level ${l}`}
          >
            {l}
          </div>
        );
      })}
    </div>
  );
}

function ClaimRow({
  claim,
  variant,
  registerSubView,
  expertLevel,
  onExpertChange,
  supervisorDecision,
  supervisorComment,
  onSupervisorChange,
  adminDecision,
  adminComment,
  onAdminChange,
}: {
  claim: Claim;
  variant: "expert" | "supervisor" | "operator-read-only";
  registerSubView: ClaimsRegisterSubView;
  expertLevel?: number | null;
  onExpertChange?: (level: number) => void;
  supervisorDecision?: "verified" | "rejected" | "flagged";
  supervisorComment?: string;
  onSupervisorChange?: (decision: "verified" | "rejected" | "flagged", comment: string) => void;
  adminDecision?: "verified" | "rejected" | "flagged";
  adminComment?: string;
  onAdminChange?: (decision: "verified" | "rejected" | "flagged", comment: string) => void;
}) {
  const hideSkill = registerSubView === "supervisor";
  const displayLevel = expertLevel ?? claim.expertLevel ?? claim.level;
  const decision = supervisorDecision ?? claim.supervisorDecision;
  const adminDec = adminDecision ?? (claim.adminDecision as "verified" | "rejected" | "flagged" | undefined);

  const aiLevel = claim.level > 0 ? claim.level : 1;

  return (
    <div className="skill-detail-row" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: hideSkill ? "1fr" : "1fr 220px", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {!hideSkill && (
            <div className="sdr-top">
              <span className="sdr-name">{claim.skillName || claim.skillCode}</span>
              <span className="sdr-code">{claim.skillCode}</span>
            </div>
          )}
          {(claim.summary || claim.interpretedClaim) && (
            <div className="sdr-desc">{claim.summary || claim.interpretedClaim}</div>
          )}
          {claim.interpretedClaim && claim.summary && claim.summary !== claim.interpretedClaim && (
            <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>{claim.interpretedClaim}</div>
          )}
          {claim.verbatimQuote && (
            <div className="evidence-quote">
              &ldquo;{claim.verbatimQuote}&rdquo;
            </div>
          )}
          <ConfBar value={claim.confidence} />
        </div>

        {!hideSkill && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)" }}>
              Level {displayLevel}
              <small style={{ fontSize: 12, color: "var(--ink-4)", marginLeft: 4 }}>/ 7</small>
            </div>
            <LevelLadder
              aiLevel={aiLevel}
              expertLevel={expertLevel ?? claim.expertLevel}
              selectable={variant === "expert"}
              onSelect={onExpertChange}
            />
            {variant === "expert" && !expertLevel && (
              <div style={{ fontSize: 11, color: "var(--ink-4)" }}>Click a rung to adjust</div>
            )}
          </div>
        )}
      </div>

      {variant === "supervisor" && registerSubView === "supervisor" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--line-2)", paddingTop: 10 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>Decision:</span>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(["verified", "rejected", "flagged"] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => onSupervisorChange?.(d, supervisorComment ?? claim.supervisorComment ?? "")}
                  style={{
                    padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                    border: "1px solid",
                    borderColor: decision === d ? "var(--ok)" : "var(--line)",
                    background: decision === d ? "var(--ok-2)" : "var(--paper)",
                    color: decision === d ? "var(--ok)" : "var(--ink-3)",
                    cursor: "pointer",
                  }}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <input
            type="text"
            placeholder="Comment (required on submit for rejected)…"
            value={supervisorComment ?? claim.supervisorComment ?? ""}
            onChange={(e) => onSupervisorChange?.(
              (decision === "verified" || decision === "rejected" || decision === "flagged")
                ? decision
                : "verified",
              e.target.value,
            )}
            style={{
              background: "var(--paper)", border: "1px solid var(--line-2)",
              borderRadius: 7, padding: "7px 10px", fontSize: 13,
              color: "var(--ink)", fontFamily: "inherit", outline: "none",
            }}
          />
        </div>
      )}

      {variant === "operator-read-only" && onAdminChange && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--line-2)", paddingTop: 10 }}>
          <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Operator pre-review
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(["verified", "rejected", "flagged"] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => onAdminChange(d, adminComment ?? claim.adminComment ?? "")}
                style={{
                  padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                  border: "1px solid",
                  borderColor: adminDec === d ? "var(--accent)" : "var(--line)",
                  background: adminDec === d ? "var(--accent-2)" : "var(--paper)",
                  color: adminDec === d ? "var(--accent-ink)" : "var(--ink-3)",
                  cursor: "pointer",
                }}
              >
                {d}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Comment…"
            value={adminComment ?? claim.adminComment ?? ""}
            onChange={(e) => onAdminChange(
              adminDec ?? "verified",
              e.target.value,
            )}
            style={{
              background: "var(--paper)", border: "1px solid var(--line-2)",
              borderRadius: 7, padding: "7px 10px", fontSize: 13,
              color: "var(--ink)", fontFamily: "inherit", outline: "none",
            }}
          />
          {claim.adminActor && (
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>
              Last: {claim.adminActor}
              {claim.adminUpdatedAt ? ` · ${claim.adminUpdatedAt}` : ""}
            </div>
          )}
        </div>
      )}

      {variant === "operator-read-only" && (decision || adminDec) && !onAdminChange && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {decision && (
            <span className={`claim-badge ${decision}`}>{decision}</span>
          )}
          {claim.supervisorComment && (
            <span style={{ fontSize: 12, color: "var(--ink-3)", fontStyle: "italic" }}>
              {claim.supervisorComment}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function ClaimsRegisterTable({
  claims,
  variant,
  registerSubView,
  expertState = {},
  onExpertChange,
  supervisorState = {},
  onSupervisorChange,
  adminState = {},
  onAdminChange,
}: Props) {
  return (
    <div className="skills-table">
      <div className="st-head">
        <b>Claims register</b>
        <span style={{ fontSize: 11.5, color: "var(--ink-4)" }}>{claims.length} claims · {registerSubView}</span>
      </div>
      {claims.length === 0 ? (
        <div style={{ padding: "16px 18px", fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}>
          No claims in this view.
        </div>
      ) : (
        claims.map((claim) => (
          <ClaimRow
            key={claim.id}
            claim={claim}
            variant={variant}
            registerSubView={registerSubView}
            expertLevel={expertState[claim.id] ?? undefined}
            onExpertChange={(l) => onExpertChange?.(claim.id, l)}
            supervisorDecision={supervisorState[claim.id]?.decision}
            supervisorComment={supervisorState[claim.id]?.comment}
            onSupervisorChange={(d, c) => onSupervisorChange?.(claim.id, d, c)}
            adminDecision={adminState[claim.id]?.decision}
            adminComment={adminState[claim.id]?.comment}
            onAdminChange={onAdminChange ? (d, c) => onAdminChange(claim.id, d, c) : undefined}
          />
        ))
      )}
    </div>
  );
}

export type { ExpertState, SupervisorState };
