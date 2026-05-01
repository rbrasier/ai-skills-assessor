"use client";

import { useCallback, useEffect, useState } from "react";
import type { AdminSessionSummary, AdminStats } from "@ai-skills-assessor/shared-types";
import AdminSidebar from "@/components/admin-shell/AdminSidebar";
import AssessmentsTable from "@/components/admin-shell/AssessmentsTable";
import CallsBarChart from "@/components/admin-shell/CallsBarChart";
import OutcomesDonut from "@/components/admin-shell/OutcomesDonut";
import StatsRow from "@/components/admin-shell/StatsRow";

const PAGE_SIZE = 25;
const POLL_MS = 30_000;

type Filter = "all" | "complete" | "review" | "incomplete";

export default function AdminDashboardPage() {
  const [sessions, setSessions] = useState<AdminSessionSummary[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));

      const [sessRes, statsRes] = await Promise.all([
        fetch(`/api/admin/sessions/enriched${params.size ? `?${params}` : ""}`, { cache: "no-store" }),
        fetch("/api/admin/stats", { cache: "no-store" }),
      ]);

      if (!sessRes.ok) throw new Error(`Sessions request failed (${sessRes.status})`);
      setSessions((await sessRes.json()) as AdminSessionSummary[]);

      if (statsRes.ok) setStats((await statsRes.json()) as AdminStats);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [search, offset]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const totalCompleted = stats?.totalCalls ?? 0;
  const awaitingReview = stats?.awaitingReviewCount ?? 0;

  return (
    <div className="shell">
      <AdminSidebar />

      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Assessment Overview</span>
          <div className="sp" />
          <a href="/" className="btn btn-primary">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"/>
            </svg>
            Candidate portal
          </a>
        </div>

        <div className="page">
          <div className="page-head">
            <h1>Assessments <span className="serif">last 30 days.</span></h1>
            <p>
              {totalCompleted} total calls · {awaitingReview} awaiting review
              {loading && " · Refreshing…"}
            </p>
          </div>

          {error && (
            <div style={{ background: "var(--danger-2)", border: "1px solid var(--danger)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "var(--danger)", marginBottom: 20 }}>
              {error}
            </div>
          )}

          <StatsRow stats={stats} />

          <div className="charts">
            <CallsBarChart data={stats?.callsPerDay ?? []} />
            <OutcomesDonut buckets={stats?.outcomeBuckets ?? []} />
          </div>

          <AssessmentsTable
            sessions={sessions}
            loading={loading}
            search={search}
            onSearchChange={(v) => { setSearch(v); setOffset(0); }}
            filter={filter}
            onFilterChange={(f) => { setFilter(f); setOffset(0); }}
            canPrev={offset > 0}
            canNext={sessions.length === PAGE_SIZE}
            onPrev={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            onNext={() => setOffset(offset + PAGE_SIZE)}
          />
        </div>
      </div>
    </div>
  );
}
