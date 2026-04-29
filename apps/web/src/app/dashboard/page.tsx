"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { AssessmentStatus, SessionSummary } from "@ai-skills-assessor/shared-types";
import { listSessions } from "@/lib/api-client";

const STATUSES: AssessmentStatus[] = [
  "pending",
  "dialling",
  "in_progress",
  "completed",
  "failed",
  "cancelled",
];

const PAGE_SIZE = 25;
const POLL_MS = 5000;

export default function AdminDashboardPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<AssessmentStatus | "">("");
  const [emailFilter, setEmailFilter] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listSessions({
        status: statusFilter || undefined,
        email: emailFilter.trim() || undefined,
        since: since || undefined,
        until: until || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setSessions(items);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, emailFilter, since, until, offset]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => {
      void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const canPrev = offset > 0;
  const canNext = sessions.length === PAGE_SIZE;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-8">
      <header className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Assessment sessions</h1>
          <p className="text-sm text-slate-600">
            Read-only monitoring of candidate self-service calls. Auto-refreshes every 5 s.
          </p>
        </div>
        {loading ? <span className="text-xs text-slate-500">Loading…</span> : null}
      </header>

      <Filters
        statusFilter={statusFilter}
        setStatusFilter={(v) => {
          setStatusFilter(v);
          setOffset(0);
        }}
        emailFilter={emailFilter}
        setEmailFilter={(v) => {
          setEmailFilter(v);
          setOffset(0);
        }}
        since={since}
        setSince={(v) => {
          setSince(v);
          setOffset(0);
        }}
        until={until}
        setUntil={(v) => {
          setUntil(v);
          setOffset(0);
        }}
      />

      {error ? (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm font-medium text-red-700">
          {error}
        </p>
      ) : null}

      <SessionsTable sessions={sessions} />

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => canPrev && setOffset(Math.max(0, offset - PAGE_SIZE))}
          disabled={!canPrev}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-700 disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => canNext && setOffset(offset + PAGE_SIZE)}
          disabled={!canNext}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-700 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </main>
  );
}

interface FiltersProps {
  statusFilter: AssessmentStatus | "";
  setStatusFilter: (value: AssessmentStatus | "") => void;
  emailFilter: string;
  setEmailFilter: (value: string) => void;
  since: string;
  setSince: (value: string) => void;
  until: string;
  setUntil: (value: string) => void;
}

function Filters({
  statusFilter,
  setStatusFilter,
  emailFilter,
  setEmailFilter,
  since,
  setSince,
  until,
  setUntil,
}: FiltersProps) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-100 sm:grid-cols-2 lg:grid-cols-4">
      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-600">
        Status
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as AssessmentStatus | "")}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-normal text-slate-900"
        >
          <option value="">Any</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-600">
        Candidate email
        <input
          type="email"
          value={emailFilter}
          onChange={(e) => setEmailFilter(e.target.value)}
          placeholder="amara@helixrobotics.com"
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-normal text-slate-900"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-600">
        Since
        <input
          type="datetime-local"
          value={since}
          onChange={(e) => setSince(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-normal text-slate-900"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-600">
        Until
        <input
          type="datetime-local"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-normal text-slate-900"
        />
      </label>
    </div>
  );
}

function SessionsTable({ sessions }: { sessions: SessionSummary[] }) {
  const rows = useMemo(() => sessions, [sessions]);

  if (rows.length === 0) {
    return (
      <div className="rounded-xl bg-white p-8 text-center text-sm text-slate-500 shadow-sm ring-1 ring-slate-100">
        No sessions match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-100">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50">
          <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            <th className="px-4 py-3">Session</th>
            <th className="px-4 py-3">Candidate email</th>
            <th className="px-4 py-3">Phone</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Duration</th>
            <th className="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((s) => (
            <tr key={s.sessionId} className="text-sm text-slate-700">
              <td className="px-4 py-3 font-mono text-xs text-slate-500">{s.sessionId.slice(0, 8)}</td>
              <td className="px-4 py-3">{s.candidateEmail}</td>
              <td className="px-4 py-3 font-mono text-xs">{s.phoneNumber}</td>
              <td className="px-4 py-3">
                <StatusBadge status={s.status} />
              </td>
              <td className="px-4 py-3 font-mono text-xs">{formatDuration(s.durationSeconds)}</td>
              <td className="px-4 py-3 text-xs text-slate-500">{formatCreatedAt(s.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: AssessmentStatus }) {
  const tone: Record<AssessmentStatus, string> = {
    pending: "bg-slate-100 text-slate-700",
    dialling: "bg-amber-100 text-amber-800",
    in_progress: "bg-sky-100 text-sky-800",
    completed: "bg-emerald-100 text-emerald-800",
    failed: "bg-red-100 text-red-800",
    cancelled: "bg-slate-200 text-slate-700",
  };
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wider ${tone[status]}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return "—";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatCreatedAt(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}
