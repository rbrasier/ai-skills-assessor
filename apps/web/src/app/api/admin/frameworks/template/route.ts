import { NextResponse } from "next/server";
import * as XLSX from "xlsx";

export const dynamic = "force-dynamic";

const INSTRUCTIONS = [
  ["SFIA Framework Import Template"],
  [""],
  ["Instructions:"],
  ["1. Fill in the Framework sheet with exactly one row of framework metadata."],
  ["2. Fill in the Skills sheet — one row per skill. skill_code must be unique."],
  ["3. Fill in the SkillLevels sheet — one row per (skill_code, level) pair."],
  ["   level must be an integer 1–7. skill_code must match a row in the Skills sheet."],
  ["4. Fill in the Attributes sheet (optional) — one row per (attribute, level) pair."],
  ["5. Do NOT rename or reorder column headers."],
  ["6. Upload this file via the Skills library page → Upload framework."],
  [""],
  ["Notes:"],
  ["• Uploading an existing framework (same type + version) updates all rows."],
  ["• When level content changes, the embedding for that level is cleared and"],
  ["  marked for re-vectorization. Run the vectorize-framework.sh script"],
  ["  afterwards to regenerate embeddings."],
  ["• The rubric column in the Framework sheet is the assessor scoring guidance"],
  ["  injected into the system prompt. Leave blank to keep the existing rubric."],
];

const FRAMEWORK_HEADERS = ["type", "version", "name", "rubric"];
const FRAMEWORK_EXAMPLE = ["sfia-9", "9.0", "SFIA 9", "Scoring rubric text..."];

const SKILLS_HEADERS = [
  "skill_code", "skill_name", "category", "subcategory", "description", "guidance",
];
const SKILLS_EXAMPLE = [
  "PROG", "Programming/Software Development", "Development and implementation",
  "Software design", "Creating and refining executable code…", "",
];

const LEVELS_HEADERS = ["skill_code", "level", "content"];
const LEVELS_EXAMPLE = [
  "PROG", 3, "Designs, codes, verifies, tests, documents…",
];

const ATTRIBUTES_HEADERS = ["attribute", "level", "description"];
const ATTRIBUTES_EXAMPLE = [
  "Autonomy", 3, "Works under general direction within a clear framework of accountability…",
];

function makeSheet(headers: string[], example: (string | number)[]): XLSX.WorkSheet {
  const ws = XLSX.utils.aoa_to_sheet([headers, example]);
  // Bold the header row
  const range = XLSX.utils.decode_range(ws["!ref"] ?? "A1");
  for (let c = range.s.c; c <= range.e.c; c++) {
    const cell = XLSX.utils.encode_cell({ r: 0, c });
    if (ws[cell]) ws[cell].s = { font: { bold: true } };
  }
  return ws;
}

export async function GET(): Promise<NextResponse> {
  const wb = XLSX.utils.book_new();

  const wsInstructions = XLSX.utils.aoa_to_sheet(INSTRUCTIONS);
  const wsFramework = makeSheet(FRAMEWORK_HEADERS, FRAMEWORK_EXAMPLE);
  const wsSkills = makeSheet(SKILLS_HEADERS, SKILLS_EXAMPLE);
  const wsLevels = makeSheet(LEVELS_HEADERS, LEVELS_EXAMPLE);
  const wsAttributes = makeSheet(ATTRIBUTES_HEADERS, ATTRIBUTES_EXAMPLE);

  XLSX.utils.book_append_sheet(wb, wsInstructions, "Instructions");
  XLSX.utils.book_append_sheet(wb, wsFramework, "Framework");
  XLSX.utils.book_append_sheet(wb, wsSkills, "Skills");
  XLSX.utils.book_append_sheet(wb, wsLevels, "SkillLevels");
  XLSX.utils.book_append_sheet(wb, wsAttributes, "Attributes");

  const buf = XLSX.write(wb, { type: "buffer", bookType: "xlsx" }) as Buffer;

  return new NextResponse(new Uint8Array(buf), {
    status: 200,
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": 'attachment; filename="framework-import-template.xlsx"',
    },
  });
}
