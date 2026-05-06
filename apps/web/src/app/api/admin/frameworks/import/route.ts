import { NextResponse, type NextRequest } from "next/server";
import * as XLSX from "xlsx";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

type Row = Record<string, unknown>;

function sheetToRows(wb: XLSX.WorkBook, name: string): Row[] {
  const ws = wb.Sheets[name];
  if (!ws) return [];
  return XLSX.utils.sheet_to_json<Row>(ws, { defval: "" });
}

function str(v: unknown): string {
  return v == null || v === "" ? "" : String(v).trim();
}

function optStr(v: unknown): string | null {
  const s = str(v);
  return s === "" ? null : s;
}

function num(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart/form-data upload" }, { status: 400 });
  }

  const file = formData.get("file");
  if (!file || typeof file === "string") {
    return NextResponse.json({ error: "No file uploaded (field name: file)" }, { status: 400 });
  }

  const bytes = await (file as File).arrayBuffer();
  let wb: XLSX.WorkBook;
  try {
    wb = XLSX.read(bytes, { type: "array" });
  } catch {
    return NextResponse.json({ error: "Could not parse file as Excel (.xlsx)" }, { status: 422 });
  }

  // ── Framework sheet (exactly one data row) ────────────────────────
  const fwRows = sheetToRows(wb, "Framework");
  if (fwRows.length === 0) {
    return NextResponse.json(
      { error: "Framework sheet is empty. Add one row with type, version, name, rubric." },
      { status: 422 },
    );
  }
  const fw = fwRows[0]!;
  const fwType = str(fw.type);
  const fwVersion = str(fw.version);
  const fwName = str(fw.name) || fwType;
  const fwRubric = str(fw.rubric);
  if (!fwType || !fwVersion) {
    return NextResponse.json(
      { error: "Framework sheet: type and version are required." },
      { status: 422 },
    );
  }

  // ── Skills sheet ──────────────────────────────────────────────────
  const skills = sheetToRows(wb, "Skills")
    .filter((r) => str(r.skill_code))
    .map((r) => ({
      skill_code: str(r.skill_code),
      skill_name: str(r.skill_name) || str(r.skill_code),
      category: str(r.category) || "General",
      subcategory: optStr(r.subcategory),
      description: str(r.description),
      guidance: optStr(r.guidance),
    }));

  // ── SkillLevels sheet ─────────────────────────────────────────────
  const skill_levels = sheetToRows(wb, "SkillLevels")
    .filter((r) => str(r.skill_code) && num(r.level) !== null && str(r.content))
    .map((r) => ({
      skill_code: str(r.skill_code),
      level: num(r.level) as number,
      content: str(r.content),
    }))
    .filter((r) => r.level >= 1 && r.level <= 7);

  // ── Attributes sheet (optional) ───────────────────────────────────
  const attributes = sheetToRows(wb, "Attributes")
    .filter((r) => str(r.attribute) && num(r.level) !== null && str(r.description))
    .map((r) => ({
      attribute: str(r.attribute),
      level: num(r.level) as number,
      description: str(r.description),
    }))
    .filter((r) => r.level >= 1 && r.level <= 7);

  const payload = {
    type: fwType,
    version: fwVersion,
    name: fwName,
    rubric: fwRubric,
    skills,
    skill_levels,
    attributes,
  };

  const upstream = await fetch(`${BASE()}/api/v1/admin/frameworks/bulk-import`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...voiceEngineAdminHeaders(request) },
    body: JSON.stringify(payload),
  });

  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json(data);
}
