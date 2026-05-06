"use client";

import { useEffect, useRef, useState } from "react";
import type {
  FrameworkRecord,
  FrameworkSkillRecord,
  FrameworkSyncStatus,
} from "@ai-skills-assessor/shared-types";
import AdminSidebar from "@/components/admin-shell/AdminSidebar";

export default function SkillsLibraryPage() {
  const [frameworks, setFrameworks] = useState<FrameworkRecord[]>([]);
  const [fwId, setFwId] = useState<string>("");
  const [skills, setSkills] = useState<FrameworkSkillRecord[]>([]);
  const [attrs, setAttrs] = useState<Array<{ id: string; attribute: string; level: number; description: string }>>([]);
  const [syncStatus, setSyncStatus] = useState<FrameworkSyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fwModal, setFwModal] = useState(false);
  const [skillModal, setSkillModal] = useState<FrameworkSkillRecord | "new" | null>(null);
  const [levelModal, setLevelModal] = useState<{ skillId: string; levelId?: string | null; level: number | null; content: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ ok: boolean; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadFrameworks() {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/frameworks", { cache: "no-store" });
      if (!res.ok) throw new Error(`Frameworks ${res.status}`);
      const data = (await res.json()) as FrameworkRecord[];
      setFrameworks(data);
      setFwId((cur) => (cur || (data[0]?.id ?? "")));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadFrameworks(); }, []);

  useEffect(() => {
    if (!fwId) return;
    setSyncStatus(null);
    void (async () => {
      const [sRes, aRes, syncRes] = await Promise.all([
        fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/skills`, { cache: "no-store" }),
        fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/attributes`, { cache: "no-store" }),
        fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/sync-status`, { cache: "no-store" }),
      ]);
      if (sRes.ok) setSkills((await sRes.json()) as FrameworkSkillRecord[]);
      if (aRes.ok) setAttrs((await aRes.json()) as typeof attrs);
      if (syncRes.ok) setSyncStatus((await syncRes.json()) as FrameworkSyncStatus);
    })();
  }, [fwId]);

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/admin/frameworks/import", { method: "POST", body: form });
      const data = (await res.json()) as Record<string, unknown>;
      if (!res.ok) {
        setUploadResult({ ok: false, message: String(data.error ?? "Import failed") });
      } else {
        const { skills_upserted, levels_upserted, levels_stale, attributes_upserted } = data as {
          skills_upserted: number;
          levels_upserted: number;
          levels_stale: number;
          attributes_upserted: number;
        };
        setUploadResult({
          ok: true,
          message: `Imported: ${skills_upserted} skills, ${levels_upserted} levels` +
            (levels_stale > 0 ? ` (${levels_stale} levels need re-vectorization)` : "") +
            (attributes_upserted > 0 ? `, ${attributes_upserted} attributes` : ""),
        });
        await loadFrameworks();
      }
    } catch (e) {
      setUploadResult({ ok: false, message: (e as Error).message });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const selectedFw = frameworks.find((f) => f.id === fwId);

  return (
    <div className="shell">
      <AdminSidebar />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Skills library</span>
          <div className="sp" />
          {/* Template download */}
          <a
            href="/api/admin/frameworks/template"
            download="framework-import-template.xlsx"
            className="btn"
            title="Download blank Excel template for importing a framework"
          >
            ↓ Download template
          </a>
          {/* Upload trigger */}
          <label
            style={{
              cursor: uploading ? "not-allowed" : "pointer",
              opacity: uploading ? 0.6 : 1,
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              style={{ display: "none" }}
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUpload(f);
              }}
            />
            <span className="btn btn-primary" aria-busy={uploading}>
              {uploading ? "Uploading…" : "↑ Upload framework"}
            </span>
          </label>
          <a href="/dashboard" className="btn">← Dashboard</a>
        </div>

        <div className="page">
          <div className="page-head">
            <h1>Framework catalog</h1>
            <p>Import a framework via Excel, or edit skill definitions individually below.</p>
          </div>

          {/* Upload result feedback */}
          {uploadResult && (
            <div
              style={{
                background: uploadResult.ok ? "var(--success-2, #f0fdf4)" : "var(--danger-2)",
                border: `1px solid ${uploadResult.ok ? "var(--success, #16a34a)" : "var(--danger)"}`,
                borderRadius: 8,
                padding: "10px 14px",
                fontSize: 13,
                marginBottom: 16,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span>{uploadResult.message}</span>
              <button
                type="button"
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, lineHeight: 1 }}
                onClick={() => setUploadResult(null)}
                aria-label="Dismiss"
              >
                ×
              </button>
            </div>
          )}

          {error && (
            <div style={{ background: "var(--danger-2)", borderRadius: 8, padding: 12, marginBottom: 16, color: "var(--danger)" }}>{error}</div>
          )}

          {/* Framework selector */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
            <label style={{ fontSize: 13, color: "var(--ink-3)" }}>Framework</label>
            <select value={fwId} onChange={(e) => setFwId(e.target.value)} style={{ padding: 8, borderRadius: 6, border: "1px solid var(--line)", minWidth: 220 }}>
              {frameworks.map((f) => (
                <option key={f.id} value={f.id}>{f.type} {f.version} — {f.name}</option>
              ))}
            </select>
            <button type="button" className="btn btn-primary" onClick={() => setFwModal(true)}>Add framework</button>
            <button type="button" className="btn" onClick={() => setSkillModal("new")}>Add skill</button>
          </div>

          {/* Embedding sync status */}
          {syncStatus && (
            <SyncStatusBanner
              syncStatus={syncStatus}
              frameworkType={selectedFw?.type ?? ""}
              frameworkVersion={selectedFw?.version ?? ""}
            />
          )}

          <div className="table-card">
            <div className="table-toolbar"><b>Skills</b> <span style={{ marginLeft: 8, fontSize: 12, color: "var(--ink-3)" }}>({skills.length})</span></div>
            <div className="thead" style={{ gridTemplateColumns: "1fr 1fr 2fr 100px" }}>
              <div>Code</div>
              <div>Name</div>
              <div>Description</div>
              <div />
            </div>
            {loading ? <div style={{ padding: 20 }}>Loading…</div> : skills.map((sk) => (
              <div key={sk.id} className="trow" style={{ gridTemplateColumns: "1fr 1fr 2fr 100px" }}>
                <div className="mono">{sk.skillCode}</div>
                <div>{sk.skillName}</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{sk.description.slice(0, 120)}{sk.description.length > 120 ? "…" : ""}</div>
                <div>
                  <button type="button" className="btn" onClick={() => setSkillModal(sk)}>Edit</button>
                </div>
              </div>
            ))}
          </div>

          <div className="table-card" style={{ marginTop: 20 }}>
            <div className="table-toolbar"><b>Generic attributes</b></div>
            <div className="thead" style={{ gridTemplateColumns: "1fr 80px 2fr" }}>
              <div>Attribute</div>
              <div>Level</div>
              <div>Description</div>
            </div>
            {attrs.map((a) => (
              <div key={a.id} className="trow" style={{ gridTemplateColumns: "1fr 80px 2fr" }}>
                <div>{a.attribute}</div>
                <div>{a.level}</div>
                <div style={{ fontSize: 12 }}>{a.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {fwModal && (
        <FrameworkModal
          onClose={() => setFwModal(false)}
          onSaved={async () => {
            setFwModal(false);
            await loadFrameworks();
          }}
        />
      )}

      {skillModal && fwId && (
        <SkillModal
          key={skillModal === "new" ? "new-skill" : skillModal.id}
          frameworkId={fwId}
          initial={skillModal === "new" ? null : skillModal}
          onClose={() => setSkillModal(null)}
          onSaved={async () => {
            setSkillModal(null);
            if (!fwId) return;
            const sRes = await fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/skills`, { cache: "no-store" });
            if (sRes.ok) setSkills((await sRes.json()) as FrameworkSkillRecord[]);
            const syncRes = await fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/sync-status`, { cache: "no-store" });
            if (syncRes.ok) setSyncStatus((await syncRes.json()) as FrameworkSyncStatus);
          }}
          onAddLevel={(skillId) => setLevelModal({ skillId, levelId: null, level: 1, content: "" })}
          onEditLevel={(skillId, lv) => setLevelModal({ skillId, levelId: lv.id, level: lv.level, content: lv.content })}
        />
      )}

      {levelModal && (
        <LevelModal
          frameworkSkillId={levelModal.skillId}
          initial={levelModal}
          onClose={() => setLevelModal(null)}
          onSaved={async () => {
            setLevelModal(null);
            if (!fwId) return;
            const sRes = await fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/skills`, { cache: "no-store" });
            if (sRes.ok) setSkills((await sRes.json()) as FrameworkSkillRecord[]);
            const syncRes = await fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/sync-status`, { cache: "no-store" });
            if (syncRes.ok) setSyncStatus((await syncRes.json()) as FrameworkSyncStatus);
          }}
        />
      )}
    </div>
  );
}

function SyncStatusBanner({
  syncStatus,
  frameworkType,
  frameworkVersion,
}: {
  syncStatus: FrameworkSyncStatus;
  frameworkType: string;
  frameworkVersion: string;
}) {
  const { total, embedded, stale } = syncStatus;
  const allGood = stale === 0 && total > 0;

  if (total === 0) return null;

  return (
    <div
      style={{
        background: allGood ? "var(--success-2, #f0fdf4)" : "var(--warn-2)",
        border: `1px solid ${allGood ? "var(--success, #16a34a)" : "var(--warn)"}`,
        borderRadius: 10,
        padding: "12px 14px",
        fontSize: 13,
        color: "var(--ink-2)",
        marginBottom: 18,
        display: "flex",
        gap: 16,
        alignItems: "flex-start",
        flexWrap: "wrap",
      }}
    >
      <div style={{ flex: 1 }}>
        <b>Embeddings:</b>{" "}
        {allGood ? (
          <>All {total} skill levels have up-to-date vectors. ✓</>
        ) : (
          <>
            {embedded}/{total} levels have embeddings.{" "}
            <b>{stale} level{stale !== 1 ? "s" : ""} need{stale === 1 ? "s" : ""} re-vectorization</b>
            {stale > 0 && " — content has changed or embeddings were never generated."}{" "}
            Run the vectorization script to regenerate:
          </>
        )}
        {!allGood && (
          <div
            style={{
              marginTop: 8,
              background: "rgba(0,0,0,0.05)",
              borderRadius: 6,
              padding: "6px 10px",
              fontFamily: "monospace",
              fontSize: 12,
              userSelect: "all",
            }}
          >
            ./scripts/vectorize-framework.sh --framework-type {frameworkType} --framework-version {frameworkVersion}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 12, fontSize: 12, color: "var(--ink-3)", flexShrink: 0 }}>
        <span>Total <b>{total}</b></span>
        <span>Embedded <b style={{ color: "var(--success, #16a34a)" }}>{embedded}</b></span>
        {stale > 0 && <span>Stale <b style={{ color: "var(--warn, #d97706)" }}>{stale}</b></span>}
      </div>
    </div>
  );
}

function FrameworkModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [type, setType] = useState("sfia-9");
  const [version, setVersion] = useState("9.0");
  const [name, setName] = useState("SFIA 9");
  const [rubric, setRubric] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    await fetch("/api/admin/frameworks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, version, name, rubric: rubric || " ", isActive: true }),
    });
    setSaving(false);
    await onSaved();
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-meta">
            <div className="modal-name">New framework</div>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label>Type <input value={type} onChange={(e) => setType(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Version <input value={version} onChange={(e) => setVersion(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Name <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Rubric <textarea value={rubric} onChange={(e) => setRubric(e.target.value)} rows={4} style={{ width: "100%", padding: 8 }} /></label>
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>Save</button>
        </div>
      </div>
    </div>
  );
}

function SkillModal({
  frameworkId,
  initial,
  onClose,
  onSaved,
  onAddLevel,
  onEditLevel,
}: {
  frameworkId: string;
  initial: FrameworkSkillRecord | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onAddLevel: (skillId: string) => void;
  onEditLevel: (skillId: string, lv: { id: string; level: number | null; content: string }) => void;
}) {
  const [id, setId] = useState(initial?.id ?? "");
  const [code, setCode] = useState(initial?.skillCode ?? "");
  const [sname, setSname] = useState(initial?.skillName ?? "");
  const [cat, setCat] = useState(initial?.category ?? "General");
  const [sub, setSub] = useState(initial?.subcategory ?? "");
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [guide, setGuide] = useState(initial?.guidance ?? "");
  const [levels, setLevels] = useState(initial?.levels ?? []);
  const [saving, setSaving] = useState(false);

  async function saveSkill() {
    setSaving(true);
    const res = await fetch(`/api/admin/frameworks/${encodeURIComponent(frameworkId)}/skills`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: id || null,
        skillCode: code,
        skillName: sname,
        category: cat,
        subcategory: sub || null,
        description: desc,
        guidance: guide || null,
      }),
    });
    const data = (await res.json()) as { id: string };
    if (data.id) setId(data.id);
    setSaving(false);
    await onSaved();
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-meta">
            <div className="modal-name">{initial ? "Edit skill" : "Add skill"}</div>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label>Code <input value={code} onChange={(e) => setCode(e.target.value)} className="mono" style={{ width: "100%", padding: 8 }} /></label>
          <label>Name <input value={sname} onChange={(e) => setSname(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Category <input value={cat} onChange={(e) => setCat(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Subcategory <input value={sub} onChange={(e) => setSub(e.target.value)} style={{ width: "100%", padding: 8 }} /></label>
          <label>Description <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} style={{ width: "100%", padding: 8 }} /></label>
          <label>Guidance <textarea value={guide} onChange={(e) => setGuide(e.target.value)} rows={2} style={{ width: "100%", padding: 8 }} /></label>
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void saveSkill()}>Save skill</button>

          {id && (
            <>
              <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, marginTop: 8 }}>
                <b>Level content</b>
                <button type="button" className="btn" style={{ marginLeft: 10 }} onClick={() => onAddLevel(id)}>Add level</button>
              </div>
              {levels.map((lv) => (
                <div key={lv.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span className="mono">L{lv.level ?? "—"}</span>
                  <span style={{ flex: 1, fontSize: 12, color: "var(--ink-3)" }}>{lv.content.slice(0, 80)}…</span>
                  <button type="button" className="btn" onClick={() => onEditLevel(id, lv)}>Edit</button>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LevelModal({
  frameworkSkillId,
  initial,
  onClose,
  onSaved,
}: {
  frameworkSkillId: string;
  initial: { levelId?: string | null; level: number | null; content: string };
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [level, setLevel] = useState<number | "">(initial.level ?? 1);
  const [content, setContent] = useState(initial.content);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    await fetch(`/api/admin/framework-skills/${encodeURIComponent(frameworkSkillId)}/levels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: initial.levelId ?? null,
        level: level === "" ? null : level,
        content,
      }),
    });
    setSaving(false);
    await onSaved();
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-meta">
            <div className="modal-name">Skill level</div>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label>Level (1–7) <input type="number" min={1} max={7} value={level} onChange={(e) => setLevel(e.target.value === "" ? "" : Number(e.target.value))} style={{ width: "100%", padding: 8 }} /></label>
          <label>Content <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={6} style={{ width: "100%", padding: 8 }} /></label>
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>Save</button>
        </div>
      </div>
    </div>
  );
}
