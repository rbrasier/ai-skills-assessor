"use client";

import { useEffect, useMemo, useState } from "react";

import type { AssessmentStatus, CallStatusResponse } from "@ai-skills-assessor/shared-types";

interface CallStateDisplayProps {
  sessionId: string;
  onCancel?: () => void;
}

const POLL_MS = 2000;

export function CallStateDisplay({ sessionId, onCancel }: CallStateDisplayProps) {
  const [status, setStatus] = useState<CallStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const res = await fetch(`/api/assessment/${sessionId}/status`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`Status request failed (${res.status})`);
        }
        const body = (await res.json()) as CallStatusResponse;
        if (cancelled) return;
        setStatus(body);
        setError(null);

        if (body.status !== "completed" && body.status !== "failed" && body.status !== "cancelled") {
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

  const label = labelFor(status?.status ?? "pending");
  const description = descriptionFor(
    status?.status ?? "pending",
    status?.failureReason,
    status?.dialingMethod,
  );

  const handleCancel = async () => {
    if (!onCancel) return;
    setCancelling(true);
    try {
      await fetch(`/api/assessment/${sessionId}/cancel`, { method: "POST" });
      onCancel();
    } finally {
      setCancelling(false);
    }
  };

  return (
    <section className="space-y-8">
      <header className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
          Step 02 of 02
        </p>
        <h2 className="text-3xl font-bold text-slate-900">{label}</h2>
        <p className="text-sm text-slate-600">{description}</p>
      </header>

      {status?.dialingMethod === "browser" && status?.browserJoinUrl ? (
        <LiveKitIframe joinUrl={status.browserJoinUrl} />
      ) : null}

      <StateVisual
        status={status?.status ?? "pending"}
        durationSeconds={status?.durationSeconds ?? 0}
        dialingMethod={status?.dialingMethod}
      />

      {error ? (
        <p role="alert" className="text-sm font-medium text-amber-600">
          Connection hiccup — retrying…
        </p>
      ) : null}

      {status?.status === "completed" ? null : (
        <button
          type="button"
          onClick={handleCancel}
          disabled={cancelling}
          className="w-full rounded-full border border-slate-200 bg-white py-3 text-sm font-semibold uppercase tracking-wider text-slate-700 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {cancelling ? "Cancelling…" : "Cancel"}
        </button>
      )}
    </section>
  );
}

function labelFor(s: AssessmentStatus): string {
  switch (s) {
    case "pending":
    case "dialling":
      return "DIALLING";
    case "in_progress":
      return "CALL IN PROGRESS";
    case "completed":
      return "INTERVIEW COMPLETE";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
  }
}

function descriptionFor(
  s: AssessmentStatus,
  failureReason?: string | null,
  dialingMethod?: string | null,
): string {
  switch (s) {
    case "pending":
    case "dialling":
      if (dialingMethod === "browser") {
        return "Open the link above in this browser (or another on the same device). Microphone access is required. Noa will start once you are connected.";
      }
      return "Your phone should ring in a moment. Answer when it does — caller ID will show Resonant · Noa.";
    case "in_progress":
      return "Relax and speak naturally. Noa will guide the conversation through three short phases — there are no wrong answers.";
    case "completed":
      return "Thank you. Your interview will now be analysed and reviewed before the results are available. You'll hear back by email, usually within 2 working days.";
    case "failed":
      return failureReason ?? "Something went wrong with the call. Please try again.";
    case "cancelled":
      return "Call cancelled. Refresh to start a new assessment.";
  }
}

function StateVisual({
  status,
  durationSeconds,
  dialingMethod,
}: {
  status: AssessmentStatus;
  durationSeconds: number;
  dialingMethod?: string | null;
}) {
  const timer = useMemo(() => formatDuration(durationSeconds), [durationSeconds]);

  if (status === "completed") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-slate-100 py-12 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-teal-600 text-3xl text-white">
          ✓
        </div>
        <p className="text-sm font-medium text-slate-700">Interview complete</p>
      </div>
    );
  }

  if (status === "in_progress") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl bg-slate-900 py-12 text-center text-white">
        <Waveform />
        <p className="text-3xl font-mono tabular-nums">{timer}</p>
      </div>
    );
  }

  if (status === "failed" || status === "cancelled") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-slate-100 py-12 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-300 text-3xl text-slate-700">
          !
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-slate-100 py-12 text-center">
      <div className="flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-teal-500 text-3xl text-white">
        {dialingMethod === "browser" ? "🌐" : "📞"}
      </div>
      <p className="text-sm font-medium text-slate-700">
        {dialingMethod === "browser" ? "Waiting for you to join…" : "Calling your phone…"}
      </p>
    </div>
  );
}

function Waveform() {
  const bars = Array.from({ length: 18 }, (_, i) => i);
  return (
    <div className="flex items-end gap-1 text-teal-300">
      {bars.map((i) => (
        <span
          key={i}
          className="inline-block w-1 animate-pulse rounded-full bg-current"
          style={{
            height: `${12 + ((i * 7) % 20)}px`,
            animationDelay: `${i * 80}ms`,
            animationDuration: "1200ms",
          }}
        />
      ))}
    </div>
  );
}

function LiveKitIframe({ joinUrl }: { joinUrl: string }) {
  return (
    <div className="aspect-video w-full overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
      <iframe
        src={joinUrl}
        title="Interview Call"
        allow="microphone; camera; usb"
        sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-top-navigation-by-user-activation"
        className="h-full w-full border-none"
      />
    </div>
  );
}

function formatDuration(total: number): string {
  if (!Number.isFinite(total) || total < 0) total = 0;
  const totalSeconds = Math.floor(total);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}
