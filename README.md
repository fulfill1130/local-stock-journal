# stock_daily_helper

本專案是一個私人的本機股票決策 Dashboard，用來整理自己與家人的台股 ETF / 股票持股、買賣紀錄、即時或延遲報價、官方日線資料與未來 AI 判讀資料。

它不是自動交易系統，也不串接券商 API。所有買進、賣出、現金異動都由使用者手動輸入；系統只負責整理資料、計算成本與損益、抓取市場價格、顯示 Dashboard。

## 目前架構

```text
stock_daily_helper/
├─ data/
│  ├─ profiles/
│  │  ├─ son/state.json
│  │  └─ mom/state.json
│  ├─ market_data/
│  │  ├─ etf.sqlite
│  │  ├─ twse.sqlite
│  │  └─ tpex.sqlite
│  ├─ quote_cache.json
│  ├─ refresh.log
│  ├─ server.out.log
│  └─ server.err.log
├─ scripts/
├─ src/
│  ├─ main.py
│  ├─ server.py
│  ├─ scheduler.py
│  ├─ store.py
│  ├─ analyzer.py
│  ├─ central_store.py
│  ├─ official_market.py
│  ├─ official_sync.py
│  ├─ market.py
│  ├─ static/
│  │  ├─ app.js
│  │  ├─ database.js
│  │  ├─ history.js
│  │  └─ style.css
│  └─ templates/
│     ├─ dashboard.html
│     ├─ database.html
│     └─ history.html
└─ README.md
```

## 安裝

建議使用 Python 3.11 以上。

```bash
pip install -r requirements.txt
```

目前主要套件：

```text
flask
pandas
yfinance
pyyaml
jinja2
```

## 啟動 Dashboard

本機使用：

```bash
python src/main.py serve
```

Tailscale 私網使用：

```bash
python src/main.py serve --host 100.70.96.67 --port 8787 --refresh-on-start
```

目前入口：

```text
http://100.70.96.67:8787/son
http://100.70.96.67:8787/mom
http://100.70.96.67:8787/database
```

`/son` 是兒子帳戶，`/mom` 是母親帳戶。兩邊持股、現金、交易紀錄分開保存，但市場資料共用同一套中央資料庫。

## 帳戶資料

各帳戶資料放在：

```text
data/profiles/son/state.json
data/profiles/mom/state.json
```

每個帳戶保存自己的：

- 持股
- 觀察清單
- 可用資金
- 買進 / 賣出 / 現金紀錄
- 每檔股票的買入批次 `lots`
- 手動設定，例如券商損益、兩平價、股利估計

交易資料不會送到外部券商，也不會自動下單。

## 中央市場資料庫

市場資料已改成中央系統，前端不再各自抓 Yahoo。兒子帳戶與母親帳戶都只跟中央資料庫讀資料，避免同一支股票在不同帳戶名稱不一致。

中央資料庫分成三個 SQLite 檔案：

```text
data/market_data/etf.sqlite
data/market_data/twse.sqlite
data/market_data/tpex.sqlite
```

用途：

- `etf.sqlite`：ETF
- `twse.sqlite`：上市股票，Yahoo suffix 通常是 `.TW`
- `tpex.sqlite`：上櫃股票，Yahoo suffix 通常是 `.TWO`

這樣做的原因是降低單一資料庫損壞時的影響，也方便未來擴充成完整台灣股票資料庫。

## 中央資料庫表格

每個 SQLite 內主要有這些表：

- `instruments`
  - 股票主檔，保存代號、名稱、類型、交易所 suffix、Yahoo symbol。
- `quotes`
  - 目前或最近一次主報價。
- `ohlcv_daily`
  - 官方日線 OHLCV。
  - 未來 KRONOS 或其他 AI 主要會讀這張。
- `ohlcv_intraday_15m`
  - 盤中 15 分鐘 OHLCV。
  - 來源目前是 Yahoo / yfinance。
- `quote_snapshots_15m`
  - 每 15 分鐘的報價快照。
  - 用來保存延遲報價紀錄。
- `after_close_quotes`
  - 盤後收尾報價。
  - 只顯示在前端股票卡旁邊，不覆蓋主收盤價。

## 資料來源

### 官方日線

日線資料優先使用官方來源：

- `.TW` 上市股票與 ETF：TWSE 台灣證券交易所
- `.TWO` 上櫃股票：TPEx 櫃買中心

這些資料會寫進 `ohlcv_daily`，作為正式歷史資料。

### 盤中與美股

盤中台股與美股目前使用 Yahoo Finance / yfinance。

用途：

- 台股盤中 15 分鐘報價
- 台股盤中 15 分鐘 OHLCV
- 美股指數與個股報價
- 盤後收尾報價

Yahoo / yfinance 可能延遲、失敗或短時間被限制，不能當成交易用即時報價。

## 自動更新排程

排程是在 Flask Python 程式內啟動，不是 Windows 工作排程，也不是外部伺服器。

目前邏輯：

- 台股盤中：`09:01` 到 `13:01`
  - 每 15 分鐘一次
  - 節點大約是 `09:01 / 09:16 / 09:31 / ... / 13:01`
  - 寫入 `quote_snapshots_15m` 與 `ohlcv_intraday_15m`
- 台股盤後收尾：`13:31`
  - 寫入 `after_close_quotes`
  - 不覆蓋主收盤價
- 官方日線補資料：`14:00`
  - 向 TWSE / TPEx 補 `ohlcv_daily`
- 美股盤中：`21:30` 到 `05:00`
  - 每 15 分鐘一次

如果不在允許時間內，前端按「更新」也不會亂打 API。例外是手動新增買賣交易時，系統會強制更新該檔股票一次，避免新股票完全沒有價格。

## 買進、賣出與 FIFO

前端右下角 `+` 可以輸入交易。

買進欄位：

- 日期
- 股票代碼
- 張數
- 零股股數
- 成交價
- 手續費
- 備註

賣出欄位：

- 日期
- 股票代碼
- 張數
- 零股股數
- 成交價
- 手續費
- 交易稅
- 備註

券商賣出邏輯採用 FIFO，系統也照這個邏輯處理：

- 賣出時會先消耗最早買入的批次。
- 如果只賣部分股數，該批次會保留 `remaining_shares`。
- 持股股數與平均成本會從剩餘 `lots` 重新計算。

每張持股卡可以展開「買入批次」，會列出：

- 幾月幾號買
- 買入幾股
- 成交價
- 如果該批次被部分賣出，會顯示剩幾股
- 手續費
- 每股成本

早期匯入但沒有 `lots` 的資料，頁面輸出前會從完整交易紀錄重建批次。

## 前端 Dashboard

目前前端是手機與電腦都能看的本機網頁。

主要功能：

- 兒子 / 母親雙帳戶入口
- Dashboard 標題置中顯示帳戶名稱
- 可用資金卡，旁邊可新增存入資金
- 美股與總經區塊可收合
- 持股依類型分流：
  - ETF：綠色
  - 上市：黃色
  - 上櫃：紫色
- 每個分流區塊可收合
- 每張持股卡可單獨展開買入批次
- ETF 卡片強化代號顯示，因為 ETF 通常看代號比中文名稱更快
- 損益正數用紅色、負數用綠色，符合台股習慣
- 數字會依來源改顏色：
  - TWSE / TPEx 官方：亮金色
  - Yahoo：青色
  - 手動或不明來源：暗灰色

## 中央資料庫頁

入口：

```text
http://100.70.96.67:8787/database
```

這裡可以看中央股票主檔與資料狀態：

- 股票代號
- 名稱
- ETF / STOCK 類型
- `.TW` 或 `.TWO`
- Yahoo symbol
- 日線資料筆數
- 日線起訖日期
- 最新主檔時間

也可以手動修正股票名稱或 suffix。未來如果要收錄全部台灣上市、上櫃與 ETF，會從這裡慢慢擴充。

每檔有日線資料時，可以進入：

```text
/database/<ticker>/history
```

查看該檔歷史日線資料。

## CLI 指令

### 買進

```bash
python src/main.py buy 2330 5 2250 --name 台積電 --fee 1 --date 2026-05-10
python src/main.py buy 2330 5 2250 --name 台積電 --fee 1 --date 2026-05-10 --profile mom
```

### 賣出

```bash
python src/main.py sell 00900 100 16.4 --fee 1 --tax 1 --date 2026-05-10 --note 部分獲利
```

### 新增觀察

```bash
python src/main.py watch 1605 --name 華新 --buy 22 --alert 25 --stop 20 --sell 28
```

### 設定現金

```bash
python src/main.py cash 30000
python src/main.py cash 30000 --profile mom
```

### 抓官方日線

```bash
python src/main.py history-sync 2330 --start 2021-05-17 --end 2026-05-17
python src/main.py history-sync-all --start 2021-05-17 --end 2026-05-17
python src/main.py history-sync-verified-all --start 2021-05-17 --end 2026-05-17
python src/main.py official-daily-sync
```

說明：

- `history-sync`：抓單檔。
- `history-sync-all`：抓中央資料庫內所有檔案。
- `history-sync-verified-all`：慢速逐檔抓，抓完會驗證資料完整度。
- `official-daily-sync`：補缺少的官方日線資料。

## Tailscale 私有連線

這個 Dashboard 預設不掛公開網路。手機外出要看時，建議使用 Tailscale 私網。

流程：

1. 電腦安裝 Tailscale 並登入。
2. 手機安裝 Tailscale 並登入同一個 tailnet。
3. 電腦啟動 Dashboard，host 綁 Tailscale IP。
4. 手機打開：

```text
http://100.70.96.67:8787/son
http://100.70.96.67:8787/mom
http://100.70.96.67:8787/database
```

如果 Tailscale IP 變了，要改成目前電腦的 Tailscale IP。

## 目前啟動中的服務

目前常用啟動方式：

```powershell
python src/main.py serve --host 100.70.96.67 --port 8787 --refresh-on-start
```

`--refresh-on-start` 會在啟動時補一次官方日線與必要的快取資料。

## 與 KRONOS / AI 的未來整合方向

未來若要加入 KRONOS 或其他股票判讀 AI，建議不要讓 AI 直接改 Dashboard 主程式。

建議架構：

```text
Dashboard Flask
  ↓ 讀取
market_data/*.sqlite
  ↑ 寫入分析結果
KRONOS worker / subprocess
  ↑ 讀取 OHLCV
TWSE / TPEx / Yahoo / 其他資料源
```

預計資料流：

- KRONOS 讀 `ohlcv_daily` 做日線分析。
- 若需要盤中判讀，再讀 `ohlcv_intraday_15m`。
- AI 結果未來可以另外寫進 `kronos_signals` 或類似表格。
- Dashboard 只讀 AI 結果，不讓 AI 直接控制交易。

這樣可以避免 Python 套件衝突。KRONOS 如果需要 PyTorch、Hugging Face、特殊 numpy 版本，可以放在獨立 virtual environment，用 subprocess 或 worker 跟 Dashboard 分開跑。

## 重要限制

- 本工具不會自動下單。
- 本工具不串接券商 API。
- Yahoo / yfinance 資料可能延遲、失敗或被限制。
- 盤中資料不是交易用即時報價。
- 官方日線以 TWSE / TPEx 為主，但官方資料也可能因日期、休市、網站變動而需要修正。
- 所有資料都在本機，請自行備份 `data/`。
## 2026-06-04 日線補齊策略

資料庫頁面的歷史日線不再從前端手動更新。系統保留每日收盤後寫入新價錢的流程，另外在 Flask 服務內啟動一個背景補齊器：

- 每 30 分鐘檢查一次中央市場資料庫。
- 每次只處理一檔股票，避免一次對 TWSE / TPEx 打太多請求。
- 補齊目標為最近 5 年加 30 天的官方日線資料。
- 如果某檔股票已有「上市/資料起始日」，補齊器會從該日開始判斷需要多少資料。
- 如果沒有上市日，但目前日線第一筆在最近 120 天內、最後一筆資料也很新，系統會視為新上市或新掛牌標的，不會一直要求補滿 5 年。
- 每檔股票會記錄 `listing_date`、`history_status`、`history_checked_at`。
- 連續 3 次官方日線都查無資料時，資料庫頁面會用紅框標示疑似下市，並提供「排查」與「下市」按鈕。
- 標記為下市後，背景補齊器會跳過該檔。

這個背景補齊器只補中央市場資料庫，不會下單，也不會連接券商 API。
