const databaseState = {
  items: [],
  actionMessages: {},
  pageSize: 80,
  pagination: {
    limit: 80,
    offset: 0,
    returned: 0,
    total: 0,
    has_more: false,
  },
  loading: false,
  splitTicker: "",
  splitButton: null,
};

let databaseLoadTimer = null;

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
  const sign = num >= 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}%`;
}

function valueClass(value) {
  const num = numberValue(value);
  if (num === null) return "";
  if (num > 0) return "positive";
  if (num < 0) return "negative";
  return "";
}

function databaseChangePct(item) {
  const changePct = numberValue(item?.change_pct);
  if (changePct !== null) return changePct;
  return numberValue(item?.close) !== null ? 0 : null;
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

const historyStatusLabels = {
  ok: "正常",
  recent_ok_partial_history: "近期正常，早期缺資料",
  new_listing: "新上市 / 新掛牌",
  partial_old_missing: "早期缺資料",
  recent_missing: "近期缺資料",
  broken: "資料異常",
  symbol_problem: "代號或來源疑似錯誤",
  delisted_candidate: "疑似下市",
  delisted: "已下市",
  manual_review: "需人工排查",
};

const severeHistoryStatuses = new Set([
  "recent_missing",
  "broken",
  "symbol_problem",
  "delisted_candidate",
  "manual_review",
]);

function historyStatusLabel(value) {
  const key = String(value || "");
  return historyStatusLabels[key] || key || "未檢查";
}

function databaseQueryParams(offset = 0) {
  const params = new URLSearchParams({
    limit: String(databaseState.pageSize),
    offset: String(Math.max(Number(offset) || 0, 0)),
  });
  const keyword = byId("database-search")?.value.trim() || "";
  const suffix = byId("database-suffix-filter")?.value || "";
  const type = byId("database-type-filter")?.value || "";

  if (keyword) params.set("q", keyword);
  if (type) params.set("type", type);
  if (suffix) params.set("suffix", suffix);
  return params;
}

async function loadDatabase(options = {}) {
  const append = Boolean(options.append);
  const offset = append ? databaseState.items.length : 0;
  const params = databaseQueryParams(offset);

  databaseState.loading = true;
  renderPagination();

  const response = await fetch(withToken(`/api/database?${params.toString()}`));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const data = await response.json();
  const nextItems = data.instruments || [];
  databaseState.items = append ? databaseState.items.concat(nextItems) : nextItems;
  databaseState.pagination = data.pagination || databaseState.pagination;
  databaseState.loading = false;
  renderDatabase(data);
}

function scheduleDatabaseLoad() {
  window.clearTimeout(databaseLoadTimer);
  databaseLoadTimer = window.setTimeout(() => {
    loadDatabase({ append: false }).catch((error) => {
      databaseState.loading = false;
      byId("database-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
      renderPagination();
    });
  }, 220);
}

function renderDatabase(data) {
  const summary = data.summary || {};
  byId("instrument-count").textContent = money(summary.instrument_count, 0);
  byId("etf-count").textContent = money(summary.etf_count, 0);
  byId("listed-count").textContent = money(summary.listed_count, 0);
  byId("otc-count").textContent = money(summary.otc_count, 0);
  byId("quote-count").textContent = money(summary.quote_count, 0);
  byId("database-updated-at").textContent = data.updated_at || "N/A";
  renderInstrumentList();
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

function renderInstrumentList() {
  const root = byId("database-list");
  const items = databaseState.items;
  if (!items.length) {
    root.innerHTML = `<div class="empty">目前沒有符合條件的股票主檔</div>`;
    return;
  }

  root.innerHTML = items.map((item) => {
    const message = databaseState.actionMessages[item.ticker] || "";
    const historyStatus = String(item.history_status || "");
    const severe = severeHistoryStatuses.has(historyStatus);
    const suspect = historyStatus === "delisted_candidate";
    const delisted = historyStatus === "delisted";
    const hasListingDate = Boolean(String(item.listing_date || "").trim());
    const listingText = item.listing_date || "待補";
    const missingMonths = numberValue(item.missing_month_count) || 0;
    const coverageText = missingMonths > 0
      ? `缺 ${money(missingMonths, 0)} 個月，首缺 ${item.first_missing_month || "N/A"}`
      : "月份完整";
    const latestIssue = item.latest_issue || item.last_error || "";
    const corporateActionCount = numberValue(item.corporate_action_count) || 0;
    const latestCorporateAction = item.latest_corporate_action_date || "";
    const displayedChangePct = databaseChangePct(item);
    return `
      <article class="database-row ${hasListingDate ? "has-listing-date" : ""} ${severe ? "suspect-delisted" : ""} ${delisted ? "marked-delisted" : ""}">
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
            <span>狀態 ${escapeHtml(historyStatusLabel(historyStatus))}</span>
            <span>${escapeHtml(coverageText)}</span>
            ${item.last_checked_at ? `<span>檢查 ${formatIsoTime(item.last_checked_at)}</span>` : ""}
            ${item.last_success_at ? `<span>成功 ${formatIsoTime(item.last_success_at)}</span>` : ""}
            ${item.issue_count ? `<span>issue ${money(item.issue_count, 0)}</span>` : ""}
            ${corporateActionCount ? `<span>分割 ${money(corporateActionCount, 0)} 筆${latestCorporateAction ? `，最近 ${escapeHtml(latestCorporateAction)}` : ""}</span>` : ""}
            <span>主檔 ${formatTimeFromTs(item.updated_at_ts)}</span>
          </div>
        </div>
        <div class="database-quote">
          <strong>${money(item.close, 2)}</strong>
          <span class="${valueClass(displayedChangePct)}">${pct(displayedChangePct)}</span>
          <small>${escapeHtml(item.price_time || "無報價")}</small>
        </div>
        <div class="database-actions">
          ${item.daily_bar_count ? `<a class="icon-button top-link database-link-button" href="${withToken(`/database/${encodeURIComponent(item.ticker)}/history`)}">日線</a>` : ""}
          <button class="icon-button database-refresh-button" type="button" data-listing-date="${escapeHtml(item.ticker)}">上市日</button>
          <button class="icon-button database-refresh-button" type="button" data-split-action="${escapeHtml(item.ticker)}">分割</button>
          ${severe ? `<button class="icon-button database-refresh-button" type="button" data-check-history="${escapeHtml(item.ticker)}">排查</button>` : ""}
          ${suspect ? `<button class="icon-button database-refresh-button danger" type="button" data-mark-delisted="${escapeHtml(item.ticker)}">下市</button>` : ""}
        </div>
        ${severe && latestIssue ? `<p class="database-row-message danger">${escapeHtml(latestIssue)}</p>` : ""}
        ${suspect ? `<p class="database-row-message danger">官方連續查無資料，請排查 suffix / 代號；確認下市後再手動標記。</p>` : ""}
        ${delisted ? `<p class="database-row-message">已手動標記下市，背景補齊器會跳過這檔。</p>` : ""}
        ${message ? `<p class="database-row-message">${escapeHtml(message)}</p>` : ""}
      </article>
    `;
  }).join("");
}

function renderPagination() {
  const root = byId("database-pagination");
  if (!root) return;
  const pagination = databaseState.pagination || {};
  const loaded = databaseState.items.length;
  const total = numberValue(pagination.total) ?? loaded;
  const hasMore = Boolean(pagination.has_more);
  const isLoading = Boolean(databaseState.loading);
  root.innerHTML = `
    <div class="database-pagination-info">已載入 ${money(loaded, 0)} / ${money(total, 0)} 檔</div>
    ${
      hasMore
        ? `<button id="database-load-more" class="icon-button database-load-more" type="button" ${isLoading ? "disabled" : ""}>${isLoading ? "載入中" : "載入更多"}</button>`
        : ""
    }
  `;
}

function suggestInstrumentType() {
  const ticker = String(byId("instrument-ticker")?.value || "").trim().toUpperCase();
  const typeInput = byId("instrument-type");
  const suffixInput = byId("instrument-suffix");
  if (!ticker || !typeInput || !suffixInput) return;
  if (ticker.startsWith("00")) {
    typeInput.value = "ETF";
    suffixInput.value = ".TW";
  }
}

async function submitInstrumentForm(event) {
  event.preventDefault();
  const status = byId("instrument-status");
  const button = byId("instrument-submit");
  const ticker = String(byId("instrument-ticker")?.value || "").trim().toUpperCase();
  const name = String(byId("instrument-name")?.value || "").trim();
  const assetType = String(byId("instrument-type")?.value || "STOCK").trim().toUpperCase();
  const exchangeSuffix = String(byId("instrument-suffix")?.value || ".TW").trim().toUpperCase();

  if (!ticker) {
    status.textContent = "請先輸入股票代號。";
    return;
  }

  status.textContent = `寫入 ${ticker} 中...`;
  if (button) button.disabled = true;

  try {
    const response = await fetch(withToken("/api/database/instrument"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        name,
        type: assetType,
        exchange_suffix: exchangeSuffix,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);

    status.textContent = data.message || (data.duplicate ? `${ticker} 已存在，未重複新增。` : `${ticker} 已加入主檔。`);
    if (!data.duplicate) {
      byId("instrument-ticker").value = "";
      byId("instrument-name").value = "";
      byId("instrument-type").value = "STOCK";
      byId("instrument-suffix").value = ".TW";
    }
    if (data.database) {
      databaseState.items = data.database.instruments || [];
      databaseState.pagination = data.database.pagination || databaseState.pagination;
      renderDatabase(data.database);
    } else {
      await loadDatabase({ append: false });
    }
  } catch (error) {
    status.textContent = `寫入失敗：${error.message || error}`;
  } finally {
    if (button) button.disabled = false;
  }
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
    databaseState.actionMessages[normalized] = data.message || `已更新 ${normalized}`;
    await loadDatabase({ append: false });
  } catch (error) {
    databaseState.actionMessages[normalized] = `動作失敗：${error.message || error}`;
    renderInstrumentList();
  } finally {
    button.disabled = false;
  }
}

function openSplitModal(ticker, button) {
  const normalized = String(ticker || "").trim().toUpperCase();
  if (!normalized) return;
  databaseState.splitTicker = normalized;
  databaseState.splitButton = button;
  byId("split-target").textContent = `標的 ${normalized}：輸入分割生效日與倍率`;
  byId("split-effective-date").value = "";
  byId("split-ratio").value = "";
  byId("split-modal").hidden = false;
  window.setTimeout(() => byId("split-effective-date").focus(), 0);
}

function closeSplitModal() {
  byId("split-modal").hidden = true;
  databaseState.splitTicker = "";
  databaseState.splitButton = null;
}

async function submitSplitAction(event) {
  event.preventDefault();
  const normalized = databaseState.splitTicker;
  if (!normalized) return;
  const button = databaseState.splitButton;
  const dateText = byId("split-effective-date").value;
  const ratioTo = Number(byId("split-ratio").value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText)) {
    databaseState.actionMessages[normalized] = "分割日期格式請用 YYYY-MM-DD";
    renderInstrumentList();
    return;
  }
  if (!Number.isFinite(ratioTo) || ratioTo <= 0) {
    databaseState.actionMessages[normalized] = "分割倍率必須大於 0";
    renderInstrumentList();
    return;
  }
  if (button) button.disabled = true;
  databaseState.actionMessages[normalized] = "寫入分割事件並重建帳戶...";
  closeSplitModal();
  renderInstrumentList();
  try {
    const response = await fetch(withToken(`/api/database/${encodeURIComponent(normalized)}/split`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        effective_date: dateText,
        ratio_from: 1,
        ratio_to: ratioTo,
        note: "手動輸入 ETF/股票分割事件",
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    databaseState.actionMessages[normalized] = data.message || `已新增 ${normalized} 分割事件`;
    await loadDatabase({ append: false });
  } catch (error) {
    databaseState.actionMessages[normalized] = `分割事件寫入失敗：${error.message || error}`;
    renderInstrumentList();
  } finally {
    if (button) button.disabled = false;
  }
}

async function updateListingDate(ticker, button) {
  const normalized = String(ticker || "").trim().toUpperCase();
  if (!normalized) return;
  const current = databaseState.items.find((item) => item.ticker === normalized)?.listing_date || "";
  const value = window.prompt(`輸入 ${normalized} 上市/掛牌日 YYYY-MM-DD`, current);
  if (value === null) return;
  const listingDate = String(value || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(listingDate)) {
    databaseState.actionMessages[normalized] = "日期格式請用 YYYY-MM-DD";
    renderInstrumentList();
    return;
  }
  button.disabled = true;
  databaseState.actionMessages[normalized] = "更新上市日中...";
  renderInstrumentList();
  try {
    const response = await fetch(withToken(`/api/database/${encodeURIComponent(normalized)}/listing-date`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ listing_date: listingDate }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    databaseState.actionMessages[normalized] = data.message || `已更新 ${normalized}`;
    await loadDatabase({ append: false });
  } catch (error) {
    databaseState.actionMessages[normalized] = `更新失敗：${error.message || error}`;
    renderInstrumentList();
  } finally {
    button.disabled = false;
  }
}

byId("database-search").addEventListener("input", scheduleDatabaseLoad);
byId("database-suffix-filter").addEventListener("change", scheduleDatabaseLoad);
byId("database-type-filter").addEventListener("change", scheduleDatabaseLoad);

if (byId("instrument-form")) {
  byId("instrument-form").addEventListener("submit", submitInstrumentForm);
}

if (byId("instrument-ticker")) {
  byId("instrument-ticker").addEventListener("input", suggestInstrumentType);
}

if (byId("split-form") && byId("split-cancel") && byId("split-modal")) {
  byId("split-form").addEventListener("submit", submitSplitAction);
  byId("split-cancel").addEventListener("click", closeSplitModal);
  byId("split-modal").addEventListener("click", (event) => {
    if (event.target === byId("split-modal")) closeSplitModal();
  });
}

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

  const listingDateButton = event.target.closest("[data-listing-date]");
  if (listingDateButton) {
    updateListingDate(listingDateButton.dataset.listingDate, listingDateButton);
    return;
  }

  const splitButton = event.target.closest("[data-split-action]");
  if (splitButton) {
    openSplitModal(splitButton.dataset.splitAction, splitButton);
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

if (byId("database-pagination")) {
  byId("database-pagination").addEventListener("click", (event) => {
    const button = event.target.closest("#database-load-more");
    if (!button) return;
    button.disabled = true;
    loadDatabase({ append: true }).catch((error) => {
      databaseState.loading = false;
      byId("database-list").insertAdjacentHTML(
        "beforeend",
        `<div class="empty">載入更多失敗：${escapeHtml(error.message || error)}</div>`
      );
      renderPagination();
    });
  });
}

loadDatabase({ append: false }).catch((error) => {
  databaseState.loading = false;
  byId("database-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
  renderPagination();
});
