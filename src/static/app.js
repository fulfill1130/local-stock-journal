const state = {
  timer: null,
  lastData: null,
  holdingPanelOpen: true,
  holdingGroupOpen: {},
  holdingDetailOpen: {},
  sparklineDays: 10,
  importRows: [],
  importStagingBatches: [],
  editingTransactionId: "",
  transactionSearch: "",
  transactionActionFilter: "ALL",
  transactionStatusFilter: "ALL",
  dividendGroupOpen: {},
};

const el = (id) => document.getElementById(id);
const shareToken = new URLSearchParams(window.location.search).get("token") || "";
const rawProfileConfig = window.DASHBOARD_PROFILE || {};
const profileConfig = {
  slug: rawProfileConfig.slug || "son",
  label: rawProfileConfig.label || "兒子帳戶",
  apiBase: rawProfileConfig.apiBase || rawProfileConfig.api_base || "/son",
};

function withToken(path) {
  if (!shareToken) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(shareToken)}`;
}

function apiPath(path) {
  return withToken(`${profileConfig.apiBase}${path}`);
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

function pct(value) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}%`;
}

function todayInputValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function readNumber(id) {
  const target = el(id);
  if (!target || target.value.trim() === "") return null;
  return numberValue(target.value);
}

function estimateCharge(amount, rate) {
  const value = numberValue(rate) || 0;
  if (!amount || amount <= 0 || value <= 0) return 0;
  return Math.max(1, Math.round(amount * value));
}

function cls(value) {
  const num = numberValue(value);
  if (num === null) return "";
  if (num > 0) return "positive";
  if (num < 0) return "negative";
  return "";
}

function badgeClass(text) {
  const value = String(text || "");
  if (value.includes("停損") || value.includes("不追高") || value.includes("近除息")) return "warn";
  if (value.includes("買價") || value.includes("觸發")) return "buy";
  if (value.includes("可賣") || value.includes("獲利")) return "profit";
  return "";
}

function setText(id, value) {
  const target = el(id);
  if (target) target.textContent = value;
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

async function loadState(force = false) {
  const button = el("refresh-button");
  if (button) {
    button.disabled = true;
    button.textContent = force ? "更新中" : "載入中";
  }

  try {
    const response = force
      ? await fetch(apiPath("/api/refresh"), { method: "POST" })
      : await fetch(apiPath("/api/state"));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.lastData = data;
    render(data);
    return data;
  } catch (error) {
    setText("updated-at", `載入失敗：${error.message || error}`);
    throw error;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "更新";
    }
  }
}

async function manualFetch() {
  const button = el("manual-fetch-button");
  const status = el("manual-fetch-status");
  button.disabled = true;
  status.textContent = "正在依市場時段檢查報價...";

  try {
    const data = await loadState(true);
    const requested = data.refresh_policy?.requested_symbols || [];
    if (requested.length) {
      status.textContent = `已送出 ${requested.length} 檔報價請求：${data.updated_at || "N/A"}`;
    } else {
      status.textContent = `未送出新請求，使用本機快取：${data.updated_at || "N/A"}`;
    }
  } catch (error) {
    status.textContent = `更新失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

function toggleCashForm() {
  const form = el("cash-form");
  form.classList.toggle("hidden");
  if (!form.classList.contains("hidden")) {
    el("cash-amount").focus();
  }
}

async function submitCashDeposit(event) {
  event.preventDefault();
  const amount = readNumber("cash-amount");
  const status = el("cash-status");
  if (amount === null || amount <= 0) {
    status.textContent = "請輸入大於 0 的金額。";
    return;
  }

  status.textContent = "寫入中...";
  try {
    const response = await fetch(apiPath("/api/cash"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount,
        date: todayInputValue(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    state.lastData = data;
    render(data);
    el("cash-amount").value = "";
    status.textContent = "已存入。";
    window.setTimeout(() => {
      el("cash-form").classList.add("hidden");
      status.textContent = "";
    }, 450);
  } catch (error) {
    status.textContent = `寫入失敗：${error.message || error}`;
  }
}

async function submitDividendIncome(event) {
  event.preventDefault();
  const ticker = el("dividend-income-ticker").value.trim().toUpperCase();
  const amount = readNumber("dividend-income-amount");
  const status = el("dividend-income-status");
  if (!ticker) {
    status.textContent = "請輸入股票代碼。";
    return;
  }
  if (amount === null || amount === 0) {
    status.textContent = "請輸入實際入帳金額；修正可輸入負數。";
    return;
  }

  status.textContent = "寫入中...";
  try {
    const response = await fetch(apiPath("/api/dividend-income"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, amount, date: el("dividend-income-date").value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    state.lastData = data;
    render(data);
    el("dividend-income-amount").value = "";
    status.textContent = "已加入。";
    window.setTimeout(() => {
      status.textContent = "";
    }, 1200);
  } catch (error) {
    status.textContent = `寫入失敗：${error.message || error}`;
  }
}

function render(data) {
  const settings = data.settings || {};
  const profile = data.profile || profileConfig;
  const summary = data.summary || {};
  const holdings = data.holdings || [];

  const title = profile.label || settings.app_title || profileConfig.label;
  setText("app-title", title);
  document.title = title;
  setText("updated-at", data.updated_at || "N/A");
  setText("realized-pnl-total", money(summary.realized_pnl_total));
  el("realized-pnl-total").className = `hero-value ${cls(summary.realized_pnl_total)}`;
  setText("realized-trade-pnl-total", money(summary.realized_trade_pnl_total));
  el("realized-trade-pnl-total").className = cls(summary.realized_trade_pnl_total);
  setText("dividend-income-total", money(summary.dividend_income_total));
  setText("total-market-value", money(summary.total_market_value));
  setText("total-pnl", money(summary.total_pnl));
  setText("total-pnl-pct", pct(summary.total_pnl_pct));
  el("total-pnl").className = cls(summary.total_pnl);
  el("total-pnl-pct").className = cls(summary.total_pnl_pct);
  setText("total-cost", money(summary.total_cost_value));
  setText("holding-count", holdings.length);

  renderMarkets(data.markets || []);
  renderHoldings(holdings);
  renderWatchlist(data.watchlist || []);
  renderTransactions(data.transactions || []);
  renderTransactionBook(data.transaction_book || []);
  renderDividendMovements(data.dividend_movements || []);
}

function renderDividendMovements(items) {
  const root = el("dividend-income-list");
  if (!root) return;
  root.querySelectorAll("[data-dividend-ticker]").forEach((details) => {
    state.dividendGroupOpen[details.dataset.dividendTicker] = details.open;
  });
  setText("dividend-record-count", items.length);
  if (!items.length) {
    root.innerHTML = `<div class="empty dividend-empty">尚未登記股利入帳</div>`;
    return;
  }
  const groups = new Map();
  items.forEach((item) => {
    const ticker = String(item.ticker || "未指定").trim().toUpperCase() || "未指定";
    if (!groups.has(ticker)) groups.set(ticker, []);
    groups.get(ticker).push(item);
  });
  root.innerHTML = Array.from(groups.entries()).map(([ticker, rows]) => {
    const total = rows.reduce((sum, item) => sum + (numberValue(item.amount) || 0), 0);
    const open = state.dividendGroupOpen[ticker] ? " open" : "";
    return `
      <details class="dividend-stock-group" data-dividend-ticker="${escapeHtml(ticker)}"${open}>
        <summary class="dividend-stock-summary">
          <strong>${escapeHtml(ticker)}</strong>
          <span>${rows.length} 筆 · ${money(total, 2)}</span>
        </summary>
        <div class="dividend-stock-entries">
          ${rows.map((item) => `
            <div class="dividend-income-row">
              <span>${escapeHtml(String(item.time || item.date || "").slice(0, 10))}</span>
              <strong>${money(item.amount, 2)}</strong>
            </div>
          `).join("")}
        </div>
      </details>
    `;
  }).join("");
}

function renderMarkets(items) {
  const root = el("market-list");
  if (!items.length) {
    root.innerHTML = `<div class="empty">沒有美股與總經資料</div>`;
    return;
  }

  root.innerHTML = items.map((item) => {
    const closeText = item.symbol === "^TNX" ? `${money(item.close, 2)}%` : money(item.close, 2);
    return `
      <article class="market-card">
        <div class="market-label">${escapeHtml(item.label)}</div>
        <div class="market-value">${closeText}</div>
        <div class="market-change ${cls(item.change_pct)}">${pct(item.change_pct)}</div>
      </article>
    `;
  }).join("");
}

function renderDataStatus(items) {
  const root = el("data-status-bar");
  if (!root) return;
  const visible = (items || []).filter((item) =>
    ["tw_intraday_15m", "official_daily", "us_intraday_15m", "tw_after_close"].includes(item.job_name)
  );
  if (!visible.length) {
    root.innerHTML = `<div class="data-status-empty">資料狀態尚未建立</div>`;
    return;
  }
  root.innerHTML = visible.map((item) => {
    const failed = item.last_status === "failed";
    const statusText = item.last_status || "unknown";
    return `
      <article class="data-status-card ${failed ? "failed" : ""}">
        <div class="data-status-head">
          <strong>${escapeHtml(item.label || item.job_name)}</strong>
          <span>${escapeHtml(statusText)}</span>
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

function renderHoldings(items) {
  const root = el("holding-list");
  syncHoldingPanelState();
  root.querySelectorAll(".asset-group").forEach((group) => {
    const key = group.dataset.segment;
    if (key) state.holdingGroupOpen[key] = group.open;
  });
  const groups = [
    { key: "etf", label: "ETF", hint: "ETF", items: [] },
    { key: "twse", label: "上市", hint: ".TW", items: [] },
    { key: "tpex", label: "上櫃", hint: ".TWO", items: [] },
  ];
  const groupsByKey = Object.fromEntries(groups.map((group) => [group.key, group]));
  items.forEach((item) => groupsByKey[holdingSegment(item)].items.push(item));

  if (!items.length) {
    root.innerHTML = `<div class="empty">尚未建立持股資料</div>`;
    return;
  }

  root.innerHTML = groups.map((group) => `
    <details
      class="asset-group asset-group-${group.key}"
      data-segment="${group.key}"
      ${groupShouldOpen(group) ? "open" : ""}
    >
      <summary class="asset-group-summary">
        <span>${escapeHtml(group.label)}</span>
        <small>${group.items.length} 檔 ${escapeHtml(group.hint)}</small>
      </summary>
      <div class="card-grid holding-card-grid">
        ${group.items.length ? group.items.map(renderHoldingCard).join("") : `<div class="empty">目前沒有持股</div>`}
      </div>
    </details>
  `).join("");
}

function syncHoldingPanelState() {
  const panel = el("holding-panel");
  const toggle = el("holding-panel-toggle");
  if (!panel || !toggle) return;
  panel.classList.toggle("collapsed", !state.holdingPanelOpen);
  toggle.textContent = state.holdingPanelOpen ? "收合" : "展開";
  toggle.setAttribute("aria-expanded", state.holdingPanelOpen ? "true" : "false");
}

function renderHoldingCard(item) {
  const detailOpen = Boolean(state.holdingDetailOpen[item.ticker]);
  const lotCount = Array.isArray(item.lots) ? item.lots.length : 0;
  const cardClass = String(item.type || "").toUpperCase() === "ETF" ? "stock-card holding-etf" : "stock-card";
  return `
    <article class="${cardClass}">
      <div class="stock-head">
        <div>
          <span class="ticker">${escapeHtml(item.ticker)} · ${escapeHtml(item.type || "")}</span>
          <div class="stock-name">${escapeHtml(item.name || item.ticker)}</div>
        </div>
        ${renderQuoteCluster(item)}
      </div>
      <div class="badges">${(item.signals || []).map(renderBadge).join("")}</div>
      ${renderSparkline(item.sparkline)}
      <div class="card-metrics">
        ${metric("股數", money(item.shares))}
        ${metric("成本", money(item.avg_cost, 2))}
        ${metric("兩平", money(item.breakeven_price, 2))}
        ${metric("市值", money(item.market_value))}
        ${metric("損益", `<span class="${cls(item.unrealized_pnl)}">${money(item.unrealized_pnl)}</span>`)}
        ${metric("損益率", `<span class="${cls(item.pnl_pct)}">${pct(item.pnl_pct)}</span>`)}
        ${metric("配息週期", escapeHtml(item.dividend_schedule?.frequency?.label || "不固定"))}
      </div>
      ${renderDividendSchedule(item)}
      ${item.days_to_ex_dividend === null || item.days_to_ex_dividend === undefined ? "" : `<p class="note">除息倒數：${escapeHtml(item.days_to_ex_dividend)} 天</p>`}
      ${item.broker && item.broker.breakeven_price !== undefined ? `<p class="note">損益與兩平價使用券商估值</p>` : ""}
      ${item.note ? `<p class="note">${escapeHtml(item.note)}</p>` : ""}
      <div class="card-detail-bar">
        <button
          class="lot-toggle"
          type="button"
          data-toggle-lots="${escapeHtml(item.ticker)}"
          aria-expanded="${detailOpen ? "true" : "false"}"
        >
          <span>${detailOpen ? "收合批次" : "展開批次"}</span>
          <small>${lotCount} 筆</small>
        </button>
      </div>
      ${detailOpen ? renderLotSection(item) : ""}
    </article>
  `;
}

function renderDividendSchedule(item) {
  const schedule = item.dividend_schedule || {};
  const event = schedule.next_event || null;
  if (!event || !event.ex_dividend_date) return "";
  const dateLabel = event.is_upcoming ? "下一次除息" : "最近除息";
  const perUnit = money(event.dividend, 3);
  const cash = money(event.estimated_cash);
  const payout = event.payout_date ? formatShortDate(event.payout_date) : "未提供";
  const monthly = money(schedule.estimated_monthly_cash);
  const frequency = schedule.frequency?.label || "不固定";
  return `
    <div class="holding-dividend-box">
      <div>
        <span>${escapeHtml(dateLabel)}</span>
        <strong>${escapeHtml(formatShortDate(event.ex_dividend_date))}</strong>
      </div>
      <div>
        <span>每單位</span>
        <strong>${perUnit}</strong>
      </div>
      <div>
        <span>預估入息</span>
        <strong>${cash}</strong>
      </div>
      <div>
        <span>發放日</span>
        <strong>${escapeHtml(payout)}</strong>
      </div>
      <small>${escapeHtml(frequency)}；近一年平均每月約 ${monthly}，來源 Yahoo 股利資料庫</small>
    </div>
  `;
}

function renderLotSection(item) {
  const lots = Array.isArray(item.lots) ? item.lots : [];
  if (!lots.length) {
    return `<div class="lot-section"><div class="empty">這檔目前沒有可列出的買入批次。</div></div>`;
  }

  const rows = lots
    .slice()
    .sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")))
    .map((lot) => {
      const date = String(lot.date || "").replaceAll("-", "/") || "日期未填";
      const shares = numberValue(lot.shares);
      const remaining = numberValue(lot.remaining_shares);
      const remainingText = remaining === null || remaining === shares
        ? ""
        : `<span>剩 ${money(remaining)} 股</span>`;
      return `
        <div class="lot-row">
          <div class="lot-main">
            <strong>${escapeHtml(date)}</strong>
            <span>買入 ${money(shares)} 股</span>
          </div>
          <div class="lot-values">
            <span>成交 ${money(lot.price, 2)}</span>
            ${remainingText}
            <span>手續 ${money(lot.fee)}</span>
            <span>成本 ${money(lot.cost_per_share, 2)}</span>
          </div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="lot-section">
      <div class="lot-title">買入批次</div>
      <div class="lot-list">${rows}</div>
    </div>
  `;
}

function formatShortDate(value) {
  const text = String(value || "");
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return text || "N/A";
  return `${match[2]}/${match[3]}`;
}

function renderSparkline(sparkline) {
  const allPoints = Array.isArray(sparkline?.points)
    ? sparkline.points.filter((point) => numberValue(point.close) !== null)
    : [];
  const points = allPoints.slice(-state.sparklineDays);
  if (points.length < 5) {
    return `<div class="sparkline-box step-chart sparkline-empty">日線資料不足</div>`;
  }

  // 首頁卡片只顯示「每日收盤價」的簡化直方圖。
  // 每根柱代表一個已確認的日收盤價。
  const width = 320;
  const height = 72;
  const padX = 12;
  const padTop = 14;
  const padBottom = 14;
  const innerWidth = width - padX * 2;
  const innerHeight = height - padTop - padBottom;

  const closes = points.map((point) => numberValue(point.close));
  const first = closes[0];
  const latest = closes[closes.length - 1];
  const avgCost = numberValue(sparkline?.avg_cost);

  // y 軸範圍以收盤價為主。
  // 成本線只有在接近價格區間時才納入縮放，避免成本太遠把線壓扁。
  let min = Math.min(...closes);
  let max = Math.max(...closes);
  const visibleRange = Math.max(max - min, Math.abs(max) * 0.015, 0.5);

  if (
    avgCost !== null &&
    avgCost >= min - visibleRange * 0.5 &&
    avgCost <= max + visibleRange * 0.5
  ) {
    min = Math.min(min, avgCost);
    max = Math.max(max, avgCost);
  }

  if (min === max) {
    min -= 1;
    max += 1;
  }

  const domainPadding = (max - min) * 0.18;
  min -= domainPadding;
  max += domainPadding;

  const yFor = (value) => {
    return padTop + ((max - value) / (max - min)) * innerHeight;
  };

  const chartPoints = closes.map((close, index) => ({
    x: Number((padX + (index / points.length) * innerWidth).toFixed(2)),
    y: Number(yFor(close).toFixed(2)),
    close,
    date: points[index].date,
  }));

  const trendClass = latest >= first ? "up" : "down";
  const lastPoint = chartPoints[chartPoints.length - 1];
  const barGap = points.length <= 5 ? 6 : points.length <= 10 ? 4 : 3;
  const barWidth = Math.max(5, (innerWidth - barGap * (points.length - 1)) / points.length);
  const baseY = height - padBottom;
  const bars = chartPoints.map((point, index) => {
    const x = Number((padX + index * (barWidth + barGap)).toFixed(2));
    const y = Math.min(point.y, baseY - 2);
    const barHeight = Math.max(2, baseY - y);
    const previousClose = index > 0 ? chartPoints[index - 1].close : point.close;
    const change = point.close - previousClose;
    const changePct = index > 0 && previousClose !== 0 ? (change / previousClose) * 100 : null;
    const barTrend = index === 0 ? "flat" : change > 0 ? "up" : change < 0 ? "down" : "flat";
    const changeLabel = index === 0
      ? "首日"
      : `${change > 0 ? "+" : ""}${money(change, 2)}${changePct === null ? "" : ` / ${pct(changePct)}`}`;
    const label = `${formatSparkDate(point.date)} 收盤 ${money(point.close, 2)}｜${changeLabel}`;
    const classes = ["hist-bar", barTrend, index === chartPoints.length - 1 ? "latest-bar" : ""]
      .filter(Boolean)
      .join(" ");
    return `<rect class="${classes}" x="${x}" y="${Number(y.toFixed(2))}" width="${Number(barWidth.toFixed(2))}" height="${Number(barHeight.toFixed(2))}" data-spark-tooltip="${escapeHtml(label)}" tabindex="0"><title>${escapeHtml(label)}</title></rect>`;
  }).join("");

  const costY = avgCost === null ? null : Number(yFor(avgCost).toFixed(2));
  const showCostLine = costY !== null && costY >= 0 && costY <= height;

  const startDate = formatSparkDate(points[0]?.date);
  const endDate = formatSparkDate(points[points.length - 1]?.date);

  const latestTrend = chartPoints.length < 2
    ? "flat"
    : latest > chartPoints[chartPoints.length - 2].close
      ? "up"
      : latest < chartPoints[chartPoints.length - 2].close
        ? "down"
        : "flat";

  return `
    <div class="sparkline-box step-chart hist-chart ${trendClass}" title="近 ${state.sparklineDays} 日收盤價">
      <div class="sparkline-topline">
        <span>近${state.sparklineDays}日收盤</span>
        <span>${escapeHtml(startDate)}${startDate && endDate ? " → " : ""}${escapeHtml(endDate)}</span>
      </div>

      <svg class="step-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
        ${showCostLine ? `<line class="step-cost-line" x1="${padX}" x2="${width - padX}" y1="${costY}" y2="${costY}"></line>` : ""}
        ${bars}
        <circle class="latest-dot ${latestTrend}" cx="${Number((padX + (chartPoints.length - 1) * (barWidth + barGap) + barWidth / 2).toFixed(2))}" cy="${lastPoint.y}" r="3"></circle>
      </svg>

      <div class="sparkline-bottomline">
        <span>首 ${money(first, 2)}</span>
        ${avgCost === null ? "" : `<span>成本 ${money(avgCost, 2)}</span>`}
        <span>末 ${money(latest, 2)}</span>
      </div>
    </div>
  `;
}

function formatSparkDate(value) {
  if (!value) return "";

  const text = String(value);
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);

  if (!match) return text;

  return `${match[2]}/${match[3]}`;
}

function sparkTooltip() {
  let tooltip = document.querySelector(".spark-tooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.className = "spark-tooltip";
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

function showSparkTooltip(event, target) {
  const tooltipText = target?.dataset?.sparkTooltip;
  if (!tooltipText) return;
  const tooltip = sparkTooltip();
  tooltip.textContent = tooltipText;
  tooltip.classList.add("visible");

  const viewportPadding = 12;
  const rect = tooltip.getBoundingClientRect();
  let left = event.clientX;
  let top = event.clientY - 14;

  left = Math.max(viewportPadding + rect.width / 2, Math.min(window.innerWidth - viewportPadding - rect.width / 2, left));
  top = Math.max(viewportPadding + rect.height, top);

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideSparkTooltip() {
  document.querySelector(".spark-tooltip")?.classList.remove("visible");
}
function holdingSegment(item) {
  if (String(item.type || "").toUpperCase() === "ETF") return "etf";
  if (String(item.exchange_suffix || "").toUpperCase() === ".TWO") return "tpex";
  return "twse";
}

function groupShouldOpen(group) {
  if (Object.prototype.hasOwnProperty.call(state.holdingGroupOpen, group.key)) {
    return state.holdingGroupOpen[group.key];
  }
  return group.items.length > 0;
}

function renderWatchlist(items) {
  const root = el("watch-list");
  if (!items.length) {
    root.innerHTML = `<div class="empty">目前沒有短線觀察名單</div>`;
    return;
  }

  root.innerHTML = items.map((item) => `
    <article class="stock-card">
      <div class="stock-head">
        <div>
          <span class="ticker">${escapeHtml(item.ticker)}</span>
          <div class="stock-name">${escapeHtml(item.name || item.ticker)}</div>
        </div>
        ${renderQuoteCluster(item)}
      </div>
      <div class="badges">${(item.signals || []).map(renderBadge).join("")}</div>
      <div class="card-metrics">
        ${metric("買價", money(item.target_buy_price, 2))}
        ${metric("提醒", money(item.alert_price, 2))}
        ${metric("停損", money(item.stop_loss_price, 2))}
        ${metric("賣價", money(item.target_sell_price, 2))}
      </div>
      ${item.reason ? `<p class="note">${escapeHtml(item.reason)}</p>` : ""}
      ${item.note ? `<p class="note">${escapeHtml(item.note)}</p>` : ""}
    </article>
  `).join("");
}

function renderTransactions(items) {
  const root = el("transaction-list");
  if (!root) return;
  if (!items.length) {
    root.innerHTML = `<div class="empty">尚無交易紀錄</div>`;
    return;
  }

  root.innerHTML = items.map((item) => `
    <div class="timeline-row">
      <div>
        <strong>${escapeHtml(actionText(item.action))} ${escapeHtml(item.ticker)}</strong>
        <div class="muted">
          ${escapeHtml(item.time)}${item.fee ? ` · fee ${money(item.fee)}` : ""}${item.tax ? ` · tax ${money(item.tax)}` : ""}
        </div>
      </div>
      <div class="price">${money(item.shares)} @ ${money(item.price, 2)}</div>
    </div>
  `).join("");
}

function actionText(action) {
  if (action === "BUY") return "買進";
  if (action === "SELL") return "賣出";
  return action || "";
}

function renderTransactionBook(items) {
  const root = el("transaction-book");
  if (!root) return;
  renderTransactionLedgerSummary(items);
  if (!items.length) {
    root.innerHTML = `<div class="empty">尚無歷史買賣紀錄</div>`;
    return;
  }

  const filteredItems = filterTransactionBook(items);
  if (!filteredItems.length) {
    root.innerHTML = `<div class="empty">沒有符合篩選條件的交易。</div>`;
    return;
  }

  root.innerHTML = filteredItems.map((item) => {
    const warnings = Array.isArray(item.warnings) ? item.warnings : [];
    const status = item.status || "normal";
    const isEditing = item.id === state.editingTransactionId;
    if (isEditing) return renderTransactionEditRow(item, warnings, status);
    const cashFlow = numberValue(item.amount);
    const cashLabel = item.action === "SELL" ? "入帳" : "扣款";
    const sourceLabel = transactionSourceLabel(item);
    return `
      <article class="transaction-card ${statusClass(status)}" data-transaction-id="${escapeHtml(item.id || "")}">
        <div class="transaction-main">
          <div>
            <strong class="transaction-title ${item.action === "SELL" ? "sell-text" : "buy-text"}">
              ${escapeHtml(actionText(item.action))} ${escapeHtml(item.ticker || "")}
              ${item.name ? `<span>${escapeHtml(item.name)}</span>` : ""}
            </strong>
            <div class="transaction-subline">
              <span>${escapeHtml(item.date || String(item.time || "").slice(0, 10))}</span>
              <span>${escapeHtml(sourceLabel)}</span>
              ${item.order_no ? `<span>單號 ${escapeHtml(item.order_no)}</span>` : ""}
            </div>
          </div>
          <div class="transaction-amount">
            <strong>${money(item.shares)} 股</strong>
            <span>@ ${money(item.price, 2)}</span>
          </div>
        </div>
        <div class="transaction-meta">
          <span>手續 ${money(item.fee)}</span>
          <span>稅 ${money(item.tax)}</span>
          <span>${escapeHtml(cashLabel)} <strong class="${cashFlow !== null && cashFlow >= 0 ? "sell-text" : "buy-text"}">${money(Math.abs(cashFlow ?? 0))}</strong></span>
          ${item.note ? `<span class="transaction-note">${escapeHtml(item.note)}</span>` : ""}
        </div>
        ${warnings.length ? `<div class="transaction-warnings">${warnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}</div>` : ""}
        <div class="transaction-actions">
          <button class="small-ghost-button" type="button" data-transaction-edit="${escapeHtml(item.id || "")}">編輯</button>
          <button class="small-ghost-button" type="button" data-transaction-confirm="${escapeHtml(item.id || "")}">確認</button>
          <button class="small-danger-button" type="button" data-transaction-delete="${escapeHtml(item.id || "")}">刪除</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderTransactionLedgerSummary(items) {
  const root = el("transaction-ledger-summary");
  if (!root) return;
  const total = items.length;
  const buyCount = items.filter((item) => item.action === "BUY").length;
  const sellCount = items.filter((item) => item.action === "SELL").length;
  const issueCount = items.filter((item) => ["warning", "error"].includes(item.status)).length;
  const unreviewedCount = items.filter((item) => !item.reviewed).length;
  const filteredCount = filterTransactionBook(items).length;
  root.innerHTML = `
    <div><span>總筆數</span><strong>${money(total)}</strong></div>
    <div><span>買進</span><strong class="buy-text">${money(buyCount)}</strong></div>
    <div><span>賣出</span><strong class="sell-text">${money(sellCount)}</strong></div>
    <div><span>待確認</span><strong>${money(unreviewedCount)}</strong></div>
    <div><span>需檢查</span><strong>${money(issueCount)}</strong></div>
    <div><span>目前顯示</span><strong>${money(filteredCount)}</strong></div>
  `;
}

function filterTransactionBook(items) {
  const keyword = state.transactionSearch.trim().toLowerCase();
  const actionFilter = state.transactionActionFilter;
  const statusFilter = state.transactionStatusFilter;
  return items.filter((item) => {
    if (actionFilter !== "ALL" && item.action !== actionFilter) return false;
    if (statusFilter === "ACTIVE" && item.reviewed && !["warning", "error"].includes(item.status)) return false;
    if (!["ALL", "ACTIVE"].includes(statusFilter) && item.status !== statusFilter) return false;
    if (!keyword) return true;
    const haystack = [
      item.date,
      item.time,
      item.action,
      actionText(item.action),
      item.ticker,
      item.name,
      item.note,
      item.source,
      item.order_no,
      item.status,
    ].join(" ").toLowerCase();
    return haystack.includes(keyword);
  });
}

function transactionSourceLabel(item) {
  const source = String(item.source || "").toLowerCase();
  if (source === "pdf_statement") return "PDF 對帳單";
  if (source === "manual") return "手動輸入";
  if (source) return item.source;
  return "本機紀錄";
}

function renderTransactionEditRow(item, warnings, status) {
  return `
    <article class="transaction-card editing ${statusClass(status)}" data-transaction-id="${escapeHtml(item.id || "")}">
      <div class="transaction-edit-grid">
        <select data-tx-field="action">
          <option value="BUY" ${item.action === "BUY" ? "selected" : ""}>買進</option>
          <option value="SELL" ${item.action === "SELL" ? "selected" : ""}>賣出</option>
        </select>
        <input data-tx-field="date" type="date" value="${escapeHtml(item.date || String(item.time || "").slice(0, 10))}">
        <input data-tx-field="ticker" type="text" value="${escapeHtml(item.ticker || "")}" placeholder="代號">
        <input data-tx-field="shares" type="number" min="0" step="1" value="${escapeHtml(item.shares || 0)}" placeholder="股數">
        <input data-tx-field="price" type="number" min="0" step="0.01" value="${escapeHtml(item.price || "")}" placeholder="成交價">
        <input data-tx-field="fee" type="number" min="0" step="1" value="${escapeHtml(item.fee ?? "")}" placeholder="手續費">
        <input data-tx-field="tax" type="number" min="0" step="1" value="${escapeHtml(item.tax ?? "")}" placeholder="交易稅">
        <input data-tx-field="note" type="text" value="${escapeHtml(item.note || "")}" placeholder="備註">
      </div>
      ${warnings.length ? `<div class="transaction-warnings">${warnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}</div>` : ""}
      <div class="transaction-actions">
        <button class="small-primary-button" type="button" data-transaction-save="${escapeHtml(item.id || "")}">儲存</button>
        <button class="small-ghost-button" type="button" data-transaction-cancel>取消</button>
      </div>
    </article>
  `;
}

function statusClass(status) {
  if (status === "error") return "tx-error";
  if (status === "warning") return "tx-warning";
  if (status === "reviewed") return "tx-reviewed";
  return "tx-normal";
}

function renderQuoteCluster(item) {
  const afterClose = item.after_close_quote || null;
  const afterCloseValue = afterClose?.close;
  const afterCloseDate = afterClose?.trade_date || "";
  const mainTone = sourceToneFromRecord(item.quote || {});
  const afterCloseTone = sourceToneFromRecord(afterClose || {});
  return `
    <div class="quote-cluster">
      <div class="price source-number ${mainTone}">
        ${money(item.close, 2)}
        <div class="${cls(item.change_pct)} market-change">${pct(item.change_pct)}</div>
      </div>
      ${numberValue(afterCloseValue) === null ? "" : `
        <div class="after-close-price" title="${escapeHtml(afterCloseDate)}">
          <span>${escapeHtml(afterCloseDate ? `盤後 ${afterCloseDate.slice(5)}` : "盤後")}</span>
          <strong class="source-number ${afterCloseTone}">${money(afterCloseValue, 2)}</strong>
        </div>
      `}
    </div>
  `;
}

function renderBadge(text) {
  return `<span class="badge ${badgeClass(text)}">${escapeHtml(text)}</span>`;
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`;
}

function sourceValue(value, tone) {
  return `<span class="source-number ${escapeHtml(tone || "manual")}">${value}</span>`;
}

function sourceToneFromRecord(record) {
  const sourceMarket = String(record?.source_market || "").toUpperCase();
  const source = String(record?.source || "").toLowerCase();
  if (sourceMarket === "TWSE" || sourceMarket === "TPEX") return "official";
  if (sourceMarket === "YAHOO" || source === "yfinance") return "yahoo";
  if (source === "manual") return "manual";
  return "manual";
}

function dividendSourceTone(item) {
  const source = String(item?.dividend_source || "").toLowerCase();
  if (source === "twse" || source === "tpex") return "official";
  if (source === "yahoo") return "yahoo";
  return "manual";
}

function toggleMarketPanel() {
  const panel = el("market-panel");
  const toggle = el("market-toggle");
  const text = el("market-toggle-text");
  const collapsed = panel.classList.toggle("collapsed");
  toggle.setAttribute("aria-expanded", String(!collapsed));
  text.textContent = collapsed ? "展開" : "收合";
}

function openTradeSheet() {
  el("trade-sheet").classList.remove("hidden");
  el("trade-ticker").focus();
  updateTradePreview();
}

function closeTradeSheet() {
  el("trade-sheet").classList.add("hidden");
}

function setTradeAction(action) {
  el("trade-action").value = action;
  document.querySelectorAll(".trade-action-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.action === action);
  });
  const taxInput = el("trade-tax");
  taxInput.disabled = action !== "SELL";
  if (action !== "SELL") taxInput.value = "";
  updateTradePreview();
}

function tradeTotals() {
  const lots = readNumber("trade-lots") || 0;
  const oddShares = readNumber("trade-shares") || 0;
  const price = readNumber("trade-price") || 0;
  const shares = lots * 1000 + oddShares;
  const gross = shares * price;
  const settings = state.lastData?.settings || {};
  const manualFee = readNumber("trade-fee");
  const manualTax = readNumber("trade-tax");
  const fee = manualFee ?? estimateCharge(gross, settings.broker_fee_rate);
  const tax = el("trade-action").value === "SELL"
    ? manualTax ?? estimateCharge(gross, settings.transaction_tax_rate)
    : 0;
  return { lots, oddShares, price, shares, gross, fee, tax };
}

function updateTradePreview() {
  const preview = el("trade-preview");
  if (!preview) return;
  const totals = tradeTotals();
  const action = el("trade-action").value;
  const net = action === "BUY" ? totals.gross + totals.fee : totals.gross - totals.fee - totals.tax;
  preview.innerHTML = `
    合計股數：<strong>${money(totals.shares)}</strong><br>
    成交金額：<strong>${money(totals.gross)}</strong><br>
    手續費：<strong>${money(totals.fee)}</strong>，交易稅：<strong>${money(totals.tax)}</strong><br>
    ${action === "BUY" ? "預估扣款" : "預估入帳"}：<strong>${money(net)}</strong>
  `;
}

async function submitTrade(event) {
  event.preventDefault();
  const submit = el("trade-submit");
  const status = el("trade-status");
  const totals = tradeTotals();
  const payload = {
    action: el("trade-action").value,
    date: el("trade-date").value,
    ticker: el("trade-ticker").value,
    lots: el("trade-lots").value,
    shares: el("trade-shares").value,
    price: el("trade-price").value,
    fee: el("trade-fee").value,
    tax: el("trade-tax").value,
    note: el("trade-note").value,
  };

  if (totals.shares <= 0) {
    status.textContent = "請輸入張數或股數。";
    return;
  }

  submit.disabled = true;
  status.textContent = "寫入中...";
  try {
    const response = await fetch(apiPath("/api/transaction"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    state.lastData = data;
    render(data);
    status.textContent = "已寫入交易。";
    el("trade-form").reset();
    el("trade-date").value = todayInputValue();
    setTradeAction("BUY");
    window.setTimeout(closeTradeSheet, 350);
  } catch (error) {
    status.textContent = `寫入失敗：${error.message || error}`;
  } finally {
    submit.disabled = false;
  }
}

function openImportSheet() {
  el("import-sheet").classList.remove("hidden");
  loadImportStagingBatches();
  el("import-text").focus();
}

function closeImportSheet() {
  el("import-sheet").classList.add("hidden");
}

function clearImportSheet() {
  state.importRows = [];
  el("import-text").value = "";
  el("import-pdf-password").value = "";
  el("import-image").value = "";
  el("import-image-preview").classList.add("hidden");
  el("import-image-preview").removeAttribute("src");
  el("import-preview").innerHTML = "";
  el("import-submit").classList.add("hidden");
  el("import-status").textContent = "";
  el("import-staging-status").textContent = "";
  el("import-staging-detail").innerHTML = "";
}

async function previewImportImage() {
  const file = el("import-image").files?.[0];
  const preview = el("import-image-preview");
  const status = el("import-status");
  if (!file) {
    preview.classList.add("hidden");
    preview.removeAttribute("src");
    status.textContent = "";
    return;
  }
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (isPdf) {
    preview.classList.add("hidden");
    preview.removeAttribute("src");
    status.textContent = "已選擇 PDF。請確認密碼後按「抽取 PDF 文字」。";
    return;
  }
  preview.src = URL.createObjectURL(file);
  preview.classList.remove("hidden");
  status.textContent = "已選擇圖片。本機尚未安裝 OCR，請用 Google Lens / AI 轉文字後貼上。";
}

async function extractSelectedImportFileText() {
  const file = el("import-image").files?.[0];
  const status = el("import-status");
  const button = el("import-extract");
  if (!file) {
    status.textContent = "請先選擇 PDF。";
    return;
  }
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    status.textContent = "圖片目前只能預覽，尚未接本機 OCR。";
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", el("import-pdf-password").value || "");
  button.disabled = true;
  status.textContent = "上傳 PDF 中，請稍候...";
  try {
    let data;
    try {
      data = await uploadImportFormData(apiPath("/api/import/extract"), formData, (progress) => {
        status.textContent = progress
          ? `上傳 PDF 中 ${progress}%...`
          : "上傳 PDF 中，請稍候...";
      });
    } catch (uploadError) {
      status.textContent = `一般上傳失敗，改用備援上傳：${uploadError.message || uploadError}`;
      data = await uploadImportFileAsBase64(file, (progress) => {
        status.textContent = progress
          ? `備援上傳 PDF 中 ${progress}%...`
          : "正在讀取 PDF 並改用備援上傳...";
      });
    }
    if (data.ok === false) throw new Error(data.error || "PDF 抽取失敗");
    el("import-text").value = data.text || "";
    status.textContent = `已抽取 PDF 文字：${data.page_count || 0} 頁，${data.char_count || 0} 字。請按解析成確認表。`;
  } catch (error) {
    status.textContent = `抽取失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

async function saveSelectedImportFileToLibrary() {
  const file = el("import-image").files?.[0];
  const status = el("import-status");
  const button = el("import-save-upload");
  if (!file) {
    status.textContent = "請先選擇 PDF 或截圖。";
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source", "dashboard_import_panel");
  formData.append("note", "從交易匯入面板存入");
  button.disabled = true;
  status.textContent = "存入上傳庫中...";
  try {
    let data;
    try {
      data = await uploadImportFormData(apiPath("/api/uploads"), formData, (progress) => {
        status.textContent = progress
          ? `存入上傳庫中 ${progress}%...`
          : "存入上傳庫中...";
      });
    } catch (uploadError) {
      status.textContent = `一般上傳失敗，改用備援保存：${uploadError.message || uploadError}`;
      data = await uploadFileToLibraryAsBase64(file, (progress) => {
        status.textContent = progress
          ? `備援存入上傳庫中 ${progress}%...`
          : "正在讀取檔案並改用備援保存...";
      });
    }
    if (data.ok === false) throw new Error(data.error || "上傳失敗");
    status.textContent = data.document?.duplicate ? "這份檔案已在上傳庫，已更新紀錄。" : "已存入上傳庫。";
  } catch (error) {
    status.textContent = `存入上傳庫失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

function uploadFileToLibraryAsBase64(file, onProgress) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.max(1, Math.round((event.loaded / event.total) * 70)));
    };
    reader.onerror = () => reject(new Error("讀取檔案失敗"));
    reader.onload = async () => {
      try {
        const payload = {
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          data: String(reader.result || ""),
          source: "dashboard_import_panel_base64",
          note: "從交易匯入面板存入",
        };
        onProgress?.(80);
        const response = await fetch(apiPath("/api/uploads-base64"), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        onProgress?.(95);
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
        resolve(data);
      } catch (error) {
        reject(error);
      }
    };
    onProgress?.(10);
    reader.readAsDataURL(file);
  });
}

function uploadImportFormData(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.timeout = 60000;
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        onProgress?.(0);
        return;
      }
      const progress = Math.max(1, Math.min(99, Math.round((event.loaded / event.total) * 100)));
      onProgress?.(progress);
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch {
        reject(new Error(`伺服器回傳不是 JSON，HTTP ${xhr.status}`));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(data.error || `HTTP ${xhr.status}`));
        return;
      }
      resolve(data);
    };
    xhr.onerror = () => reject(new Error("上傳連線失敗，請確認手機仍連著 Tailscale，並重新整理頁面再試。"));
    xhr.ontimeout = () => reject(new Error("上傳逾時，請確認網路連線或改用較小 PDF 測試。"));
    xhr.onabort = () => reject(new Error("上傳已中止。"));
    xhr.send(formData);
  });
}

function uploadImportFileAsBase64(file, onProgress) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("手機讀取 PDF 失敗，請重新選檔。"));
    reader.onload = async () => {
      try {
        onProgress?.(35);
        const result = String(reader.result || "");
        const base64Data = result.includes(",") ? result.split(",", 2)[1] : result;
        const payload = {
          filename: file.name,
          content_type: file.type || "application/pdf",
          password: el("import-pdf-password").value || "",
          data: base64Data,
        };
        onProgress?.(55);
        const response = await fetch(apiPath("/api/import/extract-base64"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        onProgress?.(95);
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
        resolve(data);
      } catch (error) {
        reject(error);
      }
    };
    onProgress?.(10);
    reader.readAsDataURL(file);
  });
}

async function extractLatestLocalPdfText() {
  const status = el("import-status");
  const button = el("import-extract-local");
  button.disabled = true;
  status.textContent = "讀取電腦資料夾最新 PDF 中，請稍候...";
  try {
    const formData = new FormData();
    formData.append("password", el("import-pdf-password").value || "");
    const response = await fetch(apiPath("/api/import/extract-latest-local"), {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    el("import-text").value = data.text || "";
    status.textContent = `已抽取 ${data.filename || "PDF"}：${data.page_count || 0} 頁，${data.char_count || 0} 字。請按解析成確認表。`;
  } catch (error) {
    status.textContent = `讀取資料夾 PDF 失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

function parseImportText() {
  const text = el("import-text").value.trim();
  const status = el("import-status");
  if (!text) {
    status.textContent = "請先貼上 OCR / AI 文字或 JSON。";
    return;
  }
  const rows = parseTradeImportRows(text);
  state.importRows = rows;
  renderImportPreview();
  status.textContent = rows.length
    ? `已解析 ${rows.length} 筆，請核對後再寫入。`
    : "沒有解析到交易，請改貼 JSON 或把文字稍微整理成一行一筆。";
}

function parseTradeImportRows(text) {
  const jsonRows = parseTradeJson(text);
  if (jsonRows.length) return jsonRows;

  const defaultDate = parseImportedDate(text) || todayInputValue();
  const knownItems = knownTradeItems();
  const statementRows = parseStatementTradeRows(text, defaultDate, knownItems);
  if (statementRows.length) return statementRows;

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const rows = [];
  for (const line of lines) {
    const row = parseTradeLine(line, defaultDate, knownItems);
    if (row) rows.push(row);
  }
  return rows;
}

function parseTradeJson(text) {
  try {
    const parsed = JSON.parse(text);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    return items.map((item) => normalizeImportRow(item)).filter(Boolean);
  } catch {
    return [];
  }
}

function normalizeImportRow(item) {
  const action = normalizeAction(item.action || item.type || item.side || item.buy_sell);
  const ticker = String(item.ticker || item.stock || item.code || "").trim().toUpperCase();
  const shares = numberValue(item.shares ?? item.qty ?? item.quantity);
  const lots = numberValue(item.lots);
  const price = numberValue(item.price ?? item["成交價"]);
  if (!action || !ticker || price === null || ((shares || 0) <= 0 && (lots || 0) <= 0)) return null;
  return {
    action,
    date: normalizeDateText(item.date || item.trade_date) || todayInputValue(),
    ticker,
    name: String(item.name || ""),
    lots: lots || 0,
    shares: shares || 0,
    price,
    fee: numberValue(item.fee) ?? "",
    tax: numberValue(item.tax) ?? "",
    note: String(item.note || "批次匯入"),
  };
}

function parseStatementTradeRows(text, defaultDate, knownItems) {
  const normalized = String(text || "")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n+/g, " ")
    .trim();
  if (!normalized || !/(現買|現賣|買沖|賣沖)/.test(normalized)) return [];

  const rows = [];
  const tradePattern = /(?:^|\s)(現買|現賣|買沖|賣沖)\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)(.*?)(?=\s+(?:現買|現賣|買沖|賣沖|小計|提醒您|注意事項)|$)/g;
  for (const match of normalized.matchAll(tradePattern)) {
    const action = normalizeAction(match[1]);
    const rawName = cleanStatementStockName(match[2]);
    const known = matchKnownItem(rawName, knownItems);
    if (!action) continue;
    rows.push({
      action,
      date: defaultDate,
      ticker: known?.ticker || "",
      name: known.name || rawName,
      lots: 0,
      shares: cleanNumber(match[3]),
      price: cleanNumber(match[5]),
      fee: cleanNumber(match[7]),
      tax: action === "SELL" ? cleanNumber(match[8]) : 0,
      note: known?.ticker ? "PDF 對帳單匯入" : `PDF 對帳單匯入，需補代號：${rawName}`,
    });
  }
  return rows;
}

function parseTradeLine(line, defaultDate, knownItems) {
  const statementRow = parseStatementTradeLine(line, defaultDate, knownItems);
  if (statementRow) return statementRow;

  const action = normalizeAction(line);
  if (!action) return null;
  const known = matchKnownItem(line, knownItems);
  const tickerMatch = line.match(/\b\d{4}[A-Z]?\b/i);
  const ticker = (tickerMatch?.[0] || known?.ticker || "").toUpperCase();
  if (!ticker) return null;

  const date = parseImportedDate(line) || defaultDate;
  let parseLine = line;
  if (known?.name) parseLine = parseLine.replace(known.name, " ");
  if (ticker) parseLine = parseLine.replace(new RegExp(`\\b${ticker}\\b`, "i"), " ");
  const numbers = extractNumbers(parseLine);
  const explicitShares = parseLine.match(/(\d+(?:,\d{3})*|\d+)\s*股/);
  const explicitLots = parseLine.match(/(\d+(?:,\d{3})*|\d+)\s*張/);
  const shares = explicitShares ? cleanNumber(explicitShares[1]) : inferShares(line, numbers, action);
  const lots = explicitLots ? cleanNumber(explicitLots[1]) : 0;
  const price = inferPrice(parseLine, numbers, shares);
  if (!price || (shares <= 0 && lots <= 0)) return null;

  return {
    action,
    date,
    ticker,
    name: known?.name || "",
    lots,
    shares,
    price,
    fee: inferNamedAmount(parseLine, ["手續費", "手續"]) ?? "",
    tax: inferNamedAmount(parseLine, ["交易稅", "稅"]) ?? "",
    note: "批次匯入",
  };
}

function parseStatementTradeLine(line, defaultDate, knownItems) {
  const text = String(line || "").replace(/\s*\|\s*/g, " ").replace(/\s+/g, " ").trim();
  const actionMatch = text.match(/\b(20\d{6})\s+(現買|現賣|買沖|賣沖)\s+([\d,]+)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)/);
  if (!actionMatch) return null;
  const beforeAction = text.slice(0, actionMatch.index).trim();
  const tickerMatches = [...beforeAction.matchAll(/\b\d{4}[A-Z]?\b/gi)];
  const ticker = tickerMatches.length ? tickerMatches[tickerMatches.length - 1][0].toUpperCase() : "";
  if (!ticker) return null;
  const known = matchKnownItem(text, knownItems);
  const action = normalizeAction(actionMatch[2]);
  if (!action) return null;
  return {
    action,
    date: normalizeDateText(actionMatch[1]) || defaultDate,
    ticker,
    name: known?.name || "",
    lots: 0,
    shares: cleanNumber(actionMatch[3]),
    price: cleanNumber(actionMatch[4]),
    fee: cleanNumber(actionMatch[6]),
    tax: action === "SELL" ? cleanNumber(actionMatch[7]) : 0,
    note: "PDF 對帳單匯入",
  };
}

function cleanStatementStockName(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .replace(/[：:，,。]+$/g, "")
    .trim();
}

function knownTradeItems() {
  const data = state.lastData || {};
  const items = [...(data.holdings || []), ...(data.watchlist || []), ...(data.known_trade_items || [])];
  return items
    .map((item) => ({
      ticker: String(item.ticker || "").toUpperCase(),
      name: String(item.name || "").trim(),
    }))
    .filter((item) => item.ticker || item.name)
    .sort((a, b) => b.name.length - a.name.length);
}

function matchKnownItem(line, items) {
  const normalizedLine = compactTradeText(line);
  return items.find((item) => item.name && normalizedLine.includes(compactTradeText(item.name)))
    || items.find((item) => {
      const name = compactTradeText(item.name);
      return name.length >= 4 && normalizedLine.length >= 4 && name.includes(normalizedLine);
    })
    || items.find((item) => item.ticker && normalizedLine.includes(compactTradeText(item.ticker)))
    || null;
}

function compactTradeText(value) {
  return String(value || "").replace(/\s+/g, "").toUpperCase();
}

function normalizeAction(value) {
  const text = String(value || "").toUpperCase();
  if (text.includes("SELL") || text.includes("賣") || text.includes("現賣")) return "SELL";
  if (text.includes("BUY") || text.includes("買") || text.includes("現買")) return "BUY";
  return "";
}

function parseImportedDate(text) {
  const normalized = normalizeDateText(text);
  if (normalized) return normalized;
  const minguo = String(text || "").match(/(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
  if (!minguo) return "";
  return `${Number(minguo[1]) + 1911}-${String(minguo[2]).padStart(2, "0")}-${String(minguo[3]).padStart(2, "0")}`;
}

function normalizeDateText(value) {
  const text = String(value || "");
  const compact = text.match(/\b(20\d{2})(\d{2})(\d{2})\b/);
  if (compact) return `${compact[1]}-${compact[2]}-${compact[3]}`;
  const match = text.match(/(20\d{2})[/-](\d{1,2})[/-](\d{1,2})/);
  if (!match) return "";
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

function extractNumbers(line) {
  return [...String(line).matchAll(/-?\d+(?:,\d{3})*(?:\.\d+)?/g)]
    .map((match) => cleanNumber(match[0]))
    .filter((num) => Number.isFinite(num));
}

function cleanNumber(value) {
  return Number(String(value || "").replaceAll(",", ""));
}

function inferShares(line, numbers, action) {
  if (!numbers.length) return 0;
  const nonPriceCandidates = numbers.filter((num) => Number.isInteger(num) && num > 0 && num <= 100000);
  if (line.includes("現買") || line.includes("現賣")) {
    const index = numbers.findIndex((num) => num > 0 && Number.isInteger(num));
    return index >= 0 ? numbers[index] : 0;
  }
  return nonPriceCandidates[0] || 0;
}

function inferPrice(line, numbers, shares) {
  const named = inferNamedAmount(line, ["成交價", "價格", "價錢"]);
  if (named !== null) return named;
  const decimal = numbers.find((num) => num > 0 && num < 10000 && !Number.isInteger(num));
  if (decimal) return decimal;
  const afterShares = numbers.find((num) => shares && Math.abs(num - shares) > 0 && num > 0 && num < 10000);
  return afterShares || 0;
}

function inferNamedAmount(line, labels) {
  for (const label of labels) {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = String(line).match(new RegExp(`${escaped}\\s*[:：]?\\s*(-?\\d+(?:,\\d{3})*(?:\\.\\d+)?)`));
    if (match) return cleanNumber(match[1]);
  }
  return null;
}

function renderImportPreview() {
  const root = el("import-preview");
  const rows = state.importRows || [];
  if (!rows.length) {
    root.innerHTML = `<div class="empty">尚未解析到交易。</div>`;
    el("import-submit").classList.add("hidden");
    return;
  }
  root.innerHTML = `
    <div class="import-table">
      ${rows.map((row, index) => renderImportRow(row, index)).join("")}
    </div>
  `;
  el("import-submit").classList.remove("hidden");
}

async function submitImportStaging() {
  const status = el("import-staging-status");
  const button = el("import-staging-submit");
  const text = el("import-text").value.trim();
  if (!text) {
    status.textContent = "請先貼上固定格式 JSON。";
    return;
  }
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    status.textContent = "JSON 格式不正確，請先修正後再送入暫存審核。";
    return;
  }
  button.disabled = true;
  status.textContent = "建立暫存審核批次中...";
  try {
    const response = await fetch(apiPath("/api/import-staging"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    const batch = { ...(data.batch || {}), rows: data.rows || [] };
    status.textContent = `已建立暫存批次 ${batch.batch_id || ""}。尚未寫入最終帳本。`;
    renderImportStagingDetail(batch);
    await loadImportStagingBatches();
  } catch (error) {
    status.textContent = `暫存失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

async function loadImportStagingBatches() {
  const root = el("import-staging-list");
  const status = el("import-staging-status");
  root.innerHTML = `<div class="empty">讀取暫存批次中...</div>`;
  try {
    const response = await fetch(apiPath("/api/import-staging"));
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    state.importStagingBatches = Array.isArray(data.batches) ? data.batches : [];
    renderImportStagingList();
  } catch (error) {
    root.innerHTML = `<div class="empty warning-text">暫存批次讀取失敗：${escapeHtml(error.message || error)}</div>`;
    if (!status.textContent) status.textContent = "無法讀取暫存審核批次。";
  }
}

function renderImportStagingList() {
  const root = el("import-staging-list");
  const batches = state.importStagingBatches || [];
  if (!batches.length) {
    root.innerHTML = `<div class="empty">目前沒有匯入暫存批次。</div>`;
    return;
  }
  root.innerHTML = batches.map((batch) => `
    <button class="import-staging-batch" type="button" data-import-staging-batch="${escapeHtml(batch.batch_id || "")}">
      <span>
        <strong>${escapeHtml(batch.batch_id || "未命名批次")}</strong>
        <small>${escapeHtml(batch.created_at || "")}</small>
      </span>
      <span>${escapeHtml(batch.row_count ?? 0)} 筆 · 警告 ${escapeHtml(batch.warning_count ?? 0)} · 錯誤 ${escapeHtml(batch.error_count ?? 0)}</span>
    </button>
  `).join("");
}

async function openImportStagingBatch(batchId) {
  const status = el("import-staging-status");
  status.textContent = "讀取暫存批次明細中...";
  try {
    const response = await fetch(apiPath(`/api/import-staging/${encodeURIComponent(batchId)}`));
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    renderImportStagingDetail(data.batch || {});
    status.textContent = `已載入暫存批次 ${batchId}。尚未寫入最終帳本。`;
  } catch (error) {
    status.textContent = `讀取批次失敗：${error.message || error}`;
  }
}

function renderImportStagingDetail(batch) {
  const root = el("import-staging-detail");
  const rows = Array.isArray(batch.rows) ? batch.rows : [];
  root.innerHTML = `
    <div class="import-staging-detail-head">
      <strong>批次 ${escapeHtml(batch.batch_id || "")}</strong>
      <span class="muted">狀態 ${escapeHtml(batch.status || "draft")} · ${rows.length} 筆 · 只供審核</span>
    </div>
    ${rows.length ? rows.map(renderImportStagingRow).join("") : `<div class="empty">此批次沒有列資料。</div>`}
  `;
}

function renderImportStagingRow(row) {
  const normalized = row.normalized || {};
  const warnings = Array.isArray(row.warnings) ? row.warnings : [];
  const errors = Array.isArray(row.errors) ? row.errors : [];
  const duplicates = Array.isArray(row.duplicate_candidates) ? row.duplicate_candidates : [];
  return `
    <div class="import-staging-row ${errors.length ? "has-error" : warnings.length ? "has-warning" : ""}">
      <div class="import-staging-row-main">
        <strong>${escapeHtml(normalized.action || row.kind || "")} ${escapeHtml(normalized.ticker || "")}</strong>
        <span>${escapeHtml(normalized.date || "")}</span>
        <span>股數 ${escapeHtml(normalized.shares ?? "")}</span>
        <span>價格 ${escapeHtml(normalized.price ?? "")}</span>
        <span>成交金額 ${escapeHtml(row.computed_amount ?? "--")}</span>
        <span>差異 ${escapeHtml(row.amount_difference ?? "--")}</span>
      </div>
      ${errors.length ? `<div class="import-staging-messages error-text">${errors.map(escapeHtml).join("；")}</div>` : ""}
      ${warnings.length ? `<div class="import-staging-messages warning-text">${warnings.map(escapeHtml).join("；")}</div>` : ""}
      ${duplicates.length ? `<div class="import-staging-messages">疑似重複：${duplicates.map((item) => escapeHtml(item.id || item.date || item.ticker || "existing")).join("、")}</div>` : ""}
    </div>
  `;
}

function renderImportRow(row, index) {
  const duplicate = isImportRowDuplicate(row);
  return `
    <div class="import-row ${duplicate ? "duplicate-import-row" : ""}" data-import-row="${index}">
      <select data-import-field="action">
        <option value="BUY" ${row.action === "BUY" ? "selected" : ""}>買進</option>
        <option value="SELL" ${row.action === "SELL" ? "selected" : ""}>賣出</option>
      </select>
      <input data-import-field="date" type="date" value="${escapeHtml(row.date || todayInputValue())}">
      <input data-import-field="ticker" type="text" value="${escapeHtml(row.ticker || "")}" placeholder="代號">
      <input data-import-field="shares" type="number" min="0" step="1" value="${escapeHtml(row.shares || 0)}" placeholder="股數">
      <input data-import-field="price" type="number" min="0" step="0.01" value="${escapeHtml(row.price || "")}" placeholder="成交價">
      <input data-import-field="fee" type="number" min="0" step="1" value="${escapeHtml(row.fee ?? "")}" placeholder="手續費">
      <input data-import-field="tax" type="number" min="0" step="1" value="${escapeHtml(row.tax ?? "")}" placeholder="交易稅">
      <input data-import-field="note" type="text" value="${escapeHtml(row.note || "")}" placeholder="備註">
      ${duplicate ? `<span class="import-duplicate-badge">疑似重複</span>` : ""}
      <button class="icon-button compact-button" type="button" data-remove-import-row="${index}">×</button>
    </div>
  `;
}

function isImportRowDuplicate(row) {
  const transactions = Array.isArray(state.lastData?.transactions) ? state.lastData.transactions : [];
  const rowKey = transactionImportKey(row);
  return transactions.some((transaction) => transactionImportKey({
    action: transaction.action,
    date: String(transaction.time || "").slice(0, 10),
    ticker: transaction.ticker,
    shares: transaction.shares,
    price: transaction.price,
    fee: transaction.fee,
    tax: transaction.tax,
  }) === rowKey);
}

function transactionImportKey(row) {
  return [
    String(row.action || "").trim().toUpperCase(),
    String(row.date || "").slice(0, 10),
    String(row.ticker || "").trim().toUpperCase(),
    fixedKeyNumber(row.shares),
    fixedKeyNumber(row.price),
    fixedKeyNumber(row.fee),
    fixedKeyNumber(row.tax),
  ].join("|");
}

function fixedKeyNumber(value) {
  return String(Number(numberValue(value) || 0).toFixed(4));
}

function syncImportRowsFromDom() {
  state.importRows = [...document.querySelectorAll("[data-import-row]")].map((row) => {
    const value = (field) => row.querySelector(`[data-import-field="${field}"]`)?.value || "";
    return {
      action: value("action"),
      date: value("date"),
      ticker: value("ticker").trim().toUpperCase(),
      lots: 0,
      shares: value("shares"),
      price: value("price"),
      fee: value("fee"),
      tax: value("tax"),
      note: value("note"),
    };
  });
}

async function submitImportRows() {
  syncImportRowsFromDom();
  const rows = state.importRows.filter((row) => row.ticker && numberValue(row.shares) > 0 && numberValue(row.price) > 0);
  const status = el("import-status");
  if (!rows.length) {
    status.textContent = "沒有可寫入的有效交易。";
    return;
  }
  const submit = el("import-submit");
  submit.disabled = true;
  status.textContent = `寫入 ${rows.length} 筆交易中...`;
  try {
    let latestData = null;
    let writtenCount = 0;
    let skippedCount = 0;
    for (let index = 0; index < rows.length; index += 1) {
      const response = await fetch(apiPath("/api/transaction"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rows[index]),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(`${rows[index].ticker}：${data.error || `HTTP ${response.status}`}`);
      if (data?.transaction_result?.skipped || data?.transaction_result?.duplicate) {
        skippedCount += 1;
      } else {
        writtenCount += 1;
      }
      latestData = data;
    }
    if (latestData) {
      state.lastData = latestData;
      render(latestData);
    }
    status.textContent = `已寫入 ${writtenCount} 筆，跳過重複 ${skippedCount} 筆。`;
    window.setTimeout(() => {
      clearImportSheet();
      closeImportSheet();
    }, skippedCount ? 1400 : 500);
  } catch (error) {
    status.textContent = `寫入失敗：${error.message || error}`;
  } finally {
    submit.disabled = false;
  }
}

async function updateTransaction(id, payload) {
  const response = await fetch(apiPath(`/api/transactions/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  state.lastData = data;
  render(data);
}

async function deleteTransaction(id) {
  const response = await fetch(apiPath(`/api/transactions/${encodeURIComponent(id)}`), {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  state.lastData = data;
  render(data);
}

function transactionPayloadFromCard(card, reviewed = false) {
  const value = (field) => card.querySelector(`[data-tx-field="${field}"]`)?.value || "";
  return {
    action: value("action"),
    date: value("date"),
    ticker: value("ticker").trim().toUpperCase(),
    shares: value("shares"),
    price: value("price"),
    fee: value("fee"),
    tax: value("tax"),
    note: value("note"),
    reviewed,
  };
}

function setupTradeForm() {
  el("trade-date").value = todayInputValue();
  el("trade-fab").addEventListener("click", openTradeSheet);
  el("trade-close").addEventListener("click", closeTradeSheet);
  el("trade-form").addEventListener("submit", submitTrade);
  el("import-fab").addEventListener("click", openImportSheet);
  el("import-close").addEventListener("click", closeImportSheet);
  el("import-clear").addEventListener("click", clearImportSheet);
  el("import-image").addEventListener("change", previewImportImage);
  el("import-save-upload").addEventListener("click", saveSelectedImportFileToLibrary);
  el("import-extract").addEventListener("click", extractSelectedImportFileText);
  el("import-extract-local").addEventListener("click", extractLatestLocalPdfText);
  el("import-parse").addEventListener("click", parseImportText);
  el("import-staging-submit").addEventListener("click", submitImportStaging);
  el("import-staging-refresh").addEventListener("click", loadImportStagingBatches);
  el("import-submit").addEventListener("click", submitImportRows);
  el("import-staging-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-import-staging-batch]");
    if (!button) return;
    openImportStagingBatch(button.dataset.importStagingBatch);
  });
  el("import-preview").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-import-row]");
    if (!button) return;
    syncImportRowsFromDom();
    state.importRows.splice(Number(button.dataset.removeImportRow), 1);
    renderImportPreview();
  });
  document.querySelectorAll(".trade-action-button").forEach((button) => {
    button.addEventListener("click", () => setTradeAction(button.dataset.action));
  });
  ["trade-lots", "trade-shares", "trade-price", "trade-fee", "trade-tax"].forEach((id) => {
    el(id).addEventListener("input", updateTradePreview);
  });
}

el("refresh-button").addEventListener("click", () => loadState(true));
el("manual-fetch-button").addEventListener("click", manualFetch);
el("market-toggle").addEventListener("click", toggleMarketPanel);
if (document.getElementById("cash-toggle") && document.getElementById("cash-form")) {
  el("cash-toggle").addEventListener("click", toggleCashForm);
  el("cash-form").addEventListener("submit", submitCashDeposit);
}
el("dividend-income-form").addEventListener("submit", submitDividendIncome);
el("holding-panel-toggle").addEventListener("click", () => {
  state.holdingPanelOpen = !state.holdingPanelOpen;
  syncHoldingPanelState();
});
el("transaction-search").addEventListener("input", (event) => {
  state.transactionSearch = event.target.value || "";
  if (state.lastData) renderTransactionBook(state.lastData.transaction_book || []);
});
el("transaction-action-filter").addEventListener("change", (event) => {
  state.transactionActionFilter = event.target.value || "ALL";
  if (state.lastData) renderTransactionBook(state.lastData.transaction_book || []);
});
el("transaction-status-filter").addEventListener("change", (event) => {
  state.transactionStatusFilter = event.target.value || "ALL";
  if (state.lastData) renderTransactionBook(state.lastData.transaction_book || []);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-toggle-lots]");
  if (!button) return;
  const ticker = button.dataset.toggleLots;
  state.holdingDetailOpen[ticker] = !state.holdingDetailOpen[ticker];
  if (state.lastData) render(state.lastData);
});
document.addEventListener("toggle", (event) => {
  const details = event.target.closest?.("[data-dividend-ticker]");
  if (!details) return;
  state.dividendGroupOpen[details.dataset.dividendTicker] = details.open;
}, true);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-sparkline-days]");
  if (!button) return;
  const days = Number(button.dataset.sparklineDays);
  if (![5, 10, 15].includes(days)) return;
  state.sparklineDays = days;
  document.querySelectorAll("[data-sparkline-days]").forEach((target) => {
    target.classList.toggle("active", target === button);
  });
  if (state.lastData) render(state.lastData);
});
document.addEventListener("click", async (event) => {
  const edit = event.target.closest("[data-transaction-edit]");
  const cancel = event.target.closest("[data-transaction-cancel]");
  const save = event.target.closest("[data-transaction-save]");
  const confirmButton = event.target.closest("[data-transaction-confirm]");
  const deleteButton = event.target.closest("[data-transaction-delete]");

  if (edit) {
    state.editingTransactionId = edit.dataset.transactionEdit;
    if (state.lastData) render(state.lastData);
    return;
  }
  if (cancel) {
    state.editingTransactionId = "";
    if (state.lastData) render(state.lastData);
    return;
  }
  if (save) {
    const card = save.closest("[data-transaction-id]");
    if (!card) return;
    save.disabled = true;
    try {
      state.editingTransactionId = "";
      await updateTransaction(save.dataset.transactionSave, transactionPayloadFromCard(card, false));
    } catch (error) {
      alert(`儲存失敗：${error.message || error}`);
    } finally {
      save.disabled = false;
    }
    return;
  }
  if (confirmButton) {
    confirmButton.disabled = true;
    const item = (state.lastData?.transaction_book || []).find((row) => row.id === confirmButton.dataset.transactionConfirm);
    try {
      await updateTransaction(confirmButton.dataset.transactionConfirm, {
        action: item?.action,
        date: item?.date || String(item?.time || "").slice(0, 10),
        ticker: item?.ticker,
        shares: item?.shares,
        price: item?.price,
        fee: item?.fee,
        tax: item?.tax,
        note: item?.note,
        reviewed: true,
        conflict_acknowledged: true,
      });
    } catch (error) {
      alert(`確認失敗：${error.message || error}`);
    } finally {
      confirmButton.disabled = false;
    }
    return;
  }
  if (deleteButton) {
    const item = (state.lastData?.transaction_book || []).find((row) => row.id === deleteButton.dataset.transactionDelete);
    const label = `${actionText(item?.action)} ${item?.ticker || ""} ${item?.date || ""} ${money(item?.shares)}股`;
    if (!window.confirm(`確定刪除這筆交易？\n${label}`)) return;
    deleteButton.disabled = true;
    try {
      await deleteTransaction(deleteButton.dataset.transactionDelete);
    } catch (error) {
      alert(`刪除失敗：${error.message || error}`);
    } finally {
      deleteButton.disabled = false;
    }
  }
});
document.addEventListener("pointerover", (event) => {
  const bar = event.target.closest(".hist-bar[data-spark-tooltip]");
  if (!bar) return;
  showSparkTooltip(event, bar);
});
document.addEventListener("pointermove", (event) => {
  const bar = event.target.closest(".hist-bar[data-spark-tooltip]");
  if (!bar) return;
  showSparkTooltip(event, bar);
});
document.addEventListener("pointerout", (event) => {
  if (!event.target.closest(".hist-bar[data-spark-tooltip]")) return;
  hideSparkTooltip();
});
document.addEventListener("click", (event) => {
  const bar = event.target.closest(".hist-bar[data-spark-tooltip]");
  if (!bar) {
    hideSparkTooltip();
    return;
  }
  showSparkTooltip(event, bar);
});
window.addEventListener("scroll", hideSparkTooltip, { passive: true, capture: true });
window.addEventListener("resize", hideSparkTooltip, { passive: true });
document.addEventListener("touchmove", hideSparkTooltip, { passive: true });
document.addEventListener("pointercancel", hideSparkTooltip);
setupTradeForm();
el("dividend-income-date").value = todayInputValue();
loadState(false);
state.timer = window.setInterval(() => loadState(false), 10000);


