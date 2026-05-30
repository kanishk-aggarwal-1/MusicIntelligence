const apiBaseInput = document.getElementById("apiBase");
const saveBaseBtn = document.getElementById("saveBase");
const actionButtons = Array.from(document.querySelectorAll("button[data-action]"));

const featureOutput = document.getElementById("featureOutput");

const outputMap = {
  login: document.getElementById("userFlowOutput"),
  sync: document.getElementById("userFlowOutput"),
  backfill: document.getElementById("userFlowOutput"),
  generate: document.getElementById("playlistOutput") || document.getElementById("userFlowOutput"),
  previewPlaylist: document.getElementById("playlistOutput") || document.getElementById("userFlowOutput"),
  loadJobs: document.getElementById("jobsOutput") || document.getElementById("userFlowOutput"),
  loadPlaylistHistory: document.getElementById("playlistHistoryOutput") || document.getElementById("playlistOutput"),
  loadGeneratedPlaylist: document.getElementById("playlistHistoryOutput") || document.getElementById("playlistOutput"),
  regenerateGeneratedPlaylist: document.getElementById("playlistHistoryOutput") || document.getElementById("playlistOutput"),
  createFromGeneratedPlaylist: document.getElementById("playlistHistoryOutput") || document.getElementById("playlistOutput"),
  contextPlaylist: document.getElementById("playlistOutput") || featureOutput,
  dashboard: document.getElementById("dashboardCharts"),
  songs: document.getElementById("songsOutput"),
  songDetail: document.getElementById("songDetailOutput") || document.getElementById("songsOutput"),
  songRetryEnrichment: document.getElementById("songDetailOutput") || document.getElementById("songsOutput"),
  songHide: document.getElementById("songDetailOutput") || document.getElementById("songsOutput"),
  songRestore: document.getElementById("songDetailOutput") || document.getElementById("songsOutput"),
  topSongs: document.getElementById("filterOutput"),
  songsByTag: document.getElementById("filterOutput"),
  topByTag: document.getElementById("filterOutput"),
  tasteTimeline: featureOutput,
  discoveryFeed: featureOutput,
  dataQuality: featureOutput,
  retryFailedMetadata: featureOutput,
  retryPartialMetadata: featureOutput,
  clearLastfmCache: featureOutput,
  discoveryPreviewJob: featureOutput,
  acceptDiscoveryCandidates: featureOutput,
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
  sync: "Queueing listening history sync",
  backfill: "Queueing metadata backfill",
  generate: "Generating playlist",
  previewPlaylist: "Building playlist preview",
  loadJobs: "Loading recent jobs",
  loadPlaylistHistory: "Loading saved playlist history",
  loadGeneratedPlaylist: "Loading saved playlist detail",
  regenerateGeneratedPlaylist: "Regenerating saved playlist preview",
  createFromGeneratedPlaylist: "Creating Spotify playlist from saved preview",
  contextPlaylist: "Generating context playlist",
  dashboard: "Loading dashboard stats",
  songs: "Loading songs",
  songDetail: "Loading song detail",
  songRetryEnrichment: "Retrying song enrichment",
  songHide: "Hiding song",
  songRestore: "Restoring song",
  topSongs: "Loading top songs",
  songsByTag: "Loading songs by tag",
  topByTag: "Loading top songs by tag",
  tasteTimeline: "Loading taste timeline",
  discoveryFeed: "Loading discovery feed",
  dataQuality: "Checking data quality",
  retryFailedMetadata: "Queueing failed-metadata retry",
  retryPartialMetadata: "Queueing partial-metadata retry",
  clearLastfmCache: "Clearing Last.fm cache",
  discoveryPreviewJob: "Queueing discovery preview",
  acceptDiscoveryCandidates: "Accepting discovery candidates",
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
  job_type: "Job Type",
  progress_current: "Progress Done",
  progress_total: "Progress Total",
  created_at: "Created At",
  started_at: "Started At",
  finished_at: "Finished At",
  generated_playlist_id: "Generated Playlist ID",
  algorithm_version: "Algorithm Version",
  candidate_pool_size: "Candidate Pool Size",
  candidate_count: "Candidate Count",
  candidate_id: "Candidate ID",
  seed_artist: "Seed Artist",
  listening_count: "Listening Count",
  playlist_inclusion_count: "Playlist Inclusions",
  tag_count: "Tag Count",
  is_deleted: "Hidden",
  context_type: "Context",
  final_score: "Final Score",
  score_breakdown: "Score Breakdown",
  request_params: "Request Settings",
  summary_json: "Summary",
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
  generated_playlist: "Generated Playlist",
  request_params: "Request Settings",
  summary: "Playlist Summary",
  tracks: "Selected Tracks",
};

const BASE_KEY = "musicintel_api_base";
const DEFAULT_BASE = window.MUSICINTEL_CONFIG?.apiBaseUrl || "http://127.0.0.1:8000";
const USER_KEY = "musicintel_user_id";
const GENERATED_PLAYLIST_KEY = "musicintel_generated_playlist_id";
const FEEDBACK_CHOICES = [
  { value: "like", label: "Like" },
  { value: "more_like_this", label: "More Like This" },
  { value: "too_familiar", label: "Too Familiar" },
  { value: "too_obscure", label: "Too Obscure" },
  { value: "wrong_vibe", label: "Wrong Vibe" },
  { value: "dislike", label: "Dislike" },
];

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

function getSelectedGeneratedPlaylistId() {
  const input = document.getElementById("generatedPlaylistId");
  return Number(input?.value || localStorage.getItem(GENERATED_PLAYLIST_KEY) || 0);
}

function setSelectedGeneratedPlaylistId(id) {
  if (!id) return;
  localStorage.setItem(GENERATED_PLAYLIST_KEY, String(id));
  const input = document.getElementById("generatedPlaylistId");
  if (input) {
    input.value = String(id);
  }
}

function getSelectedSongId() {
  return Number(document.getElementById("selectedSongId")?.value || 0);
}

function setSelectedSongId(id) {
  if (!id) return;
  const input = document.getElementById("selectedSongId");
  if (input) {
    input.value = String(id);
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

  if (["last_listened_at", "played_at", "day", "week", "merged_at", "token_expires_at", "created_at", "started_at", "finished_at"].includes(key) || key.endsWith("_date") || key.endsWith("_time") || key.endsWith("_at")) {
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
    return `<tr><td colspan="${cols.length + 1}" class="output-hint">No matching songs</td></tr>`;
  }

  return rows.map((row) => {
    const cells = cols.map((c) => `<td>${escapeHtml(formatValue(c, row[c]))}</td>`).join("");
    const actionButtons = `
      <td class="song-action-cell">
        <div class="song-row-actions">
          <button type="button" class="mini-action-btn song-row-action-btn" data-song-id="${escapeHtml(row.id)}" data-song-row-action="select">Select</button>
          <button type="button" class="mini-action-btn song-row-action-btn" data-song-id="${escapeHtml(row.id)}" data-song-row-action="detail">Detail</button>
          <button type="button" class="mini-action-btn song-row-action-btn" data-song-id="${escapeHtml(row.id)}" data-song-row-action="retry">Retry</button>
          <button type="button" class="mini-action-btn song-row-action-btn" data-song-id="${escapeHtml(row.id)}" data-song-row-action="${row.is_deleted ? "restore" : "hide"}">${row.is_deleted ? "Restore" : "Hide"}</button>
        </div>
      </td>
    `;
    return `<tr>${cells}${actionButtons}</tr>`;
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
  `).join("") + `<th>Actions</th>`;
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

function setJobOutput(el, payload, title = "Job Status") {
  if (!el) return;

  if (Array.isArray(payload?.items)) {
    const rows = payload.items.map((job) => ({
      id: job.id,
      job_type: job.job_type,
      status: job.status,
      progress: `${job.progress_current || 0}/${job.progress_total || 0}`,
      message: job.message,
      created_at: job.created_at,
      finished_at: job.finished_at,
    }));
    el.innerHTML = `
      <div class="output-title">${escapeHtml(title)}</div>
      <div class="metric-inline">${rows.length} jobs shown</div>
      ${renderPayload(rows)}
    `;
    return;
  }

  const current = Number(payload?.progress_current || 0);
  const total = Number(payload?.progress_total || 0);
  const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : null;

  el.innerHTML = `
    <div class="output-title">${escapeHtml(title)}</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Status</div>
        <div class="metric-value">${escapeHtml(formatValue("status", payload?.status || "-"))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Progress</div>
        <div class="metric-value">${percent === null ? `${current}/${total}` : `${percent}%`}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Job Type</div>
        <div class="metric-value">${escapeHtml(formatValue("job_type", payload?.job_type || "-"))}</div>
      </div>
    </div>
    <div class="job-progress">
      <div class="job-progress-bar" style="width:${percent === null ? 0 : percent}%"></div>
    </div>
    ${payload?.message ? `<div class="metric-inline">${escapeHtml(String(payload.message))}</div>` : ""}
    ${renderPayload(payload)}
  `;
}

function renderFeedbackButtons(songId) {
  if (!songId) return "";
  const buttons = FEEDBACK_CHOICES.map((item) => `
    <button
      type="button"
      class="mini-action-btn feedback-btn"
      data-song-id="${escapeHtml(songId)}"
      data-feedback-action="${escapeHtml(item.value)}"
    >${escapeHtml(item.label)}</button>
  `).join("");
  return `<div class="feedback-button-row">${buttons}</div>`;
}

function setGeneratedPlaylistOutput(el, payload, title = "Generated Playlist") {
  if (!el) return;

  if (Array.isArray(payload?.items)) {
    const cards = payload.items.map((item) => `
      <div class="history-card">
        <div class="playlist-track-head">
          <div>
            <div class="playlist-track-title">${escapeHtml(item.name || "Generated Playlist")}</div>
            <div class="playlist-track-meta">ID ${escapeHtml(formatValue("generated_playlist_id", item.id))} | ${escapeHtml(formatValue("context_type", item.context_type || "general"))}</div>
          </div>
          <button type="button" class="mini-action-btn generated-select-btn" data-generated-playlist-id="${escapeHtml(item.id)}">Select</button>
        </div>
        <div class="playlist-pill-row">
          <span class="summary-pill">Candidates: ${escapeHtml(formatValue("candidate_pool_size", item.candidate_pool_size || 0))}</span>
          <span class="summary-pill">Algorithm: ${escapeHtml(item.algorithm_version || "-")}</span>
          <span class="summary-pill">${item.spotify_playlist_id ? "Created on Spotify" : "Preview only"}</span>
        </div>
        <div class="metric-inline">${escapeHtml(formatValue("created_at", item.created_at))}</div>
      </div>
    `).join("");
    el.innerHTML = `
      <div class="output-title">${escapeHtml(title)}</div>
      <div class="metric-inline">${payload.items.length} saved playlists</div>
      <div class="history-grid">${cards || '<div class="output-hint">No saved playlists</div>'}</div>
    `;
    return;
  }

  const playlist = payload?.generated_playlist || payload;
  const tracks = Array.isArray(playlist?.tracks) ? playlist.tracks : [];
  const familiarRatio = Number(playlist?.summary?.familiar_ratio || 0);
  const artistCount = Number(playlist?.summary?.artist_count || 0);
  const dominantTags = Array.isArray(playlist?.summary?.dominant_tags) ? playlist.summary.dominant_tags : [];
  const dominantGenres = Array.isArray(playlist?.summary?.dominant_genres) ? playlist.summary.dominant_genres : [];
  const trackRows = tracks.map((track) => {
    const components = track.score_breakdown || {};
    const explanation = track.explanation || {};
    const componentEntries = Object.entries(components)
      .map(([key, value]) => `<div class="component-pill"><span>${escapeHtml(prettyLabel(key))}</span><strong>${escapeHtml(formatValue(key, value))}</strong></div>`)
      .join("");
    const reasons = Array.isArray(explanation.reasons) ? explanation.reasons : [];
    return `
      <div class="playlist-track-card">
        <div class="playlist-track-head">
          <div>
            <div class="playlist-track-title">${escapeHtml(track.song?.title || "-")}</div>
            <div class="playlist-track-meta">${escapeHtml(track.song?.artist || "-")} | Position ${escapeHtml(formatValue("position", track.position))}</div>
          </div>
          <div class="playlist-track-score">${escapeHtml(formatValue("final_score", track.final_score))}</div>
        </div>
        <div class="playlist-track-meta">Genre: ${escapeHtml(formatValue("genre", track.song?.genre))} | Metadata: ${escapeHtml(formatValue("enrichment_status", track.song?.enrichment_status))}</div>
        ${reasons.length ? `<div class="playlist-reasons">${reasons.map((reason) => `<span class="reason-pill">${escapeHtml(String(reason))}</span>`).join("")}</div>` : ""}
        ${componentEntries ? `<div class="playlist-components">${componentEntries}</div>` : ""}
        ${renderFeedbackButtons(track.song_id)}
      </div>
    `;
  }).join("") + `<th class="song-actions-filter-hint">Inline actions</th>`;

  el.innerHTML = `
    <div class="output-title">${escapeHtml(title)}</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Generated Playlist ID</div>
        <div class="metric-value">${escapeHtml(formatValue("generated_playlist_id", playlist?.id || "-"))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Tracks</div>
        <div class="metric-value">${tracks.length}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Familiar Ratio</div>
        <div class="metric-value">${escapeHtml(formatValue("known_track_ratio", familiarRatio))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Artists</div>
        <div class="metric-value">${artistCount}</div>
      </div>
    </div>
    <div class="playlist-summary-grid">
      <div class="playlist-summary-card">
        <div class="metric-label">Name</div>
        <div class="metric-inline">${escapeHtml(playlist?.name || "-")}</div>
        <div class="metric-label">Algorithm</div>
        <div class="metric-inline">${escapeHtml(playlist?.algorithm_version || "-")}</div>
      </div>
      <div class="playlist-summary-card">
        <div class="metric-label">Dominant Tags</div>
        <div class="playlist-pill-row">${dominantTags.length ? dominantTags.map((item) => `<span class="summary-pill">${escapeHtml(String(item))}</span>`).join("") : '<span class="summary-pill">None</span>'}</div>
        <div class="metric-label">Dominant Genres</div>
        <div class="playlist-pill-row">${dominantGenres.length ? dominantGenres.map((item) => `<span class="summary-pill">${escapeHtml(String(item))}</span>`).join("") : '<span class="summary-pill">None</span>'}</div>
      </div>
      <div class="playlist-summary-card">
        <div class="metric-label">Diversity Summary</div>
        <div class="metric-inline">${escapeHtml(playlist?.summary?.diversity_summary || "-")}</div>
        <div class="metric-label">Context Fit</div>
        <div class="metric-inline">${escapeHtml(formatValue("context_type", playlist?.summary?.context_fit || playlist?.context_type || "general"))}</div>
      </div>
    </div>
    <div class="output-section">
      <div class="output-title">Selected Tracks</div>
      <div class="playlist-track-grid">${trackRows || '<div class="output-hint">No tracks saved</div>'}</div>
    </div>
    <details class="raw-details">
      <summary>Raw payload</summary>
      ${renderPayload(payload)}
    </details>
  `;
}

function setSongDetailOutput(el, payload, title = "Song Detail") {
  if (!el) return;
  const detail = payload?.song || payload;
  const tags = Array.isArray(detail?.tags) ? detail.tags : [];
  if (detail?.id) {
    setSelectedSongId(detail.id);
  }

  el.innerHTML = `
    <div class="output-title">${escapeHtml(title)}</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Song ID</div>
        <div class="metric-value">${escapeHtml(formatValue("id", detail?.id || "-"))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Listening Count</div>
        <div class="metric-value">${escapeHtml(formatValue("listening_count", detail?.listening_count || 0))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Playlist Inclusions</div>
        <div class="metric-value">${escapeHtml(formatValue("playlist_inclusion_count", detail?.playlist_inclusion_count || 0))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Metadata Status</div>
        <div class="metric-value">${escapeHtml(formatValue("enrichment_status", detail?.enrichment_status || "-"))}</div>
      </div>
    </div>
    <div class="playlist-pill-row">${tags.length ? tags.map((tag) => `<span class="summary-pill">${escapeHtml(String(tag))}</span>`).join("") : '<span class="summary-pill">No tags</span>'}</div>
    ${renderPayload(payload)}
  `;
}

function setDiscoveryPreviewOutput(el, payload, title = "Discovery Preview") {
  if (!el) return;

  const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
  const seedArtists = Array.isArray(payload?.seed_artists) ? payload.seed_artists : [];
  const candidateCards = candidates.map((candidate) => `
    <div class="history-card discovery-candidate-card">
      <div class="playlist-track-head">
        <div>
          <div class="playlist-track-title">${escapeHtml(candidate.title || "-")}</div>
          <div class="playlist-track-meta">${escapeHtml(candidate.artist || "-")} | Seed: ${escapeHtml(candidate.seed_artist || "-")}</div>
        </div>
        <div class="playlist-track-score">#${escapeHtml(formatValue("candidate_id", candidate.candidate_id))}</div>
      </div>
      <div class="playlist-pill-row">
        <span class="summary-pill">Source: ${escapeHtml(formatValue("discovery_source", candidate.discovery_source || "-"))}</span>
        <span class="summary-pill">Confidence: ${escapeHtml(formatValue("discovery_confidence", candidate.discovery_confidence || 0))}</span>
      </div>
      <div class="feedback-button-row">
        <button type="button" class="mini-action-btn discovery-candidate-btn" data-candidate-id="${escapeHtml(candidate.candidate_id)}" data-discovery-action="select">Add ID</button>
        <button type="button" class="mini-action-btn discovery-candidate-btn" data-candidate-id="${escapeHtml(candidate.candidate_id)}" data-discovery-action="accept">Accept Now</button>
      </div>
    </div>
  `).join("");

  el.innerHTML = `
    <div class="output-title">${escapeHtml(title)}</div>
    <div class="metric-strip">
      <div class="metric-card">
        <div class="metric-label">Seed Artists</div>
        <div class="metric-value">${seedArtists.length || Number(payload?.seed_artist_count || 0)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Candidates</div>
        <div class="metric-value">${escapeHtml(formatValue("candidate_count", payload?.candidate_count || candidates.length))}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Source</div>
        <div class="metric-value">${escapeHtml(payload?.source || "lastfm")}</div>
      </div>
    </div>
    <div class="playlist-summary-card">
      <div class="metric-label">Seed Artists Used</div>
      <div class="playlist-pill-row">${seedArtists.length ? seedArtists.map((artist) => `<span class="summary-pill">${escapeHtml(String(artist))}</span>`).join("") : '<span class="summary-pill">No seed list returned</span>'}</div>
    </div>
    <div class="output-section">
      <div class="output-title">Discovery Candidates</div>
      <div class="history-grid">${candidateCards || '<div class="output-hint">No candidates found</div>'}</div>
    </div>
    <details class="raw-details">
      <summary>Raw payload</summary>
      ${renderPayload(payload)}
    </details>
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

async function pollJobUntilDone(jobId, output, title = "Job Status") {
  const terminalStates = new Set(["succeeded", "failed", "cancelled"]);

  for (;;) {
    const job = await callApi(`/jobs/${encodeURIComponent(jobId)}`);
    setJobOutput(output, job, title);
    if (terminalStates.has(job.status)) {
      return job;
    }
    await sleep(1200);
  }
}

async function submitQuickFeedback(songId, feedbackAction, output) {
  const data = await callApi("/insights/feedback", {
    method: "POST",
    body: JSON.stringify({
      song_id: Number(songId),
      action: feedbackAction,
    }),
  });

  const targetOutput = output || featureOutput || outputMap.loadGeneratedPlaylist || outputMap.generate;
  setOutput(targetOutput, "Feedback Saved", {
    message: `Saved '${feedbackAction}' feedback for song ${songId}`,
    song_id: songId,
    action: feedbackAction,
  });
  return data;
}

async function loginWithPopup() {
  try {
    await callApi("/user/logout", { method: "POST" });
  } finally {
    localStorage.removeItem(USER_KEY);
  }

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
      const job = await callApi("/user/sync-history/job", {
        method: "POST",
      });
      setJobOutput(output, job, "Sync Job");
      const finalJob = await pollJobUntilDone(job.id, output, "Sync Job");
      if (finalJob.status === "succeeded") {
        setOutput(output, "Sync Result", finalJob.result || finalJob);
      } else {
        setJobOutput(output, finalJob, "Sync Job");
      }
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
      const job = await callApi(`/user/backfill-metadata/job?${params.toString()}`, { method: "POST" });
      setJobOutput(output, job, "Backfill Job");
      const finalJob = await pollJobUntilDone(job.id, output, "Backfill Job");
      if (finalJob.status === "succeeded") {
        setBackfillOutput(output, finalJob.result || finalJob);
      } else {
        setJobOutput(output, finalJob, "Backfill Job");
      }
      return;
    }

    if (action === "loadJobs") {
      const data = await callApi("/jobs?limit=20");
      setJobOutput(output, data, "Recent Jobs");
      return;
    }

    if (action === "previewPlaylist") {
      const maxTracks = Number(document.getElementById("playlistMaxTracks")?.value || 30);
      const diversity = Number(document.getElementById("playlistDiversity")?.value || 0.5);
      const familiarity = Number(document.getElementById("playlistFamiliarity")?.value || 0.5);
      const minKnownRatio = Number(document.getElementById("playlistMinKnownRatio")?.value || 0.6);
      const name = (document.getElementById("playlistName")?.value || "").trim();
      const contextType = (document.getElementById("playlistContextType")?.value || "").trim();

      const data = await callApi("/playlists/preview", {
        method: "POST",
        body: JSON.stringify({
          max_tracks: maxTracks,
          diversity,
          familiarity,
          min_known_ratio: minKnownRatio,
          name: name || null,
          context_type: contextType || null,
        }),
      });
      if (data?.generated_playlist?.id) {
        setSelectedGeneratedPlaylistId(data.generated_playlist.id);
      }
      setGeneratedPlaylistOutput(output, data, "Playlist Preview");
      return;
    }

    if (action === "generate") {
      const maxTracks = Number(document.getElementById("playlistMaxTracks")?.value || 30);
      const diversity = Number(document.getElementById("playlistDiversity")?.value || 0.5);
      const familiarity = Number(document.getElementById("playlistFamiliarity")?.value || 0.5);
      const minKnownRatio = Number(document.getElementById("playlistMinKnownRatio")?.value || 0.6);
      const name = (document.getElementById("playlistName")?.value || "").trim();
      const contextType = (document.getElementById("playlistContextType")?.value || "").trim();

      const data = await callApi("/playlists/generate", {
        method: "POST",
        body: JSON.stringify({
          max_tracks: maxTracks,
          diversity,
          familiarity,
          min_known_ratio: minKnownRatio,
          name: name || null,
          context_type: contextType || null,
        }),
      });
      if (data?.generated_playlist_id) {
        setSelectedGeneratedPlaylistId(data.generated_playlist_id);
      }
      setPlaylistOutput(output, data);
      return;
    }

    if (action === "loadPlaylistHistory") {
      const data = await callApi("/playlists/generated?limit=20");
      setGeneratedPlaylistOutput(output, data, "Saved Playlist History");
      return;
    }

    if (action === "loadGeneratedPlaylist") {
      const generatedPlaylistId = getSelectedGeneratedPlaylistId();
      if (!generatedPlaylistId) {
        throw new Error("Enter or select a generated playlist ID first.");
      }
      const data = await callApi(`/playlists/generated/${encodeURIComponent(generatedPlaylistId)}`);
      setSelectedGeneratedPlaylistId(data.id);
      setGeneratedPlaylistOutput(output, data, "Saved Playlist Detail");
      return;
    }

    if (action === "regenerateGeneratedPlaylist") {
      const generatedPlaylistId = getSelectedGeneratedPlaylistId();
      if (!generatedPlaylistId) {
        throw new Error("Enter or select a generated playlist ID first.");
      }
      const data = await callApi(`/playlists/generated/${encodeURIComponent(generatedPlaylistId)}/regenerate`, {
        method: "POST",
      });
      if (data?.generated_playlist?.id) {
        setSelectedGeneratedPlaylistId(data.generated_playlist.id);
      }
      setGeneratedPlaylistOutput(output, data, "Regenerated Playlist Preview");
      return;
    }

    if (action === "createFromGeneratedPlaylist") {
      const generatedPlaylistId = getSelectedGeneratedPlaylistId();
      if (!generatedPlaylistId) {
        throw new Error("Enter or select a generated playlist ID first.");
      }
      const data = await callApi(`/playlists/generated/${encodeURIComponent(generatedPlaylistId)}/create`, {
        method: "POST",
      });
      if (data?.generated_playlist?.id) {
        setSelectedGeneratedPlaylistId(data.generated_playlist.id);
      }
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
      const quickFilterInput = document.getElementById("songQuickFilter");
      const recentDaysInput = document.getElementById("recentlyPlayedDays");
      const genre = genreInput ? genreInput.value.trim() : "";
      const enrichmentStatus = statusInput ? statusInput.value.trim() : "";
      const quickFilter = quickFilterInput ? quickFilterInput.value.trim() : "";
      const recentDays = recentDaysInput ? Number(recentDaysInput.value || 30) : 30;
      const limitInput = document.getElementById("songLimit");
      const limit = limitInput ? Number(limitInput.value || 1000) : 1000;
      const query = new URLSearchParams();
      if (genre) query.set("genre", genre);
      if (enrichmentStatus) query.set("enrichment_status", enrichmentStatus);
      if (quickFilter) query.set("quick_filter", quickFilter);
      query.set("recently_played_days", String(recentDays));
      query.set("limit", String(limit));
      const data = await callApi(`/songs/?${query.toString()}`);
      setSongExplorerOutput(output, data);
      return;
    }

    if (action === "songDetail") {
      const songId = getSelectedSongId();
      if (!songId) throw new Error("Enter or select a song ID first.");
      const data = await callApi(`/songs/${encodeURIComponent(songId)}`);
      setSongDetailOutput(output, data, "Song Detail");
      return;
    }

    if (action === "songRetryEnrichment") {
      const songId = getSelectedSongId();
      if (!songId) throw new Error("Enter or select a song ID first.");
      const data = await callApi(`/songs/${encodeURIComponent(songId)}/retry-enrichment`, { method: "POST" });
      setSongDetailOutput(output, data, "Enrichment Retry Result");
      return;
    }

    if (action === "songHide") {
      const songId = getSelectedSongId();
      if (!songId) throw new Error("Enter or select a song ID first.");
      const data = await callApi(`/songs/${encodeURIComponent(songId)}/hide`, { method: "POST" });
      setOutput(output, "Song Hidden", data);
      if (outputMap.songs) {
        const query = new URLSearchParams();
        const genre = document.getElementById("genre")?.value.trim() || "";
        const enrichmentStatus = document.getElementById("enrichmentStatus")?.value.trim() || "";
        const quickFilter = document.getElementById("songQuickFilter")?.value.trim() || "";
        const recentDays = Number(document.getElementById("recentlyPlayedDays")?.value || 30);
        const limit = Number(document.getElementById("songLimit")?.value || 1000);
        if (genre) query.set("genre", genre);
        if (enrichmentStatus) query.set("enrichment_status", enrichmentStatus);
        if (quickFilter) query.set("quick_filter", quickFilter);
        query.set("recently_played_days", String(recentDays));
        query.set("limit", String(limit));
        const refreshed = await callApi(`/songs/?${query.toString()}`);
        setSongExplorerOutput(outputMap.songs, refreshed);
      }
      return;
    }

    if (action === "songRestore") {
      const songId = getSelectedSongId();
      if (!songId) throw new Error("Enter or select a song ID first.");
      const data = await callApi(`/songs/${encodeURIComponent(songId)}/restore`, { method: "POST" });
      setOutput(output, "Song Restored", data);
      if (outputMap.songs) {
        const query = new URLSearchParams();
        const genre = document.getElementById("genre")?.value.trim() || "";
        const enrichmentStatus = document.getElementById("enrichmentStatus")?.value.trim() || "";
        const quickFilter = document.getElementById("songQuickFilter")?.value.trim() || "";
        const recentDays = Number(document.getElementById("recentlyPlayedDays")?.value || 30);
        const limit = Number(document.getElementById("songLimit")?.value || 1000);
        if (genre) query.set("genre", genre);
        if (enrichmentStatus) query.set("enrichment_status", enrichmentStatus);
        if (quickFilter) query.set("quick_filter", quickFilter);
        query.set("recently_played_days", String(recentDays));
        query.set("limit", String(limit));
        const refreshed = await callApi(`/songs/?${query.toString()}`);
        setSongExplorerOutput(outputMap.songs, refreshed);
      }
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

    if (action === "retryFailedMetadata" || action === "retryPartialMetadata") {
      const retryFailed = action === "retryFailedMetadata";
      const retryPartial = action === "retryPartialMetadata";
      const retryLimit = Number(document.getElementById("metadataRetryLimit")?.value || 25);
      const params = new URLSearchParams({
        limit: String(Math.max(1, Math.min(retryLimit, 5000))),
        retry_partial: String(retryPartial),
        retry_failed: String(retryFailed),
      });
      const job = await callApi(`/user/backfill-metadata/job?${params.toString()}`, { method: "POST" });
      setJobOutput(output, job, retryFailed ? "Retry Failed Metadata Job" : "Retry Partial Metadata Job");
      const finalJob = await pollJobUntilDone(job.id, output, retryFailed ? "Retry Failed Metadata Job" : "Retry Partial Metadata Job");
      if (finalJob.status === "succeeded") {
        setBackfillOutput(output, finalJob.result || finalJob);
      } else {
        setJobOutput(output, finalJob, "Metadata Retry Job");
      }
      return;
    }

    if (action === "clearLastfmCache") {
      const data = await callApi("/insights/cache/clear?provider=lastfm", { method: "POST" });
      setOutput(output, "Last.fm Cache Cleared", data);
      return;
    }

    if (action === "discoveryPreviewJob") {
      const seedLimit = Number(document.getElementById("discoverySeedLimit")?.value || 8);
      const candidateLimit = Number(document.getElementById("discoveryCandidateLimit")?.value || 60);
      const params = new URLSearchParams({
        seed_limit: String(seedLimit),
        max_candidates: String(candidateLimit),
      });
      const job = await callApi(`/discoveries/preview/job?${params.toString()}`, { method: "POST" });
      const jobInput = document.getElementById("discoveryJobId");
      if (jobInput) jobInput.value = job.id;
      setJobOutput(output, job, "Discovery Preview Job");
      const finalJob = await pollJobUntilDone(job.id, output, "Discovery Preview Job");
      if (finalJob.status === "succeeded") {
        setDiscoveryPreviewOutput(output, finalJob.result || finalJob, "Discovery Preview");
      } else {
        setJobOutput(output, finalJob, "Discovery Preview Job");
      }
      return;
    }

    if (action === "acceptDiscoveryCandidates") {
      const jobId = (document.getElementById("discoveryJobId")?.value || "").trim();
      if (!jobId) throw new Error("Run a discovery preview first.");
      const candidateText = (document.getElementById("discoveryCandidateIds")?.value || "").trim();
      const candidateIds = candidateText
        ? candidateText.split(",").map((item) => Number(item.trim())).filter((value) => Number.isFinite(value) && value > 0)
        : [];
      const data = await callApi("/discoveries/accept", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, candidate_ids: candidateIds }),
      });
      setOutput(output, "Discovery Candidates Accepted", data);
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

      await submitQuickFeedback(songId, feedbackAction, output);
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
setSelectedGeneratedPlaylistId(localStorage.getItem(GENERATED_PLAYLIST_KEY));
cleanupLegacyUi();

actionButtons.forEach((btn) => {
  btn.addEventListener("click", () => handleAction(btn.dataset.action));
});

document.addEventListener("click", async (event) => {
  const target = event.target.closest(".feedback-btn, .generated-select-btn, .song-row-action-btn, .discovery-candidate-btn");
  if (!target) return;

  if (target.classList.contains("generated-select-btn")) {
    const generatedPlaylistId = Number(target.dataset.generatedPlaylistId || 0);
    if (generatedPlaylistId) {
      setSelectedGeneratedPlaylistId(generatedPlaylistId);
      const historyOutput = outputMap.loadPlaylistHistory;
      if (historyOutput) {
        setOutput(historyOutput, "Selection Updated", {
          message: `Selected generated playlist ${generatedPlaylistId}`,
          generated_playlist_id: generatedPlaylistId,
        });
      }
    }
    return;
  }

  if (target.classList.contains("song-row-action-btn")) {
    const songId = Number(target.dataset.songId || 0);
    const rowAction = target.dataset.songRowAction;
    if (!songId || !rowAction) return;

    setSelectedSongId(songId);

    if (rowAction === "select") {
      const detailOutput = outputMap.songDetail || outputMap.songs;
      if (detailOutput) {
        setOutput(detailOutput, "Song Selected", {
          message: `Selected song ${songId}. Use the action panel or inline buttons to continue.`,
          song_id: songId,
        });
      }
      return;
    }

    const actionMap = {
      detail: "songDetail",
      retry: "songRetryEnrichment",
      hide: "songHide",
      restore: "songRestore",
    };
    const mappedAction = actionMap[rowAction];
    if (mappedAction) {
      await handleAction(mappedAction);
    }
    return;
  }

  if (target.classList.contains("discovery-candidate-btn")) {
    const candidateId = Number(target.dataset.candidateId || 0);
    const discoveryAction = target.dataset.discoveryAction;
    if (!candidateId || !discoveryAction) return;

    const candidateInput = document.getElementById("discoveryCandidateIds");
    if (discoveryAction === "select") {
      const existing = (candidateInput?.value || "")
        .split(",")
        .map((item) => Number(item.trim()))
        .filter((value) => Number.isFinite(value) && value > 0);
      if (!existing.includes(candidateId)) {
        existing.push(candidateId);
      }
      if (candidateInput) {
        candidateInput.value = existing.join(", ");
      }
      return;
    }

    if (discoveryAction === "accept") {
      const jobId = (document.getElementById("discoveryJobId")?.value || "").trim();
      if (!jobId) {
        const output = outputMap.discoveryPreviewJob || featureOutput;
        setOutput(output, "Discovery Error", { message: "Run a discovery preview first." });
        return;
      }
      if (candidateInput) {
        candidateInput.value = String(candidateId);
      }
      await handleAction("acceptDiscoveryCandidates");
      return;
    }
  }

  const songId = Number(target.dataset.songId || 0);
  const feedbackAction = target.dataset.feedbackAction;
  if (!songId || !feedbackAction) return;

  const historyOutput = outputMap.loadGeneratedPlaylist || outputMap.generate || featureOutput;
  const originalText = target.textContent;
  target.disabled = true;
  target.textContent = "Saving...";
  try {
    await submitQuickFeedback(songId, feedbackAction, historyOutput);
  } catch (error) {
    setOutput(historyOutput, "Feedback Error", { message: String(error.message || error) });
  } finally {
    target.disabled = false;
    target.textContent = originalText;
  }
});












