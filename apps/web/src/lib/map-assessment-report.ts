/** Map voice-engine snake_case report JSON to camelCase AssessmentReport for the web app. */

export function mapVoiceEngineClaim(c: Record<string, unknown>) {
  return {
    id: String(c.id ?? ""),
    sessionId: c.session_id != null ? String(c.session_id) : undefined,
    verbatimQuote: String(c.verbatim_quote ?? ""),
    interpretedClaim: String(c.interpreted_claim ?? ""),
    summary: String(c.summary ?? ""),
    claimType: String(c.claim_type ?? "sme"),
    skillCode: String(c.sfia_skill_code ?? c.skill_code ?? ""),
    skillName: String(c.sfia_skill_name ?? c.skill_name ?? ""),
    level: typeof c.sfia_level === "number" ? c.sfia_level : Number(c.level ?? 0),
    confidence: typeof c.confidence === "number" ? c.confidence : Number(c.confidence ?? 0),
    reasoning: c.reasoning != null ? String(c.reasoning) : undefined,
    expertLevel: c.expert_level != null ? Number(c.expert_level) : null,
    supervisorDecision: (c.supervisor_decision as string | null | undefined) ?? null,
    supervisorComment: (c.supervisor_comment as string | null | undefined) ?? null,
    adminDecision: (c.admin_decision as string | null | undefined) ?? null,
    adminComment: (c.admin_comment as string | null | undefined) ?? null,
    adminActor: (c.admin_actor as string | null | undefined) ?? null,
    adminUpdatedAt: (c.admin_updated_at as string | null | undefined) ?? null,
  };
}

export function mapVoiceEngineReport(raw: Record<string, unknown>) {
  const claims = Array.isArray(raw.claims_json)
    ? raw.claims_json.map((c: Record<string, unknown>) => mapVoiceEngineClaim(c))
    : [];

  const holistic = Array.isArray(raw.holistic_assessment_json)
    ? raw.holistic_assessment_json.map((h: Record<string, unknown>) => ({
        skillCode: String(h.skill_code ?? ""),
        skillName: String(h.skill_name ?? ""),
        estimatedLevel: Number(h.estimated_level ?? 0),
        prominence: Number(h.prominence ?? 0),
        evidenceSummary: String(h.evidence_summary ?? ""),
      }))
    : [];

  return {
    sessionId: String(raw.session_id ?? ""),
    candidateName: (raw.candidate_name as string | null | undefined) ?? null,
    expertReviewToken: (raw.expert_review_token as string | null | undefined) ?? null,
    supervisorReviewToken: (raw.supervisor_review_token as string | null | undefined) ?? null,
    overallConfidence: raw.overall_confidence != null ? Number(raw.overall_confidence) : null,
    reportStatus: (raw.report_status as string | null | undefined) ?? null,
    claimsJson: claims,
    holisticAssessmentJson: holistic,
    transcriptJson: (raw.transcript_json as object | null | undefined) ?? null,
    reportGeneratedAt: (raw.report_generated_at as string | null | undefined) ?? null,
    expiresAt: (raw.expires_at as string | null | undefined) ?? null,
    expertSubmittedAt: (raw.expert_submitted_at as string | null | undefined) ?? null,
    expertReviewerName: (raw.expert_reviewer_name as string | null | undefined) ?? null,
    expertReviewerEmail: (raw.expert_reviewer_email as string | null | undefined) ?? null,
    supervisorSubmittedAt: (raw.supervisor_submitted_at as string | null | undefined) ?? null,
    supervisorReviewerName: (raw.supervisor_reviewer_name as string | null | undefined) ?? null,
    supervisorReviewerEmail: (raw.supervisor_reviewer_email as string | null | undefined) ?? null,
    reviewsCompletedAt: (raw.reviews_completed_at as string | null | undefined) ?? null,
  };
}
