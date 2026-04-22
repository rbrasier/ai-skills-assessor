"use client";

import { useState, useEffect } from "react";

import { CallStateDisplay } from "@/components/candidate/CallStateDisplay";
import { IntakeForm, type IntakeFormValues } from "@/components/candidate/IntakeForm";
import { createCandidate, triggerCall } from "@/lib/api-client";

type Step = "intake" | "calling";

export default function CandidatePortalPage() {
  const [step, setStep] = useState<Step>("intake");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [dialingMethod, setDialingMethod] = useState<string | null>(null);

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
        phoneNumber: values.phoneNumber.trim() || undefined,
        dialingMethod,
      });
      setSessionId(call.sessionId);
      setStep("calling");
    } catch (error) {
      setSubmitError((error as Error).message);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f4f1ea] px-4 py-10">
      <div className="w-full max-w-md space-y-10">
        <div className="space-y-3 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.4em] text-slate-500">
            Resonant
          </p>
          <h1 className="text-4xl font-bold text-slate-900">
            Your skills,
            <br />
            <span className="italic text-teal-600">in your own words.</span>
          </h1>
          <p className="text-sm text-slate-600">
            A 20-minute phone conversation — no camera, no coding test.
          </p>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm ring-1 ring-slate-100">
          {step === "intake" ? (
            <IntakeForm onSubmit={handleIntake} submitError={submitError} />
          ) : sessionId ? (
            <CallStateDisplay
              sessionId={sessionId}
              onCancel={() => {
                setStep("intake");
                setSessionId(null);
              }}
            />
          ) : null}
        </div>
      </div>
    </main>
  );
}
