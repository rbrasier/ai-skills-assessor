"use client";

import { useState } from "react";

export interface ReviewerIdentity {
  fullName: string;
  email: string;
}

interface Props {
  value: ReviewerIdentity;
  onChange: (v: ReviewerIdentity) => void;
  disabled?: boolean;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateIdentity(v: ReviewerIdentity): { fullName?: string; email?: string } {
  const errs: { fullName?: string; email?: string } = {};
  if (!v.fullName.trim()) errs.fullName = "Full name is required.";
  if (!v.email.trim()) errs.email = "Email is required.";
  else if (!EMAIL_RE.test(v.email)) errs.email = "Enter a valid email address.";
  return errs;
}

export default function ReviewerIdentityForm({ value, onChange, disabled }: Props) {
  const [touched, setTouched] = useState({ fullName: false, email: false });
  const errs = validateIdentity(value);

  return (
    <div className="identity-row">
      <div className="field-wrap">
        <label htmlFor="rev-name">Full name</label>
        <input
          id="rev-name"
          type="text"
          placeholder="Your full name"
          value={value.fullName}
          disabled={disabled}
          className={touched.fullName && errs.fullName ? "err" : ""}
          onChange={(e) => onChange({ ...value, fullName: e.target.value })}
          onBlur={() => setTouched((t) => ({ ...t, fullName: true }))}
        />
        {touched.fullName && errs.fullName && (
          <span className="field-err">{errs.fullName}</span>
        )}
      </div>
      <div className="field-wrap">
        <label htmlFor="rev-email">Work email</label>
        <input
          id="rev-email"
          type="email"
          placeholder="you@company.com"
          value={value.email}
          disabled={disabled}
          className={touched.email && errs.email ? "err" : ""}
          onChange={(e) => onChange({ ...value, email: e.target.value })}
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
        />
        {touched.email && errs.email && (
          <span className="field-err">{errs.email}</span>
        )}
      </div>
    </div>
  );
}
