const profile = window.DASHBOARD_PROFILE || {};
const token = new URLSearchParams(window.location.search).get("token") || "";
const pageState = {
  holdings: [],
  watchlist: [],
  searchResults: [],
  dividendMovements: [],
  transactionBook: [],
  selectionItems: [],
  selectedKey: "",
  searchTerm: "",
  searchStatus: "idle",
  klineRangeDays: 180,
  klineCache: {},
  dividendCalendarCache: {},
  etfHoldingsCache: {},
  etfHoldingsImport: {
    ticker: "",
    csvText: "",
    source: "manual_csv",
    sourceUrl: "",
    override: false,
    panelOpen: false,
    status: "idle",
    preview: null,
    previewValid: false,
    message: "",
    errors: [],
    warnings: [],
  },
  etfHoldingsProvider: {
    ticker: "",
    providerId: "",
    override: false,
    panelOpen: false,
    sourcesStatus: "idle",
    sources: [],
    sourcesMessage: "",
    status: "idle",
    preview: null,
    previewValid: false,
    message: "",
    errors: [],
    warnings: [],
  },
  klineSelections: {},
  klineDisplay: {
    ma: true,
    volume: true,
    range: true,
    detail: true,
    cost: true,
    buys: true,
    dividends: true,
  },
  klineBuySelections: {},
  klineDividendSelections: {},
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

function weightPercent(value) {
  const result = numberValue(value);
  if (result === null) return "N/A";
  return `${money(result, 2)}%`;
}

function friendlySourceLabel(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === "N/A") return "N/A";
  if (raw.includes(" / ")) {
    return raw.split(" / ").map(friendlySourceLabel).join(" / ");
  }
  const labels = {
    TWSE_STOCK_DAY: "TWSE 官方日線",
    TPEX_TRADING_STOCK: "TPEX 官方日線",
    TWSE: "TWSE 官方資料",
    TPEX: "TPEX 官方資料",
    YAHOO: "Yahoo 資料",
  };
  const lowerLabels = {
    official_daily_fallback: "官方日線收盤",
    yfinance: "Yahoo Finance 報價",
    yahoo_historical: "Yahoo 歷史股利",
    twse_etfortune: "TWSE ETF 配息資料",
    local_csv: "本地 CSV",
  };
  const label = labels[raw.toUpperCase()] || lowerLabels[raw.toLowerCase()];
  return label ? `${label}（${raw}）` : raw;
}

function valueClass(value) {
  const result = numberValue(value);
  if (result === null || result === 0) return "flat";
  return result > 0 ? "positive" : "negative";
}

function shortDate(value) {
  return value ? String(value).replaceAll("-", "/") : "N/A";
}

function isoDate(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function dateDaysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDate(date);
}

function yearFromDate(value) {
  const match = String(value || "").match(/^(\d{4})/);
  return match ? Number(match[1]) : new Date().getFullYear();
}

function klineDateRange() {
  const start = dateDaysAgo(pageState.klineRangeDays);
  const end = isoDate(new Date());
  return {
    start,
    end,
    startYear: yearFromDate(start),
    endYear: yearFromDate(end),
  };
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

function isEtfInstrument(item) {
  const type = String(item?.type || item?.asset_type || "").trim().toUpperCase();
  const ticker = String(item?.ticker || "").trim();
  return type === "ETF" || ticker.startsWith("00");
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
  const source = item.quote?.source || item.quote_source || item.source || "";
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>資料來源</h2></div>
      <div class="stock-detail-metrics compact">
        ${detailMetric("狀態", escapeHtml(stateLabel(item.instrument_state)))}
        ${detailMetric("代號", escapeHtml(item.symbol || item.yahoo_symbol || ""))}
        ${detailMetric("時間", escapeHtml(shortDate(quoteDate)))}
        ${detailMetric("來源", escapeHtml(friendlySourceLabel(source)))}
        ${detailMetric("日線筆數", money(item.daily_bar_count, 0))}
        ${detailMetric("最近日線", escapeHtml(shortDate(item.daily_last_date)))}
      </div>
    </section>`;
}

function etfHoldingsCacheKey(item) {
  return String(item?.ticker || "").toUpperCase();
}

function sortedEtfComponents(payload) {
  return Array.isArray(payload?.components)
    ? [...payload.components].sort((a, b) => {
        const orderA = numberValue(a.sort_order) ?? 9999;
        const orderB = numberValue(b.sort_order) ?? 9999;
        if (orderA !== orderB) return orderA - orderB;
        return (numberValue(b.weight) || 0) - (numberValue(a.weight) || 0);
      })
    : [];
}

function etfHoldingsSourceLabel(value) {
  const source = String(value || "").trim();
  if (!source) return "N/A";
  if (source === "synthetic_demo") return "Demo 合成資料";
  if (source === "local_csv" || source === "local_csv_etf_holdings") return "本機 CSV";
  return friendlySourceLabel(source);
}

function renderEtfDonut(topRows, otherWeight) {
  const weights = topRows
    .map((row) => Math.max(0, numberValue(row.weight) || 0))
    .filter((value) => value > 0);
  const other = Math.max(0, numberValue(otherWeight) || 0);
  const total = weights.reduce((sum, value) => sum + value, 0) + other;
  if (!total) return "";

  const colors = ["#7cc4ff", "#70e1c8", "#ffd166", "#c084fc", "#ff6961", "#92a0b3"];
  let cursor = 0;
  const segments = weights.map((weight, index) => {
    const start = cursor;
    const end = cursor + (weight / total) * 360;
    cursor = end;
    return `${colors[index % colors.length]} ${start.toFixed(2)}deg ${end.toFixed(2)}deg`;
  });
  if (other > 0) {
    segments.push(`${colors[colors.length - 1]} ${cursor.toFixed(2)}deg 360deg`);
  }
  return `<div class="etf-holdings-donut" style="background: conic-gradient(${segments.join(", ")});" aria-hidden="true"></div>`;
}

function etfImportIssueText(issue) {
  const code = String(issue?.code || "");
  const messages = {
    csv_text_required: "請先貼上 CSV 內容。",
    etf_ticker_required: "CSV 需要 ETF 代號，或使用目前頁面的 ETF 代號。",
    as_of_date_required: "CSV 需要快照日期 as_of_date 或 date。",
    source_required: "資料來源不可空白。",
    components_required: "至少需要一筆成分股代號或名稱。",
    negative_weight: "權重不可為負數。",
    older_snapshot_exists: "已有較新的持股快照；如仍要匯入，請勾選允許匯入較舊快照。",
    provider_config_missing: "尚未設定此 ETF 的投信來源，可改用 CSV 匯入。",
    provider_not_found: "找不到可用的投信來源設定，可改用 CSV 匯入。",
    provider_unsupported_ticker: "目前設定的投信來源不支援這檔 ETF，可改用 CSV 匯入。",
    provider_fetch_failed: "投信來源暫時無法讀取，請稍後再試或改用 CSV 匯入。",
    provider_parse_failed: "投信來源格式無法解析，可改用 CSV 匯入。",
    provider_no_snapshot: "投信來源未回傳可用的持股快照。",
    ticker_required: "缺少 ETF 代號。",
  };
  return messages[code] || issue?.message || code || "CSV 驗證失敗。";
}

function renderEtfImportMessages(items, className) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return "";
  return `
    <div class="etf-import-messages ${className}">
      ${rows.map((issue) => `<p>${escapeHtml(etfImportIssueText(issue))}</p>`).join("")}
    </div>`;
}

function renderEtfImportPreview(preview, statusLabel = "") {
  if (!preview) return "";
  const snapshot = preview.snapshot || {};
  const summary = preview.summary || {};
  const rows = Array.isArray(preview.components) ? preview.components.slice(0, 5) : [];
  const label = statusLabel || (preview.imported ? "已匯入" : "預覽");
  return `
    <div class="etf-import-preview">
      <div class="stock-detail-metrics compact etf-import-preview-metrics">
        ${detailMetric("快照日期", escapeHtml(shortDate(snapshot.as_of_date || summary.as_of_date)))}
        ${detailMetric("來源", escapeHtml(etfHoldingsSourceLabel(snapshot.source || summary.source)))}
        ${detailMetric("成分數", money(summary.component_count ?? rows.length))}
        ${detailMetric("權重合計", weightPercent(summary.weight_total))}
        ${detailMetric("狀態", escapeHtml(label))}
      </div>
      ${rows.length ? `
        <div class="etf-import-preview-list">
          ${rows.map((row) => `
            <div class="etf-import-preview-row">
              <strong>${escapeHtml(row.constituent_ticker || "--")}</strong>
              <span>${escapeHtml(row.constituent_name || "")}</span>
              <small>${weightPercent(row.weight)}</small>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </div>`;
}

function renderEtfHoldingsImportPanel(item) {
  if (!isEtfInstrument(item)) return "";
  const key = etfHoldingsCacheKey(item);
  const importState = pageState.etfHoldingsImport;
  if (importState.ticker !== key) {
    importState.ticker = key;
    importState.preview = null;
    importState.previewValid = false;
    importState.message = "";
    importState.errors = [];
    importState.warnings = [];
    importState.status = "idle";
  }
  const loading = importState.status === "loading";
  const canConfirm = importState.previewValid && !loading;
  const open = importState.panelOpen || importState.status !== "idle" || importState.preview;
  return `
    <details class="etf-import-panel" ${open ? "open" : ""}>
      <summary class="etf-import-summary">
        <strong>手動匯入 ETF 持股 CSV</strong>
        <span>先預覽，再確認寫入研究資料</span>
      </summary>
      <div class="etf-import-body">
        <label>
          <span>CSV</span>
          <textarea data-etf-import-field="csvText" rows="7" placeholder="貼上 ETF 持股 CSV；支援 etf_ticker/as_of_date/constituent_ticker/weight 等欄位">${escapeHtml(importState.csvText)}</textarea>
        </label>
        <div class="etf-import-controls">
          <label>
            <span>來源</span>
            <input data-etf-import-field="source" type="text" value="${escapeHtml(importState.source || "manual_csv")}" placeholder="manual_csv">
          </label>
          <label>
            <span>來源網址</span>
            <input data-etf-import-field="sourceUrl" type="url" value="${escapeHtml(importState.sourceUrl || "")}" placeholder="選填">
          </label>
          <label class="etf-import-checkbox">
            <input data-etf-import-field="override" type="checkbox" ${importState.override ? "checked" : ""}>
            <span>允許匯入較舊快照</span>
          </label>
        </div>
        <div class="etf-import-actions">
          <button class="icon-button" type="button" data-etf-import-action="preview" ${loading ? "disabled" : ""}>預覽</button>
          <button class="icon-button" type="button" data-etf-import-action="confirm" ${canConfirm ? "" : "disabled"}>確認匯入</button>
        </div>
        ${importState.message ? `<p class="etf-import-status">${escapeHtml(importState.message)}</p>` : ""}
        ${renderEtfImportMessages(importState.errors, "error-text")}
        ${renderEtfImportMessages(importState.warnings, "warning-text")}
        ${renderEtfImportPreview(importState.preview)}
      </div>
    </details>`;
}

function renderEtfProviderSourceControl(providerState) {
  const sources = Array.isArray(providerState.sources) ? providerState.sources : [];
  if (providerState.sourcesStatus === "loading") {
    return `<p class="etf-provider-source-message">載入可用來源...</p>`;
  }
  if (!sources.length) {
    return `<p class="etf-provider-source-message">${escapeHtml(providerState.sourcesMessage || "尚未設定此 ETF 的投信來源，可使用 CSV 匯入。")}</p>`;
  }
  const selected = sources.some((source) => source.provider_id === providerState.providerId)
    ? providerState.providerId
    : sources[0].provider_id;
  providerState.providerId = selected;
  return `
    <label>
      <span>可用來源</span>
      <select data-etf-provider-field="providerId">
        ${sources.map((source) => {
          const label = source.display_name || source.provider_id;
          const issuer = source.issuer ? ` · ${source.issuer}` : "";
          return `<option value="${escapeHtml(source.provider_id)}" ${source.provider_id === selected ? "selected" : ""}>${escapeHtml(label + issuer)}</option>`;
        }).join("")}
      </select>
    </label>`;
}

function renderEtfHoldingsProviderPanel(item) {
  if (!isEtfInstrument(item)) return "";
  const key = etfHoldingsCacheKey(item);
  const providerState = pageState.etfHoldingsProvider;
  if (providerState.ticker !== key) {
    providerState.ticker = key;
    providerState.providerId = "";
    providerState.preview = null;
    providerState.previewValid = false;
    providerState.message = "";
    providerState.errors = [];
    providerState.warnings = [];
    providerState.status = "idle";
    providerState.sourcesStatus = "idle";
    providerState.sources = [];
    providerState.sourcesMessage = "";
  }
  if (providerState.sourcesStatus === "idle") {
    providerState.sourcesStatus = "loading";
    window.setTimeout(() => loadEtfProviderSourcesForSelected(), 0);
  }
  const loading = providerState.status === "loading";
  const sourcesLoading = providerState.sourcesStatus === "loading";
  const hasSources = Array.isArray(providerState.sources) && providerState.sources.length > 0;
  const canConfirm = providerState.previewValid && !loading;
  const open = providerState.panelOpen || providerState.status !== "idle" || providerState.preview;
  return `
    <details class="etf-import-panel etf-provider-panel" ${open ? "open" : ""}>
      <summary class="etf-import-summary">
        <strong>從投信來源更新</strong>
        <span>手動預覽投信/供應商資料，確認後才寫入</span>
      </summary>
      <div class="etf-import-body">
        <div class="etf-provider-controls">
          ${renderEtfProviderSourceControl(providerState)}
          <label class="etf-provider-manual-id">
            <span>Provider ID</span>
            <input data-etf-provider-field="providerId" type="text" value="${escapeHtml(providerState.providerId || "")}" placeholder="留空使用第一個可用來源">
          </label>
          <label class="etf-import-checkbox">
            <input data-etf-provider-field="override" type="checkbox" ${providerState.override ? "checked" : ""}>
            <span>允許匯入較舊快照</span>
          </label>
        </div>
        <div class="etf-import-actions">
          <button class="icon-button" type="button" data-etf-provider-action="preview" ${loading || sourcesLoading || !hasSources ? "disabled" : ""}>預覽來源</button>
          <button class="icon-button" type="button" data-etf-provider-action="confirm" ${canConfirm ? "" : "disabled"}>確認匯入</button>
        </div>
        ${providerState.message ? `<p class="etf-import-status">${escapeHtml(providerState.message)}</p>` : ""}
        ${renderEtfImportMessages(providerState.errors, "error-text")}
        ${renderEtfImportMessages(providerState.warnings, "warning-text")}
        ${renderEtfImportPreview(providerState.preview, providerState.preview?.imported ? "已匯入" : "未匯入預覽")}
      </div>
    </details>`;
}

function renderEtfHoldingsSection(item) {
  const key = etfHoldingsCacheKey(item);
  if (!key) return "";
  const cache = pageState.etfHoldingsCache[key] || { status: "idle" };
  const isEtf = isEtfInstrument(item);

  if (!isEtf && cache.status !== "loaded") return "";
  if (!isEtf && cache.status === "loaded" && !cache.payload?.snapshot) return "";

  if (cache.status === "idle" || cache.status === "loading") {
    return isEtf ? `
      <section class="stock-detail-section etf-holdings-card">
        <div class="section-title stock-detail-section-title"><h2>ETF 持股組成</h2></div>
        <div class="empty">讀取 ETF 持股資料中...</div>
        ${renderEtfHoldingsProviderPanel(item)}
        ${renderEtfHoldingsImportPanel(item)}
      </section>` : "";
  }

  if (cache.status === "error") {
    return isEtf ? `
      <section class="stock-detail-section etf-holdings-card">
        <div class="section-title stock-detail-section-title"><h2>ETF 持股組成</h2></div>
        <div class="empty">尚未建立持股快照</div>
        ${renderEtfHoldingsProviderPanel(item)}
        ${renderEtfHoldingsImportPanel(item)}
      </section>` : "";
  }

  const payload = cache.payload || {};
  const snapshot = payload.snapshot || null;
  const components = sortedEtfComponents(payload);
  if (!snapshot || !components.length) {
    return isEtf ? `
      <section class="stock-detail-section etf-holdings-card">
        <div class="section-title stock-detail-section-title"><h2>ETF 持股組成</h2></div>
        <div class="empty">${escapeHtml(payload.message ? "無 ETF 持股資料" : "尚未建立持股快照")}</div>
        ${renderEtfHoldingsProviderPanel(item)}
        ${renderEtfHoldingsImportPanel(item)}
      </section>` : "";
  }

  const topRows = components.slice(0, 8);
  const topWeight = topRows.reduce((sum, row) => sum + (numberValue(row.weight) || 0), 0);
  const otherWeight = components.slice(topRows.length).reduce((sum, row) => sum + (numberValue(row.weight) || 0), 0);
  const maxWeight = Math.max(...topRows.map((row) => numberValue(row.weight) || 0), 1);
  const source = snapshot.source || payload.summary?.source || "";
  const asOfDate = snapshot.as_of_date || payload.summary?.as_of_date || "";
  const componentCount = payload.summary?.component_count ?? components.length;
  const statusMessage = payload.message || snapshot.status || payload.data_status?.official_daily?.message || "";

  return `
    <section class="stock-detail-section etf-holdings-card">
      <div class="section-title stock-detail-section-title">
        <h2>ETF 持股組成</h2>
        <span class="muted">${escapeHtml(shortDate(asOfDate))} · ${escapeHtml(etfHoldingsSourceLabel(source))}</span>
      </div>
      <div class="etf-holdings-summary">
        ${renderEtfDonut(topRows.slice(0, 5), otherWeight)}
        <div class="stock-detail-metrics compact etf-holdings-metrics">
          ${detailMetric("快照日期", escapeHtml(shortDate(asOfDate)))}
          ${detailMetric("來源", escapeHtml(etfHoldingsSourceLabel(source)))}
          ${detailMetric("成分數", money(componentCount))}
          ${detailMetric("前段權重", weightPercent(topWeight))}
          ${detailMetric("其他權重", otherWeight > 0 ? weightPercent(otherWeight) : "N/A")}
        </div>
      </div>
      ${statusMessage ? `<p class="etf-holdings-message">${escapeHtml(statusMessage)}</p>` : ""}
      <div class="etf-holdings-list">
        ${topRows.map((row, index) => {
          const weight = numberValue(row.weight);
          const width = weight === null ? 0 : Math.max(2, Math.min(100, (weight / maxWeight) * 100));
          return `
            <article class="etf-holding-row">
              <div class="etf-holding-rank">${escapeHtml(row.sort_order || index + 1)}</div>
              <div class="etf-holding-main">
                <strong>${escapeHtml(row.constituent_ticker || "--")}</strong>
                <span>${escapeHtml(row.constituent_name || "")}</span>
                ${row.industry ? `<small>${escapeHtml(row.industry)}</small>` : ""}
              </div>
              <div class="etf-holding-weight">
                <strong>${weightPercent(weight)}</strong>
                <span class="etf-weight-bar"><span style="width: ${width.toFixed(2)}%;"></span></span>
              </div>
            </article>`;
        }).join("")}
      </div>
      ${renderEtfHoldingsProviderPanel(item)}
      ${renderEtfHoldingsImportPanel(item)}
    </section>`;
}

function klineCacheKey(item) {
  return `${String(item?.ticker || "").toUpperCase()}:${pageState.klineRangeDays}`;
}

function dividendCalendarCacheKey(item) {
  const ticker = String(item?.ticker || "").toUpperCase();
  const range = klineDateRange();
  return `${ticker}:${range.startYear}:${range.endYear}`;
}

function klineRows(cache) {
  return Array.isArray(cache?.rows)
    ? cache.rows
        .filter((row) => ["open", "high", "low", "close"].every((key) => numberValue(row[key]) !== null))
        .sort((a, b) => String(a.trade_date || a.date || "").localeCompare(String(b.trade_date || b.date || "")))
    : [];
}

function isHeldInstrument(item) {
  return item?.instrument_state === "held";
}

function buyTransactionsForItem(item, rows) {
  if (!isHeldInstrument(item)) return [];
  const ticker = String(item.ticker || "").toUpperCase();
  const visibleDates = new Set(rows.map((row) => String(row.trade_date || row.date || "").slice(0, 10)));
  return pageState.transactionBook
    .filter((row) => String(row.action || "").toUpperCase() === "BUY")
    .filter((row) => String(row.ticker || "").toUpperCase() === ticker)
    .filter((row) => visibleDates.has(String(row.date || row.time || "").slice(0, 10)))
    .sort((a, b) => String(a.date || a.time || "").localeCompare(String(b.date || b.time || "")));
}

function dividendSourceRank(row) {
  const source = String(row?.source || "").toLowerCase();
  if (source.includes("twse_etfortune")) return 3;
  if (source.includes("twse")) return 2;
  if (source.includes("yahoo")) return 1;
  return 0;
}

function dedupedDividendEvents(item, rows) {
  if (!pageState.klineDisplay.dividends) return [];
  const cache = pageState.dividendCalendarCache[dividendCalendarCacheKey(item)] || {};
  const records = Array.isArray(cache.rows) ? cache.rows : [];
  if (!records.length) return [];
  const ticker = String(item?.ticker || "").toUpperCase();
  const visibleDates = new Set(rows.map((row) => String(row.trade_date || row.date || "").slice(0, 10)));
  const byDate = new Map();
  records.forEach((row) => {
    const rowTicker = String(row.ticker || ticker).toUpperCase();
    const exDate = String(row.ex_dividend_date || "").slice(0, 10);
    if (!exDate || rowTicker !== ticker || !visibleDates.has(exDate)) return;
    const key = `${rowTicker}:${exDate}`;
    const source = String(row.source || "").trim();
    const existing = byDate.get(key);
    const sources = new Set(existing?._sources || []);
    if (source) sources.add(source);
    if (!existing || dividendSourceRank(row) > dividendSourceRank(existing)) {
      byDate.set(key, { ...row, _sources: sources });
    } else {
      existing._sources = sources;
    }
  });
  return Array.from(byDate.values())
    .map((row) => ({
      ...row,
      marker_id: String(row.ex_dividend_date || "").slice(0, 10),
      combined_source: Array.from(row._sources || []).filter(Boolean).join(" / ") || row.source || "",
    }))
    .sort((a, b) => String(a.ex_dividend_date || "").localeCompare(String(b.ex_dividend_date || "")));
}

function movingAverageSeries(rows, period) {
  const closes = rows.map((row) => numberValue(row.close));
  let sum = 0;
  return closes.map((close, index) => {
    if (close === null) return null;
    sum += close;
    if (index >= period) {
      sum -= closes[index - period] || 0;
    }
    return index >= period - 1 ? sum / period : null;
  });
}

function latestMovingAverage(rows, period) {
  const series = movingAverageSeries(rows, period).filter((value) => value !== null);
  return series.length ? series[series.length - 1] : null;
}

function movingAverageText(rows, period) {
  const value = latestMovingAverage(rows, period);
  return value === null ? "--" : money(value, 2);
}

function renderMovingAverageLegend(rows) {
  return `
    <div class="kline-ma-legend">
      <span class="ma5">MA5（5日均線） ${movingAverageText(rows, 5)}</span>
      <span class="ma20">MA20（20日均線） ${movingAverageText(rows, 20)}</span>
      <span class="ma60">MA60（60日均線） ${movingAverageText(rows, 60)}</span>
    </div>
    <p class="kline-ma-note">MA = 移動平均線，用來看短中期趨勢。</p>`;
}

function renderKlineToggles(item) {
  const toggles = [
    ["ma", "MA（均線）"],
    ["volume", "成交量"],
    ["range", "高低點"],
    ["detail", "明細"],
    ["dividends", "除息"],
  ];
  if (isHeldInstrument(item)) {
    toggles.push(["cost", "成本線"], ["buys", "買進點"]);
  }
  return `
    <div class="kline-display-toggles" aria-label="K-line 顯示切換">
      ${toggles.map(([key, label]) => `
        <button
          class="kline-toggle-button ${pageState.klineDisplay[key] ? "active" : ""}"
          type="button"
          data-kline-toggle="${key}"
          aria-pressed="${pageState.klineDisplay[key] ? "true" : "false"}"
        >${label}</button>
      `).join("")}
    </div>`;
}

function renderKlineSvg(rows, cacheKey, selectedDate, item, dividendEvents, display = pageState.klineDisplay) {
  const width = 720;
  const height = 260;
  const padX = 46;
  const rightPad = 56;
  const priceTop = 16;
  const priceHeight = 156;
  const volumeTop = 196;
  const volumeHeight = 44;
  const innerWidth = width - padX - rightPad;
  const maSeries = [
    { period: 5, className: "ma5", values: movingAverageSeries(rows, 5) },
    { period: 20, className: "ma20", values: movingAverageSeries(rows, 20) },
    { period: 60, className: "ma60", values: movingAverageSeries(rows, 60) },
  ];
  const avgCost = numberValue(item?.avg_cost);
  const showCostLine = isHeldInstrument(item) && display.cost && avgCost !== null;
  const buyTransactions = isHeldInstrument(item) && display.buys ? buyTransactionsForItem(item, rows) : [];
  const rowPrices = rows.flatMap((row) => [row.open, row.high, row.low, row.close].map(numberValue)).filter((value) => value !== null);
  const maPrices = display.ma ? maSeries.flatMap((series) => series.values).filter((value) => value !== null) : [];
  const prices = rowPrices.concat(maPrices).concat(showCostLine ? [avgCost] : []);
  const volumes = rows.map((row) => numberValue(row.volume) || 0);
  const rangeLow = Math.min(...rowPrices);
  const rangeHigh = Math.max(...rowPrices);
  let min = rangeLow;
  let max = rangeHigh;
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const padding = (max - min) * 0.08;
  min -= padding;
  max += padding;
  const maxVolume = Math.max(...volumes, 1);
  const slot = innerWidth / rows.length;
  const candleWidth = Math.max(2, Math.min(10, slot * 0.55));
  const yFor = (value) => priceTop + ((max - value) / (max - min)) * priceHeight;
  const xFor = (index) => padX + slot * index + slot / 2;
  const priceTicks = [max, (max + min) / 2, min].map((value) => ({
    value,
    y: yFor(value),
  }));
  const rangeHighY = yFor(rangeHigh);
  const rangeLowY = yFor(rangeLow);
  const priceLabels = priceTicks.map((tick) => `
    <text class="kline-price-label" x="8" y="${tick.y.toFixed(2)}">${money(tick.value, 2)}</text>
  `).join("");

  const maPaths = display.ma
    ? maSeries.map((series) => {
      let started = false;
      const path = series.values.map((value, index) => {
        if (value === null) return "";
        const command = started ? "L" : "M";
        started = true;
        return `${command}${xFor(index).toFixed(2)},${yFor(value).toFixed(2)}`;
      }).filter(Boolean).join(" ");
      if (!path) return "";
      return `<path class="kline-ma-line ${series.className}" d="${path}"></path>`;
    }).join("")
    : "";

  const candles = rows.map((row, index) => {
    const open = numberValue(row.open);
    const high = numberValue(row.high);
    const low = numberValue(row.low);
    const close = numberValue(row.close);
    const volume = numberValue(row.volume) || 0;
    const x = xFor(index);
    const trend = close > open ? "up" : close < open ? "down" : "flat";
    const bodyY = Math.min(yFor(open), yFor(close));
    const bodyHeight = Math.max(1, Math.abs(yFor(open) - yFor(close)));
    const volumeHeightValue = Math.max(1, (volume / maxVolume) * volumeHeight);
    const date = row.trade_date || row.date || "";
    const title = `${date} O ${money(open, 2)} H ${money(high, 2)} L ${money(low, 2)} C ${money(close, 2)} V ${money(volume)}`;
    const selected = String(date) === String(selectedDate);
    const volumeBar = display.volume
      ? `<rect class="kline-volume" x="${(x - candleWidth / 2).toFixed(2)}" y="${(volumeTop + volumeHeight - volumeHeightValue).toFixed(2)}" width="${candleWidth.toFixed(2)}" height="${volumeHeightValue.toFixed(2)}"></rect>`
      : "";
    return `
      <g class="kline-candle ${trend} ${selected ? "selected" : ""}" data-kline-key="${escapeHtml(cacheKey)}" data-kline-candle="${escapeHtml(date)}" tabindex="0" role="button">
        <title>${escapeHtml(title)}</title>
        <line x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${yFor(high).toFixed(2)}" y2="${yFor(low).toFixed(2)}"></line>
        <rect x="${(x - candleWidth / 2).toFixed(2)}" y="${bodyY.toFixed(2)}" width="${candleWidth.toFixed(2)}" height="${bodyHeight.toFixed(2)}"></rect>
        ${volumeBar}
      </g>`;
  }).join("");

  const rangeMarks = display.range ? `
    <line class="kline-range-line high" x1="${padX}" x2="${width - rightPad}" y1="${rangeHighY.toFixed(2)}" y2="${rangeHighY.toFixed(2)}"></line>
    <line class="kline-range-line low" x1="${padX}" x2="${width - rightPad}" y1="${rangeLowY.toFixed(2)}" y2="${rangeLowY.toFixed(2)}"></line>
    <text class="kline-range-label high" x="${width - rightPad + 5}" y="${rangeHighY.toFixed(2)}">H ${money(rangeHigh, 2)}</text>
    <text class="kline-range-label low" x="${width - rightPad + 5}" y="${rangeLowY.toFixed(2)}">L ${money(rangeLow, 2)}</text>
  ` : "";
  const costOverlay = showCostLine ? `
    <line class="kline-cost-line" x1="${padX}" x2="${width - rightPad}" y1="${yFor(avgCost).toFixed(2)}" y2="${yFor(avgCost).toFixed(2)}"></line>
    <text class="kline-cost-label" x="${width - rightPad + 5}" y="${yFor(avgCost).toFixed(2)}">成本 ${money(avgCost, 2)}</text>
  ` : "";
  const dateToIndex = new Map(rows.map((row, index) => [String(row.trade_date || row.date || "").slice(0, 10), index]));
  const buyMarkers = buyTransactions.map((transaction, index) => {
    const date = String(transaction.date || transaction.time || "").slice(0, 10);
    const rowIndex = dateToIndex.get(date);
    if (rowIndex === undefined) return "";
    const row = rows[rowIndex];
    const low = numberValue(row.low);
    const markerId = `${date}:${index}`;
    const selected = pageState.klineBuySelections[cacheKey] === markerId;
    const y = low === null ? priceTop + priceHeight : Math.min(priceTop + priceHeight + 10, yFor(low) + 10);
    const x = xFor(rowIndex);
    const title = `${date} 買進 ${money(transaction.shares)} 股，價格 ${money(transaction.price, 2)}，手續費 ${money(transaction.fee)}`;
    return `
      <g class="kline-buy-marker ${selected ? "selected" : ""}" data-kline-buy-key="${escapeHtml(cacheKey)}" data-kline-buy-marker="${escapeHtml(markerId)}" tabindex="0" role="button">
        <title>${escapeHtml(title)}</title>
        <path d="M ${x.toFixed(2)} ${(y - 5).toFixed(2)} L ${(x - 5).toFixed(2)} ${(y + 4).toFixed(2)} L ${(x + 5).toFixed(2)} ${(y + 4).toFixed(2)} Z"></path>
      </g>`;
  }).join("");
  const dividendMarkers = display.dividends ? dividendEvents.map((event) => {
    const exDate = String(event.ex_dividend_date || "").slice(0, 10);
    const rowIndex = dateToIndex.get(exDate);
    if (rowIndex === undefined) return "";
    const row = rows[rowIndex];
    const high = numberValue(row.high);
    const x = xFor(rowIndex);
    const y = high === null ? priceTop + 10 : Math.max(priceTop + 10, yFor(high) - 14);
    const selected = pageState.klineDividendSelections[cacheKey] === event.marker_id;
    const title = `${exDate} 除息，每單位配息 ${money(event.dividend, 3)}，發放日 ${shortDate(event.payout_date)}，來源 ${friendlySourceLabel(event.combined_source || event.source || "")}`;
    return `
      <g class="kline-dividend-marker ${selected ? "selected" : ""}" data-kline-dividend-key="${escapeHtml(cacheKey)}" data-kline-dividend-marker="${escapeHtml(event.marker_id)}" tabindex="0" role="button">
        <title>${escapeHtml(title)}</title>
        <circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="7"></circle>
        <text x="${x.toFixed(2)}" y="${(y + 0.7).toFixed(2)}">D</text>
      </g>`;
  }).join("") : "";

  return `
    <svg class="kline-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="local daily OHLCV K-line">
      <line class="kline-grid" x1="${padX}" x2="${width - rightPad}" y1="${priceTop}" y2="${priceTop}"></line>
      <line class="kline-grid" x1="${padX}" x2="${width - rightPad}" y1="${(priceTop + priceHeight / 2).toFixed(2)}" y2="${(priceTop + priceHeight / 2).toFixed(2)}"></line>
      <line class="kline-grid" x1="${padX}" x2="${width - rightPad}" y1="${priceTop + priceHeight}" y2="${priceTop + priceHeight}"></line>
      <line class="kline-grid" x1="${padX}" x2="${width - rightPad}" y1="${volumeTop + volumeHeight}" y2="${volumeTop + volumeHeight}"></line>
      ${priceLabels}
      ${rangeMarks}
      ${costOverlay}
      ${candles}
      ${maPaths}
      ${buyMarkers}
      ${dividendMarkers}
    </svg>`;
}

function renderSelectedCandle(rows, selectedDate) {
  const index = rows.findIndex((row) => String(row.trade_date || row.date || "") === String(selectedDate));
  const row = rows[index >= 0 ? index : rows.length - 1];
  if (!row) return "";
  const previous = rows[index > 0 ? index - 1 : rows.length - 2] || null;
  const close = numberValue(row.close);
  const previousClose = numberValue(previous?.close);
  const change = close !== null && previousClose !== null ? close - previousClose : null;
  const changePct = change !== null && previousClose ? (change / previousClose) * 100 : null;
  const changeText = change === null
    ? "N/A"
    : `${change >= 0 ? "+" : ""}${money(change, 2)}${changePct === null ? "" : ` / ${percent(changePct)}`}`;
  return `
    <div class="kline-selected-detail">
      ${detailMetric("日期", escapeHtml(shortDate(row.trade_date || row.date)))}
      ${detailMetric("開盤", money(row.open, 2))}
      ${detailMetric("最高", money(row.high, 2))}
      ${detailMetric("最低", money(row.low, 2))}
      ${detailMetric("收盤", money(row.close, 2))}
      ${detailMetric("成交量", money(row.volume))}
      ${detailMetric("日變動", `<span class="${valueClass(change)}">${changeText}</span>`)}
    </div>`;
}

function renderSelectedBuyMarker(item, rows, cacheKey) {
  if (!isHeldInstrument(item) || !pageState.klineDisplay.buys) return "";
  const markerId = pageState.klineBuySelections[cacheKey];
  if (!markerId) return "";
  const buys = buyTransactionsForItem(item, rows);
  const indexText = String(markerId).split(":").pop();
  const transaction = buys[Number(indexText)];
  if (!transaction) return "";
  return `
    <div class="kline-buy-detail">
      ${detailMetric("買進日期", escapeHtml(shortDate(transaction.date || transaction.time)))}
      ${detailMetric("股數", money(transaction.shares))}
      ${detailMetric("價格", money(transaction.price, 2))}
      ${detailMetric("手續費", money(transaction.fee))}
    </div>`;
}

function renderSelectedDividendMarker(item, rows, cacheKey) {
  if (!pageState.klineDisplay.dividends) return "";
  const markerId = pageState.klineDividendSelections[cacheKey];
  if (!markerId) return "";
  const event = dedupedDividendEvents(item, rows).find((row) => row.marker_id === markerId);
  if (!event) return "";
  return `
    <div class="kline-dividend-detail">
      ${detailMetric("除息日", escapeHtml(shortDate(event.ex_dividend_date)))}
      ${detailMetric("每單位配息", money(event.dividend, 3))}
      ${detailMetric("發放日", escapeHtml(shortDate(event.payout_date)))}
      ${detailMetric("來源", escapeHtml(friendlySourceLabel(event.combined_source || event.source || "N/A")))}
    </div>`;
}

function renderKlineSection(item) {
  const cacheKey = klineCacheKey(item);
  const cache = pageState.klineCache[cacheKey] || { status: "idle" };
  const rows = klineRows(cache);
  const ranges = [
    [90, "3M"],
    [180, "6M"],
    [365, "1Y"],
  ];
  const buttons = ranges.map(([days, label]) => `
    <button class="kline-range-button ${pageState.klineRangeDays === days ? "active" : ""}" type="button" data-kline-range="${days}">${label}</button>
  `).join("");

  let body = `<div class="empty">正在讀取本地日線...</div>`;
  if (cache.status === "error") {
    body = `<div class="empty">讀取本地日線失敗：${escapeHtml(cache.error || "")}</div>`;
  } else if (cache.status === "loaded" && rows.length < 2) {
    body = `<div class="empty">本地日線資料不足，請先到資料庫頁更新或檢查此標的。</div>`;
  } else if (rows.length >= 2) {
    const first = rows[0];
    const latest = rows[rows.length - 1];
    const selectedDate = pageState.klineSelections[cacheKey] || latest.trade_date || latest.date || "";
    const source = latest.source || first.source || latest.source_market || first.source_market || "N/A";
    const dividendEvents = dedupedDividendEvents(item, rows);
    body = `
      <div class="kline-summary">
        ${detailMetric("最新收盤", money(latest.close, 2))}
        ${detailMetric("日期範圍", `${escapeHtml(shortDate(first.trade_date || first.date))} - ${escapeHtml(shortDate(latest.trade_date || latest.date))}`)}
        ${detailMetric("筆數", money(rows.length))}
        ${detailMetric("來源", escapeHtml(friendlySourceLabel(source)))}
      </div>
      ${pageState.klineDisplay.ma ? renderMovingAverageLegend(rows) : ""}
      ${renderKlineSvg(rows, cacheKey, selectedDate, item, dividendEvents)}
      ${renderSelectedBuyMarker(item, rows, cacheKey)}
      ${renderSelectedDividendMarker(item, rows, cacheKey)}
      ${pageState.klineDisplay.detail ? renderSelectedCandle(rows, selectedDate) : ""}`;
  }

  return `
    <section class="stock-detail-section stock-detail-kline">
      <div class="section-title stock-detail-section-title">
        <h2>K-line / OHLCV</h2>
        <div class="kline-range-buttons" aria-label="K-line range">${buttons}</div>
      </div>
      ${renderKlineToggles(item)}
      ${body}
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
      ${renderEtfHoldingsSection(item)}
      ${renderKlineSection(item)}

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
  pageState.transactionBook = Array.isArray(data.transaction_book) ? data.transaction_book : [];
  buildSelectionItems();
  byId("stock-detail-count").textContent = money(pageState.selectionItems.length);
  byId("stock-detail-updated-at").textContent = data.updated_at || "N/A";
  renderSelector();
  renderSelectedInstrument();
  loadKlineForSelected();
  loadDividendCalendarForSelected();
  loadEtfHoldingsForSelected();
}

async function searchLocalInstruments(term) {
  const query = String(term || "").trim();
  if (!query) {
    pageState.searchResults = [];
    pageState.searchStatus = "idle";
    buildSelectionItems();
    renderSelector();
    renderSelectedInstrument();
    loadKlineForSelected();
    loadDividendCalendarForSelected();
    loadEtfHoldingsForSelected();
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
  loadKlineForSelected();
  loadDividendCalendarForSelected();
  loadEtfHoldingsForSelected();
}

async function loadKlineForSelected() {
  const item = selectedItem();
  if (!item?.ticker) return;
  const key = klineCacheKey(item);
  const cached = pageState.klineCache[key];
  if (cached?.status === "loading" || cached?.status === "loaded") return;
  pageState.klineCache[key] = { status: "loading", rows: [] };
  renderSelectedInstrument();
  const end = isoDate(new Date());
  const start = dateDaysAgo(pageState.klineRangeDays);
  const params = new URLSearchParams({ start, end });
  try {
    const response = await fetch(withToken(`/api/database/${encodeURIComponent(item.ticker)}/history?${params.toString()}`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    pageState.klineCache[key] = {
      status: "loaded",
      rows: Array.isArray(data.rows) ? data.rows : [],
      summary: data.summary || {},
      updated_at: data.updated_at || "",
    };
  } catch (error) {
    pageState.klineCache[key] = {
      status: "error",
      rows: [],
      error: error.message || String(error),
    };
  }
  if (klineCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
}

async function loadDividendCalendarForSelected() {
  const item = selectedItem();
  if (!item?.ticker) return;
  const key = dividendCalendarCacheKey(item);
  const cached = pageState.dividendCalendarCache[key];
  if (cached?.status === "loading" || cached?.status === "loaded") return;
  pageState.dividendCalendarCache[key] = { status: "loading", rows: [] };
  const range = klineDateRange();
  const params = new URLSearchParams({
    ticker: String(item.ticker || "").toUpperCase(),
    start_year: String(range.startYear),
    end_year: String(range.endYear),
  });
  try {
    const response = await fetch(withToken(`/api/database/dividends?${params.toString()}`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    pageState.dividendCalendarCache[key] = {
      status: "loaded",
      rows: Array.isArray(data.records) ? data.records : [],
      updated_at: data.updated_at || "",
    };
  } catch (error) {
    pageState.dividendCalendarCache[key] = {
      status: "error",
      rows: [],
      error: error.message || String(error),
    };
  }
  if (dividendCalendarCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
}

async function loadEtfHoldingsForSelected() {
  const item = selectedItem();
  if (!item?.ticker) return;
  const key = etfHoldingsCacheKey(item);
  const cached = pageState.etfHoldingsCache[key];
  if (cached?.status === "loading" || cached?.status === "loaded") return;
  pageState.etfHoldingsCache[key] = { status: "loading", payload: null };
  renderSelectedInstrument();
  try {
    const response = await fetch(withToken(`/api/database/${encodeURIComponent(item.ticker)}/etf-holdings?as_of=latest`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    pageState.etfHoldingsCache[key] = {
      status: "loaded",
      payload: data || {},
    };
  } catch (error) {
    pageState.etfHoldingsCache[key] = {
      status: "error",
      payload: null,
      error: error.message || String(error),
    };
  }
  if (etfHoldingsCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
}

async function loadEtfProviderSourcesForSelected() {
  const item = selectedItem();
  if (!item?.ticker || !isEtfInstrument(item)) return;
  const key = etfHoldingsCacheKey(item);
  const providerState = pageState.etfHoldingsProvider;
  if (providerState.ticker !== key || providerState.sourcesStatus !== "loading") return;
  try {
    const params = new URLSearchParams({ ticker: String(item.ticker || "").trim().toUpperCase() });
    const response = await fetch(withToken(`/api/database/etf-holdings/providers?${params.toString()}`));
    const data = await response.json().catch(() => ({}));
    const sources = response.ok && data?.ok === true && Array.isArray(data.providers) ? data.providers : [];
    providerState.sourcesStatus = "loaded";
    providerState.sources = sources;
    providerState.sourcesMessage = data?.message || (sources.length ? "" : "尚未設定此 ETF 的投信來源，可使用 CSV 匯入。");
    if (!sources.some((source) => source.provider_id === providerState.providerId)) {
      providerState.providerId = sources[0]?.provider_id || "";
      providerState.preview = null;
      providerState.previewValid = false;
    }
  } catch (error) {
    providerState.sourcesStatus = "error";
    providerState.sources = [];
    providerState.sourcesMessage = "無法讀取可用投信來源，可使用 CSV 匯入。";
  }
  if (etfHoldingsCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
}

function etfImportIssues(data) {
  const issues = [];
  if (Array.isArray(data?.errors)) issues.push(...data.errors);
  if (!issues.length && data?.message) {
    issues.push({ code: "request_failed", message: data.message });
  }
  return issues;
}

function syncEtfImportStateFromDom({ resetPreview = false } = {}) {
  const fields = document.querySelectorAll("[data-etf-import-field]");
  if (!fields.length) return;
  const importState = pageState.etfHoldingsImport;
  importState.panelOpen = Boolean(document.querySelector(".etf-import-panel")?.open);
  fields.forEach((field) => {
    const key = field.dataset.etfImportField;
    if (!Object.prototype.hasOwnProperty.call(importState, key)) return;
    importState[key] = field.type === "checkbox" ? field.checked : field.value;
  });
  if (resetPreview) {
    importState.preview = null;
    importState.previewValid = false;
    importState.status = "idle";
    importState.message = "";
    importState.errors = [];
    importState.warnings = [];
    document.querySelectorAll('[data-etf-import-action="confirm"]').forEach((button) => {
      button.disabled = true;
    });
    document.querySelectorAll(".etf-import-status, .etf-import-messages, .etf-import-preview").forEach((node) => {
      node.remove();
    });
  }
}

function etfImportPayload(item, confirm) {
  const importState = pageState.etfHoldingsImport;
  return {
    csv_text: importState.csvText || "",
    etf_ticker: String(item?.ticker || "").trim().toUpperCase(),
    source: String(importState.source || "manual_csv").trim() || "manual_csv",
    source_url: String(importState.sourceUrl || "").trim(),
    override: Boolean(importState.override),
    confirm: Boolean(confirm),
  };
}

function syncEtfProviderStateFromDom({ resetPreview = false } = {}) {
  const fields = document.querySelectorAll("[data-etf-provider-field]");
  if (!fields.length) return;
  const providerState = pageState.etfHoldingsProvider;
  providerState.panelOpen = Boolean(document.querySelector(".etf-provider-panel")?.open);
  fields.forEach((field) => {
    if (field.closest(".etf-provider-manual-id")) return;
    const key = field.dataset.etfProviderField;
    if (!Object.prototype.hasOwnProperty.call(providerState, key)) return;
    providerState[key] = field.type === "checkbox" ? field.checked : field.value;
  });
  if (resetPreview) {
    providerState.preview = null;
    providerState.previewValid = false;
    providerState.status = "idle";
    providerState.message = "";
    providerState.errors = [];
    providerState.warnings = [];
    document.querySelectorAll('[data-etf-provider-action="confirm"]').forEach((button) => {
      button.disabled = true;
    });
    document.querySelectorAll(".etf-provider-panel .etf-import-status, .etf-provider-panel .etf-import-messages, .etf-provider-panel .etf-import-preview").forEach((node) => {
      node.remove();
    });
  }
}

function etfProviderPayload(item, confirm) {
  const providerState = pageState.etfHoldingsProvider;
  const payload = {
    ticker: String(item?.ticker || "").trim().toUpperCase(),
    override: Boolean(providerState.override),
    confirm: Boolean(confirm),
  };
  const providerId = String(providerState.providerId || "").trim();
  if (providerId) payload.provider_id = providerId;
  return payload;
}

async function submitEtfHoldingsImport(confirm = false) {
  const item = selectedItem();
  if (!item?.ticker || !isEtfInstrument(item)) return;
  syncEtfImportStateFromDom();
  const importState = pageState.etfHoldingsImport;
  if (confirm && !importState.previewValid) {
    importState.status = "error";
    importState.message = "請先完成有效預覽，再確認匯入。";
    importState.errors = [];
    renderSelectedInstrument();
    return;
  }
  if (!String(importState.csvText || "").trim()) {
    importState.status = "error";
    importState.previewValid = false;
    importState.message = "請先貼上 ETF 持股 CSV。";
    importState.errors = [];
    renderSelectedInstrument();
    return;
  }

  const key = etfHoldingsCacheKey(item);
  importState.status = "loading";
  importState.message = confirm ? "匯入中..." : "建立預覽中...";
  importState.errors = [];
  importState.warnings = [];
  renderSelectedInstrument();

  try {
    const response = await fetch(withToken("/api/database/etf-holdings/import-csv"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(etfImportPayload(item, confirm)),
    });
    const data = await response.json().catch(() => ({}));
    const ok = response.ok && data?.ok === true;
    importState.status = ok ? "success" : "error";
    importState.preview = data && (data.snapshot || data.components || data.summary) ? data : null;
    importState.previewValid = ok && !confirm;
    importState.errors = ok ? [] : etfImportIssues(data);
    importState.warnings = Array.isArray(data?.warnings) ? data.warnings : [];
    importState.message = ok
      ? (confirm ? "ETF 持股快照已匯入。" : "預覽完成，確認後才會寫入。")
      : (data?.message || "CSV 無法匯入，請檢查欄位與內容。");

    if (ok && confirm) {
      pageState.etfHoldingsCache[key] = {
        status: "loaded",
        payload: {
          ok: true,
          ticker: data?.snapshot?.etf_ticker || key,
          snapshot: data?.snapshot || null,
          components: Array.isArray(data?.components) ? data.components : [],
          summary: data?.summary || {},
          message: data?.message || "",
        },
      };
    }
  } catch (error) {
    importState.status = "error";
    importState.previewValid = false;
    importState.message = "CSV 匯入服務暫時無法使用。";
    importState.errors = [{ code: "request_failed", message: error.message || String(error) }];
    importState.warnings = [];
  }

  if (etfHoldingsCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
}

async function submitEtfHoldingsProvider(confirm = false) {
  const item = selectedItem();
  if (!item?.ticker || !isEtfInstrument(item)) return;
  syncEtfProviderStateFromDom();
  const providerState = pageState.etfHoldingsProvider;
  if (confirm && !providerState.previewValid) {
    providerState.status = "error";
    providerState.message = "請先完成有效的來源預覽，再確認匯入。";
    providerState.errors = [];
    renderSelectedInstrument();
    return;
  }
  if (!String(providerState.providerId || "").trim()) {
    providerState.status = "error";
    providerState.previewValid = false;
    providerState.message = providerState.sourcesMessage || "尚未設定此 ETF 的投信來源，可使用 CSV 匯入。";
    providerState.errors = [];
    renderSelectedInstrument();
    return;
  }

  const key = etfHoldingsCacheKey(item);
  providerState.status = "loading";
  providerState.message = confirm ? "匯入投信來源中..." : "讀取投信來源預覽中...";
  providerState.errors = [];
  providerState.warnings = [];
  renderSelectedInstrument();

  try {
    const response = await fetch(withToken("/api/database/etf-holdings/fetch-provider"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(etfProviderPayload(item, confirm)),
    });
    const data = await response.json().catch(() => ({}));
    const ok = response.ok && data?.ok === true;
    providerState.status = ok ? "success" : "error";
    providerState.preview = data && (data.snapshot || data.components || data.summary) ? data : null;
    providerState.previewValid = ok && !confirm;
    providerState.errors = ok ? [] : etfImportIssues(data);
    providerState.warnings = Array.isArray(data?.warnings) ? data.warnings : [];
    providerState.message = ok
      ? (confirm ? "ETF 持股已從投信來源匯入。" : "未匯入預覽完成，確認後才會寫入。")
      : (data?.message || "尚未設定此 ETF 的投信來源，可改用 CSV 匯入。");

    if (ok && confirm) {
      providerState.previewValid = false;
      pageState.etfHoldingsCache[key] = { status: "idle", payload: null };
      if (etfHoldingsCacheKey(selectedItem()) === key) {
        await loadEtfHoldingsForSelected();
        return;
      }
    }
  } catch (error) {
    providerState.status = "error";
    providerState.previewValid = false;
    providerState.message = "投信來源暫時無法使用，可改用 CSV 匯入。";
    providerState.errors = [{ code: "provider_fetch_failed", message: error.message || String(error) }];
    providerState.warnings = [];
  }

  if (etfHoldingsCacheKey(selectedItem()) === key) {
    renderSelectedInstrument();
  }
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
  loadKlineForSelected();
  loadDividendCalendarForSelected();
  loadEtfHoldingsForSelected();
  searchTimer = window.setTimeout(() => {
    searchLocalInstruments(pageState.searchTerm).catch((error) => {
      byId("stock-detail-view").innerHTML = `<div class="panel empty">搜尋失敗：${escapeHtml(error.message || error)}</div>`;
    });
  }, 220);
});

byId("stock-detail-select").addEventListener("change", (event) => {
  pageState.selectedKey = event.target.value;
  renderSelectedInstrument();
  loadKlineForSelected();
  loadDividendCalendarForSelected();
  loadEtfHoldingsForSelected();
});
document.addEventListener("click", (event) => {
  const candle = event.target.closest("[data-kline-candle]");
  if (!candle) return;
  pageState.klineSelections[candle.dataset.klineKey] = candle.dataset.klineCandle;
  renderSelectedInstrument();
});
document.addEventListener("click", (event) => {
  const marker = event.target.closest("[data-kline-buy-marker]");
  if (!marker) return;
  pageState.klineBuySelections[marker.dataset.klineBuyKey] = marker.dataset.klineBuyMarker;
  renderSelectedInstrument();
});
document.addEventListener("click", (event) => {
  const marker = event.target.closest("[data-kline-dividend-marker]");
  if (!marker) return;
  pageState.klineDividendSelections[marker.dataset.klineDividendKey] = marker.dataset.klineDividendMarker;
  renderSelectedInstrument();
});
document.addEventListener("keydown", (event) => {
  const candle = event.target.closest("[data-kline-candle]");
  if (!candle || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  pageState.klineSelections[candle.dataset.klineKey] = candle.dataset.klineCandle;
  renderSelectedInstrument();
});
document.addEventListener("keydown", (event) => {
  const marker = event.target.closest("[data-kline-buy-marker]");
  if (!marker || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  pageState.klineBuySelections[marker.dataset.klineBuyKey] = marker.dataset.klineBuyMarker;
  renderSelectedInstrument();
});
document.addEventListener("keydown", (event) => {
  const marker = event.target.closest("[data-kline-dividend-marker]");
  if (!marker || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  pageState.klineDividendSelections[marker.dataset.klineDividendKey] = marker.dataset.klineDividendMarker;
  renderSelectedInstrument();
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-kline-range]");
  if (!button) return;
  const days = Number(button.dataset.klineRange);
  if (![90, 180, 365].includes(days)) return;
  pageState.klineRangeDays = days;
  renderSelectedInstrument();
  loadKlineForSelected();
  loadDividendCalendarForSelected();
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-kline-toggle]");
  if (!button) return;
  const key = button.dataset.klineToggle;
  if (!Object.prototype.hasOwnProperty.call(pageState.klineDisplay, key)) return;
  pageState.klineDisplay[key] = !pageState.klineDisplay[key];
  renderSelectedInstrument();
});
document.addEventListener("input", (event) => {
  if (!event.target.closest("[data-etf-import-field]")) return;
  syncEtfImportStateFromDom({ resetPreview: true });
});
document.addEventListener("change", (event) => {
  if (!event.target.closest("[data-etf-import-field]")) return;
  syncEtfImportStateFromDom({ resetPreview: true });
});
document.addEventListener("input", (event) => {
  if (!event.target.closest("[data-etf-provider-field]")) return;
  syncEtfProviderStateFromDom({ resetPreview: true });
});
document.addEventListener("change", (event) => {
  if (!event.target.closest("[data-etf-provider-field]")) return;
  syncEtfProviderStateFromDom({ resetPreview: true });
});
document.addEventListener("toggle", (event) => {
  if (!event.target.matches(".etf-import-panel") || event.target.matches(".etf-provider-panel")) return;
  pageState.etfHoldingsImport.panelOpen = event.target.open;
}, true);
document.addEventListener("toggle", (event) => {
  if (!event.target.matches(".etf-provider-panel")) return;
  pageState.etfHoldingsProvider.panelOpen = event.target.open;
}, true);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-etf-import-action]");
  if (!button) return;
  pageState.etfHoldingsImport.panelOpen = true;
  submitEtfHoldingsImport(button.dataset.etfImportAction === "confirm");
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-etf-provider-action]");
  if (!button) return;
  pageState.etfHoldingsProvider.panelOpen = true;
  submitEtfHoldingsProvider(button.dataset.etfProviderAction === "confirm");
});
byId("stock-detail-refresh").addEventListener("click", () => loadPage(true));
loadPage(false);
