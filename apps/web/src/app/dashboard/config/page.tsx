"use client";

import { useEffect, useState } from "react";
import AdminSidebar from "@/components/admin-shell/AdminSidebar";

interface SiteConfig {
  enable_sfia_flow: boolean;
  dialing_method: string;
  stt_provider: string;
  tts_provider: string;
  bot_name: string;
  bot_org_name: string;
}

function ReadOnlyRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ width: 180, fontSize: 13, color: "var(--fg-muted)", flexShrink: 0 }}>{label}</span>
      <code style={{ fontSize: 13, background: "var(--surface-2)", padding: "2px 8px", borderRadius: 4 }}>{value}</code>
    </div>
  );
}

export default function SiteConfigPage() {
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/admin/site-config", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => { setConfig(d as SiteConfig); setLoading(false); })
      .catch((e) => { setError((e as Error).message); setLoading(false); });
  }, []);

  async function toggleBot(enableSfia: boolean) {
    if (!config) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const res = await fetch("/api/admin/site-config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_sfia_flow: enableSfia }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setConfig((await res.json()) as SiteConfig);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="shell">
      <AdminSidebar />

      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Site Configuration</span>
        </div>

        <div className="page">
          <div className="page-head">
            <h1>Site <span className="serif">Config.</span></h1>
            <p>Runtime settings for this deployment. Bot selection takes effect on the next call.</p>
          </div>

          {error && (
            <div style={{ background: "var(--danger-2)", border: "1px solid var(--danger)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "var(--danger)", marginBottom: 20 }}>
              {error}
            </div>
          )}

          {loading && <p style={{ fontSize: 13, color: "var(--fg-muted)" }}>Loading…</p>}

          {config && (
            <>
              {/* Bot selector */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "20px 24px", marginBottom: 24 }}>
                <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--fg-muted)", marginBottom: 16 }}>
                  Active call bot
                </div>

                <div style={{ display: "flex", gap: 12 }}>
                  {/* Basic bot card */}
                  <button
                    onClick={() => toggleBot(false)}
                    disabled={saving}
                    style={{
                      flex: 1, padding: "16px 18px", borderRadius: 8, cursor: saving ? "default" : "pointer",
                      border: `2px solid ${!config.enable_sfia_flow ? "var(--accent)" : "var(--border)"}`,
                      background: !config.enable_sfia_flow ? "var(--accent-2, rgba(79,70,229,0.06))" : "var(--surface-2)",
                      textAlign: "left", transition: "border-color 0.15s",
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                      Basic call bot
                    </div>
                    <div style={{ fontSize: 12, color: "var(--fg-muted)", lineHeight: 1.5 }}>
                      Scripted greeting + one open question. Lightweight — no Anthropic key required.
                    </div>
                    {!config.enable_sfia_flow && (
                      <div style={{ marginTop: 8, fontSize: 11, fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Active
                      </div>
                    )}
                  </button>

                  {/* SFIA bot card */}
                  <button
                    onClick={() => toggleBot(true)}
                    disabled={saving}
                    style={{
                      flex: 1, padding: "16px 18px", borderRadius: 8, cursor: saving ? "default" : "pointer",
                      border: `2px solid ${config.enable_sfia_flow ? "var(--accent)" : "var(--border)"}`,
                      background: config.enable_sfia_flow ? "var(--accent-2, rgba(79,70,229,0.06))" : "var(--surface-2)",
                      textAlign: "left", transition: "border-color 0.15s",
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                      SFIA assessment bot
                    </div>
                    <div style={{ fontSize: 12, color: "var(--fg-muted)", lineHeight: 1.5 }}>
                      Full 5-state SFIA 9 flow with RAG retrieval, claim extraction, and report generation. Requires Anthropic key.
                    </div>
                    {config.enable_sfia_flow && (
                      <div style={{ marginTop: 8, fontSize: 11, fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Active
                      </div>
                    )}
                  </button>
                </div>

                {saved && (
                  <p style={{ marginTop: 12, fontSize: 12, color: "var(--success, #16a34a)" }}>
                    Saved — takes effect on the next call.
                  </p>
                )}
                <p style={{ marginTop: 12, fontSize: 11, color: "var(--fg-muted)" }}>
                  This override is held in memory. Set <code>ENABLE_SFIA_FLOW</code> in <code>.env</code> to make it permanent.
                </p>
              </div>

              {/* Read-only provider info */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "20px 24px" }}>
                <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--fg-muted)", marginBottom: 8 }}>
                  Deployment settings
                </div>
                <p style={{ fontSize: 12, color: "var(--fg-muted)", marginBottom: 12 }}>
                  Read from environment variables — change via <code>.env</code> and restart.
                </p>
                <ReadOnlyRow label="Dialing method" value={config.dialing_method} />
                <ReadOnlyRow label="STT provider" value={config.stt_provider} />
                <ReadOnlyRow label="TTS provider" value={config.tts_provider} />
                <ReadOnlyRow label="Bot name" value={config.bot_name} />
                <ReadOnlyRow label="Organisation" value={config.bot_org_name} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
