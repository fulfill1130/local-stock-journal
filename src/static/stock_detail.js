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
  klineSelections: {},
  klineDisplay: {
    ma: true,
    volume: true,
    range: true,
    detail: true,
    cost: true,
    buys: true,
  },
  klineBuySelections: {},
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

function isoDate(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function dateDaysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDate(date);
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

function klineCacheKey(item) {
  return `${String(item?.ticker || "").toUpperCase()}:${pageState.klineRangeDays}`;
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
      <span class="ma5">MA5 ${movingAverageText(rows, 5)}</span>
      <span class="ma20">MA20 ${movingAverageText(rows, 20)}</span>
      <span class="ma60">MA60 ${movingAverageText(rows, 60)}</span>
    </div>`;
}

function renderKlineToggles(item) {
  const toggles = [
    ["ma", "MA"],
    ["volume", "Volume"],
    ["range", "H/L"],
    ["detail", "Detail"],
  ];
  if (isHeldInstrument(item)) {
    toggles.push(["cost", "Cost"], ["buys", "Buys"]);
  }
  return `
    <div class="kline-display-toggles" aria-label="K-line display toggles">
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

function renderKlineSvg(rows, cacheKey, selectedDate, item, display = pageState.klineDisplay) {
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
    const title = `${date} BUY ${money(transaction.shares)} @ ${money(transaction.price, 2)} fee ${money(transaction.fee)}`;
    return `
      <g class="kline-buy-marker ${selected ? "selected" : ""}" data-kline-buy-key="${escapeHtml(cacheKey)}" data-kline-buy-marker="${escapeHtml(markerId)}" tabindex="0" role="button">
        <title>${escapeHtml(title)}</title>
        <path d="M ${x.toFixed(2)} ${(y - 5).toFixed(2)} L ${(x - 5).toFixed(2)} ${(y + 4).toFixed(2)} L ${(x + 5).toFixed(2)} ${(y + 4).toFixed(2)} Z"></path>
      </g>`;
  }).join("");

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
      ${detailMetric("買進日", escapeHtml(shortDate(transaction.date || transaction.time)))}
      ${detailMetric("股數", money(transaction.shares))}
      ${detailMetric("價格", money(transaction.price, 2))}
      ${detailMetric("手續費", money(transaction.fee))}
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
    body = `
      <div class="kline-summary">
        ${detailMetric("最新收盤", money(latest.close, 2))}
        ${detailMetric("日期範圍", `${escapeHtml(shortDate(first.trade_date || first.date))} - ${escapeHtml(shortDate(latest.trade_date || latest.date))}`)}
        ${detailMetric("筆數", money(rows.length))}
        ${detailMetric("來源", escapeHtml(source))}
      </div>
      ${pageState.klineDisplay.ma ? renderMovingAverageLegend(rows) : ""}
      ${renderKlineSvg(rows, cacheKey, selectedDate, item)}
      ${renderSelectedBuyMarker(item, rows, cacheKey)}
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
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-kline-range]");
  if (!button) return;
  const days = Number(button.dataset.klineRange);
  if (![90, 180, 365].includes(days)) return;
  pageState.klineRangeDays = days;
  renderSelectedInstrument();
  loadKlineForSelected();
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-kline-toggle]");
  if (!button) return;
  const key = button.dataset.klineToggle;
  if (!Object.prototype.hasOwnProperty.call(pageState.klineDisplay, key)) return;
  pageState.klineDisplay[key] = !pageState.klineDisplay[key];
  renderSelectedInstrument();
});
byId("stock-detail-refresh").addEventListener("click", () => loadPage(true));
loadPage(false);
