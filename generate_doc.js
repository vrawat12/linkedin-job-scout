"use strict";
/**
 * Generates a tailored resume Word document from JSON received via stdin.
 * Uses the docx npm package (v8). Called by bio_agent.py via subprocess.
 *
 * Visual spec:
 *   Navy #1B3A6B — name, all section headers
 *   Black #000000 — all body text, contact, bullets
 *   Margins: top/bottom 1080 DXA (0.75"), left/right 1260 DXA (0.875")
 *   US Letter: 12240 x 15840 DXA
 *   Tailored-for metadata in footer only (not in resume body)
 */

const {
  Document,
  Footer,
  Packer,
  Paragraph,
  TextRun,
  AlignmentType,
  LevelFormat,
  BorderStyle,
  TabStopType,
} = require("docx");
const fs = require("fs");
const path = require("path");

// ── Layout constants ──────────────────────────────────────────────────────────
const FONT        = "Arial";
const PAGE_W      = 12240;   // 8.5 inches
const PAGE_H      = 15840;   // 11 inches
const MARGIN_TB   = 1080;    // 0.75 inch top/bottom
const MARGIN_LR   = 1260;    // 0.875 inch left/right
const CONTENT_W   = PAGE_W - MARGIN_LR * 2;  // 9720 DXA — tab stop for dates

// Colors
const NAVY  = "1B3A6B";
const BLACK = "000000";
const GRAY  = "888888";

// Font sizes (half-points: pt × 2)
const SZ_NAME    = 56;  // 28pt — candidate name
const SZ_CONTACT = 20;  // 10pt — contact line
const SZ_HEADING = 22;  // 11pt — section headers
const SZ_BODY    = 21;  // 10.5pt — body text and bullets
const SZ_FOOTER  = 16;  // 8pt — footer metadata

const BULLET_REF = "resume-bullets";

// ── Run / Paragraph helpers ───────────────────────────────────────────────────

function tr(text, { size = SZ_BODY, bold = false, italics = false, color = BLACK } = {}) {
  return new TextRun({ text, font: FONT, size, bold, italics, color });
}

/**
 * Section header: 11pt bold navy ALL CAPS, navy border bottom.
 */
function sectionHeader(text) {
  return new Paragraph({
    children: [tr(text.toUpperCase(), { size: SZ_HEADING, bold: true, color: NAVY })],
    border: {
      bottom: { color: NAVY, space: 4, style: BorderStyle.SINGLE, size: 6 },
    },
    spacing: { before: 200, after: 80 },
  });
}

/**
 * Body paragraph: 10.5pt black.
 */
function bodyPara(text, spacingAfter = 80) {
  return new Paragraph({
    children: [tr(text)],
    spacing: { after: spacingAfter },
  });
}

/**
 * Bullet paragraph using LevelFormat.BULLET — never unicode in body text.
 */
function bulletPara(text) {
  return new Paragraph({
    children: [tr(text)],
    numbering: { reference: BULLET_REF, level: 0 },
    spacing: { before: 40, after: 40 },
  });
}

/**
 * Job header row: "Company | Title [TAB] Dates"
 * Company is bold, title is normal, dates are right-aligned via tab stop.
 */
function jobHeader(company, title, dates) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
    children: [
      tr(`${company}`, { bold: true }),
      tr(` | ${title}`),
      new TextRun({ text: "\t", font: FONT }),
      tr(dates, { size: SZ_CONTACT }),
    ],
    spacing: { before: 160, after: 60 },
  });
}

function spacer(after = 60) {
  return new Paragraph({ children: [], spacing: { after } });
}

// ── Footer ────────────────────────────────────────────────────────────────────

function buildFooter(data) {
  const text = `Tailored for ${data.target_title} at ${data.target_company} | ${data.target_date} | Score: ${data.target_score}/10 | ${data.role_type_detected}`;
  return new Footer({
    children: [
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [tr(text, { size: SZ_FOOTER, color: GRAY })],
      }),
    ],
  });
}

// ── Document builder ──────────────────────────────────────────────────────────

function buildDocument(data) {
  const children = [];

  // ── 1. HEADER — name + contact ───────────────────────────────────────────
  children.push(
    new Paragraph({
      children: [tr(data.candidate_name, { size: SZ_NAME, bold: true, color: NAVY })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 40 },
    }),
    new Paragraph({
      children: [tr(data.contact, { size: SZ_CONTACT })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
    }),
  );

  // ── 2. EXECUTIVE SUMMARY ─────────────────────────────────────────────────
  children.push(
    sectionHeader("Executive Summary"),
    bodyPara(data.summary, 120),
  );

  // ── 3. EXPERIENCE ────────────────────────────────────────────────────────
  children.push(sectionHeader("Experience"));
  for (const role of (data.experience || [])) {
    children.push(jobHeader(role.company, role.title, role.dates));
    for (const b of (role.bullets || [])) {
      children.push(bulletPara(b));
    }
    children.push(spacer(80));
  }

  // ── 4. EDUCATION — carried through unchanged ─────────────────────────────
  const education = data.education || [];
  if (education.length > 0) {
    children.push(sectionHeader("Education"));
    for (const line of education) {
      children.push(bodyPara(line, 60));
    }
    children.push(spacer(40));
  }

  // ── 5. COMMUNITY — carried through unchanged ─────────────────────────────
  const community = data.community || [];
  if (community.length > 0) {
    children.push(sectionHeader("Community"));
    for (const line of community) {
      children.push(bodyPara(line, 60));
    }
    children.push(spacer(40));
  }

  // ── 6. SKILLS — conditional ──────────────────────────────────────────────
  const skills = data.skills || {};
  const hasSkills =
    (skills.domain && skills.domain.length > 0) ||
    (skills.product && skills.product.length > 0) ||
    (skills.tools && skills.tools.length > 0);

  if (hasSkills) {
    children.push(sectionHeader("Skills"));
    if (skills.domain && skills.domain.length > 0) {
      children.push(new Paragraph({
        children: [tr("Domain: ", { bold: true }), tr(skills.domain.join(", "))],
        spacing: { after: 60 },
      }));
    }
    if (skills.product && skills.product.length > 0) {
      children.push(new Paragraph({
        children: [tr("Product: ", { bold: true }), tr(skills.product.join(", "))],
        spacing: { after: 60 },
      }));
    }
    if (skills.tools && skills.tools.length > 0) {
      children.push(new Paragraph({
        children: [tr("Tools: ", { bold: true }), tr(skills.tools.join(", "))],
        spacing: { after: 60 },
      }));
    }
    children.push(spacer(40));
  }

  // ── 7. COVER LETTER OPENER — supplementary, below resume body ────────────
  children.push(
    sectionHeader(`Cover Letter Opening — ${data.target_company}`),
    bodyPara(data.why_this_role, 80),
    new Paragraph({
      children: [tr("Customize before sending.", { italics: true, size: SZ_FOOTER, color: GRAY })],
    }),
  );

  return new Document({
    numbering: {
      config: [
        {
          reference: BULLET_REF,
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "•",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: 360, hanging: 360 },
                },
                run: {
                  font: FONT,
                  size: SZ_BODY,
                },
              },
            },
          ],
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: PAGE_W, height: PAGE_H },
            margin: {
              top: MARGIN_TB,
              bottom: MARGIN_TB,
              left: MARGIN_LR,
              right: MARGIN_LR,
            },
          },
        },
        footers: {
          default: buildFooter(data),
        },
        children,
      },
    ],
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

async function main() {
  let raw = "";
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) {
    raw += chunk;
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`Failed to parse input JSON: ${err.message}\n`);
    process.exit(1);
  }

  const outputPath = data.output_path;
  if (!outputPath) {
    process.stderr.write("No output_path in input JSON\n");
    process.exit(1);
  }

  const doc = buildDocument(data);
  const buffer = await Packer.toBuffer(doc);

  const dir = path.dirname(outputPath);
  if (dir && dir !== ".") {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(outputPath, buffer);
  process.stdout.write(`Generated: ${outputPath}\n`);
}

main().catch((err) => {
  process.stderr.write(`generate_doc.js error: ${err.message}\n`);
  process.exit(1);
});
