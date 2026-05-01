"use client";

import { useEffect, useState } from "react";
import type { AssessmentReport, ReviewSaveResponse } from "@ai-skills-assessor/shared-types";
import AssessmentReviewModal from "@/components/review-modal/AssessmentReviewModal";

interface PageProps {
  params: { token: string };
}

export default function ExpertReviewPage({ params }: PageProps) {
  const { token } = params;
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    fetch(`/api/review/expert/${token}`, { cache: "no-store" })
      .then(async (res) => {
        if (res.status === 404) { setNotFound(true); return; }
        if (!res.ok) throw new Error(`Failed: ${res.status}`);
        setReport((await res.json()) as AssessmentReport);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(payload: {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; expertLevel: number }>;
  }) {
    const res = await fetch(`/api/review/expert/${token}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 409) throw new Error("409: already submitted");
    if (!res.ok) throw new Error(`Save failed (${res.status})`);
    const updated = (await res.json()) as ReviewSaveResponse;
    setReport((r) => r ? { ...r, reportStatus: updated.reportStatus, claimsJson: updated.claims } : r);
  }

  if (loading) {
    return (
      <div className="review-host" style={{ alignItems: "center" }}>
        <div style={{ color: "var(--ink-4)", fontSize: 14 }}>Loading assessment…</div>
      </div>
    );
  }

  if (notFound || !report) {
    return (
      <div className="review-host" style={{ alignItems: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 48, fontWeight: 500, color: "var(--ink-3)", letterSpacing: "-0.04em" }}>404</div>
          <div style={{ fontSize: 16, color: "var(--ink-3)", marginTop: 8 }}>Review link not found or has expired.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="review-host">
      <AssessmentReviewModal
        variant="expert"
        report={report}
        onExpertSubmit={handleSubmit}
      />
    </div>
  );
}
