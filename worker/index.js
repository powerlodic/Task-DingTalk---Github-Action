import { dispatchWorkflow, getLatestWorkflowRun, uploadFile } from "./github_api.js";

const TARGET_PATH = "uploads/Schedule.xlsx";
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set([".csv", ".xlsx"]);

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return corsResponse(null, 204, env);
    }

    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/health") {
        return jsonResponse({
          ok: true,
          github: hasGitHubConfig(env),
          scheduler: true,
          dingtalk: Boolean(env.DINGTALK_WEBHOOK_URL || env.DINGTALK_CONFIGURED),
          repository: [env.GITHUB_OWNER, env.GITHUB_REPO].filter(Boolean).join("/"),
          branch: env.GITHUB_BRANCH || null,
        }, 200, env);
      }

      if (request.method === "GET" && url.pathname === "/status") {
        const run = await getLatestWorkflowRun(env);
        return jsonResponse({
          ok: true,
          scheduler: run ? {
            status: run.status,
            conclusion: run.conclusion,
            startedAt: run.run_started_at,
            updatedAt: run.updated_at,
            url: run.html_url,
          } : null,
        }, 200, env);
      }

      if (request.method === "POST" && url.pathname === "/run-scheduler") {
        await dispatchWorkflow(env, "dingtalk.yml", { run_notify: "true" });
        return jsonResponse({ ok: true, message: "Scheduler workflow started." }, 202, env);
      }

      if (request.method === "POST" && url.pathname === "/upload") {
        return handleUpload(request, env);
      }

      return jsonResponse({ ok: false, error: "Not found." }, 404, env);
    } catch (error) {
      return jsonResponse({ ok: false, error: error.message || "Unexpected error." }, 500, env);
    }
  },
};

async function handleUpload(request, env) {
  const contentType = request.headers.get("content-type") || "";
  if (!contentType.includes("multipart/form-data")) {
    return jsonResponse({ ok: false, error: "Use multipart/form-data with file field schedule_file." }, 400, env);
  }

  const formData = await request.formData();
  const file = formData.get("schedule_file");
  if (!(file instanceof File)) {
    return jsonResponse({ ok: false, error: "schedule_file is required." }, 400, env);
  }

  const extension = getExtension(file.name);
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return jsonResponse({ ok: false, error: "Only .csv and .xlsx files are allowed." }, 400, env);
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return jsonResponse({ ok: false, error: "Maximum file size is 10 MB." }, 413, env);
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  const uploadBytes = extension === ".csv"
    ? csvToXlsx(bytes)
    : bytes;
  const contentBase64 = bytesToBase64(uploadBytes);
  const result = await uploadFile(
    env,
    TARGET_PATH,
    contentBase64,
    `Upload schedule from GitHub Pages: ${file.name}`,
  );
  const workflow = await dispatchCalendarBuild(env);

  return jsonResponse({
    ok: true,
    path: TARGET_PATH,
    sourceFile: file.name,
    originalType: extension,
    size: uploadBytes.byteLength,
    commit: result.commit?.sha || null,
    commitUrl: result.commit?.html_url || null,
    workflowDispatched: workflow.dispatched,
    workflowWarning: workflow.warning,
    uploadedAt: new Date().toISOString(),
  }, 200, env);
}

async function dispatchCalendarBuild(env) {
  try {
    await dispatchWorkflow(env, "dingtalk.yml", { run_notify: "false" });
    return { dispatched: true, warning: null };
  } catch (error) {
    return {
      dispatched: false,
      warning: error.message || "Workflow dispatch failed.",
    };
  }
}

function hasGitHubConfig(env) {
  return Boolean(env.GITHUB_TOKEN && env.GITHUB_OWNER && env.GITHUB_REPO && env.GITHUB_BRANCH);
}

function getExtension(filename) {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

function jsonResponse(payload, status, env) {
  return corsResponse(JSON.stringify(payload), status, env, {
    "Content-Type": "application/json; charset=utf-8",
  });
}

function corsResponse(body, status, env, headers = {}) {
  const origin = env.ALLOWED_ORIGIN || "*";
  return new Response(body, {
    status,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      ...headers,
    },
  });
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function csvToXlsx(csvBytes) {
  const csvText = new TextDecoder("utf-8").decode(csvBytes);
  const rows = parseCsv(csvText);
  const sheetXml = buildSheetXml(rows);
  const files = {
    "[Content_Types].xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`,
    "_rels/.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
    "xl/workbook.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Schedule" sheetId="1" r:id="rId1"/></sheets>
</workbook>`,
    "xl/_rels/workbook.xml.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`,
    "xl/worksheets/sheet1.xml": sheetXml,
  };
  return zipStore(files);
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell);
  if (row.some((value) => value !== "") || rows.length === 0) {
    rows.push(row);
  }
  return rows;
}

function buildSheetXml(rows) {
  const sheetData = rows.map((row, rowIndex) => {
    const cells = row.map((value, colIndex) => {
      const ref = `${columnName(colIndex + 1)}${rowIndex + 1}`;
      return `<c r="${ref}" t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>`;
    }).join("");
    return `<row r="${rowIndex + 1}">${cells}</row>`;
  }).join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>${sheetData}</sheetData>
</worksheet>`;
}

function columnName(number) {
  let name = "";
  while (number > 0) {
    const remainder = (number - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    number = Math.floor((number - 1) / 26);
  }
  return name;
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function zipStore(files) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const [name, content] of Object.entries(files)) {
    const nameBytes = encoder.encode(name);
    const dataBytes = encoder.encode(content);
    const crc = crc32(dataBytes);
    const localHeader = concatBytes(
      u32(0x04034b50), u16(20), u16(0), u16(0), u16(0), u16(0),
      u32(crc), u32(dataBytes.length), u32(dataBytes.length),
      u16(nameBytes.length), u16(0), nameBytes,
    );
    localParts.push(localHeader, dataBytes);

    const centralHeader = concatBytes(
      u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0),
      u32(crc), u32(dataBytes.length), u32(dataBytes.length),
      u16(nameBytes.length), u16(0), u16(0), u16(0), u16(0), u32(0),
      u32(offset), nameBytes,
    );
    centralParts.push(centralHeader);
    offset += localHeader.length + dataBytes.length;
  }

  const centralDirectory = concatBytes(...centralParts);
  const endRecord = concatBytes(
    u32(0x06054b50), u16(0), u16(0), u16(Object.keys(files).length),
    u16(Object.keys(files).length), u32(centralDirectory.length),
    u32(offset), u16(0),
  );
  return concatBytes(...localParts, centralDirectory, endRecord);
}

function concatBytes(...parts) {
  const length = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function u16(value) {
  return new Uint8Array([value & 255, (value >>> 8) & 255]);
}

function u32(value) {
  return new Uint8Array([
    value & 255,
    (value >>> 8) & 255,
    (value >>> 16) & 255,
    (value >>> 24) & 255,
  ]);
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
