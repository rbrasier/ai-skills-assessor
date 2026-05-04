"use client";

import { useEffect, useState } from "react";
import type { FrameworkRecord, FrameworkSkillRecord } from "@ai-skills-assessor/shared-types";
import AdminSidebar from "@/components/admin-shell/AdminSidebar";

export default function SkillsLibraryPage() {
  const [frameworks, setFrameworks] = useState<FrameworkRecord[]>([]);
  const [fwId, setFwId] = useState<string>("");
  const [skills, setSkills] = useState<FrameworkSkillRecord[]>([]);
  const [attrs, setAttrs] = useState<Array<{ id: string; attribute: string; level: number; description: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fwModal, setFwModal] = useState(false);
  const [skillModal, setSkillModal] = useState<FrameworkSkillRecord | "new" | null>(null);
  const [levelModal, setLevelModal] = useState<{ skillId: string; levelId?: string | null; level: number | null; content: string } | null>(null);

  useEffect(() => {
    void (async () => {
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
    })();
  }, []);

  useEffect(() => {
    if (!fwId) return;
    void (async () => {
      const [sRes, aRes] = await Promise.all([
        fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/skills`, { cache: "no-store" }),
        fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/attributes`, { cache: "no-store" }),
      ]);
      if (sRes.ok) setSkills((await sRes.json()) as FrameworkSkillRecord[]);
      if (aRes.ok) setAttrs((await aRes.json()) as typeof attrs);
    })();
  }, [fwId]);

  return (
    <div className="shell">
      <AdminSidebar />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Skills library</span>
          <div className="sp" />
          <a href="/dashboard" className="btn">← Dashboard</a>
        </div>
        <div className="page">
          <div className="page-head">
            <h1>Framework catalog</h1>
            <p>Edit skill definitions and level text. Embeddings are loaded separately via ingestion scripts.</p>
          </div>

          <div style={{ background: "var(--warn-2)", border: "1px solid var(--warn)", borderRadius: 10, padding: "12px 14px", fontSize: 13, color: "var(--ink-2)", marginBottom: 18 }}>
            <b>Vectors:</b> skill level embeddings are not editable here. Use the repository scripts (for example <span className="mono">python -m src.scripts.ingest_sfia_skills</span>) to populate <span className="mono">framework_skill_levels.embedding</span> after you add or change level content.
          </div>

          {error && (
            <div style={{ background: "var(--danger-2)", borderRadius: 8, padding: 12, marginBottom: 16, color: "var(--danger)" }}>{error}</div>
          )}

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

          <div className="table-card">
            <div className="table-toolbar"><b>Skills</b></div>
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
            const res = await fetch("/api/admin/frameworks", { cache: "no-store" });
            if (res.ok) {
              const data = (await res.json()) as FrameworkRecord[];
              setFrameworks(data);
              if (data[0]) setFwId(data[0].id);
            }
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
            const [sRes] = await Promise.all([
              fetch(`/api/admin/frameworks/${encodeURIComponent(fwId)}/skills`, { cache: "no-store" }),
            ]);
            if (sRes.ok) setSkills((await sRes.json()) as FrameworkSkillRecord[]);
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
          }}
        />
      )}
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
          <div className="modal-name">New framework</div>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
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
          <div className="modal-name">{initial ? "Edit skill" : "Add skill"}</div>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
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
          <div className="modal-name">Skill level</div>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
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
