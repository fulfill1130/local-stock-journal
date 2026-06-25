const logState = {
  items: [],
  pageSize: 80,
  pagination: {
    limit: 80,
    offset: 0,
    returned: 0,
    total: 0,
    has_more: false,
  },
  loading: false,
};

const byId = (id) => document.getElementById(id);
const shareToken = new URLSearchParams(window.location.search).get("token") || "";

const jobLabels = {
  tw_intraday_15m: "台股盤中",
  tw_after_close: "台股盤後",
  official_daily: "官方日線",
  official_history_backfill: "歷史補齊",
  us_intraday_15m: "美股盤中",
};

function withToken(path) {
  if (!shareToken) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(shareToken)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function numberValue(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function money(value, decimals = 0) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  return num.toLocaleString("zh-TW", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

function formatIsoTime(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function labelForJob(jobName) {
  const name = String(jobName || "");
  if (name.startsWith("dividend_refresh:")) {
    return `股利更新 ${name.split(":")[1] || ""}`;
  }
  return jobLabels[name] || name || "unknown";
}

function logQueryParams(offset = 0) {
  const params = new URLSearchParams({
    limit: String(logState.pageSize),
    offset: String(Math.max(Number(offset) || 0, 0)),
  });
  const status = byId("log-status-filter")?.value || "";
  if (status) params.set("status", status);
  return params;
}

async function loadLogs(options = {}) {
  const append = Boolean(options.append);
  const offset = append ? logState.items.length : 0;
  const params = logQueryParams(offset);
  logState.loading = true;
  renderPagination();

  const response = await fetch(withToken(`/api/database/logs?${params.toString()}`));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  const nextItems = data.logs || [];
  logState.items = append ? logState.items.concat(nextItems) : nextItems;
  logState.pagination = data.pagination || logState.pagination;
  logState.loading = false;
  renderLogs(data);
}

function renderLogs(data) {
  const latest = logState.items[0] || {};
  byId("log-count").textContent = money(data.pagination?.total ?? logState.items.length);
  byId("latest-log-status").textContent = latest.status || "N/A";
  byId("latest-log-job").textContent = latest.job_name ? labelForJob(latest.job_name) : "N/A";
  byId("logs-updated-at").textContent = data.updated_at || "N/A";
  renderDataStatus(data.data_status || []);
  renderLogList();
  renderPagination();
}

function renderDataStatus(items) {
  const root = byId("data-status-bar");
  if (!root) return;
  const visible = (items || []).filter((item) =>
    ["tw_intraday_15m", "official_daily", "official_history_backfill", "us_intraday_15m", "tw_after_close"].includes(item.job_name)
  );
  if (!visible.length) {
    root.innerHTML = `<div class="data-status-empty">尚無資料更新狀態</div>`;
    return;
  }
  root.innerHTML = visible.map((item) => {
    const failed = item.last_status === "failed";
    return `
      <article class="data-status-card ${failed ? "failed" : ""}">
        <div class="data-status-head">
          <strong>${escapeHtml(labelForJob(item.job_name))}</strong>
          <span>${escapeHtml(item.last_status || "unknown")}</span>
        </div>
        <div class="data-status-times">
          <span>上次 ${formatIsoTime(item.last_finished_at || item.last_started_at)}</span>
          <span>下次 ${formatIsoTime(item.next_run_at)}</span>
        </div>
        ${failed && item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
      </article>
    `;
  }).join("");
}

function renderLogList() {
  const root = byId("operation-log-list");
  if (!root) return;
  if (!logState.items.length) {
    root.innerHTML = `<div class="empty">目前沒有作業紀錄</div>`;
    return;
  }
  root.innerHTML = logState.items.map((item) => {
    const failed = item.status === "failed";
    const duration = numberValue(item.duration_ms);
    return `
      <article class="operation-log-row ${failed ? "failed" : ""}">
        <div class="operation-log-main">
          <div class="operation-log-title">
            <strong>${escapeHtml(labelForJob(item.job_name))}</strong>
            <span class="operation-log-badge ${failed ? "failed" : "success"}">${escapeHtml(item.status || "unknown")}</span>
          </div>
          <div class="database-meta">
            <span>${escapeHtml(item.event_type || "")}</span>
            <span>${escapeHtml(item.source || "")}</span>
            <span>${formatIsoTime(item.finished_at || item.created_at)}</span>
            ${duration === null ? "" : `<span>${money(duration)} ms</span>`}
          </div>
          ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
          ${item.details ? `
            <details class="operation-log-details">
              <summary>查看細節</summary>
              <pre>${escapeHtml(item.details)}</pre>
            </details>
          ` : ""}
        </div>
      </article>
    `;
  }).join("");
}

function renderPagination() {
  const root = byId("operation-log-pagination");
  if (!root) return;
  const pagination = logState.pagination || {};
  const loaded = logState.items.length;
  const total = numberValue(pagination.total) ?? loaded;
  const hasMore = Boolean(pagination.has_more);
  const isLoading = Boolean(logState.loading);
  root.innerHTML = `
    <div class="database-pagination-info">已載入 ${money(loaded)} / ${money(total)} 筆</div>
    ${
      hasMore
        ? `<button id="operation-log-load-more" class="icon-button database-load-more" type="button" ${isLoading ? "disabled" : ""}>${isLoading ? "載入中" : "載入更多"}</button>`
        : ""
    }
  `;
}

byId("log-status-filter").addEventListener("change", () => {
  loadLogs({ append: false }).catch((error) => {
    logState.loading = false;
    byId("operation-log-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
    renderPagination();
  });
});

byId("operation-log-pagination").addEventListener("click", (event) => {
  const button = event.target.closest("#operation-log-load-more");
  if (!button) return;
  button.disabled = true;
  loadLogs({ append: true }).catch((error) => {
    logState.loading = false;
    byId("operation-log-list").insertAdjacentHTML(
      "beforeend",
      `<div class="empty">載入更多失敗：${escapeHtml(error.message || error)}</div>`
    );
    renderPagination();
  });
});

loadLogs({ append: false }).catch((error) => {
  logState.loading = false;
  byId("operation-log-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
  renderPagination();
});
