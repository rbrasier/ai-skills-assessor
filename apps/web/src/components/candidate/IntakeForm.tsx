"use client";

import { useState } from "react";

export interface IntakeFormValues {
  firstName: string;
  lastName: string;
  workEmail: string;
  employeeId: string;
  phoneNumber: string;
}

interface IntakeFormProps {
  onSubmit: (values: IntakeFormValues) => Promise<void>;
  submitError?: string | null;
}

const EMPTY: IntakeFormValues = {
  firstName: "",
  lastName: "",
  workEmail: "",
  employeeId: "",
  phoneNumber: "",
};

export function IntakeForm({ onSubmit, submitError }: IntakeFormProps) {
  const [values, setValues] = useState<IntakeFormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof IntakeFormValues, string>>>({});
  const [submitting, setSubmitting] = useState(false);

  const set = <K extends keyof IntakeFormValues>(key: K, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const validate = (): boolean => {
    const next: Partial<Record<keyof IntakeFormValues, string>> = {};
    if (!values.firstName.trim()) next.firstName = "Required";
    if (!values.lastName.trim()) next.lastName = "Required";
    if (!values.workEmail.includes("@")) next.workEmail = "Invalid email";
    if (!values.employeeId.trim()) next.employeeId = "Required";
    // Accept +format with spaces, hyphens, parentheses; require ≥10 characters.
    const phoneRegex = /^\+?[\d\s\-().]{10,}$/;
    if (!phoneRegex.test(values.phoneNumber.trim())) next.phoneNumber = "Invalid phone";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    try {
      await onSubmit(values);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <header className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
          Step 01 of 02
        </p>
        <h2 className="text-3xl font-bold text-slate-900">
          A few <span className="italic text-teal-600">quick details.</span>
        </h2>
        <p className="text-sm text-slate-600">
          We use these to reach you and match your interview to the right review panel.
        </p>
      </header>

      <div className="space-y-5">
        <Field
          label="First name"
          name="firstName"
          placeholder="Amara"
          value={values.firstName}
          onChange={(v) => set("firstName", v)}
          error={errors.firstName}
          autoComplete="given-name"
        />
        <Field
          label="Last name"
          name="lastName"
          placeholder="Okafor"
          value={values.lastName}
          onChange={(v) => set("lastName", v)}
          error={errors.lastName}
          autoComplete="family-name"
        />
        <Field
          label="Work email"
          name="workEmail"
          type="email"
          placeholder="amara@helixrobotics.com"
          value={values.workEmail}
          onChange={(v) => set("workEmail", v)}
          error={errors.workEmail}
          autoComplete="email"
        />
        <Field
          label="Employee ID"
          name="employeeId"
          placeholder="HLX-00481"
          value={values.employeeId}
          onChange={(v) => set("employeeId", v)}
          error={errors.employeeId}
        />
        <Field
          label="Phone number"
          name="phoneNumber"
          type="tel"
          placeholder="+44 7700 900118"
          value={values.phoneNumber}
          onChange={(v) => set("phoneNumber", v)}
          error={errors.phoneNumber}
          autoComplete="tel"
        />
      </div>

      {submitError ? (
        <p role="alert" className="text-sm font-medium text-red-600">
          {submitError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-full bg-slate-900 py-3 text-sm font-semibold uppercase tracking-wider text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Starting…" : "Start the call"}
      </button>

      <p className="text-xs leading-relaxed text-slate-500">
        By starting, you agree to the call being recorded and analysed for this assessment.
      </p>
    </form>
  );
}

interface FieldProps {
  label: string;
  name: string;
  type?: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  autoComplete?: string;
}

function Field({
  label,
  name,
  type = "text",
  placeholder,
  value,
  onChange,
  error,
  autoComplete,
}: FieldProps) {
  const id = `intake-${name}`;
  return (
    <div className="space-y-1">
      <label
        htmlFor={id}
        className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
      >
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`w-full rounded-xl border bg-white px-4 py-3 text-sm text-slate-900 shadow-sm transition focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 ${
          error ? "border-red-400" : "border-slate-200"
        }`}
      />
      {error ? (
        <p id={`${id}-error`} className="text-xs font-medium text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
