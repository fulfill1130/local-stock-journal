const uploadState = {
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

function formatBytes(value) {
  const size = numberValue(value);
  if (size === null) return "N/A";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
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
  const labels = {
    tw_intraday_15m: "台股盤中",
    tw_after_close: "台股盤後",
    official_daily: "官方日線",
    official_history_backfill: "歷史補齊",
    us_intraday_15m: "美股盤中",
  };
  return labels[jobName] || jobName || "unknown";
}

function uploadQueryParams(offset = 0) {
  const params = new URLSearchParams({
    limit: String(uploadState.pageSize),
    offset: String(Math.max(Number(offset) || 0, 0)),
  });
  const profile = byId("upload-profile-filter")?.value || "";
  const status = byId("upload-status-filter")?.value || "";
  if (profile) params.set("profile", profile);
  if (status) params.set("status", status);
  return params;
}

async function loadUploads(options = {}) {
  const append = Boolean(options.append);
  const offset = append ? uploadState.items.length : 0;
  const params = uploadQueryParams(offset);
  uploadState.loading = true;
  renderPagination();

  const response = await fetch(withToken(`/api/database/uploads?${params.toString()}`));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  const nextItems = data.uploads || [];
  uploadState.items = append ? uploadState.items.concat(nextItems) : nextItems;
  uploadState.pagination = data.pagination || uploadState.pagination;
  uploadState.loading = false;
  renderUploads(data);
}

function renderUploads(data) {
  const latest = uploadState.items[0] || {};
  byId("upload-count").textContent = money(data.pagination?.total ?? uploadState.items.length);
  byId("latest-upload-name").textContent = latest.original_filename || "N/A";
  byId("latest-upload-status").textContent = latest.status || "N/A";
  byId("uploads-updated-at").textContent = data.updated_at || "N/A";
  renderDataStatus(data.data_status || []);
  renderUploadList();
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

function renderUploadList() {
  const root = byId("upload-list");
  if (!root) return;
  if (!uploadState.items.length) {
    root.innerHTML = `<div class="empty">目前沒有上傳檔案</div>`;
    return;
  }
  root.innerHTML = uploadState.items.map((item) => {
    const fileUrl = withToken(`/api/database/uploads/${encodeURIComponent(item.id)}/file`);
    const isImage = String(item.mime_type || "").startsWith("image/");
    return `
      <article class="upload-row">
        <div class="upload-row-main">
          <div class="upload-title">
            <strong>${escapeHtml(item.original_filename || "")}</strong>
            <span class="operation-log-badge">${escapeHtml(item.status || "stored")}</span>
          </div>
          <div class="database-meta">
            <span>${escapeHtml(item.profile_slug || "")}</span>
            <span>${escapeHtml(item.mime_type || "")}</span>
            <span>${formatBytes(item.file_size)}</span>
            <span>${formatIsoTime(item.created_at)}</span>
          </div>
          ${item.note ? `<p class="muted">${escapeHtml(item.note)}</p>` : ""}
          ${isImage ? `<img class="upload-preview" src="${fileUrl}" alt="${escapeHtml(item.original_filename || "upload")}">` : ""}
        </div>
        <div class="upload-actions">
          <a class="icon-button compact-button" href="${fileUrl}" target="_blank" rel="noreferrer">預覽</a>
          <button class="icon-button compact-button" type="button" data-upload-status="${item.id}" data-status="reviewed">已核對</button>
          <button class="icon-button compact-button" type="button" data-upload-status="${item.id}" data-status="ignored">忽略</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderPagination() {
  const root = byId("upload-pagination");
  if (!root) return;
  if (uploadState.loading) {
    root.innerHTML = `<span class="muted">讀取中...</span>`;
    return;
  }
  const page = uploadState.pagination;
  root.innerHTML = `
    <span class="muted">已載入 ${money(uploadState.items.length)} / ${money(page.total || 0)}</span>
    ${page.has_more ? `<button id="upload-load-more" class="icon-button" type="button">載入更多</button>` : ""}
  `;
  byId("upload-load-more")?.addEventListener("click", () => loadUploads({ append: true }).catch(showError));
}

async function uploadDocument(event) {
  event.preventDefault();
  const status = byId("upload-status");
  const file = byId("upload-file").files?.[0];
  if (!file) {
    status.textContent = "請先選擇檔案。";
    return;
  }
  const formData = new FormData();
  formData.append("profile", byId("upload-profile").value || "son");
  formData.append("file", file);
  formData.append("note", byId("upload-note").value || "");
  formData.append("source", "upload_library");
  status.textContent = "上傳中...";
  let data;
  try {
    data = await uploadFormData(formData);
  } catch (error) {
    status.textContent = `一般上傳失敗，改用備援保存：${error.message || error}`;
    data = await uploadFileAsBase64(file, {
      profile: byId("upload-profile").value || "son",
      note: byId("upload-note").value || "",
      source: "upload_library_base64",
    });
  }
  status.textContent = data.document?.duplicate ? "檔案已存在，上傳庫已更新時間。" : "已存入上傳庫。";
  byId("upload-file").value = "";
  byId("upload-note").value = "";
  await loadUploads();
}

async function uploadFormData(formData) {
  const response = await fetch(withToken("/api/database/uploads"), {
    method: "POST",
    body: formData,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function uploadFileAsBase64(file, meta) {
  const status = byId("upload-status");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onprogress = (event) => {
      if (event.lengthComputable) {
        status.textContent = `備援讀取檔案 ${Math.max(1, Math.round((event.loaded / event.total) * 70))}%...`;
      }
    };
    reader.onerror = () => reject(new Error("讀取檔案失敗"));
    reader.onload = async () => {
      try {
        status.textContent = "備援上傳中...";
        const response = await fetch(withToken("/api/database/uploads-base64"), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            profile: meta.profile,
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            data: String(reader.result || ""),
            source: meta.source,
            note: meta.note,
          }),
        });
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
        resolve(data);
      } catch (error) {
        reject(error);
      }
    };
    reader.readAsDataURL(file);
  });
}

async function updateUploadStatus(id, status) {
  const response = await fetch(withToken(`/api/database/uploads/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({status}),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  await loadUploads();
}

function showError(error) {
  uploadState.loading = false;
  renderPagination();
  const status = byId("upload-status");
  if (status) status.textContent = `錯誤：${error.message || error}`;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-upload-status]");
  if (!button) return;
  updateUploadStatus(button.dataset.uploadStatus, button.dataset.status).catch(showError);
});

byId("upload-form")?.addEventListener("submit", (event) => {
  uploadDocument(event).catch(showError);
});
byId("upload-profile-filter")?.addEventListener("change", () => loadUploads().catch(showError));
byId("upload-status-filter")?.addEventListener("change", () => loadUploads().catch(showError));

loadUploads().catch(showError);
