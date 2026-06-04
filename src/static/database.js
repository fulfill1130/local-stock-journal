const databaseState = {
  items: [],
  actionMessages: {},
};

const byId = (id) => document.getElementById(id);
const shareToken = new URLSearchParams(window.location.search).get("token") || "";

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

function money(value, decimals = 2) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  return num.toLocaleString("zh-TW", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

function pct(value) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}%`;
}

function valueClass(value) {
  const num = numberValue(value);
  if (num === null) return "";
  if (num > 0) return "positive";
  if (num < 0) return "negative";
  return "";
}

function formatTimeFromTs(value) {
  const num = numberValue(value);
  if (num === null || num <= 0) return "N/A";
  return new Date(num * 1000).toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
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

async function loadDatabase() {
  const response = await fetch(withToken("/api/database"));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  databaseState.items = data.instruments || [];
  renderDatabase(data);
}

function renderDatabase(data) {
  const summary = data.summary || {};
  byId("instrument-count").textContent = money(summary.instrument_count, 0);
  byId("etf-count").textContent = money(summary.etf_count, 0);
  byId("listed-count").textContent = money(summary.listed_count, 0);
  byId("otc-count").textContent = money(summary.otc_count, 0);
  byId("quote-count").textContent = money(summary.quote_count, 0);
  byId("database-updated-at").textContent = data.updated_at || "N/A";
  renderDataStatus(data.data_status || []);
  renderInstrumentList();
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
          <strong>${escapeHtml(item.label || item.job_name)}</strong>
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

function filteredItems() {
  const keyword = byId("database-search").value.trim().toUpperCase();
  const suffix = byId("database-suffix-filter").value;
  const type = byId("database-type-filter").value;
  return databaseState.items.filter((item) => {
    const text = [item.ticker, item.name, item.symbol].join(" ").toUpperCase();
    if (keyword && !text.includes(keyword)) return false;
    if (suffix && item.exchange_suffix !== suffix) return false;
    if (type && item.type !== type) return false;
    return true;
  });
}

function renderInstrumentList() {
  const root = byId("database-list");
  const items = filteredItems();
  if (!items.length) {
    root.innerHTML = `<div class="empty">沒有符合條件的股票主檔</div>`;
    return;
  }

  root.innerHTML = items.map((item) => {
    const message = databaseState.actionMessages[item.ticker] || "";
    const historyStatus = String(item.history_status || "");
    const suspect = historyStatus === "suspect_delisted";
    const delisted = historyStatus === "delisted";
    const listingText = item.listing_date || item.daily_first_date || "待補";
    return `
      <article class="database-row ${suspect ? "suspect-delisted" : ""} ${delisted ? "marked-delisted" : ""}">
        <div class="database-main">
          <span class="ticker">${escapeHtml(item.ticker)} · ${escapeHtml(item.type || "")}</span>
          <div class="stock-name">${escapeHtml(item.name || item.ticker)}</div>
          <div class="database-meta">
            <span>${escapeHtml(item.symbol || "")}</span>
            <span>${escapeHtml(item.exchange_suffix || "")}</span>
            <span>${escapeHtml(item.source || "")}</span>
            <span>日線 ${money(item.daily_bar_count || 0, 0)} 筆</span>
            ${item.daily_first_date ? `<span>${escapeHtml(item.daily_first_date)} - ${escapeHtml(item.daily_last_date || "")}</span>` : ""}
            <span>上市/起始 ${escapeHtml(listingText)}</span>
            ${historyStatus ? `<span>補齊狀態 ${escapeHtml(historyStatus)}</span>` : ""}
            ${item.history_checked_at ? `<span>檢查 ${formatIsoTime(item.history_checked_at)}</span>` : ""}
            <span>主檔 ${formatTimeFromTs(item.updated_at_ts)}</span>
          </div>
        </div>
        <div class="database-quote">
          <strong>${money(item.close, 2)}</strong>
          <span class="${valueClass(item.change_pct)}">${pct(item.change_pct)}</span>
          <small>${escapeHtml(item.price_time || "無報價")}</small>
        </div>
        <div class="database-actions">
          ${item.daily_bar_count ? `<a class="icon-button top-link database-link-button" href="${withToken(`/database/${encodeURIComponent(item.ticker)}/history`)}">日線</a>` : ""}
          ${suspect ? `<button class="icon-button database-refresh-button" type="button" data-check-history="${escapeHtml(item.ticker)}">排查</button>` : ""}
          ${suspect ? `<button class="icon-button database-refresh-button danger" type="button" data-mark-delisted="${escapeHtml(item.ticker)}">下市</button>` : ""}
        </div>
        ${suspect ? `<p class="database-row-message danger">連續 3 次官方日線查無資料。請排查 suffix / 代號，或確認後標記下市。</p>` : ""}
        ${delisted ? `<p class="database-row-message">已標記下市；背景補齊器會略過這檔。</p>` : ""}
        ${message ? `<p class="database-row-message">${escapeHtml(message)}</p>` : ""}
      </article>
    `;
  }).join("");
}

async function runTickerAction(ticker, button, endpoint, pendingText) {
  const normalized = String(ticker || "").trim().toUpperCase();
  if (!normalized) return;
  button.disabled = true;
  databaseState.actionMessages[normalized] = pendingText;
  renderInstrumentList();
  try {
    const response = await fetch(withToken(endpoint(normalized)), { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    databaseState.items = data.database?.instruments || [];
    databaseState.actionMessages[normalized] = data.message || `已處理 ${normalized}`;
    renderDatabase(data.database || {});
  } catch (error) {
    databaseState.actionMessages[normalized] = `處理失敗：${error.message || error}`;
    renderInstrumentList();
  } finally {
    button.disabled = false;
  }
}

byId("database-search").addEventListener("input", renderInstrumentList);
byId("database-suffix-filter").addEventListener("change", renderInstrumentList);
byId("database-type-filter").addEventListener("change", renderInstrumentList);
byId("database-list").addEventListener("click", (event) => {
  const checkButton = event.target.closest("[data-check-history]");
  if (checkButton) {
    runTickerAction(
      checkButton.dataset.checkHistory,
      checkButton,
      (ticker) => `/api/database/${encodeURIComponent(ticker)}/history/check`,
      "排查中..."
    );
    return;
  }
  const delistedButton = event.target.closest("[data-mark-delisted]");
  if (delistedButton) {
    runTickerAction(
      delistedButton.dataset.markDelisted,
      delistedButton,
      (ticker) => `/api/database/${encodeURIComponent(ticker)}/delisted`,
      "標記下市中..."
    );
  }
});

loadDatabase().catch((error) => {
  byId("database-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
});
