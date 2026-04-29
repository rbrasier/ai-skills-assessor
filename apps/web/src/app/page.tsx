"use client";

import { useEffect, useRef, useState } from "react";

import { CallStateDisplay } from "@/components/candidate/CallStateDisplay";
import { IntakeForm, type IntakeFormValues } from "@/components/candidate/IntakeForm";
import { createCandidate, triggerCall } from "@/lib/api-client";

type Step = "intake" | "calling";

const heroBars = Array.from({ length: 120 }, (_, i) => ({
  height: 14 + Math.abs(Math.sin(i * 0.55) * Math.cos(i * 0.17)) * 280,
}));

export default function CandidatePortalPage() {
  const [step, setStep] = useState<Step>("intake");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [dialingMethod, setDialingMethod] = useState<string | null>(null);

  const prevStepRef = useRef<Step>("intake");

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch("/api/config");
        if (res.ok) {
          const data = await res.json();
          setDialingMethod(data.dialingMethod || "browser");
        } else {
          setDialingMethod("browser");
        }
      } catch {
        setDialingMethod("browser");
      }
    };
    fetchConfig();
  }, []);

  useEffect(() => {
    if (step === "calling" && prevStepRef.current === "intake") {
      setTimeout(() => {
        document.getElementById("call-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    }
    if (step === "intake" && prevStepRef.current === "calling") {
      document.getElementById("form-section")?.scrollIntoView({ behavior: "smooth" });
    }
    prevStepRef.current = step;
  }, [step]);

  const handleIntake = async (values: IntakeFormValues) => {
    setSubmitError(null);
    try {
      const candidate = await createCandidate({
        workEmail: values.workEmail.trim(),
        firstName: values.firstName.trim(),
        lastName: values.lastName.trim(),
        employeeId: values.employeeId.trim(),
      });
      const call = await triggerCall({
        candidateId: candidate.candidateId,
        phoneNumber: values.phoneNumber?.trim() || undefined,
        dialingMethod: dialingMethod ?? undefined,
      });
      setSessionId(call.sessionId);
      setStep("calling");
    } catch (error) {
      setSubmitError((error as Error).message);
    }
  };

  const handleCancel = () => {
    setStep("intake");
    setSessionId(null);
  };

  return (
    <>
      {/* ── Nav ── */}
      <nav className="nav">
        <div className="brand">
          <div className="brand-mark">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 8h1.5" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round" />
              <path d="M5 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round" />
              <path d="M8 3v10" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round" />
              <path d="M11 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round" />
              <path d="M13.5 8H14" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <div className="brand-name">Resonant</div>
            <span className="brand-sub">Skills interview</span>
          </div>
        </div>
        <div className="nav-right">
          Need help? <a href="#">Contact support</a>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="hero">
        <div className="hero-bg" aria-hidden="true">
          {heroBars.map((bar, i) => (
            <span key={i} className="b" style={{ height: `${bar.height}px` }} suppressHydrationWarning />
          ))}
        </div>
        <div className="hero-inner">
          <div className="eyebrow">
            <span className="dot" />
            A 20-minute phone conversation — no camera, no coding test
          </div>
          <h1>
            Your skills,
            <br />
            <span className="serif">in your own words.</span>
          </h1>
          <p className="lede">
            We&apos;ll call you for a short, friendly conversation about your recent work. Our AI
            interviewer listens, asks thoughtful follow-ups, and hands a structured summary to your
            reviewing expert.
          </p>
          <button
            className="cta"
            onClick={() =>
              document
                .getElementById("form-section")
                ?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            Get started
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 5v14" />
              <path d="m6 13 6 6 6-6" />
            </svg>
          </button>
          <div className="hero-meta">
            <span>
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
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
              ~20 minutes
            </span>
            <span>
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
                <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />
              </svg>
              {dialingMethod === "browser" ? "Browser call, voice only" : "Phone call, voice only"}
            </span>
            <span>
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
                <rect x="5" y="10" width="14" height="10" rx="2" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>
              Reviewed by a human expert
            </span>
          </div>
        </div>
      </section>

      {/* ── Form section ── */}
      <section className="form-section" id="form-section">
        <div className="form-wrap">
          <div className="section-head">
            <div className="section-num">STEP 01 OF 02</div>
            <h2 className="section-title">
              A few <span className="serif">quick details.</span>
            </h2>
            <p className="section-sub">
              We use these to reach you and match your interview to the right review panel.
            </p>
          </div>
          <div className="card">
            <IntakeForm
              dialingMethod={dialingMethod}
              onSubmit={handleIntake}
              submitError={submitError}
            />
          </div>
        </div>
      </section>

      {/* ── Call section (shown after form submit) ── */}
      {step === "calling" && sessionId && (
        <section className="call-section" id="call-section">
          <div className="call-card">
            <CallStateDisplay sessionId={sessionId} onCancel={handleCancel} />
          </div>
        </section>
      )}

      {/* ── Footer ── */}
      <footer>
        <span>© 2026 Resonant · Skills interview portal</span>
        <span className="sp" />
        <a href="#">Privacy</a>
        <a href="#">Accessibility</a>
        <a href="#">Support</a>
      </footer>
    </>
  );
}
