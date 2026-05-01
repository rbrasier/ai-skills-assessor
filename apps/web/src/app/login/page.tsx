"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (res.status === 401) { setError("Invalid token. Check your ADMIN_TOKEN."); return; }
      if (res.status === 503) { setError("Admin access not configured on this server."); return; }
      if (!res.ok) { setError("Login failed. Please try again."); return; }
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="brand" style={{ marginBottom: 28 }}>
          <div className="brand-mark">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 8h1.5" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M5 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M8 3v10" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M11 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M13.5 8H14" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <div className="brand-name">Resonant</div>
            <span className="brand-sub">Admin</span>
          </div>
        </div>

        <h1 style={{ fontSize: 20, fontWeight: 500, letterSpacing: "-0.02em", margin: "0 0 6px" }}>
          Sign in
        </h1>
        <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "0 0 24px" }}>
          Enter your operator access token to continue.
        </p>

        <form onSubmit={(e) => void handleLogin(e)}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 11, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 500 }}>
                Access token
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="••••••••••••••••"
                required
                style={{
                  background: "var(--paper)", border: "1px solid var(--line)",
                  borderRadius: 8, padding: "10px 12px", fontSize: 14,
                  color: "var(--ink)", outline: "none", fontFamily: "inherit",
                  transition: "border-color 0.15s",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
                onBlur={(e) => (e.target.style.borderColor = "var(--line)")}
              />
            </div>

            {error && (
              <div style={{ fontSize: 12.5, color: "var(--danger)", background: "var(--danger-2)", borderRadius: 6, padding: "8px 12px" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!token || loading}
              style={{
                padding: "11px 0", background: "var(--ink)", color: "var(--paper)",
                border: "none", borderRadius: 8, fontSize: 14, fontWeight: 500,
                cursor: token && !loading ? "pointer" : "not-allowed",
                opacity: token && !loading ? 1 : 0.5,
                fontFamily: "inherit", transition: "opacity 0.15s",
              }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
