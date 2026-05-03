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
  dialingMethod: string | null;
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

export function IntakeForm({ dialingMethod, onSubmit, submitError }: IntakeFormProps) {
  const [values, setValues] = useState<IntakeFormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof IntakeFormValues, string>>>({});
  const [submitting, setSubmitting] = useState(false);

  const isBrowser = dialingMethod === "browser";

  const set = <K extends keyof IntakeFormValues>(key: K, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const validate = (): boolean => {
    const next: Partial<Record<keyof IntakeFormValues, string>> = {};
    if (!values.firstName.trim()) next.firstName = "Required";
    if (!values.lastName.trim()) next.lastName = "Required";
    if (!values.workEmail.includes("@")) next.workEmail = "Invalid email";
    if (!values.employeeId.trim()) next.employeeId = "Required";
    if (!isBrowser) {
      const phoneRegex = /^\+?[\d\s\-().]{10,}$/;
      if (!phoneRegex.test(values.phoneNumber.trim())) next.phoneNumber = "Invalid phone";
    }
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
    <form onSubmit={handleSubmit} noValidate>
      <div className="field-grid">
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
          className="full"
        />
        {isBrowser ? (
          <Field
            label="Employee ID"
            name="employeeId"
            placeholder="HLX-00481"
            value={values.employeeId}
            onChange={(v) => set("employeeId", v)}
            error={errors.employeeId}
            className="full"
          />
        ) : (
          <>
            <Field
              label="Employee ID"
              name="employeeId"
              placeholder="HLX-00481"
              value={values.employeeId}
              onChange={(v) => set("employeeId", v)}
              error={errors.employeeId}
            />
            <PhoneField
              value={values.phoneNumber}
              onChange={(v) => set("phoneNumber", v)}
              error={errors.phoneNumber}
            />
          </>
        )}
      </div>

      <div className="form-actions">
        {submitError ? (
          <p role="alert" className="submit-error">
            {submitError}
          </p>
        ) : null}

        <button type="submit" disabled={submitting} className="btn-start">
          {submitting ? (
            "Starting…"
          ) : (
            <>
              {isBrowser ? "Start the call (browser)" : "Start the call"}
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />
              </svg>
            </>
          )}
        </button>

        <p className="consent">
          By starting, you agree to the call being recorded and analysed for this assessment.{" "}
          <a href="#">Read our privacy notice.</a>
        </p>
        <p className="consent" style={{ marginTop: "8px" }}>
          <strong>Please keep this browser window in focus</strong> during the call — focus
          changes are logged. All claims made during the assessment will be verified by your
          management and a qualified SME reviewer.
        </p>
      </div>
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
  className?: string;
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
  className,
}: FieldProps) {
  const id = `intake-${name}`;
  return (
    <div className={`field${className ? ` ${className}` : ""}`}>
      <label htmlFor={id}>{label}</label>
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
        className={`input${error ? " has-error" : ""}`}
      />
      {error ? (
        <span id={`${id}-error`} className="field-error">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function PhoneField({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  error?: string;
}) {
  return (
    <div className="field">
      <label htmlFor="intake-phoneNumber">Phone number</label>
      <div className="input-wrap">
        <span className="prefix">+</span>
        <input
          id="intake-phoneNumber"
          name="phoneNumber"
          type="tel"
          placeholder="44 7700 900118"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="tel"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "intake-phoneNumber-error" : undefined}
          className={`input with-prefix${error ? " has-error" : ""}`}
        />
      </div>
      {error ? (
        <span id="intake-phoneNumber-error" className="field-error">
          {error}
        </span>
      ) : null}
    </div>
  );
}
