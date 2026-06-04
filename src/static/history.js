const historyTicker = window.HISTORY_TICKER;
const shareToken = new URLSearchParams(window.location.search).get("token") || "";
const el = (id) => document.getElementById(id);

function withToken(path) {
  if (!shareToken) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(shareToken)}`;
}

function numberValue(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function numberText(value, decimals = 0) {
  const num = numberValue(value);
  if (num === null) return "N/A";
  return num.toLocaleString("zh-TW", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

async function loadHistory() {
  const response = await fetch(withToken(`/api/database/${encodeURIComponent(historyTicker)}/history`));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  render(data);
}

function render(data) {
  const rows = data.rows || [];
  el("history-row-count").textContent = `${numberText(data.summary?.row_count || 0)} 筆`;
  el("history-first-date").textContent = data.summary?.first_date || "N/A";
  el("history-last-date").textContent = data.summary?.last_date || "N/A";
  el("history-source").textContent = rows[0]?.source_market || "N/A";
  el("history-updated-at").textContent = data.updated_at || "N/A";

  const body = el("history-body");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="8" class="empty">目前沒有日線資料</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((row) => `
    <tr>
      <td>${row.trade_date}</td>
      <td>${numberText(row.open, 2)}</td>
      <td>${numberText(row.high, 2)}</td>
      <td>${numberText(row.low, 2)}</td>
      <td>${numberText(row.close, 2)}</td>
      <td>${numberText(row.volume)}</td>
      <td>${numberText(row.turnover)}</td>
      <td>${numberText(row.transactions)}</td>
    </tr>
  `).join("");
}

loadHistory().catch((error) => {
  el("history-body").innerHTML = `<tr><td colspan="8" class="empty">讀取失敗：${error.message || error}</td></tr>`;
});
