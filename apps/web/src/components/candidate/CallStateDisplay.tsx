"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AssessmentStatus, CallStatusResponse } from "@ai-skills-assessor/shared-types";

interface CallStateDisplayProps {
  sessionId: string;
  onCancel?: () => void;
}

const POLL_MS = 2000;

type BadgeState = "dialling" | "connected" | "finished";

function getBadgeState(status: AssessmentStatus): BadgeState {
  if (status === "in_progress") return "connected";
  if (status === "completed") return "finished";
  return "dialling";
}

async function postFocusEvent(sessionId: string, phase: string, durationMs: number) {
  try {
    await fetch(`/api/assessment/${sessionId}/focus-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phase, durationMs }),
    });
  } catch {
    // Non-critical — best-effort telemetry
  }
}

function sendCancelBeacon(sessionId: string, terminationReason: string) {
  const url = `/api/assessment/${sessionId}/cancel`;
  const data = JSON.stringify({ termination_reason: terminationReason });
  // sendBeacon is fire-and-forget and survives page unload
  if (navigator.sendBeacon) {
    const blob = new Blob([data], { type: "application/json" });
    navigator.sendBeacon(url, blob);
  }
}

function getBadgeClass(
  badgeIndex: number,
  activeIndex: number,
): "is-active" | "is-complete" | "" {
  if (badgeIndex < activeIndex) return "is-complete";
  if (badgeIndex === activeIndex) return "is-active";
  return "";
}

const BADGE_ORDER: BadgeState[] = ["dialling", "connected", "finished"];
const BADGE_LABELS = ["Dialling", "Connected", "Finished"];

export function CallStateDisplay({ sessionId, onCancel }: CallStateDisplayProps) {
  const [status, setStatus] = useState<CallStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  // Track the current assessment phase so focus events are tagged correctly.
  // Derived from status polling; defaults to "unknown" until the call connects.
  const currentPhaseRef = useRef<string>("unknown");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const res = await fetch(`/api/assessment/${sessionId}/status`, { cache: "no-store" });
        if (!res.ok) throw new Error(`Status request failed (${res.status})`);
        const body = (await res.json()) as CallStatusResponse;
        if (cancelled) return;
        setStatus(body);
        setError(null);
        const terminal =
          body.status === "completed" ||
          body.status === "failed" ||
          body.status === "cancelled" ||
          body.status === "user_ended";
        if (!terminal) {
          timer = setTimeout(poll, POLL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message);
        timer = setTimeout(poll, POLL_MS);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId]);

  // ── Focus / visibility monitoring ───────────────────────────────
  const focusLostAtRef = useRef<number | null>(null);

  useEffect(() => {
    const currentStatus = status?.status ?? "pending";
    const isLive = currentStatus === "in_progress";
    if (!isLive) return;

    const handleHidden = () => {
      if (document.visibilityState === "hidden") {
        focusLostAtRef.current = Date.now();
      } else if (focusLostAtRef.current !== null) {
        const durationMs = Date.now() - focusLostAtRef.current;
        focusLostAtRef.current = null;
        void postFocusEvent(sessionId, currentPhaseRef.current, durationMs);
      }
    };

    document.addEventListener("visibilitychange", handleHidden);
    return () => document.removeEventListener("visibilitychange", handleHidden);
  }, [sessionId, status?.status]);

  // ── Browser-close beacon ─────────────────────────────────────────
  // Fires when the candidate closes the tab or navigates away mid-call.
  useEffect(() => {
    const currentStatus = status?.status ?? "pending";
    const isLive =
      currentStatus === "in_progress" ||
      currentStatus === "dialling" ||
      currentStatus === "pending";
    if (!isLive) return;

    const handleUnload = () => {
      sendCancelBeacon(sessionId, "browser_closed");
    };

    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, [sessionId, status?.status]);

  const currentStatus = status?.status ?? "pending";
  const badgeState = getBadgeState(currentStatus);
  const badgeIndex = BADGE_ORDER.indexOf(badgeState);

  const handleCancel = useCallback(async () => {
    if (!onCancel) return;
    setCancelling(true);
    try {
      await fetch(`/api/assessment/${sessionId}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ termination_reason: "user_ended" }),
      });
      onCancel();
    } finally {
      setCancelling(false);
    }
  }, [sessionId, onCancel]);

  const isTerminal =
    currentStatus === "completed" ||
    currentStatus === "failed" ||
    currentStatus === "cancelled" ||
    currentStatus === "user_ended";

  return (
    <>
      <div className="section-num">STEP 02 OF 02</div>

      {/* Badge progression */}
      <div className="badges">
        {BADGE_LABELS.map((label, i) => (
          <Fragment key={label}>
            {i > 0 && <div key={`sep-${i}`} className="badge-sep" />}
            <div key={label} className={`badge ${getBadgeClass(i, badgeIndex)}`}>
              <span className="badge-dot" />
              {label}
            </div>
          </Fragment>
        ))}
      </div>

      {/* LiveKit embed for browser calls */}
      {status?.dialingMethod === "browser" && status?.browserJoinUrl && !isTerminal ? (
        <div className="livekit-embed">
          <iframe
            src={status.browserJoinUrl}
            title="Interview Call"
            allow="microphone; autoplay"
          />
        </div>
      ) : null}

      {/* Visual indicator */}
      <CallVisual status={currentStatus} durationSeconds={status?.durationSeconds ?? 0} />

      {/* Status label + value */}
      <StatusText status={currentStatus} dialingMethod={status?.dialingMethod} />

      {/* Sub description */}
      <CallSubText
        status={currentStatus}
        failureReason={status?.failureReason}
        dialingMethod={status?.dialingMethod}
      />

      {error ? (
        <p className="connection-error">Connection hiccup — retrying…</p>
      ) : null}

      {/* Finish actions */}
      {currentStatus === "completed" ? (
        <div className="finish-actions">
          {onCancel && (
            <button className="btn-secondary" onClick={onCancel}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 10.5 12 3l9 7.5" />
                <path d="M5 9.5V21h14V9.5" />
              </svg>
              Return to start
            </button>
          )}
          <span className="finish-note">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 12l5 5L20 6" />
            </svg>
            You can close this window — we&apos;ll email the outcome.
          </span>
        </div>
      ) : null}

      {/* Cancel button (hidden when terminal) */}
      {!isTerminal ? (
        <button
          className="btn-cancel"
          onClick={handleCancel}
          disabled={cancelling}
        >
          {cancelling ? "Cancelling…" : "Cancel"}
        </button>
      ) : null}
    </>
  );
}

function CallVisual({
  status,
  durationSeconds,
}: {
  status: AssessmentStatus;
  durationSeconds: number;
}) {
  const waveLiveRef = useRef<HTMLDivElement>(null);
  const timer = useMemo(() => formatDuration(durationSeconds), [durationSeconds]);

  useEffect(() => {
    if (status !== "in_progress") return;
    const container = waveLiveRef.current;
    if (!container) return;
    let t = 0;
    const animate = () => {
      const bars = container.querySelectorAll<HTMLSpanElement>(".wb");
      bars.forEach((bar, i) => {
        const r = Math.sin(i * 0.5 + t * 0.3) * 0.5 + 0.5;
        const r2 = Math.sin(i * 0.15 - t * 0.2) * 0.5 + 0.5;
        bar.style.height = Math.max(4, (r * 0.6 + r2 * 0.4) * 62) + "px";
      });
      t++;
    };
    animate();
    const interval = setInterval(animate, 90);
    return () => clearInterval(interval);
  }, [status]);

  if (status === "completed") {
    return (
      <div className="call-visual">
        <div className="check-big">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M5 12l5 5L20 6" />
          </svg>
        </div>
      </div>
    );
  }

  if (status === "in_progress") {
    return (
      <div className="call-visual">
        <div>
          <div className="wave-live" ref={waveLiveRef}>
            {Array.from({ length: 38 }, (_, i) => (
              <span key={i} className="wb" />
            ))}
          </div>
          <p
            style={{
              textAlign: "center",
              marginTop: "16px",
              fontFamily: "var(--font-jetbrains-mono, monospace)",
              fontSize: "28px",
              fontWeight: 500,
              letterSpacing: "-0.02em",
              color: "var(--ink)",
            }}
          >
            {timer}
          </p>
        </div>
      </div>
    );
  }

  if (status === "failed" || status === "cancelled" || status === "user_ended") {
    return (
      <div className="call-visual">
        <div className="error-circle">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
        </div>
      </div>
    );
  }

  return (
    <div className="call-visual">
      <div className="phone-ring">
        <svg
          width="42"
          height="42"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />
        </svg>
      </div>
    </div>
  );
}

function StatusText({
  status,
  dialingMethod,
}: {
  status: AssessmentStatus;
  dialingMethod?: string | null;
}) {
  const label = labelFor(status);
  const isSerif = status === "completed";
  const value = valueFor(status, dialingMethod);

  return (
    <>
      <div className="call-status-text">{label}</div>
      <div className={`call-status-val${isSerif ? " serif-style" : ""}`}>{value}</div>
    </>
  );
}

function labelFor(s: AssessmentStatus): string {
  switch (s) {
    case "pending":
    case "dialling":
      return "Dialling";
    case "in_progress":
      return "Call in progress";
    case "completed":
      return "Interview complete";
    case "failed":
      return "Call failed";
    case "cancelled":
    case "user_ended":
      return "Cancelled";
    default:
      return "";
  }
}

function valueFor(s: AssessmentStatus, dialingMethod?: string | null): string {
  switch (s) {
    case "pending":
    case "dialling":
      return dialingMethod === "browser" ? "Browser call" : "Your phone…";
    case "in_progress":
      return "";
    case "completed":
      return "Thank you";
    case "failed":
      return "Error";
    case "cancelled":
    case "user_ended":
      return "Cancelled";
    default:
      return "";
  }
}

function CallSubText({
  status,
  failureReason,
  dialingMethod,
}: {
  status: AssessmentStatus;
  failureReason?: string | null;
  dialingMethod?: string | null;
}) {
  let content: React.ReactNode;

  switch (status) {
    case "pending":
    case "dialling":
      if (dialingMethod === "browser") {
        content =
          "Open the link above in this browser. Microphone access is required. Noa will start once you are connected.";
      } else {
        content = (
          <>
            Your phone should ring in a moment. Answer when it does — caller ID will show{" "}
            <b>Resonant · Noa</b>.
          </>
        );
      }
      break;
    case "in_progress":
      content =
        "Relax and speak naturally. Noa will guide the conversation through three short phases — there are no wrong answers.";
      break;
    case "completed":
      content = (
        <>
          Your interview will now be <b>analysed and reviewed</b> before the results are available.
          You&apos;ll hear back by email, usually within 2 working days.
        </>
      );
      break;
    case "failed":
      content = failureReason ?? "Something went wrong with the call. Please try again.";
      break;
    case "cancelled":
    case "user_ended":
      content = "Call ended. Return to start a new assessment.";
      break;
  }

  return <p className="call-sub">{content}</p>;
}

function formatDuration(total: number): string {
  if (!Number.isFinite(total) || total < 0) total = 0;
  const s = Math.floor(total);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
  }
  return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
}
