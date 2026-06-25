const profile = window.DASHBOARD_PROFILE || {};
const token = new URLSearchParams(window.location.search).get("token") || "";
const pageState = {
  holdings: [],
  watchlist: [],
  searchResults: [],
  dividendMovements: [],
  selectionItems: [],
  selectedKey: "",
  searchTerm: "",
  searchStatus: "idle",
};
const byId = (id) => document.getElementById(id);
let searchTimer = null;

function withToken(path) {
  if (!token) return path;
  return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
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
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

function money(value, decimals = 0) {
  const result = numberValue(value);
  if (result === null) return "N/A";
  return result.toLocaleString("zh-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function percent(value) {
  const result = numberValue(value);
  if (result === null) return "N/A";
  return `${result >= 0 ? "+" : ""}${money(result, 2)}%`;
}

function valueClass(value) {
  const result = numberValue(value);
  if (result === null || result === 0) return "flat";
  return result > 0 ? "positive" : "negative";
}

function shortDate(value) {
  return value ? String(value).replaceAll("-", "/") : "N/A";
}

function compact(value) {
  return String(value || "").trim().toLowerCase();
}

function stateLabel(state) {
  if (state === "held") return "持有";
  if (state === "watchlist") return "觀察";
  return "搜尋";
}

function itemKey(item) {
  return `${item.instrument_state}:${String(item.ticker || "").toUpperCase()}`;
}

function matchesSearch(item) {
  const term = compact(pageState.searchTerm);
  if (!term) return true;
  return [item.ticker, item.name, item.symbol, item.yahoo_symbol]
    .map(compact)
    .some((value) => value.includes(term));
}

function normalizeAccountItem(item, instrumentState) {
  return {
    ...item,
    instrument_state: instrumentState,
    selection_group: instrumentState === "held" ? "My holdings" : "Watchlist / favorites",
  };
}

function normalizeSearchItem(item) {
  return {
    ...item,
    instrument_state: "search_only",
    selection_group: "Search results from central instrument database",
    symbol: item.symbol || item.yahoo_symbol || "",
    close: item.close,
    change_pct: item.change_pct,
    quote: {
      close: item.close,
      change_pct: item.change_pct,
      price_time: item.price_time,
      source: item.quote_source || item.source || "",
      source_market: item.market || "",
    },
  };
}

function buildSelectionItems() {
  const byTicker = new Map();
  const items = [];

  pageState.holdings.forEach((item) => {
    const normalized = normalizeAccountItem(item, "held");
    if (!matchesSearch(normalized)) return;
    byTicker.set(String(normalized.ticker || "").toUpperCase(), normalized);
    items.push(normalized);
  });

  pageState.watchlist.forEach((item) => {
    const ticker = String(item.ticker || "").toUpperCase();
    if (byTicker.has(ticker)) return;
    const normalized = normalizeAccountItem(item, "watchlist");
    if (!matchesSearch(normalized)) return;
    byTicker.set(ticker, normalized);
    items.push(normalized);
  });

  pageState.searchResults.forEach((item) => {
    const ticker = String(item.ticker || "").toUpperCase();
    if (!ticker || byTicker.has(ticker)) return;
    const normalized = normalizeSearchItem(item);
    byTicker.set(ticker, normalized);
    items.push(normalized);
  });

  pageState.selectionItems = items;
  if (!items.some((item) => itemKey(item) === pageState.selectedKey)) {
    pageState.selectedKey = items[0] ? itemKey(items[0]) : "";
  }
}

function selectedItem() {
  return pageState.selectionItems.find((item) => itemKey(item) === pageState.selectedKey) || null;
}

function emptySelectionMessage() {
  const query = String(pageState.searchTerm || "").trim();
  if (!query) {
    return `<div class="panel empty">目前沒有可選擇的標的</div>`;
  }
  if (pageState.searchStatus !== "loaded") {
    return `<div class="panel empty">正在搜尋本地資料庫...</div>`;
  }
  return `
    <div class="panel empty">
      <strong>本地資料庫找不到「${escapeHtml(query)}」</strong>
      <p>可能尚未入檔，或代號／名稱有誤。請確認輸入，或先到資料庫頁新增／更新標的。</p>
    </div>`;
}

function emptySelectLabel() {
  const query = String(pageState.searchTerm || "").trim();
  if (query && pageState.searchStatus === "loaded") {
    return `本地資料庫找不到「${query}」`;
  }
  return query ? "正在搜尋本地資料庫..." : "沒有可選擇的標的";
}

function detailMetric(label, value, className = "") {
  return `<div class="stock-detail-metric"><span>${escapeHtml(label)}</span><strong class="${className}">${value}</strong></div>`;
}

function renderLots(item) {
  const lots = Array.isArray(item.lots) ? item.lots : [];
  if (!lots.length) return `<div class="empty">目前沒有可顯示的庫存批次</div>`;
  return `
    <div class="stock-detail-lot-list">
      ${lots.map((lot) => `
        <article class="stock-detail-lot ${numberValue(lot.remaining_shares) === 0 ? "closed" : ""}">
          <div><span>日期</span><strong>${escapeHtml(shortDate(lot.date))}</strong></div>
          <div><span>股數</span><strong>${money(lot.shares)}</strong></div>
          <div><span>剩餘</span><strong>${money(lot.remaining_shares)}</strong></div>
          <div><span>成交</span><strong>${money(lot.price, 2)}</strong></div>
          <div><span>成本</span><strong>${money(lot.cost_per_share, 2)}</strong></div>
          <div><span>手續費</span><strong>${money(lot.fee)}</strong></div>
        </article>
      `).join("")}
    </div>`;
}

function renderDividendSchedule(item) {
  const schedule = item.dividend_schedule || {};
  const next = schedule.next_event || {};
  if (!Object.keys(schedule).length && !Object.keys(next).length) {
    return `
      <section class="stock-detail-section">
        <div class="section-title"><h2>股利資訊</h2></div>
        <div class="empty">目前沒有本地股利排程資料</div>
      </section>`;
  }
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>股利資訊</h2></div>
      <div class="stock-detail-metrics compact">
        ${detailMetric("頻率", escapeHtml(schedule.frequency?.label || "不固定"))}
        ${detailMetric("除息日", escapeHtml(shortDate(next.ex_dividend_date)))}
        ${detailMetric("每股配息", money(next.dividend, 3))}
        ${detailMetric("估計現金", money(next.estimated_cash))}
        ${detailMetric("發放日", escapeHtml(shortDate(next.payout_date)))}
      </div>
    </section>`;
}

function renderActualDividends(item) {
  if (item.instrument_state !== "held") return "";
  const ticker = String(item.ticker || "").toUpperCase();
  const rows = pageState.dividendMovements.filter((row) => String(row.ticker || "").toUpperCase() === ticker);
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>實收股利</h2></div>
      ${rows.length ? `
        <div class="stock-detail-lot-list">
          ${rows.map((row) => `
            <article class="stock-detail-lot">
              <div><span>日期</span><strong>${escapeHtml(shortDate(row.time))}</strong></div>
              <div><span>金額</span><strong>${money(row.amount)}</strong></div>
              <div><span>備註</span><strong>${escapeHtml(row.note || "")}</strong></div>
            </article>
          `).join("")}
        </div>
      ` : `<div class="empty">目前沒有此標的的實收股利紀錄</div>`}
    </section>`;
}

function renderAccountSection(item) {
  if (item.instrument_state !== "held") {
    return `
      <section class="stock-detail-section">
        <div class="section-title"><h2>帳戶部位</h2></div>
        <div class="empty">${item.instrument_state === "watchlist" ? "此標的是觀察名單項目，沒有帳戶損益。" : "此標的是搜尋結果，尚未加入帳戶或觀察名單。"}</div>
      </section>`;
  }

  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>帳戶部位</h2></div>
      <div class="stock-detail-metrics">
        ${detailMetric("股數", money(item.shares))}
        ${detailMetric("平均成本", money(item.avg_cost, 2))}
        ${detailMetric("損益兩平", money(item.breakeven_price, 2))}
        ${detailMetric("成本", money(item.cost_value))}
        ${detailMetric("市值", money(item.market_value))}
        ${detailMetric("未實現損益", money(item.unrealized_pnl), valueClass(item.unrealized_pnl))}
        ${detailMetric("損益率", percent(item.pnl_pct), valueClass(item.pnl_pct))}
        ${detailMetric("配息月數", money(item.dividend_months, 1))}
      </div>
    </section>`;
}

function renderWatchNotes(item) {
  if (item.instrument_state === "held") return "";
  if (!item.reason && !item.note && item.target_buy_price === undefined && item.alert_price === undefined) return "";
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>觀察設定</h2></div>
      <div class="stock-detail-metrics compact">
        ${detailMetric("買價", money(item.target_buy_price, 2))}
        ${detailMetric("提醒", money(item.alert_price, 2))}
        ${detailMetric("停損", money(item.stop_loss_price, 2))}
        ${detailMetric("賣價", money(item.target_sell_price, 2))}
      </div>
      ${item.reason ? `<p class="note">${escapeHtml(item.reason)}</p>` : ""}
      ${item.note ? `<p class="note">${escapeHtml(item.note)}</p>` : ""}
    </section>`;
}

function renderDataHealth(item) {
  const quoteDate = item.quote?.price_time || item.price_time || item.after_close_quote?.trade_date || "";
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>資料來源</h2></div>
      <div class="stock-detail-metrics compact">
        ${detailMetric("狀態", escapeHtml(stateLabel(item.instrument_state)))}
        ${detailMetric("代號", escapeHtml(item.symbol || item.yahoo_symbol || ""))}
        ${detailMetric("時間", escapeHtml(shortDate(quoteDate)))}
        ${detailMetric("來源", escapeHtml(item.quote?.source || item.quote_source || item.source || ""))}
        ${detailMetric("日線筆數", money(item.daily_bar_count, 0))}
        ${detailMetric("最近日線", escapeHtml(shortDate(item.daily_last_date)))}
      </div>
    </section>`;
}

function renderSelectedInstrument() {
  const root = byId("stock-detail-view");
  const item = selectedItem();
  if (!item) {
    root.innerHTML = emptySelectionMessage();
    return;
  }

  const quoteDate = item.quote?.price_time || item.price_time || item.after_close_quote?.trade_date || "";
  const historyUrl = withToken(`/database/${encodeURIComponent(item.ticker)}/history`);
  root.innerHTML = `
    <article class="panel stock-detail-card">
      <header class="stock-detail-head">
        <div>
          <span class="ticker">${escapeHtml(item.ticker)} · ${escapeHtml(item.type || "")} · ${escapeHtml(stateLabel(item.instrument_state))}</span>
          <h2>${escapeHtml(item.name || item.ticker)}</h2>
          <span class="muted">${escapeHtml(item.symbol || item.yahoo_symbol || "")}</span>
        </div>
        <div class="stock-detail-quote">
          <strong>${money(item.close, 2)}</strong>
          <span class="${valueClass(item.change_pct)}">${percent(item.change_pct)}</span>
          <small>${escapeHtml(shortDate(quoteDate))}</small>
        </div>
      </header>

      <div class="stock-detail-signals">
        ${(item.signals || []).map((signal) => `<span>${escapeHtml(signal)}</span>`).join("") || `<span>${escapeHtml(stateLabel(item.instrument_state))}</span>`}
      </div>

      ${renderAccountSection(item)}
      ${renderWatchNotes(item)}
      ${renderDividendSchedule(item)}
      ${renderActualDividends(item)}

      ${item.instrument_state === "held" ? `
        <section class="stock-detail-section">
          <div class="section-title stock-detail-section-title">
            <h2>庫存批次</h2>
            <span class="muted">${money((item.lots || []).length)} 筆</span>
          </div>
          ${renderLots(item)}
        </section>
      ` : ""}

      ${renderDataHealth(item)}

      <div class="stock-detail-actions">
        <a class="icon-button top-link" href="${historyUrl}">查看本地日線</a>
      </div>
    </article>`;
}

function groupedItems() {
  return [
    ["My holdings", pageState.selectionItems.filter((item) => item.instrument_state === "held")],
    ["Watchlist / favorites", pageState.selectionItems.filter((item) => item.instrument_state === "watchlist")],
    ["Search results from central instrument database", pageState.selectionItems.filter((item) => item.instrument_state === "search_only")],
  ];
}

function renderSelector() {
  const select = byId("stock-detail-select");
  const groups = groupedItems();
  const options = groups
    .filter(([, items]) => items.length)
    .map(([label, items]) => `
      <optgroup label="${escapeHtml(label)}">
        ${items.map((item) => `
          <option value="${escapeHtml(itemKey(item))}" ${itemKey(item) === pageState.selectedKey ? "selected" : ""}>
            ${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}
          </option>
        `).join("")}
      </optgroup>
    `)
    .join("");
  if (!options) {
    select.innerHTML = `<option value="">${escapeHtml(emptySelectLabel())}</option>`;
    return;
  }
  select.innerHTML = options || `<option value="">沒有符合的標的</option>`;
}

function renderPage(data) {
  pageState.holdings = Array.isArray(data.holdings) ? data.holdings : [];
  pageState.watchlist = Array.isArray(data.watchlist) ? data.watchlist : [];
  pageState.dividendMovements = Array.isArray(data.dividend_movements) ? data.dividend_movements : [];
  buildSelectionItems();
  byId("stock-detail-count").textContent = money(pageState.selectionItems.length);
  byId("stock-detail-updated-at").textContent = data.updated_at || "N/A";
  renderSelector();
  renderSelectedInstrument();
}

async function searchLocalInstruments(term) {
  const query = String(term || "").trim();
  if (!query) {
    pageState.searchResults = [];
    pageState.searchStatus = "idle";
    buildSelectionItems();
    renderSelector();
    renderSelectedInstrument();
    return;
  }

  const params = new URLSearchParams({ q: query, limit: "30" });
  const response = await fetch(withToken(`/api/database?${params.toString()}`));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  pageState.searchResults = Array.isArray(data.instruments) ? data.instruments : [];
  pageState.searchStatus = "loaded";
  buildSelectionItems();
  renderSelector();
  renderSelectedInstrument();
}

async function loadPage(force = false) {
  const button = byId("stock-detail-refresh");
  button.disabled = true;
  button.textContent = "載入中";
  try {
    const path = force ? `/${profile.slug}/api/refresh` : `/${profile.slug}/api/state`;
    const response = await fetch(withToken(path), { method: force ? "POST" : "GET" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderPage(await response.json());
  } catch (error) {
    byId("stock-detail-view").innerHTML = `<div class="panel empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "重新整理";
  }
}

byId("stock-detail-search").addEventListener("input", (event) => {
  pageState.searchTerm = event.target.value;
  pageState.searchStatus = pageState.searchTerm.trim() ? "loading" : "idle";
  window.clearTimeout(searchTimer);
  buildSelectionItems();
  renderSelector();
  renderSelectedInstrument();
  searchTimer = window.setTimeout(() => {
    searchLocalInstruments(pageState.searchTerm).catch((error) => {
      byId("stock-detail-view").innerHTML = `<div class="panel empty">搜尋失敗：${escapeHtml(error.message || error)}</div>`;
    });
  }, 220);
});

byId("stock-detail-select").addEventListener("change", (event) => {
  pageState.selectedKey = event.target.value;
  renderSelectedInstrument();
});
byId("stock-detail-refresh").addEventListener("click", () => loadPage(true));
loadPage(false);
