const dividendState = {
  records: [],
  targets: [],
  validation: { mismatch_keys: [], mismatches: [] },
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

function money(value, decimals = 3) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  return num.toLocaleString("zh-TW", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

function compactMoney(value) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  return num.toLocaleString("zh-TW", {
    maximumFractionDigits: 3,
    minimumFractionDigits: 0,
  });
}

function formatIsoTime(value) {
  if (!value) return "尚未更新";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function validationKey(ticker, exDate) {
  return `${ticker || ""}|${String(exDate || "").slice(0, 7)}`;
}

function mismatchFor(ticker, exDate) {
  const key = validationKey(ticker, exDate);
  return (dividendState.validation.mismatches || []).find((item) => item.key === key) || null;
}

async function loadDividends() {
  const status = byId("dividend-status");
  status.textContent = "讀取本機股利資料庫...";

  try {
    const response = await fetch(withToken("/api/database/dividends"));
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    renderDividends(data);
    const errorText = data.errors?.length ? `，錯誤 ${data.errors.length} 筆` : "";
    status.textContent = `已讀取本機清單，共 ${data.summary?.ticker_count || 0} 檔、${data.records?.length || 0} 筆${errorText}`;
  } catch (error) {
    status.textContent = `讀取失敗：${error.message || error}`;
    byId("dividend-list").innerHTML = `<div class="empty">讀取失敗：${escapeHtml(error.message || error)}</div>`;
  }
}

async function addDividendTarget(event) {
  event.preventDefault();
  const tickerInput = byId("dividend-new-ticker");
  const nameInput = byId("dividend-new-name");
  const suffixInput = byId("dividend-new-suffix");
  const ticker = tickerInput.value.trim().toUpperCase();
  const status = byId("dividend-status");
  if (!ticker) return;

  status.textContent = `${ticker} 加入本機清單中...`;
  try {
    const response = await fetch(withToken("/api/database/dividends/target"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        name: nameInput.value.trim(),
        type: "ETF",
        exchange_suffix: suffixInput.value,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    status.textContent = `${ticker} 已加入清單；尚未抓 API，請按該標的更新。`;
    tickerInput.value = "";
    nameInput.value = "";
    await loadDividends();
  } catch (error) {
    status.textContent = `${ticker} 新增失敗：${error.message || error}`;
  }
}

async function refreshAllDividends() {
  const button = byId("dividend-refresh-all");
  const status = byId("dividend-status");
  button.disabled = true;
  status.textContent = "一鍵更新 Yahoo 股利中，請稍候...";
  try {
    const response = await fetch(withToken("/api/database/dividends/refresh-all"), { method: "POST" });
    const data = await response.json();
    if (!response.ok && data.ok !== false) throw new Error(`HTTP ${response.status}`);
    status.textContent = data.message || `一鍵更新完成：成功 ${data.success_count || 0} 檔，失敗 ${data.fail_count || 0} 檔`;
    await loadDividends();
  } catch (error) {
    status.textContent = `一鍵更新失敗：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

function renderDividends(data) {
  const summary = data.summary || {};
  dividendState.records = data.records || [];
  dividendState.targets = data.targets || [];
  dividendState.validation = data.validation || { mismatch_keys: [], mismatches: [] };
  byId("dividend-record-count").textContent = String(summary.record_count ?? "N/A");
  byId("dividend-ticker-count").textContent = String(summary.ticker_count ?? "N/A");
  byId("latest-ex-date").textContent = summary.latest_ex_dividend_date || "N/A";
  byId("latest-dividend").textContent = money(summary.latest_dividend);
  byId("dividend-updated-at").textContent = data.updated_at || "N/A";
  byId("dividend-list-title").textContent = "ETF 股利摘要";
  byId("dividend-source").innerHTML = data.source_url
    ? `來源：<a href="${escapeHtml(data.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(data.source || "股利來源")}</a>`
    : `來源：${escapeHtml(data.source || "本機股利資料庫")}`;
  renderDataStatus(data.data_status || []);
  renderDividendList(dividendState.records, dividendState.targets);
}

function renderDataStatus(items) {
  const root = byId("data-status-bar");
  if (!root) return;
  const visible = (items || []).filter((item) =>
    ["tw_intraday_15m", "official_daily", "us_intraday_15m", "tw_after_close"].includes(item.job_name)
  );
  if (!visible.length) {
    root.innerHTML = `<div class="data-status-empty">資料更新狀態尚未建立</div>`;
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

function groupDividendRecords(records, targets) {
  const groups = new Map();
  for (const target of targets || []) {
    const ticker = String(target.ticker || "").trim().toUpperCase();
    if (!ticker) continue;
    groups.set(ticker, {
      ticker,
      name: target.name || ticker,
      rows: [],
      target,
    });
  }
  for (const record of records || []) {
    const ticker = String(record.ticker || "").trim().toUpperCase();
    if (!ticker) continue;
    if (!groups.has(ticker)) {
      groups.set(ticker, {
        ticker,
        name: record.name || ticker,
        rows: [],
        target: null,
      });
    }
    groups.get(ticker).rows.push(record);
  }
  return [...groups.values()].map((group) => {
    const byEvent = new Map();
    for (const row of group.rows) {
      const key = `${row.ex_dividend_date || ""}|${numberValue(row.dividend) ?? ""}`;
      const existing = byEvent.get(key);
      if (!existing || String(existing.source || "").startsWith("yahoo")) byEvent.set(key, row);
    }
    const dedupedRows = [...byEvent.values()].sort((a, b) =>
      String(b.ex_dividend_date || "").localeCompare(String(a.ex_dividend_date || ""))
    );
    return {
      ...group,
      name: dedupedRows[0]?.name || group.name || group.ticker,
      rows: dedupedRows,
    };
  });
}

async function refreshDividendTicker(ticker) {
  const status = byId("dividend-status");
  status.textContent = `${ticker} 更新 Yahoo 股利中...`;
  try {
    const response = await fetch(withToken(`/api/database/dividends/${encodeURIComponent(ticker)}/refresh`), {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    status.textContent = `${ticker} Yahoo 更新完成，抓到 ${data.fetched} 筆，寫入 ${data.written} 筆`;
    await loadDividends();
  } catch (error) {
    status.textContent = `${ticker} 更新失敗：${error.message || error}`;
    await loadDividends();
  }
}

function renderDividendList(records, targets) {
  const root = byId("dividend-list");
  const groups = groupDividendRecords(records, targets);
  if (!groups.length) {
    root.innerHTML = `<div class="empty">尚未建立股利標的</div>`;
    return;
  }

  root.innerHTML = groups.map((group) => {
    const latest = group.rows[0] || {};
    const totalDividend = group.rows.reduce((sum, row) => sum + (numberValue(row.dividend) || 0), 0);
    const years = [...new Set(group.rows.map((row) => row.announcement_year).filter(Boolean))];
    const refresh = group.target?.refresh_status || null;
    const failed = refresh?.last_status === "failed";
    const hasRows = group.rows.length > 0;
    return `
      <article class="dividend-stock-card ${failed ? "has-dividend-refresh-failed" : ""}">
        <div class="dividend-stock-summary">
          <div class="dividend-record-main">
            <span class="ticker">${escapeHtml(group.ticker)} · ETF</span>
            <div class="stock-name">${escapeHtml(group.name)}</div>
            <div class="database-meta">
              <span>最新除息 ${escapeHtml(latest.ex_dividend_date || "尚未更新")}</span>
              <span>${group.rows.length} 筆</span>
              <span>${escapeHtml(years.join(", ") || "尚無年度")}</span>
            </div>
            <div class="dividend-refresh-status ${failed ? "failed" : ""}">
              <span>最後更新：${escapeHtml(formatIsoTime(refresh?.last_finished_at))}</span>
              <span>${escapeHtml(refresh?.source || "Yahoo 歷史股利")}</span>
              <span>${escapeHtml(refresh?.last_status || "尚未更新")}</span>
              <span>抓到 ${escapeHtml(refresh?.fetched_count ?? "N/A")} 筆</span>
              ${failed && refresh?.message ? `<strong>${escapeHtml(refresh.message)}</strong>` : ""}
            </div>
          </div>
          <div class="dividend-amount">
            <span>每單位</span>
            <strong>${money(latest.dividend)}</strong>
            <small>期間合計 ${compactMoney(totalDividend)}</small>
          </div>
        </div>
        <div class="dividend-update-row">
          <span>${hasRows ? "更新只抓 Yahoo 股利；每檔會記錄自己的更新時間" : "此標的尚未抓取股利資料"}</span>
          <button class="icon-button dividend-refresh-button" type="button" data-dividend-refresh="${escapeHtml(group.ticker)}">
            ${hasRows ? "更新" : "查詢"} ${escapeHtml(group.ticker)}
          </button>
        </div>
        ${hasRows ? `
          <details class="dividend-history">
            <summary>展開歷史 ${group.rows.length} 筆</summary>
            <div class="dividend-history-table">
              <div class="dividend-history-head">
                <span>除息日</span>
                <span>每單位</span>
              </div>
              ${group.rows.map((record) => renderDividendHistoryRow(group.ticker, record)).join("")}
            </div>
          </details>
        ` : ""}
      </article>
    `;
  }).join("");
}

function renderDividendHistoryRow(ticker, record) {
  const mismatch = mismatchFor(ticker, record.ex_dividend_date);
  return `
    <div class="dividend-history-row ${mismatch ? "dividend-mismatch-row" : ""}">
      <span>${escapeHtml(record.ex_dividend_date || "N/A")}</span>
      <strong>${money(record.dividend)}</strong>
      ${mismatch ? `<small>${escapeHtml(mismatch.message)}</small>` : ""}
    </div>
  `;
}

byId("dividend-target-form").addEventListener("submit", addDividendTarget);
byId("dividend-refresh-all").addEventListener("click", refreshAllDividends);
byId("dividend-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-dividend-refresh]");
  if (!button) return;
  refreshDividendTicker(button.dataset.dividendRefresh);
});
loadDividends();
