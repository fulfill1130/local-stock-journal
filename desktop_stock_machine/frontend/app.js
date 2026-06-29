const DEFAULT_LANGUAGE = "zh-Hant";

const translations = {
  "zh-Hant": {
    "document.title": "桌面股票機",
    "brand.title": "股票機",
    "brand.subtitle": "桌面重建",
    "nav.overview": "總覽",
    "nav.accounts": "帳戶",
    "nav.stocks": "股票 / ETF",
    "nav.research": "研究工具",
    "nav.imports": "匯入中心",
    "nav.sources": "資料來源",
    "nav.backup": "備份與還原",
    "nav.settings": "設定 / 紀錄",
    "sidebar.footer": "僅限本機優先介面",
    "top.eyebrow": "桌面版重建",
    "status.mode": "示範 / 骨架模式",
    "status.dataRoot": "應用程式資料根目錄：尚未連線",
    "status.legacy": "網頁版原型：僅供參考",
    "status.market": "市場資料庫：規劃中",
    "overview.eyebrow": "本機研究平台",
    "overview.title": "桌面優先的股票日誌與 ETF 研究工作台",
    "overview.body": "這是一個乾淨的桌面版外殼，未來用於投資組合檢視、研究工具轉接、市場資料、匯入暫存，以及有備份保護的流程。",
    "metric.realCalls": "真實資料存取",
    "metric.ledgerWrites": "帳本寫入",
    "metric.staticValue": "靜態",
    "metric.frontendOnly": "僅前端介面",
    "card.journal.title": "投資組合日誌",
    "card.journal.body": "未來放帳戶日誌、持股、庫存、筆記與檢視介面。",
    "card.etf.title": "ETF 持股實驗室",
    "card.etf.body": "先預覽供應商資料與成分股，再存成研究結果。",
    "card.market.title": "市場資料庫",
    "card.market.body": "規劃中的本機市場快照、OHLCV 歷史與資料來源健康狀態。",
    "card.adapters.title": "外部工具轉接",
    "card.adapters.body": "替 GitHub 工具與其他外部工具建立標準化輸出合約。",
    "card.import.title": "匯入暫存",
    "card.import.body": "所有匯入先預覽、驗證、確認，再允許寫入正式資料。",
    "card.backup.title": "備份安全",
    "card.backup.body": "遷移、批次匯入或破壞性變更前，必須先 dry-run 與備份。",
    "accounts.eyebrow": "帳務邊界",
    "accounts.title": "帳戶",
    "accounts.body": "真實 profile 會先保持封鎖，直到 data root、備份與遷移安全規則完成。",
    "accounts.summary.title": "帳戶摘要",
    "accounts.summary.body": "未來顯示持股、現金流與日誌狀態。",
    "accounts.guard.title": "帳本保護",
    "accounts.guard.body": "確認資料必須透過 core storage 合約與審核寫入流程。",
    "accounts.blocked.title": "真實 profile 尚未啟用",
    "accounts.blocked.body": "這個 UI shell 不會載入私人帳戶資料。",
    "stocks.eyebrow": "研究工作區",
    "stocks.title": "股票 / ETF",
    "stocks.body": "桌面版個股與 ETF 詳細頁會在這裡重做，不複製舊網頁版頁面。",
    "stocks.canvas.title": "個股詳情畫布",
    "stocks.canvas.body": "未來放圖表、庫存、筆記與市場脈絡。",
    "stocks.etf.title": "ETF 成分檢視",
    "stocks.etf.body": "未來顯示持股快照、資料來源、快照日期與中繼資料。",
    "stocks.library.title": "研究結果庫",
    "stocks.library.body": "儲存的研究輸出會和個人確認帳本分開。",
    "research.eyebrow": "轉接平台",
    "research.title": "研究工具",
    "research.body": "未來外部工具輸出會先標準化，使用者預覽後才存成研究結果。",
    "flow.github": "GitHub 工具",
    "flow.to": "到",
    "flow.adapter": "轉接器",
    "flow.output": "標準化輸出",
    "flow.preview": "預覽",
    "flow.save": "存成研究結果",
    "research.chip.csv": "CSV / JSON 轉接器",
    "research.chip.runner": "子程序執行器",
    "research.chip.registry": "外掛登錄表規劃中",
    "research.chip.blocked": "帳本寫入封鎖",
    "research.isolation.title": "工具隔離",
    "research.isolation.body": "外部工具輸出必須先經過轉接器，才會進入審核畫面。",
    "research.preview.title": "先預覽",
    "research.preview.body": "產生的研究資料會先停在暫存狀態，明確確認後才保存。",
    "imports.eyebrow": "審核流程",
    "imports.title": "匯入中心",
    "imports.body": "匯入資料會先預覽、驗證、確認，再允許持久寫入。",
    "imports.dryRun.title": "必須 dry-run",
    "imports.dryRun.body": "匯入候選資料必須先檢查，不能直接接受。",
    "imports.confirm.title": "需要使用者確認",
    "imports.confirm.body": "沒有明確同意前，匯入結果不能寫入確認資料。",
    "imports.report.title": "暫存報告",
    "imports.report.body": "未來會顯示略過列、警告與阻擋原因。",
    "sources.eyebrow": "市場資料中心",
    "sources.title": "資料來源",
    "sources.body": "供應商動作會維持手動觸發，並以預覽流程為主。",
    "sources.etf.title": "ETF 供應商預覽",
    "sources.etf.body": "未來供應商抓取會先預覽，再確認成快照。",
    "sources.csv.title": "手動 CSV 備援",
    "sources.csv.body": "本機檔案可在驗證後成為受控備援路徑。",
    "sources.snapshot.title": "市場快照資料庫",
    "sources.snapshot.body": "規劃中的本機研究資料庫，保存報價、OHLCV 與 metadata。",
    "sources.cache.title": "Provider cache 不是事實來源",
    "sources.cache.body": "raw cache 與診斷資料只能暫存，且必須被忽略。",
    "backup.eyebrow": "資料安全",
    "backup.title": "備份與還原",
    "backup.body": "遷移與高風險寫入會先封鎖，直到安全合約完成。",
    "backup.dryRun.title": "必須 dry-run",
    "backup.dryRun.body": "任何遷移寫入前都要先檢查來源與目標路徑。",
    "backup.required.title": "必須備份",
    "backup.required.body": "備份建立成功後，才可以進行遷移或破壞性變更。",
    "backup.silent.title": "不允許靜默遷移",
    "backup.silent.body": "桌面版不會自動搬動網頁版 prototype 的資料。",
    "settings.eyebrow": "偏好設定",
    "settings.title": "設定 / 紀錄",
    "settings.body": "目前只有靜態設定介面；未來會接上資料根目錄狀態與桌面設定檔。",
    "settings.language.title": "介面語言",
    "settings.language.body": "語言切換只影響目前畫面，現在不會寫入檔案或瀏覽器儲存空間。",
    "settings.language.zh": "繁體中文",
    "settings.language.en": "English",
    "settings.language.currentLabel": "目前語言：",
    "settings.language.current.zh": "繁體中文",
    "settings.language.current.en": "英文",
    "settings.dataRoot.title": "應用程式資料根目錄",
    "settings.dataRoot.body": "尚未連線。這個介面外殼不會建立或填入 `app_data/`。",
    "settings.legacy.title": "舊版邊界",
    "settings.legacy.body": "Flask 網頁版原型僅作參考，這裡不會匯入。",
    "settings.provider.title": "資料供應商設定",
    "settings.provider.body": "靜態介面不會讀取本機供應商設定。",
    "inspector.guardrails": "執行防護",
    "guard.mode": "模式",
    "guard.modeValue": "示範 / 骨架",
    "guard.dataRoot": "資料根目錄",
    "guard.dataRootValue": "尚未連線",
    "guard.backend": "後端呼叫",
    "guard.backendValue": "停用",
    "guard.ledger": "帳本寫入",
    "guard.ledgerValue": "封鎖",
    "inspector.log": "外殼紀錄",
    "log.initialized": "桌面外殼已初始化",
    "log.legacy": "未匯入舊網頁版執行環境",
    "log.appData": "未建立 app_data",
    "log.loaded": "介面外殼已載入",
  },
  en: {
    "document.title": "Desktop Stock Machine",
    "brand.title": "Stock Machine",
    "brand.subtitle": "Desktop rebuild",
    "nav.overview": "Overview",
    "nav.accounts": "Accounts",
    "nav.stocks": "Stocks / ETFs",
    "nav.research": "Research Tools",
    "nav.imports": "Import Center",
    "nav.sources": "Data Sources",
    "nav.backup": "Backup & Restore",
    "nav.settings": "Settings / Logs",
    "sidebar.footer": "Local-first shell only",
    "top.eyebrow": "Desktop Rebuild",
    "status.mode": "Demo / Skeleton mode",
    "status.dataRoot": "App data root: not connected",
    "status.legacy": "Legacy web prototype: reference only",
    "status.market": "Market database: planned",
    "overview.eyebrow": "Local research platform",
    "overview.title": "Desktop-first stock journal and ETF workbench",
    "overview.body": "A clean shell for portfolio review, research adapters, market data, staged imports, and backup-aware workflows.",
    "metric.realCalls": "Real data calls",
    "metric.ledgerWrites": "Ledger writes",
    "metric.staticValue": "static",
    "metric.frontendOnly": "Frontend only",
    "card.journal.title": "Portfolio Journal",
    "card.journal.body": "Future account journal, holdings, lots, notes, and review surfaces.",
    "card.etf.title": "ETF Holdings Lab",
    "card.etf.body": "Preview provider snapshots and compare components before saving research results.",
    "card.market.title": "Market Database",
    "card.market.body": "Planned local market snapshots, OHLCV history, and source health views.",
    "card.adapters.title": "External Tool Adapters",
    "card.adapters.body": "Adapter contracts for GitHub tools and standardized research outputs.",
    "card.import.title": "Import Staging",
    "card.import.body": "Safe preview, validation, and confirmation before any final record writes.",
    "card.backup.title": "Backup Safety",
    "card.backup.body": "Dry-run and backup gates before migration, bulk import, or destructive change.",
    "accounts.eyebrow": "Journal boundary",
    "accounts.title": "Accounts",
    "accounts.body": "Real profiles stay blocked until data-root wiring, backup, and migration safety are ready.",
    "accounts.summary.title": "Account summaries",
    "accounts.summary.body": "Placeholder for holdings, cash movements, and journal status.",
    "accounts.guard.title": "Ledger protection",
    "accounts.guard.body": "Confirmed records will require reviewed writes through core storage contracts.",
    "accounts.blocked.title": "Real profile support blocked",
    "accounts.blocked.body": "No private account data is loaded by this UI shell.",
    "stocks.eyebrow": "Research workspace",
    "stocks.title": "Stocks / ETFs",
    "stocks.body": "Desktop detail views will be rebuilt here instead of copying the old web prototype pages.",
    "stocks.canvas.title": "Stock detail canvas",
    "stocks.canvas.body": "Future charts, lots, notes, and market context in a desktop layout.",
    "stocks.etf.title": "ETF composition view",
    "stocks.etf.body": "Future holdings snapshots with provider source and as-of metadata.",
    "stocks.library.title": "Research result library",
    "stocks.library.body": "Saved outputs will remain separate from confirmed personal ledger records.",
    "research.eyebrow": "Adapter platform",
    "research.title": "Research Tools",
    "research.body": "Future external tools will be normalized before users preview and save results.",
    "flow.github": "GitHub tool",
    "flow.to": "to",
    "flow.adapter": "Adapter",
    "flow.output": "Standardized output",
    "flow.preview": "Preview",
    "flow.save": "Save as research result",
    "research.chip.csv": "CSV / JSON adapter",
    "research.chip.runner": "Subprocess runner",
    "research.chip.registry": "Plugin registry planned",
    "research.chip.blocked": "Ledger write blocked",
    "research.isolation.title": "Tool isolation",
    "research.isolation.body": "Adapters will translate tool outputs before anything reaches review surfaces.",
    "research.preview.title": "Preview first",
    "research.preview.body": "Generated research stays staged until explicitly saved as a research result.",
    "imports.eyebrow": "Reviewed workflow",
    "imports.title": "Import Center",
    "imports.body": "Imports will use preview, validation, and confirmation before any durable writes.",
    "imports.dryRun.title": "Dry-run required",
    "imports.dryRun.body": "Import candidates must be inspected before final acceptance.",
    "imports.confirm.title": "User confirmation required",
    "imports.confirm.body": "No import result should write confirmed records without explicit approval.",
    "imports.report.title": "Staging reports",
    "imports.report.body": "Future validation results will show skipped rows, warnings, and blockers.",
    "sources.eyebrow": "Market data center",
    "sources.title": "Data Sources",
    "sources.body": "Provider actions remain manual-trigger and preview-oriented in this shell.",
    "sources.etf.title": "ETF provider preview",
    "sources.etf.body": "Future provider fetches will preview data before confirmed snapshots.",
    "sources.csv.title": "Manual CSV fallback",
    "sources.csv.body": "Local files can become a controlled fallback path after validation.",
    "sources.snapshot.title": "Market snapshot database",
    "sources.snapshot.body": "Planned local research database for quotes, OHLCV, and snapshot metadata.",
    "sources.cache.title": "Provider cache is not source of truth",
    "sources.cache.body": "Raw cache and diagnostics stay temporary and ignored.",
    "backup.eyebrow": "Data safety",
    "backup.title": "Backup & Restore",
    "backup.body": "Migration and risky writes will be blocked until the safety contract is implemented.",
    "backup.dryRun.title": "Dry-run required",
    "backup.dryRun.body": "Source and target paths must be reviewed before any migration write.",
    "backup.required.title": "Backup required",
    "backup.required.body": "Backup creation must succeed before migration or destructive changes.",
    "backup.silent.title": "No silent migration",
    "backup.silent.body": "The desktop product will not move web prototype data automatically.",
    "settings.eyebrow": "Preferences",
    "settings.title": "Settings / Logs",
    "settings.body": "These are static settings for now; future work will wire data-root status and desktop settings files.",
    "settings.language.title": "Interface language",
    "settings.language.body": "Language switching only affects the current page and does not write files or browser storage.",
    "settings.language.zh": "繁體中文",
    "settings.language.en": "English",
    "settings.language.currentLabel": "Current language: ",
    "settings.language.current.zh": "Traditional Chinese",
    "settings.language.current.en": "English",
    "settings.dataRoot.title": "App data root",
    "settings.dataRoot.body": "Not connected. This shell does not create or populate `app_data/`.",
    "settings.legacy.title": "Legacy boundary",
    "settings.legacy.body": "The Flask web prototype remains a reference and is not imported here.",
    "settings.provider.title": "Provider config",
    "settings.provider.body": "No local provider configuration is loaded by the static UI.",
    "inspector.guardrails": "Runtime Guardrails",
    "guard.mode": "Mode",
    "guard.modeValue": "Demo / Skeleton",
    "guard.dataRoot": "Data root",
    "guard.dataRootValue": "Not connected",
    "guard.backend": "Backend calls",
    "guard.backendValue": "Disabled",
    "guard.ledger": "Ledger writes",
    "guard.ledgerValue": "Blocked",
    "inspector.log": "Shell Log",
    "log.initialized": "Desktop shell initialized",
    "log.legacy": "Legacy web runtime not imported",
    "log.appData": "app_data not created",
    "log.loaded": "UI shell loaded",
  },
};

const navItems = Array.from(document.querySelectorAll("[data-section-target]"));
const sections = Array.from(document.querySelectorAll("[data-section]"));
const sectionTitle = document.querySelector("#section-title");
const languageButtons = Array.from(document.querySelectorAll("[data-lang-option]"));
const languageLabel = document.querySelector("[data-language-label]");
let currentLanguage = DEFAULT_LANGUAGE;

function translate(key) {
  return translations[currentLanguage]?.[key] ?? translations[DEFAULT_LANGUAGE]?.[key] ?? key;
}

function activeSectionId() {
  return navItems.find((item) => item.classList.contains("active"))?.dataset.sectionTarget ?? "overview";
}

function isKnownSection(sectionId) {
  return sections.some((section) => section.dataset.section === sectionId);
}

function updateSectionTitle(sectionId) {
  const activeItem = navItems.find((item) => item.dataset.sectionTarget === sectionId);
  if (activeItem && sectionTitle) {
    sectionTitle.textContent = translate(activeItem.dataset.i18n);
  }
}

function updateLanguageControls() {
  for (const button of languageButtons) {
    const isActive = button.dataset.langOption === currentLanguage;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  }

  if (languageLabel) {
    const key = currentLanguage === "en" ? "settings.language.current.en" : "settings.language.current.zh";
    languageLabel.textContent = translate(key);
  }
}

function setLanguage(language) {
  if (!translations[language]) {
    return;
  }

  currentLanguage = language;
  document.documentElement.lang = language;
  document.title = translate("document.title");

  for (const element of document.querySelectorAll("[data-i18n]")) {
    element.textContent = translate(element.dataset.i18n);
  }

  updateLanguageControls();
  updateSectionTitle(activeSectionId());
}

function showSection(sectionId) {
  for (const item of navItems) {
    const isActive = item.dataset.sectionTarget === sectionId;
    item.classList.toggle("active", isActive);
    item.setAttribute("aria-current", isActive ? "page" : "false");
  }

  for (const section of sections) {
    const isActive = section.dataset.section === sectionId;
    section.hidden = !isActive;
    section.classList.toggle("active", isActive);
  }

  updateSectionTitle(sectionId);
}

for (const item of navItems) {
  item.addEventListener("click", () => {
    showSection(item.dataset.sectionTarget);
  });
}

for (const button of languageButtons) {
  button.addEventListener("click", () => {
    setLanguage(button.dataset.langOption);
  });
}

const initialSection = window.location.hash.slice(1);

setLanguage(DEFAULT_LANGUAGE);
showSection(isKnownSection(initialSection) ? initialSection : "overview");
