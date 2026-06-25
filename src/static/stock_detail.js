const profile = window.DASHBOARD_PROFILE || {};
const token = new URLSearchParams(window.location.search).get("token") || "";
const pageState = { holdings: [], selectedTicker: "" };
const byId = (id) => document.getElementById(id);

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

function detailMetric(label, value, className = "") {
  return `<div class="stock-detail-metric"><span>${escapeHtml(label)}</span><strong class="${className}">${value}</strong></div>`;
}

function renderLots(item) {
  const lots = Array.isArray(item.lots) ? item.lots : [];
  if (!lots.length) return `<div class="empty">尚無買入批次</div>`;
  return `
    <div class="stock-detail-lot-list">
      ${lots.map((lot) => `
        <article class="stock-detail-lot ${numberValue(lot.remaining_shares) === 0 ? "closed" : ""}">
          <div><span>買入日期</span><strong>${escapeHtml(shortDate(lot.date))}</strong></div>
          <div><span>原始股數</span><strong>${money(lot.shares)}</strong></div>
          <div><span>剩餘股數</span><strong>${money(lot.remaining_shares)}</strong></div>
          <div><span>成交價</span><strong>${money(lot.price, 2)}</strong></div>
          <div><span>含費成本</span><strong>${money(lot.cost_per_share, 2)}</strong></div>
          <div><span>手續費</span><strong>${money(lot.fee)}</strong></div>
        </article>
      `).join("")}
    </div>`;
}

function renderDividend(item) {
  const schedule = item.dividend_schedule || {};
  const next = schedule.next_event || {};
  return `
    <section class="stock-detail-section">
      <div class="section-title"><h2>股利資料</h2></div>
      <div class="stock-detail-metrics compact">
        ${detailMetric("配息週期", escapeHtml(schedule.frequency?.label || "不固定"))}
        ${detailMetric("下次除息", escapeHtml(shortDate(next.ex_dividend_date)))}
        ${detailMetric("每單位", money(next.dividend, 3))}
        ${detailMetric("預估入息", money(next.estimated_cash))}
        ${detailMetric("發放日", escapeHtml(shortDate(next.payout_date)))}
      </div>
    </section>`;
}

function renderSelectedHolding() {
  const root = byId("stock-detail-view");
  const item = pageState.holdings.find((holding) => holding.ticker === pageState.selectedTicker);
  if (!item) {
    root.innerHTML = `<div class="panel empty">目前沒有持股資料</div>`;
    return;
  }

  const quoteDate = item.quote?.price_time || item.after_close_quote?.trade_date || "";
  const historyUrl = withToken(`/database/${encodeURIComponent(item.ticker)}/history`);
  root.innerHTML = `
    <article class="panel stock-detail-card">
      <header class="stock-detail-head">
        <div>
          <span class="ticker">${escapeHtml(item.ticker)} · ${escapeHtml(item.type || "")}</span>
          <h2>${escapeHtml(item.name || item.ticker)}</h2>
          <span class="muted">${escapeHtml(item.symbol || "")}</span>
        </div>
        <div class="stock-detail-quote">
          <strong>${money(item.close, 2)}</strong>
          <span class="${valueClass(item.change_pct)}">${percent(item.change_pct)}</span>
          <small>${escapeHtml(shortDate(quoteDate))}</small>
        </div>
      </header>

      <div class="stock-detail-signals">
        ${(item.signals || []).map((signal) => `<span>${escapeHtml(signal)}</span>`).join("") || `<span>人工判斷</span>`}
      </div>

      <section class="stock-detail-section">
        <div class="section-title"><h2>持股與損益</h2></div>
        <div class="stock-detail-metrics">
          ${detailMetric("股數", money(item.shares))}
          ${detailMetric("平均成本", money(item.avg_cost, 2))}
          ${detailMetric("損益兩平", money(item.breakeven_price, 2))}
          ${detailMetric("持股成本", money(item.cost_value))}
          ${detailMetric("目前市值", money(item.market_value))}
          ${detailMetric("帳面損益", money(item.unrealized_pnl), valueClass(item.unrealized_pnl))}
          ${detailMetric("損益率", percent(item.pnl_pct), valueClass(item.pnl_pct))}
          ${detailMetric("股息月數", money(item.dividend_months, 1))}
        </div>
      </section>

      ${renderDividend(item)}

      <section class="stock-detail-section">
        <div class="section-title stock-detail-section-title">
          <h2>買入批次</h2>
          <span class="muted">${money((item.lots || []).length)} 筆</span>
        </div>
        ${renderLots(item)}
      </section>

      <div class="stock-detail-actions">
        <a class="icon-button top-link" href="${historyUrl}">查看日線歷史</a>
      </div>
    </article>`;
}

function renderPage(data) {
  pageState.holdings = Array.isArray(data.holdings) ? data.holdings : [];
  if (!pageState.holdings.some((item) => item.ticker === pageState.selectedTicker)) {
    pageState.selectedTicker = pageState.holdings[0]?.ticker || "";
  }
  byId("stock-detail-count").textContent = money(pageState.holdings.length);
  byId("stock-detail-updated-at").textContent = data.updated_at || "N/A";
  byId("stock-detail-select").innerHTML = pageState.holdings.length
    ? pageState.holdings.map((item) => `<option value="${escapeHtml(item.ticker)}" ${item.ticker === pageState.selectedTicker ? "selected" : ""}>${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}</option>`).join("")
    : `<option value="">目前沒有持股</option>`;
  renderSelectedHolding();
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
    button.textContent = "更新";
  }
}

byId("stock-detail-select").addEventListener("change", (event) => {
  pageState.selectedTicker = event.target.value;
  renderSelectedHolding();
});
byId("stock-detail-refresh").addEventListener("click", () => loadPage(true));
loadPage(false);
