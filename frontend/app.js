const apiBaseInput = document.getElementById("apiBase");
const saveBaseBtn = document.getElementById("saveBase");
const actionButtons = Array.from(document.querySelectorAll("button[data-action]"));

const featureOutput = document.getElementById("featureOutput");

const outputMap = {
  login: document.getElementById("userFlowOutput"),
  sync: document.getElementById("userFlowOutput"),
  backfill: document.getElementById("userFlowOutput"),
  generate: document.getElementById("playlistOutput") || document.getElementById("userFlowOutput"),
  contextPlaylist: document.getElementById("playlistOutput") || featureOutput,
  dashboard: document.getElementById("dashboardCharts"),
  songs: document.getElementById("songsOutput"),
  topSongs: document.getElementById("filterOutput"),
  songsByTag: document.getElementById("filterOutput"),
  topByTag: document.getElementById("filterOutput"),
  tasteTimeline: featureOutput,
  discoveryFeed: featureOutput,
  dataQuality: featureOutput,
  submitFeedback: featureOutput,
  feedbackSummary: featureOutput,
  createGoal: featureOutput,
  goalsStatus: featureOutput,
  dedupPreview: featureOutput,
  dedupApply: featureOutput,
  dedupUndo: featureOutput,
  weeklyReport: featureOutput,
  opsHealth: featureOutput,
  opsMetrics: featureOutput,
};

const loadingMessages = {
  login: "Waiting for Spotify authentication",
  sync: "Syncing listening history",
  backfill: "Backfilling metadata",
  generate: "Generating playlist",
  contextPlaylist: "Generating context playlist",
  dashboard: "Loading dashboard stats",
  songs: "Loading songs",
  topSongs: "Loading top songs",
  songsByTag: "Loading songs by tag",
  topByTag: "Loading top songs by tag",
  tasteTimeline: "Loading taste timeline",
  discoveryFeed: "Loading discovery feed",
  dataQuality: "Checking data quality",
  submitFeedback: "Saving feedback",
  feedbackSummary: "Loading feedback summary",
  createGoal: "Creating goal",
  goalsStatus: "Checking goals",
  dedupPreview: "Loading dedup preview",
  dedupApply: "Applying dedup safely",
  dedupUndo: "Undoing dedup batch",
  weeklyReport: "Generating weekly report",
  opsHealth: "Checking API health",
  opsMetrics: "Loading operations metrics",
};

const FIELD_LABELS = {
  id: "ID",
  title: "Song Title",
  artist: "Artist",
  artist_id: "Artist ID",
  spotify_id: "Spotify Track ID",
  genre: "Genre",
  listeners: "Last.fm Listeners",
  playcount: "Last.fm Play Count",
  popularity_score: "Popularity Score",
  last_listened_at: "Last Played At",
  plays: "Play Events",
  day: "Day",
  week: "Week",
  hour: "Hour (24h)",
  key: "Field",
  value: "Value",
  message: "Message",
  fetched_items: "Spotify Play Events Fetched",
  new_songs: "New Unique Songs Added",
  new_history_rows: "New Play Events Saved",
  existing_history_rows: "Duplicate Events Skipped",
  received_items: "Imported Records Received",
  scanned: "Songs Scanned",
  updated: "Songs Updated",
  user_id: "Spotify User ID",
  remaining_hint: "Next Step",
  action: "Action",
  count: "Count",
  goal_id: "Goal ID",
  goal_type: "Goal Type",
  target: "Goal Target",
  progress: "Current Progress",
  percent: "Coverage %",
  metric: "Metric",
  group_key: "Duplicate Group",
  merged_songs: "Songs Merged",
  file_path: "Report File",
  score: "Recommendation Score",
  reasons: "Why Recommended",
  tracks_added: "Tracks Added",
  resolved_spotify_ids_now: "Spotify IDs Resolved Now",
  recommendation_candidates: "Recommendation Candidates",
  enrichment_status: "Metadata Status",
  enrichment_error: "Metadata Error",
  discovery_source: "Discovery Source",
  discovery_confidence: "Discovery Confidence",
  known_track_ratio: "Known Track Ratio",
  token_expires_at: "Token Expires At",
  job_id: "Job ID",
  status: "Status",
};

const SECTION_LABELS = {
  top_artists: "Top Artists",
  top_genres: "Top Genres",
  daily_genre: "Daily Genre Breakdown",
  weekly_genre: "Weekly Genre Breakdown",
  monthly_top_artists: "Monthly Top Artists",
  monthly_top_genres: "Monthly Top Genres",
  coverage: "Data Coverage",
  summary: "Feedback Summary",
  items: "Items",
  goals: "Goal Status",
  duplicate_groups: "Duplicate Groups",
  explanations: "Recommendation Explanations",
  enrichment_status: "Metadata Enrichment Status",
  comparison: "Period Comparison",
  quality_controls: "Playlist Quality Controls",
  components: "Score Components",
  meta: "Request Metadata",
  result: "Result",
};

const BASE_KEY = "musicintel_api_base";
const DEFAULT_BASE = "http://127.0.0.1:8000";
const USER_KEY = "musicintel_user_id";

function getBaseUrl() {
  if (apiBaseInput) {
    return (apiBaseInput.value || "").trim().replace(/\/$/, "");
  }
  return (localStorage.getItem(BASE_KEY) || DEFAULT_BASE).replace(/\/$/, "");
}

function saveBaseUrl() {
  localStorage.setItem(BASE_KEY, getBaseUrl());
}

function loadBaseUrl() {
  const saved = localStorage.getItem(BASE_KEY);
  if (apiBaseInput) {
    apiBaseInput.value = saved || DEFAULT_BASE;
  }

  const apiBaseDisplay = document.getElementById("apiBaseDisplay");
  if (apiBaseDisplay) {
    apiBaseDisplay.textContent = saved || DEFAULT_BASE;
  }
}
function cleanupLegacyUi() {
  document.querySelectorAll(".card h2").forEach((heading) => {
    const text = (heading.textContent || "").trim();
    if (text === "Dashboard Tables" || text === "Dashboard Notes" || text === "Go To Pages") {
      heading.closest(".card")?.remove();
    }
  });

  document.querySelectorAll(".page-meta").forEach((node) => {
    const text = (node.textContent || "").trim();
    if (text.startsWith("Tip:")) {
      node.remove();
    }
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'\"]/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    "\"": "&quot;",
  }[ch]));
}

function prettyLabel(key) {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (["last_listened_at", "played_at", "day", "week", "merged_at", "token_expires_at"].includes(key) || key.endsWith("_date") || key.endsWith("_time") || key.endsWith("_at")) {
    const dt = new Date(value);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleString();
    }
  }

  if (Array.isArray(value)) {
    return value.join(" | ");
  }

  if (typeof value === "number") {
    if (["popularity_score", "score", "discovery_confidence", "known_track_ratio"].includes(key)) {
      return value.toFixed(3);
    }
    return new Intl.NumberFormat().format(value);
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

let songExplorerRows = [];
let songExplorerColumns = [];
let songExplorerSort = { column: "", direction: "asc" };

function renderTable(rows) {
  if (!rows.length) {
    return '<div class="output-hint">No rows</div>';
  }

  const cols = Object.keys(rows[0]);
  const head = cols.map((c) => `<th title="${escapeHtml(prettyLabel(c))}">${escapeHtml(prettyLabel(c))}</th>`).join("");

  const body = rows.map((row) => {
    const cells = cols.map((c) => `<td>${escapeHtml(formatValue(c, row[c]))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  return `<table class="output-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderSongExplorerRows(rows, cols) {
  if (!rows.length) {
    return `<tr><td colspan="${cols.length}" class="output-hint">No matching songs</td></tr>`;
  }

  return rows.map((row) => {
    const cells = cols.map((c) => `<td>${escapeHtml(formatValue(c, row[c]))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
}

function getSongExplorerFilterConfig(column) {
  const values = [...new Set(songExplorerRows.map((row) => formatValue(column, row[column])).filter((value) => value && value !== "-"))].sort((a, b) => a.localeCompare(b));
  const categoricalColumns = new Set(["artist", "genre", "enrichment_status", "discovery_source"]);
  const useSelect = categoricalColumns.has(column) || (values.length > 0 && values.length <= 20);
  return { values, useSelect };
}

function getSongExplorerFilters(output) {
  const inputs = Array.from(output.querySelectorAll(".song-filter-input"));
  return Object.fromEntries(inputs.map((input) => [input.dataset.column, (input.value || "").trim().toLowerCase()]));
}

function compareSongExplorerValues(column, left, right) {
  const leftRaw = left[column];
  const rightRaw = right[column];

  if (leftRaw === null || leftRaw === undefined || leftRaw === "") return 1;
  if (rightRaw === null || rightRaw === undefined || rightRaw === "") return -1;

  if (typeof leftRaw === "number" && typeof rightRaw === "number") {
    return leftRaw - rightRaw;
  }

  if (["last_listened_at", "played_at", "day", "week", "merged_at", "token_expires_at"].includes(column) || column.endsWith("_date") || column.endsWith("_time") || column.endsWith("_at")) {
    const leftTime = new Date(leftRaw).getTime();
    const rightTime = new Date(rightRaw).getTime();
    if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime)) {
      return leftTime - rightTime;
    }
  }

  return String(formatValue(column, leftRaw)).localeCompare(String(formatValue(column, rightRaw)), undefined, { numeric: true, sensitivity: "base" });
}

function getFilteredSongExplorerRows(output) {
  const filters = getSongExplorerFilters(output);
  const filtered = songExplorerRows.filter((row) => songExplorerColumns.every((col) => {
    const needle = filters[col];
    if (!needle) return true;
    const raw = row[col];
    const formatted = formatValue(col, raw);
    const haystack = `${raw ?? ""} ${formatted}`.toLowerCase();
    return haystack.includes(needle);
  }));

  if (songExplorerSort.column) {
    filtered.sort((a, b) => {
      const result = compareSongExplorerValues(songExplorerSort.column, a, b);
      return songExplorerSort.direction === "asc" ? result : -result;
    });
  }

  return filtered;
}

function refreshSongExplorerView() {
  const output = document.getElementById("songsOutput");
  if (!output) return;

  const filtered = getFilteredSongExplorerRows(output);
  const tbody = output.querySelector("#songExplorerTableBody");
  const count = output.querySelector("#songExplorerVisibleCount");
  const sort = output.querySelector("#songExplorerSortStatus");

  if (tbody) {
    tbody.innerHTML = renderSongExplorerRows(filtered, songExplorerColumns);
  }
  if (count) {
    count.textContent = `${filtered.length} of ${songExplorerRows.length} songs shown`;
  }
  if (sort) {
    sort.textContent = songExplorerSort.column
      ? `Sorted by ${prettyLabel(songExplorerSort.column)} (${songExplorerSort.direction})`
      : "No active sort";
  }
}

function applySongExplorerFilters() {
  refreshSongExplorerView();
}

function toggleSongExplorerSort(column) {
  if (songExplorerSort.column === column) {
    songExplorerSort.direction = songExplorerSort.direction === "asc" ? "desc" : "asc";
  } else {
    songExplorerSort = { column, direction: "asc" };
  }
  refreshSongExplorerView();
}

function setSongExplorerOutput(el, rows) {
  if (!el) return;

  songExplorerRows = Array.isArray(rows) ? rows : [];
  songExplorerColumns = songExplorerRows.length ? Object.keys(songExplorerRows[0]) : [];
  songExplorerSort = { column: "", direction: "asc" };

  if (!songExplorerRows.length) {
    el.innerHTML = `<div class="output-title">Song Explorer</div><div class="output-hint">No songs found</div>`;
    return;
  }

  const head = songExplorerColumns.map((c) => `
    <th>
      <button class="sort-header-btn" type="button" data-column="${escapeHtml(c)}" title="Sort by ${escapeHtml(prettyLabel(c))}">
        ${escapeHtml(prettyLabel(c))}
      </button>
    </th>
  `).join("");
  const filterRow = songExplorerColumns.map((c) => {
    const config = getSongExplorerFilterConfig(c);
    if (config.useSelect) {
      const options = config.values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      return `
        <th>
          <select class="song-filter-input" data-column="${escapeHtml(c)}">
            <option value="">All ${escapeHtml(prettyLabel(c))}</option>
            ${options}
          </select>
        </th>
      `;
    }

    return `
      <th>
        <input
          class="song-filter-input"
          data-column="${escapeHtml(c)}"
          type="text"
          placeholder="Filter ${escapeHtml(prettyLabel(c))}"
        />
      </th>
    `;
  }).join("");

  el.innerHTML = `
    <div class="output-title">Song Explorer</div>
    <div class="song-table-toolbar">
      <div class="metric-inline" id="songExplorerVisibleCount">${songExplorerRows.length} of ${songExplorerRows.length} songs shown</div>
      <div class="metric-inline" id="songExplorerSortStatus">No active sort</div>
    </div>
    <table class="output-table song-explorer-table">
      <thead>
        <tr>${head}</tr>
        <tr class="filter-row">${filterRow}</tr>
      </thead>
      <tbody id="songExplorerTableBody">${renderSongExplorerRows(songExplorerRows, songExplorerColumns)}</tbody>
    </table>
  `;

  Array.from(el.querySelectorAll(".song-filter-input")).forEach((input) => {
    input.addEventListener("input", applySongExplorerFilters);
    input.addEventListener("change", applySongExplorerFilters);
  });

  Array.from(el.querySelectorAll(".sort-header-btn")).forEach((button) => {
    button.addEventListener("click", () => toggleSongExplorerSort(button.dataset.column));
  });
}

function renderKeyValue(obj) {
  const rows = Object.entries(obj).map(([k, v]) => ({ key: prettyLabel(k), value: formatValue(k, v) }));
  return renderTable(rows);
}

function renderPayload(payload) {
  if (Array.isArray(payload)) {
    if (!payload.length) {
      return '<div class="output-hint">No data</div>';
    }

    if (typeof payload[0] === "object" && payload[0] !== null) {
      return renderTable(payload);
    }

    return renderTable(payload.map((v) => ({ value: v })));
  }

  if (payload && typeof payload === "object") {
    const sections = Object.entries(payload).map(([key, value]) => {
      const sectionTitle = SECTION_LABELS[key] || prettyLabel(key);

      if (Array.isArray(value)) {
        return `<div class="output-section"><div class="output-title">${escapeHtml(sectionTitle)}</div>${renderPayload(value)}</div>`;
      }

      if (value && typeof value === "object") {
        return `<div class="output-section"><div class="output-title">${escapeHtml(sectionTitle)}</div>${renderKeyValue(value)}</div>`;
      }

      return `<div class="output-section"><strong>${escapeHtml(sectionTitle)}:</strong> ${escapeHtml(formatValue(key, value))}</div>`;
    });

    return sections.join("") || '<div class="output-hint">No data</div>';
  }

  return `<div>${escapeHtml(payload)}</div>`;
}

function setOutput(el, title, payload) {
  if (!el) return;
  el.innerHTML = `<div class="output-title">${escapeHtml(title)}</div>${renderPayload(payload)}`;
}

function setBackfillOutput(el, payload) {
  if (!el) return;

  const scanned = Number(payload?.scanned || 0);
  const updated = Number(payload?.updated || 0);
  const mode = payload?.mode || {};
  const modeLabel = mode.retry_failed && mode.retry_partial
    ? "Retry failed + partial"
    : mode.retry_failed
      ? "Retry failed"
      : mode.retry_partial
        ? "Retry partial"
        : "Fast mode";

  el.innerHTML = `
    <div class="output-title">Backfill Result</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Songs Scanned</div>
        <div class="metric-value">${escapeHtml(formatValue("scanned", scanned))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Songs Backfilled</div>
        <div class="metric-value">${escapeHtml(formatValue("updated", updated))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Mode</div>
        <div class="metric-value">${escapeHtml(modeLabel)}</div>
      </div>
    </div>
    ${payload?.remaining_hint ? `<div class="metric-inline">${escapeHtml(String(payload.remaining_hint))}</div>` : ""}
    ${renderPayload(payload)}
  `;
}

function setPlaylistOutput(el, payload) {
  if (!el) return;

  const tracksAdded = Number(payload?.tracks_added || 0);
  const candidates = Number(payload?.recommendation_candidates || 0);
  const resolvedNow = Number(payload?.resolved_spotify_ids_now || 0);
  const knownRatio = Number(payload?.known_track_ratio || 0);
  const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];

  el.innerHTML = `
    <div class="output-title">Playlist Result</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Tracks Added</div>
        <div class="metric-value">${escapeHtml(formatValue("tracks_added", tracksAdded))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Candidates</div>
        <div class="metric-value">${escapeHtml(formatValue("recommendation_candidates", candidates))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Resolved Now</div>
        <div class="metric-value">${escapeHtml(formatValue("resolved_spotify_ids_now", resolvedNow))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Known Ratio</div>
        <div class="metric-value">${escapeHtml(formatValue("known_track_ratio", knownRatio))}</div>
      </div>
    </div>
    ${warnings.length ? `<div class="output-section"><div class="output-title">Warnings</div>${renderPayload(warnings.map((message) => ({ message })))}</div>` : ""}
    ${renderPayload(payload)}
  `;
}

function setActionsDisabled(disabled) {
  actionButtons.forEach((btn) => {
    btn.disabled = disabled;
    btn.style.opacity = disabled ? "0.7" : "1";
    btn.style.cursor = disabled ? "not-allowed" : "pointer";
  });
}

function startLoading(outputEl, action) {
  if (!outputEl) return () => {};

  const baseMessage = loadingMessages[action] || "Loading";
  let dots = 0;

  const tick = () => {
    dots = (dots + 1) % 4;
    setOutput(outputEl, "Working", { message: `${baseMessage}${".".repeat(dots)}` });
  };

  tick();
  const intervalId = setInterval(tick, 350);

  return () => clearInterval(intervalId);
}

function buildSparklinePoints(values, width, height, pad) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const step = values.length > 1 ? (width - 2 * pad) / (values.length - 1) : 0;

  return values.map((v, i) => {
    const x = pad + i * step;
    const y = height - pad - ((v - min) / range) * (height - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function renderSparklineChart(title, rows, labelKey, valueKey) {
  const safeRows = Array.isArray(rows) ? rows.slice(-20) : [];
  if (!safeRows.length) {
    return `<div class="chart-card"><h3>${escapeHtml(title)}</h3><div class="output-hint">No data</div></div>`;
  }

  const values = safeRows.map((r) => Number(r[valueKey] || 0));
  const labels = safeRows.map((r) => String(r[labelKey]));
  const width = 340;
  const height = 120;
  const points = buildSparklinePoints(values, width, height, 12);
  const latest = values[values.length - 1] || 0;
  const peak = Math.max(...values, 0);

  return `
    <div class="chart-card">
      <h3>${escapeHtml(title)}</h3>
      <div class="metric-inline">Latest: <strong>${escapeHtml(formatValue(valueKey, latest))}</strong> | Peak: <strong>${escapeHtml(formatValue(valueKey, peak))}</strong></div>
      <svg class="spark-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)} trend">
        <polyline points="${points}" class="spark-line"></polyline>
      </svg>
      <div class="spark-axis">${escapeHtml(labels[0])} to ${escapeHtml(labels[labels.length - 1])}</div>
    </div>
  `;
}

function renderHorizontalRanking(title, rows, labelKey, valueKey, topN = 10) {
  const safeRows = Array.isArray(rows) ? rows.slice(0, topN) : [];
  if (!safeRows.length) {
    return `<div class="chart-card"><h3>${escapeHtml(title)}</h3><div class="output-hint">No data</div></div>`;
  }

  const maxVal = Math.max(...safeRows.map((r) => Number(r[valueKey] || 0)), 1);
  const bars = safeRows.map((r) => {
    const label = escapeHtml(formatValue(labelKey, r[labelKey]));
    const val = Number(r[valueKey] || 0);
    const width = Math.max(4, Math.round((val / maxVal) * 100));
    return `
      <div class="bar-row">
        <div class="bar-label">${label}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
        <div class="bar-value">${escapeHtml(formatValue(valueKey, val))}</div>
      </div>
    `;
  }).join("");

  return `<div class="chart-card"><h3>${escapeHtml(title)}</h3>${bars}</div>`;
}

function renderHourHeatmap(rows) {
  const bins = Array.from({ length: 24 }, (_, hour) => {
    const hit = (rows || []).find((r) => Number(r.hour) === hour);
    return { hour, plays: Number(hit?.plays || 0) };
  });

  const max = Math.max(...bins.map((b) => b.plays), 1);
  const cells = bins.map((b) => {
    const intensity = b.plays / max;
    const alpha = (0.15 + intensity * 0.85).toFixed(2);
    return `
      <div class="hour-cell" style="background: rgba(31, 123, 197, ${alpha})" title="${b.hour}:00 - ${b.plays} plays">
        <span>${String(b.hour).padStart(2, "0")}</span>
      </div>
    `;
  }).join("");

  return `
    <div class="chart-card">
      <h3>Listening by Hour (Heatmap)</h3>
      <div class="hour-grid">${cells}</div>
      <div class="spark-axis">Darker cells mean more play events in that hour.</div>
    </div>
  `;
}

function renderDashboardCharts(data) {
  const chartEl = document.getElementById("dashboardCharts");
  if (!chartEl) return;

  const daily = (data.daily_listening || []).slice().reverse();
  const weekly = (data.weekly_listening || []).slice().reverse();
  const hourly = data.hourly_listening || [];
  const genres = data.top_genres || [];
  const artists = data.top_artists || [];

  const totalPlays = Number(data.total_plays || daily.reduce((sum, row) => sum + Number(row.plays || 0), 0));
  const activeDays = daily.filter((row) => Number(row.plays || 0) > 0).length;
  const delta = data.comparison?.delta;

  chartEl.innerHTML = [
    `<div class="metric-strip">
      <div class="metric-card"><div class="metric-label">Plays (Window)</div><div class="metric-value">${escapeHtml(formatValue("plays", totalPlays))}</div></div>
      <div class="metric-card"><div class="metric-label">Active Days</div><div class="metric-value">${escapeHtml(formatValue("days", activeDays))}</div></div>
      <div class="metric-card"><div class="metric-label">Top Genres</div><div class="metric-value">${escapeHtml(formatValue("count", genres.length))}</div></div>
      <div class="metric-card"><div class="metric-label">Trend vs Previous</div><div class="metric-value">${delta === undefined || delta === null ? "N/A" : (delta >= 0 ? "+" : "") + formatValue("plays", delta)}</div></div>
    </div>`,
    renderSparklineChart("Daily Trend", daily, "day", "plays"),
    renderSparklineChart("Weekly Trend", weekly, "week", "plays"),
    renderHourHeatmap(hourly),
    renderHorizontalRanking("Top Genres", genres, "genre", "plays", 10),
    renderHorizontalRanking("Top Artists", artists, "artist", "plays", 10),
  ].join("");
}

async function parseBody(response) {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

async function callApi(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const userId = localStorage.getItem(USER_KEY);
  if (userId) {
    headers["X-User-Id"] = userId;
  }
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const response = await fetch(`${getBaseUrl()}${path}`, {
    ...options,
    headers,
  });

  const data = await parseBody(response);

  if (!response.ok) {
    const detail = data?.detail || data?.error || data?.message;
    throw new Error(detail ? `${response.status}: ${detail}` : JSON.stringify({ status: response.status, data }, null, 2));
  }

  return data;
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loginWithPopup() {
  const popup = window.open(
    `${getBaseUrl()}/user/login`,
    "spotify_login",
    "width=520,height=740"
  );

  if (!popup) {
    throw new Error("Popup blocked by browser. Allow popups and try again.");
  }

  const timeoutMs = 120000;
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    await sleep(1000);

    if (popup.closed) {
      const status = await callApi("/user/session");
      if (status.logged_in) {
        return status;
      }
      throw new Error("Login window closed before authentication completed.");
    }

    const status = await callApi("/user/session");
    if (status.logged_in) {
      try {
        popup.close();
      } catch {}
      return status;
    }
  }

  try {
    popup.close();
  } catch {}

  throw new Error("Login timed out. Please try again.");
}

async function handleAction(action) {
  const output = outputMap[action];
  let stopLoading = null;

  try {
    if (!getBaseUrl()) {
      throw new Error("Set API Base URL first.");
    }

    stopLoading = startLoading(output, action);
    setActionsDisabled(true);

    if (action === "login") {
      const status = await loginWithPopup();
      if (status.user_id) {
        localStorage.setItem(USER_KEY, status.user_id);
      }
      setOutput(output, "Login", {
        message: "Successfully logged in",
        user_id: status.user_id,
      });
      return;
    }

    if (action === "sync") {
      const data = await callApi("/user/sync-history", {
        method: "POST",
      });
      setOutput(output, "Sync Result", data);
      return;
    }

    if (action === "backfill") {
      const limitInput = document.getElementById("backfillLimit");
      const retryPartialInput = document.getElementById("retryPartial");
      const retryFailedInput = document.getElementById("retryFailed");
      const limit = limitInput ? Number(limitInput.value || 500) : 500;
      const retryPartial = Boolean(retryPartialInput && retryPartialInput.checked);
      const retryFailed = Boolean(retryFailedInput && retryFailedInput.checked);
      const params = new URLSearchParams({
        limit: String(limit),
        retry_partial: String(retryPartial),
        retry_failed: String(retryFailed),
      });
      const data = await callApi(`/user/backfill-metadata?${params.toString()}`, { method: "POST" });
      setBackfillOutput(output, data);
      return;
    }

    if (action === "generate") {
      const maxTracks = Number(document.getElementById("playlistMaxTracks")?.value || 30);
      const diversity = Number(document.getElementById("playlistDiversity")?.value || 0.5);
      const familiarity = Number(document.getElementById("playlistFamiliarity")?.value || 0.5);
      const minKnownRatio = Number(document.getElementById("playlistMinKnownRatio")?.value || 0.6);

      const data = await callApi("/playlists/generate", {
        method: "POST",
        body: JSON.stringify({
          max_tracks: maxTracks,
          diversity,
          familiarity,
          min_known_ratio: minKnownRatio,
        }),
      });
      setPlaylistOutput(output, data);
      return;
    }

    if (action === "contextPlaylist") {
      const contextEl = document.getElementById("contextName");
      const context = contextEl ? contextEl.value : "focus";
      const data = await callApi(`/playlists/context/${encodeURIComponent(context)}`, { method: "POST" });
      setOutput(output, "Context Playlist Result", data);
      return;
    }

    if (action === "dashboard") {
      const days = Number(document.getElementById("dashboardDays")?.value || 30);
      const compare = document.getElementById("dashboardCompare")?.checked ? "true" : "false";
      const query = new URLSearchParams({ days: String(days), compare_previous: compare });
      const data = await callApi(`/dashboard/stats?${query.toString()}`);
      renderDashboardCharts(data);
      return;
    }

    if (action === "songs") {
      const genreInput = document.getElementById("genre");
      const statusInput = document.getElementById("enrichmentStatus");
      const genre = genreInput ? genreInput.value.trim() : "";
      const enrichmentStatus = statusInput ? statusInput.value.trim() : "";
      const limitInput = document.getElementById("songLimit");
      const limit = limitInput ? Number(limitInput.value || 1000) : 1000;
      const query = new URLSearchParams();
      if (genre) query.set("genre", genre);
      if (enrichmentStatus) query.set("enrichment_status", enrichmentStatus);
      query.set("limit", String(limit));
      const data = await callApi(`/songs/?${query.toString()}`);
      setSongExplorerOutput(output, data);
      return;
    }

    if (action === "topSongs") {
      const data = await callApi("/filter/top-songs");
      setOutput(output, "Top Songs", data);
      return;
    }

    if (action === "songsByTag" || action === "topByTag") {
      const tagInput = document.getElementById("tag");
      const tag = tagInput ? tagInput.value.trim() : "";
      if (!tag) {
        throw new Error("Enter a tag first.");
      }
      const path = action === "songsByTag" ? `/filter/tag/${encodeURIComponent(tag)}` : `/filter/top/${encodeURIComponent(tag)}`;
      const data = await callApi(path);
      setOutput(output, action === "songsByTag" ? "Songs By Tag" : "Top Songs By Tag", data);
      return;
    }

    if (action === "tasteTimeline") {
      const monthsEl = document.getElementById("timelineMonths");
      const months = monthsEl ? Number(monthsEl.value || 6) : 6;
      const data = await callApi(`/insights/taste-timeline?months=${encodeURIComponent(months)}`);
      setOutput(output, "Taste Timeline", data);
      return;
    }

    if (action === "discoveryFeed") {
      const limitEl = document.getElementById("discoveryLimit");
      const limit = limitEl ? Number(limitEl.value || 20) : 20;
      const data = await callApi(`/insights/discovery-feed?limit=${encodeURIComponent(limit)}`);
      setOutput(output, "Discovery Feed", data);
      return;
    }

    if (action === "dataQuality") {
      const data = await callApi("/insights/data-quality");
      setOutput(output, "Data Quality", data);
      return;
    }

    if (action === "submitFeedback") {
      const songIdEl = document.getElementById("feedbackSongId");
      const actionEl = document.getElementById("feedbackAction");
      const songId = songIdEl ? Number(songIdEl.value || 0) : 0;
      const feedbackAction = actionEl ? actionEl.value : "like";

      if (!songId) {
        throw new Error("Enter a valid Song ID.");
      }

      const data = await callApi("/insights/feedback", {
        method: "POST",
        body: JSON.stringify({ song_id: songId, action: feedbackAction }),
      });
      setOutput(output, "Feedback Saved", data);
      return;
    }

    if (action === "feedbackSummary") {
      const data = await callApi("/insights/feedback-summary");
      setOutput(output, "Feedback Summary", data);
      return;
    }

    if (action === "createGoal") {
      const goalTypeEl = document.getElementById("goalType");
      const targetEl = document.getElementById("goalTarget");
      const goalType = goalTypeEl ? goalTypeEl.value : "new_songs_per_week";
      const target = targetEl ? Number(targetEl.value || 1) : 1;

      const data = await callApi("/insights/goals", {
        method: "POST",
        body: JSON.stringify({ goal_type: goalType, target_value: target, period: "weekly" }),
      });
      setOutput(output, "Goal Created", data);
      return;
    }

    if (action === "goalsStatus") {
      const data = await callApi("/insights/goals-status");
      setOutput(output, "Goal Status", data);
      return;
    }

    if (action === "dedupPreview") {
      const groupsEl = document.getElementById("dedupGroups");
      const groups = groupsEl ? Number(groupsEl.value || 20) : 20;
      const data = await callApi(`/insights/dedup-preview?limit_groups=${encodeURIComponent(groups)}`);
      setOutput(output, "Dedup Preview", data);
      return;
    }

    if (action === "dedupApply") {
      const groupsEl = document.getElementById("dedupGroups");
      const groups = groupsEl ? Number(groupsEl.value || 20) : 20;
      const dryRun = document.getElementById("dedupDryRun")?.checked ? "true" : "false";
      const data = await callApi(`/insights/dedup-apply?limit_groups=${encodeURIComponent(groups)}&dry_run=${dryRun}`, { method: "POST" });
      setOutput(output, dryRun === "true" ? "Dedup Dry Run" : "Dedup Applied", data);
      const batchInput = document.getElementById("dedupBatchId");
      if (batchInput && data.batch_id) batchInput.value = data.batch_id;
      return;
    }

    if (action === "dedupUndo") {
      const batchId = (document.getElementById("dedupBatchId")?.value || "").trim();
      if (!batchId) throw new Error("Enter a dedup batch id first.");
      const data = await callApi(`/insights/dedup-undo/${encodeURIComponent(batchId)}`, { method: "POST" });
      setOutput(output, "Dedup Undo", data);
      return;
    }

    if (action === "weeklyReport") {
      const data = await callApi("/reports/weekly", { method: "POST" });
      setOutput(output, "Weekly Report", data);
      return;
    }

    if (action === "opsHealth") {
      const data = await callApi("/ops/health");
      setOutput(output, "API Health", data);
      return;
    }

    if (action === "opsMetrics") {
      const data = await callApi("/ops/metrics");
      setOutput(output, "Operations Metrics", data);
      return;
    }
  } catch (error) {
    setOutput(output, "Request Error", { message: String(error.message || error) });
  } finally {
    if (stopLoading) stopLoading();
    setActionsDisabled(false);
  }
}

if (saveBaseBtn) {
  saveBaseBtn.addEventListener("click", () => {
    saveBaseUrl();
    loadBaseUrl();
    cleanupLegacyUi();
    alert("Saved API base URL.");
  });
}

loadBaseUrl();
    cleanupLegacyUi();

actionButtons.forEach((btn) => {
  btn.addEventListener("click", () => handleAction(btn.dataset.action));
});












