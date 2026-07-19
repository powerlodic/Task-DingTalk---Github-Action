const state = {
  file: null,
  workerUrl: localStorage.getItem("workerUrl") || "",
  parsedRows: [],
  schedule: null,
};

const SCHEDULE_JSON_URL = "data/schedule.json";

const elements = {
  workerUrl: document.querySelector("#workerUrl"),
  fileInput: document.querySelector("#fileInput"),
  dropZone: document.querySelector("#dropZone"),
  fileName: document.querySelector("#fileName"),
  fileMeta: document.querySelector("#fileMeta"),
  clearFile: document.querySelector("#clearFile"),
  uploadButton: document.querySelector("#uploadButton"),
  runScheduler: document.querySelector("#runScheduler"),
  progressBar: document.querySelector("#progressBar"),
  lastUpload: document.querySelector("#lastUpload"),
  githubStatus: document.querySelector("#githubStatus"),
  schedulerStatus: document.querySelector("#schedulerStatus"),
  dingtalkStatus: document.querySelector("#dingtalkStatus"),
  githubDot: document.querySelector("#githubDot"),
  schedulerDot: document.querySelector("#schedulerDot"),
  dingtalkDot: document.querySelector("#dingtalkDot"),
  totalEngineer: document.querySelector("#totalEngineer"),
  totalEvents: document.querySelector("#totalEvents"),
  scheduleMonth: document.querySelector("#scheduleMonth"),
  scheduleYear: document.querySelector("#scheduleYear"),
  calendarTitle: document.querySelector("#calendarTitle"),
  calendarGrid: document.querySelector("#calendarGrid"),
  themeToggle: document.querySelector("#themeToggle"),
  toastHost: document.querySelector("#toastHost"),
};

elements.workerUrl.value = state.workerUrl;
elements.workerUrl.addEventListener("change", () => {
  state.workerUrl = normalizeUrl(elements.workerUrl.value);
  elements.workerUrl.value = state.workerUrl;
  localStorage.setItem("workerUrl", state.workerUrl);
  refreshStatus();
});

elements.fileInput.addEventListener("change", (event) => {
  selectFile(event.target.files[0]);
});

elements.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  elements.dropZone.classList.add("dragging");
});

elements.dropZone.addEventListener("dragleave", () => {
  elements.dropZone.classList.remove("dragging");
});

elements.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
  selectFile(event.dataTransfer.files[0]);
});

elements.clearFile.addEventListener("click", () => {
  state.file = null;
  state.parsedRows = [];
  elements.fileInput.value = "";
  updateFilePreview();
  updateStats();
  if (state.schedule) {
    renderSchedule(state.schedule);
  } else {
    renderCalendar(null);
  }
});

elements.uploadButton.addEventListener("click", uploadSchedule);
elements.runScheduler.addEventListener("click", runScheduler);
elements.themeToggle.addEventListener("click", () => {
  document.documentElement.classList.toggle("light");
  localStorage.setItem("theme", document.documentElement.classList.contains("light") ? "light" : "dark");
});

if (localStorage.getItem("theme") === "light") {
  document.documentElement.classList.add("light");
}

const lastUpload = localStorage.getItem("lastUpload");
if (lastUpload) {
  elements.lastUpload.textContent = formatDateTime(lastUpload);
}

renderCalendar(null);
loadScheduleJson(true);
refreshStatus();

async function selectFile(file) {
  if (!file) {
    return;
  }

  const extension = getExtension(file.name);
  if (![".csv", ".xlsx"].includes(extension)) {
    showToast("Only .csv and .xlsx files are supported.", "error");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showToast("Maximum upload size is 10 MB.", "error");
    return;
  }

  state.file = file;
  updateFilePreview();

  if (extension === ".csv") {
    const text = await file.text();
    state.parsedRows = parseCsv(text);
    updateStatsFromRows(state.parsedRows);
    renderCalendar(state.parsedRows);
  } else {
    state.parsedRows = [];
    showToast("XLSX selected. Upload it to rebuild the published calendar.", "success");
  }
}

function updateFilePreview() {
  if (!state.file) {
    elements.fileName.textContent = "No file selected";
    elements.fileMeta.textContent = "CSV and XLSX are supported";
    elements.progressBar.style.width = "0";
    return;
  }
  elements.fileName.textContent = state.file.name;
  elements.fileMeta.textContent = `${getExtension(state.file.name).toUpperCase().slice(1)} · ${formatBytes(state.file.size)}`;
}

async function uploadSchedule() {
  const workerUrl = requireWorkerUrl();
  if (!workerUrl || !state.file) {
    if (!state.file) {
      showToast("Choose a schedule file first.", "error");
    }
    return;
  }

  const formData = new FormData();
  formData.append("schedule_file", state.file);
  setLoading(true);
  elements.progressBar.style.width = "35%";

  try {
    const previousGeneratedAt = state.schedule?.generated_at || "";
    const response = await fetch(`${workerUrl}/upload`, {
      method: "POST",
      body: formData,
    });
    elements.progressBar.style.width = "78%";
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Upload failed.");
    }
    elements.progressBar.style.width = "100%";
    localStorage.setItem("lastUpload", payload.uploadedAt);
    elements.lastUpload.textContent = formatDateTime(payload.uploadedAt);
    if (payload.workflowDispatched === false && payload.workflowWarning) {
      showToast(`Schedule uploaded. Workflow warning: ${payload.workflowWarning}`, "error");
    } else {
      showToast("Schedule uploaded. Calendar rebuild started.", "success");
    }
    refreshStatus();
    pollScheduleJson(previousGeneratedAt);
  } catch (error) {
    elements.progressBar.style.width = "0";
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function loadScheduleJson(silent = false) {
  try {
    const schedule = await fetchJson(`${SCHEDULE_JSON_URL}?v=${Date.now()}`);
    state.schedule = schedule;
    setStatsFromSchedule(schedule);
    renderSchedule(schedule);
    if (!silent) {
      showToast("Published calendar loaded.", "success");
    }
    return schedule;
  } catch (error) {
    if (!silent) {
      showToast("Calendar JSON is not available yet.", "error");
    }
    return null;
  }
}

async function pollScheduleJson(previousGeneratedAt) {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await delay(5000);
    const schedule = await loadScheduleJson(true);
    if (schedule && schedule.generated_at !== previousGeneratedAt) {
      showToast("Calendar updated from published JSON.", "success");
      refreshStatus();
      return;
    }
  }
  showToast("Upload finished, but GitHub Pages has not published the new calendar yet.", "error");
}

async function runScheduler() {
  const workerUrl = requireWorkerUrl();
  if (!workerUrl) {
    return;
  }

  elements.runScheduler.disabled = true;
  try {
    const response = await fetch(`${workerUrl}/run-scheduler`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Could not start scheduler.");
    }
    showToast("Scheduler workflow started.", "success");
    setTimeout(refreshStatus, 1600);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.runScheduler.disabled = false;
  }
}

async function refreshStatus() {
  const workerUrl = state.workerUrl;
  if (!workerUrl) {
    setStatus("github", "Worker URL needed", "pending");
    setStatus("scheduler", "Worker URL needed", "pending");
    setStatus("dingtalk", "Worker URL needed", "pending");
    return;
  }

  try {
    const health = await fetchJson(`${workerUrl}/health`);
    setStatus("github", health.github ? "Connected" : "Missing config", health.github ? "ready" : "error");
    setStatus("dingtalk", health.dingtalk ? "Configured" : "Not configured", health.dingtalk ? "ready" : "pending");
  } catch (error) {
    setStatus("github", "Unavailable", "error");
    setStatus("dingtalk", "Unknown", "pending");
  }

  try {
    const status = await fetchJson(`${workerUrl}/status`);
    const run = status.scheduler;
    if (!run) {
      setStatus("scheduler", "No workflow run", "pending");
      return;
    }
    const label = run.conclusion || run.status || "Unknown";
    setStatus("scheduler", label, label === "success" ? "ready" : "pending");
  } catch (error) {
    setStatus("scheduler", "Unavailable", "error");
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function setStatus(key, text, stateName) {
  const statusElement = elements[`${key}Status`];
  const dotElement = elements[`${key}Dot`];
  statusElement.textContent = text;
  dotElement.className = `status-dot ${stateName}`;
}

function requireWorkerUrl() {
  const workerUrl = normalizeUrl(elements.workerUrl.value);
  if (!workerUrl) {
    showToast("Add your Cloudflare Worker URL first.", "error");
    return "";
  }
  state.workerUrl = workerUrl;
  elements.workerUrl.value = workerUrl;
  localStorage.setItem("workerUrl", workerUrl);
  return workerUrl;
}

function normalizeUrl(value) {
  return value.trim().replace(/\/+$/, "");
}

function updateStats() {
  if (state.schedule) {
    setStatsFromSchedule(state.schedule);
    return;
  }
  updateStatsFromRows(state.parsedRows);
}

function updateStatsFromRows(rows) {
  if (!rows.length) {
    elements.totalEngineer.textContent = "0";
    elements.totalEvents.textContent = "0";
    elements.scheduleMonth.textContent = "-";
    elements.scheduleYear.textContent = "-";
    return;
  }

  const summary = summarizeCsvRows(rows);
  elements.totalEngineer.textContent = summary.engineers.size;
  elements.totalEvents.textContent = summary.totalEvents;
  elements.scheduleMonth.textContent = summary.monthName || "-";
  elements.scheduleYear.textContent = summary.year || "-";
}

function setStatsFromSchedule(schedule) {
  elements.totalEngineer.textContent = schedule.stats?.total_engineers ?? schedule.engineers?.length ?? 0;
  elements.totalEvents.textContent = schedule.stats?.total_events ?? schedule.events?.length ?? 0;
  elements.scheduleMonth.textContent = schedule.month_name || schedule.month || "-";
  elements.scheduleYear.textContent = schedule.year || "-";
}

function summarizeCsvRows(rows) {
  const monthYear = detectMonthYear(rows);
  const engineers = new Set();
  let totalEvents = 0;
  let headerIndex = -1;
  let dayColumns = new Map();

  rows.forEach((row, index) => {
    if (row[0]?.toLowerCase() === "no" && row[1]?.toLowerCase() === "nama") {
      headerIndex = index;
      dayColumns = findDayColumns(rows[index + 1] || []);
      return;
    }
    if (headerIndex >= 0 && index > headerIndex + 1) {
      if (row[0]?.toLowerCase() === "no" || row[0]?.toLowerCase().startsWith("task")) {
        headerIndex = -1;
        return;
      }
      if (/^\d+$/.test(row[0] || "") && row[1]) {
        engineers.add(row[1]);
        for (const column of dayColumns.keys()) {
          if ((row[column] || "").trim()) {
            totalEvents += 1;
          }
        }
      }
    }
  });

  return { ...monthYear, engineers, totalEvents };
}

function detectMonthYear(rows) {
  const months = {
    januari: "Januari",
    februari: "Februari",
    maret: "Maret",
    april: "April",
    mei: "Mei",
    juni: "Juni",
    juli: "Juli",
    agustus: "Agustus",
    september: "September",
    oktober: "Oktober",
    november: "November",
    desember: "Desember",
  };
  for (const row of rows.slice(0, 10)) {
    const text = row.join(" ").toLowerCase();
    const monthKey = Object.keys(months).find((name) => text.includes(name));
    const year = text.match(/\b(20\d{2})\b/)?.[1];
    if (monthKey && year) {
      return { monthName: months[monthKey], monthNumber: Object.keys(months).indexOf(monthKey) + 1, year };
    }
  }
  return { monthName: "", monthNumber: null, year: "" };
}

function renderCalendar(rows, message = "") {
  elements.calendarGrid.innerHTML = "";
  if (!rows?.length) {
    elements.calendarTitle.textContent = message || "Waiting for file";
    for (let index = 0; index < 35; index += 1) {
      const day = document.createElement("div");
      day.className = "calendar-day muted";
      elements.calendarGrid.append(day);
    }
    return;
  }

  const summary = summarizeCsvRows(rows);
  if (!summary.monthNumber || !summary.year) {
    elements.calendarTitle.textContent = "Preview unavailable";
    return;
  }
  elements.calendarTitle.textContent = `${summary.monthName} ${summary.year}`;
  const eventsByDay = groupEventsByDay(rows);
  const firstDay = new Date(Number(summary.year), summary.monthNumber - 1, 1);
  const daysInMonth = new Date(Number(summary.year), summary.monthNumber, 0).getDate();
  const offset = (firstDay.getDay() + 6) % 7;
  const totalCells = Math.ceil((offset + daysInMonth) / 7) * 7;

  for (let cell = 0; cell < totalCells; cell += 1) {
    const dayNumber = cell - offset + 1;
    const day = document.createElement("div");
    day.className = dayNumber < 1 || dayNumber > daysInMonth ? "calendar-day muted" : "calendar-day";
    if (dayNumber >= 1 && dayNumber <= daysInMonth) {
      day.innerHTML = `<span class="calendar-date">${dayNumber}</span>`;
      for (const event of eventsByDay.get(dayNumber) || []) {
        const item = document.createElement("div");
        item.className = "calendar-event";
        item.textContent = `${event.person}: ${event.task}`;
        day.append(item);
      }
    }
    elements.calendarGrid.append(day);
  }
}

function renderSchedule(schedule) {
  elements.calendarGrid.innerHTML = "";
  elements.calendarTitle.textContent = `${schedule.month_name || schedule.month} ${schedule.year}`;
  const weeks = schedule.calendar?.weeks || buildWeeksFromEvents(schedule);

  for (const week of weeks) {
    for (const entry of week) {
      const day = document.createElement("div");
      if (!entry) {
        day.className = "calendar-day muted";
        elements.calendarGrid.append(day);
        continue;
      }

      day.className = "calendar-day";
      day.innerHTML = `<span class="calendar-date">${entry.day}</span>`;
      for (const event of entry.events || []) {
        const item = document.createElement("div");
        item.className = "calendar-event";
        if (event.color) {
          item.style.borderLeftColor = `#${event.color}`;
        }
        item.innerHTML = [
          `<strong>${escapeHtml(event.person)}</strong>`,
          `<span>${escapeHtml(event.task_code)}</span>`,
        ].join(" ");
        day.append(item);
      }
      elements.calendarGrid.append(day);
    }
  }
}

function buildWeeksFromEvents(schedule) {
  const grouped = new Map();
  for (const event of schedule.events || []) {
    const day = Number(event.date.slice(8, 10));
    const events = grouped.get(day) || [];
    events.push(event);
    grouped.set(day, events);
  }

  const firstDay = new Date(Number(schedule.year), Number(schedule.month) - 1, 1);
  const daysInMonth = new Date(Number(schedule.year), Number(schedule.month), 0).getDate();
  const offset = (firstDay.getDay() + 6) % 7;
  const totalCells = Math.ceil((offset + daysInMonth) / 7) * 7;
  const weeks = [];
  let week = [];

  for (let cell = 0; cell < totalCells; cell += 1) {
    const day = cell - offset + 1;
    week.push(
      day < 1 || day > daysInMonth
        ? null
        : { day, events: grouped.get(day) || [] },
    );
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  return weeks;
}

function groupEventsByDay(rows) {
  const grouped = new Map();
  let headerIndex = -1;
  let dayColumns = new Map();
  rows.forEach((row, index) => {
    if (row[0]?.toLowerCase() === "no" && row[1]?.toLowerCase() === "nama") {
      headerIndex = index;
      dayColumns = findDayColumns(rows[index + 1] || []);
      return;
    }
    if (headerIndex >= 0 && index > headerIndex + 1) {
      if (row[0]?.toLowerCase() === "no" || row[0]?.toLowerCase().startsWith("task")) {
        headerIndex = -1;
        return;
      }
      if (/^\d+$/.test(row[0] || "") && row[1]) {
        for (const [column, day] of dayColumns.entries()) {
          const task = (row[column] || "").trim();
          if (!task) {
            continue;
          }
          const events = grouped.get(day) || [];
          events.push({ person: row[1], task });
          grouped.set(day, events);
        }
      }
    }
  });
  return grouped;
}

function findDayColumns(row) {
  const columns = new Map();
  row.forEach((value, index) => {
    if (/^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 31) {
      columns.set(index, Number(value));
    }
  });
  return columns;
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
      row.push(cell.trim());
      cell = "";
    } else if (char === "\n") {
      row.push(cell.trim());
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell.trim());
  if (row.some(Boolean)) {
    rows.push(row);
  }
  return rows;
}

function getExtension(filename) {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function setLoading(isLoading) {
  elements.uploadButton.disabled = isLoading;
  elements.uploadButton.classList.toggle("loading", isLoading);
}

function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastHost.append(toast);
  setTimeout(() => toast.remove(), 4200);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
