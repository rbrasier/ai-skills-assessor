"use client";

import type { Claim } from "@ai-skills-assessor/shared-types";

interface ExpertState {
  [claimId: string]: number; // chosen level 1-7
}

interface SupervisorState {
  [claimId: string]: {
    decision: "verified" | "rejected";
    comment: string;
  };
}

interface Props {
  claims: Claim[];
  variant: "expert" | "supervisor" | "operator-read-only";
  expertState?: ExpertState;
  onExpertChange?: (claimId: string, level: number) => void;
  supervisorState?: SupervisorState;
  onSupervisorChange?: (claimId: string, decision: "verified" | "rejected", comment: string) => void;
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
  expertLevel,
  onExpertChange,
  supervisorDecision,
  supervisorComment,
  onSupervisorChange,
}: {
  claim: Claim;
  variant: "expert" | "supervisor" | "operator-read-only";
  expertLevel?: number | null;
  onExpertChange?: (level: number) => void;
  supervisorDecision?: "verified" | "rejected";
  supervisorComment?: string;
  onSupervisorChange?: (decision: "verified" | "rejected", comment: string) => void;
}) {
  const displayLevel = expertLevel ?? claim.expertLevel ?? claim.level;
  const decision = supervisorDecision ?? claim.supervisorDecision;

  return (
    <div className="skill-detail-row" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 220px", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="sdr-top">
            <span className="sdr-name">{claim.skillName || claim.skillCode}</span>
            <span className="sdr-code">{claim.skillCode}</span>
          </div>
          {claim.interpretedClaim && (
            <div className="sdr-desc">{claim.interpretedClaim}</div>
          )}
          {claim.verbatimQuote && (
            <div className="evidence-quote">
              &ldquo;{claim.verbatimQuote}&rdquo;
            </div>
          )}
          <ConfBar value={claim.confidence} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)" }}>
            Level {displayLevel}
            <small style={{ fontSize: 12, color: "var(--ink-4)", marginLeft: 4 }}>/ 7</small>
          </div>
          <LevelLadder
            aiLevel={claim.level}
            expertLevel={expertLevel ?? claim.expertLevel}
            selectable={variant === "expert"}
            onSelect={onExpertChange}
          />
          {variant === "expert" && !expertLevel && (
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>Click a rung to adjust</div>
          )}
          {variant === "expert" && expertLevel && (
            <div style={{ fontSize: 11, color: "var(--accent-ink)" }}>
              AI: {claim.level} → Expert: {expertLevel}
            </div>
          )}
        </div>
      </div>

      {variant === "supervisor" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--line-2)", paddingTop: 10 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>Expert level:</span>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{displayLevel}</span>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              <button
                type="button"
                onClick={() => onSupervisorChange?.("verified", supervisorComment ?? claim.supervisorComment ?? "")}
                style={{
                  padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                  border: "1px solid",
                  borderColor: decision === "verified" ? "var(--ok)" : "var(--line)",
                  background: decision === "verified" ? "var(--ok-2)" : "var(--paper)",
                  color: decision === "verified" ? "var(--ok)" : "var(--ink-3)",
                  cursor: "pointer",
                }}
              >
                Verify
              </button>
              <button
                type="button"
                onClick={() => onSupervisorChange?.("rejected", supervisorComment ?? claim.supervisorComment ?? "")}
                style={{
                  padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                  border: "1px solid",
                  borderColor: decision === "rejected" ? "var(--danger)" : "var(--line)",
                  background: decision === "rejected" ? "var(--danger-2)" : "var(--paper)",
                  color: decision === "rejected" ? "var(--danger)" : "var(--ink-3)",
                  cursor: "pointer",
                }}
              >
                Reject
              </button>
            </div>
          </div>
          <input
            type="text"
            placeholder="Optional comment…"
            value={supervisorComment ?? claim.supervisorComment ?? ""}
            onChange={(e) => onSupervisorChange?.(
              decision === "verified" || decision === "rejected" ? decision : "verified",
              e.target.value
            )}
            style={{
              background: "var(--paper)", border: "1px solid var(--line-2)",
              borderRadius: 7, padding: "7px 10px", fontSize: 13,
              color: "var(--ink)", fontFamily: "inherit", outline: "none",
            }}
          />
        </div>
      )}

      {variant === "operator-read-only" && decision && (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span
            className={`claim-badge ${decision}`}
          >
            {decision}
          </span>
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
  expertState = {},
  onExpertChange,
  supervisorState = {},
  onSupervisorChange,
}: Props) {
  return (
    <div className="skills-table">
      <div className="st-head">
        <b>Claims register</b>
        <span style={{ fontSize: 11.5, color: "var(--ink-4)" }}>{claims.length} claims</span>
      </div>
      {claims.length === 0 ? (
        <div style={{ padding: "16px 18px", fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}>
          No claims extracted yet.
        </div>
      ) : (
        claims.map((claim) => (
          <ClaimRow
            key={claim.id}
            claim={claim}
            variant={variant}
            expertLevel={expertState[claim.id] ?? undefined}
            onExpertChange={(l) => onExpertChange?.(claim.id, l)}
            supervisorDecision={supervisorState[claim.id]?.decision}
            supervisorComment={supervisorState[claim.id]?.comment}
            onSupervisorChange={(d, c) => onSupervisorChange?.(claim.id, d, c)}
          />
        ))
      )}
    </div>
  );
}

export type { ExpertState, SupervisorState };
