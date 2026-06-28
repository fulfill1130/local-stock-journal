# Path Dependency Audit

## Purpose

This audit records path dependencies that could break during a gradual migration toward:

- `web_stock_machine/`
- `desktop_stock_machine/`
- `market_database/`

It is an audit-only document. No files were moved, no imports were changed, no runtime behavior was changed, and no data folders were touched for this task.

## Current Path Dependency Summary

The highest-risk dependency is that `src/` currently acts as a flat Python import root. Most modules import peer modules by bare names such as `server`, `central_store`, `store`, and `utils`, while tests and scripts add `ROOT / "src"` to `sys.path`.

The second highest-risk area is Flask web asset wiring. `src/server.py` points Flask directly at `project_root / "src" / "templates"` and `project_root / "src" / "static"`.

The third highest-risk area is runtime storage. The current web prototype uses `data/`, `demo_runtime/`, `sample_data/`, `config/providers.local.json`, and `data/provider_cache/` in code, scripts, tests, docs, and launch commands. These paths must not be silently moved into the future desktop `app_data/` root.

## Hardcoded Path Inventory

| Path or pattern | Found in | Purpose | Migration risk | Suggested future owner | Notes |
|---|---|---:|---|---|---|
| `src/` as module root | `src/*.py`, `tests/*.py`, `scripts/*.py` | Current Python module root | High | Shared core/storage plus web/market/desktop packages | Moving `src/` will break bare peer imports unless a compatibility layer or package plan exists. |
| `python src/main.py` | `README.md`, docs, scripts, `src/cli.py`, tests | Main CLI/server entry command | High | Transitional root launcher or web app CLI | Keep a wrapper or update docs/tests in a dedicated task. |
| `project_root / "src" / "templates"` | `src/server.py` | Flask template folder | High | `web_stock_machine/` | Needs app factory/static path plan before moving templates. |
| `project_root / "src" / "static"` | `src/server.py` | Flask static folder | High | `web_stock_machine/` | Static URLs currently depend on Flask's configured static folder. |
| `data/` | `src/server.py`, `src/settings.py`, `src/cli.py`, tests, docs | Current web prototype private runtime root | High | Web prototype until explicit migration | Must remain separate from future desktop `app_data/`. |
| `data/market_data/` | `src/server.py`, `src/settings.py`, `src/cli.py`, tests | Market/research SQLite root | High | `market_database/` concepts and shared storage APIs | Future move needs central storage abstraction and compatibility. |
| `data/profiles/` | `src/server.py`, settings/docs/tests | Personal account/profile data | High | Shared core/storage, not `market_database/` | Must not be mixed with market/research data. |
| `demo_runtime/` | `src/server.py`, scripts, tests, docs | Current demo runtime root | Medium | Web prototype demo or future desktop demo with clear boundary | Has sentinel/validation assumptions. |
| `sample_data/` | scripts, tests, providers, docs | Public synthetic fixtures/seeds | Medium | `market_database/` fixtures later | Tests and scripts assume current location. |
| `sample_data/market/` | market provider tests, demo scripts | Synthetic market CSV fixtures | Medium | `market_database/` | ETF holdings and OHLCV tests use exact fixture paths. |
| `config/providers.local.json` | `src/http_etf_holdings_provider.py`, tests, docs | Local provider config | Medium | Local config boundary, later `app_data/config/` or market provider config | Must remain ignored and private. |
| `data/provider_cache/etf_holdings/` | `src/http_etf_holdings_provider.py`, docs, `.gitignore` | Optional raw provider cache | Medium | Runtime cache under future data root | Cache is not a source of truth and must stay ignored. |
| `scripts/start_dashboard*.ps1` with `src/main.py` | `scripts/` | Local launchers | Medium | Web or desktop launch scripts | Needs entrypoint compatibility after migration. |
| `app_data/` | docs, `.gitignore` | Future desktop data root | Low now, high once implemented | `desktop_stock_machine/` runtime data | Planned only; no runtime code should use it yet. |

## Python Import Inventory

| Import pattern | Found in | Risk if moved | Suggested mitigation |
|---|---|---|---|
| Bare peer imports such as `from server import ...`, `from central_store import ...`, `from store import ...` | `src/*.py` | High: imports depend on `src` being on `sys.path` | Plan package boundaries before moving modules. |
| `sys.path.insert(0, str(ROOT / "src"))` | Many tests and scripts | High: tests/scripts assume exact source root | Add a central test helper or compatibility package in a dedicated task. |
| `python src/main.py` | README, docs, scripts, CLI messages, tests | High: CLI instructions break if `src/main.py` moves | Add a root wrapper command before moving. |
| `from src...` / `import src...` | No Python matches found | Low | No mitigation needed for this specific pattern. |
| Desktop server imports Flask app via `server` | `src/desktop_server.py`, `src/pywebview_desktop_shell.py` | Medium: desktop shell currently depends on web app module layout | Separate desktop app shell from web app in a planned refactor. |
| Provider modules import shared market types by bare names | `src/*provider*.py`, `src/market_data_providers.py` | Medium | Move provider contracts with import aliases or package names. |

## Data Path Inventory

| Path | Current meaning | Git/privacy status | Future owner | Migration notes |
|---|---|---|---|---|
| `data/` | Current web prototype private runtime data | Ignored | Web prototype until explicit migration | Do not silently migrate to `app_data/`. |
| `data/market_data/` | Market/research SQLite databases | Ignored | `market_database/` concepts, shared storage | ETF holdings and snapshots can become shared market data after storage plan. |
| `data/profiles/` | Personal account/profile data | Ignored | Shared core/storage, desktop profiles later | Must not go into `market_database/`. |
| `data/uploads/` | Web upload/runtime area | Ignored through `data/` | Web prototype/import staging | Needs import-center boundary before move. |
| `data/imports/staging/` | Current import staging area | Ignored through `data/` | Shared import staging contract | Must preserve preview/confirm semantics. |
| `data/provider_cache/` | Provider cache | Ignored | Runtime cache under future data root | Not a source of truth. |
| `demo_runtime/` | Current demo runtime root | Ignored | Demo runtime boundary | Keep separate from real data and future desktop demo root. |
| `sample_data/` | Public synthetic sample data | Tracked where appropriate | `market_database/` fixtures later | Safe to move only with tests/scripts updated. |
| `config/providers.local.json` | Private local provider config | Ignored | Local config boundary | Never commit; future UI should expose safe metadata only. |
| `config/providers.local.example.json` | Public safe example provider config | Tracked | Provider docs/config example | Can move later with docs update. |
| `app_data/` | Future desktop app data root | Ignored | Desktop product | Planned, not wired. |
| `backups/`, logs | Local backup/log output | Ignored | Desktop backup/log boundary | Do not commit private reports or logs. |

## Flask Static Template Inventory

| Path | Current usage | Risk if moved | Suggested mitigation |
|---|---|---|---|
| `src/templates/` | Flask HTML templates | High | Move only after `create_app` supports configurable template root or wrapper path. |
| `src/static/` | Flask JS/CSS assets | High | Move only after static root and cache-busting assumptions are updated. |
| `url_for('static', filename=...)` | Template asset loading | Medium | Keep Flask static endpoint stable during migration. |
| `src/static/stock_detail.js` | Stock detail, ETF holdings display/import/provider UI | High | Treat as web prototype UI, not desktop final UI. |
| `src/static/app.js` | Main dashboard/client behavior | High | Move with web prototype only after route/API compatibility review. |
| `src/templates/stock_detail.html` | Page 2 stock detail template | High | Move with matching static JS/CSS and route tests. |
| `src/server.py` routes and app factory | Flask API/UI runtime | High | Split route layer from core/storage in dedicated tasks. |

## Test Script Inventory

| File or command | Path assumption | Risk | Suggested mitigation |
|---|---|---|---|
| `README.md` commands | `python src/main.py ...` | High | Add stable launcher before moving `src/main.py`. |
| `scripts/start_dashboard.ps1` | Starts `src/main.py` | Medium | Update after CLI compatibility wrapper exists. |
| `scripts/start_dashboard_tailscale.ps1` | Starts `src/main.py` | Medium | Update after CLI compatibility wrapper exists. |
| `scripts/prepare_demo_runtime.py` | Reads `sample_data/`, writes `demo_runtime/` | Medium | Parameterize source/target roots before moving fixtures. |
| `scripts/create_demo_data.py` | Writes `sample_data/` | Medium | Move with fixture ownership plan. |
| `tests/*.py` | Many add `ROOT / "src"` to `sys.path` | High | Add package/test helper or compatibility alias. |
| ETF/provider tests | Assume `sample_data/market`, provider config path, temp `data/market_data` | Medium | Update after market fixture/config root plan. |
| Server/API tests | Assume temp `data/`, Flask app factory, template/static roots | High | Keep web app compatibility until dedicated migration. |
| Settings tests | Assert default paths like `data/market_data`, `data/central.sqlite`, `config/gmail_*`, `sample_data/market` | High | Update only when settings contract changes. |
| Desktop demo tests | Assert demo runtime and CLI messages | Medium | Update after desktop shell/data-root status plan. |

## Market Database Migration Risks

Market/research files likely to belong partly under future `market_database/` concepts include:

- `src/central_store.py`
- `src/market_data_types.py`
- `src/market_data_providers.py`
- `src/builtin_market_data_providers.py`
- `src/local_csv_market_data_provider.py`
- `src/local_csv_etf_holdings_provider.py`
- `src/http_etf_holdings_provider.py`
- `src/fubon_etf_holdings_provider.py`
- `src/yuanta_etf_holdings_provider.py`
- `src/yfinance_quote_provider.py`
- `sample_data/market/*`
- provider and ETF holdings tests

Risk is high where market storage shares current `data/market_data/` paths with the web prototype. Provider contracts can move only after import paths, config paths, fixture paths, and API tests have compatibility coverage.

## Web Stock Machine Migration Risks

Current web prototype pieces are tightly coupled:

- `src/server.py`
- `src/templates/*`
- `src/static/*`
- stock detail page and ETF holdings UI
- import/provider UI routes
- upload/history/database/dividend pages
- API tests that instantiate Flask app with temporary roots

Migration risk is high. Move only after a web app package boundary and static/template compatibility plan exists.

## Desktop Stock Machine Migration Risks

Current desktop-related pieces are smaller but still depend on the Flask prototype:

- `src/desktop_shell.py` is relatively isolated: low risk.
- `src/desktop_server.py` imports the Flask app factory: medium risk.
- `src/pywebview_desktop_shell.py` depends on current server lifecycle: medium risk.
- `src/cli.py` desktop demo commands and messages assume current paths: medium risk.
- runtime info/status endpoints live in `src/server.py`: medium to high risk if moved before desktop data-root design.

Desktop code should not be moved until the desktop app shell/data-root status surface is defined.

## Migration Risk Map

### Safe To Move Later With Link Updates Only

- Placeholder README files under `web_stock_machine/`, `desktop_stock_machine/`, and `market_database/`.
- Some docs after `docs/CODEX_CONTEXT.md` routing is updated.
- Public example config docs, if links are updated.

### Requires Compatibility Wrapper Or Alias

- `python src/main.py` entrypoint.
- Bare peer imports from modules in `src/`.
- Tests and scripts that insert `ROOT / "src"` into `sys.path`.
- Desktop demo commands that reference current Flask server paths.

### Requires Test Updates

- Tests that assert exact CLI text or path defaults.
- Provider tests that assume `sample_data/market`.
- API tests that assume temp `data/market_data`.
- Settings tests that assert `data/`, `config/`, and `sample_data/` defaults.

### High Risk, Do Not Move Until Dedicated Task

- `src/server.py`
- `src/templates/`
- `src/static/`
- `src/central_store.py`
- `src/store.py`
- current `data/` root semantics
- provider config/cache paths
- import staging and profile storage behavior

## Recommended Migration Sequence

1. `SRC-COMPATIBILITY-LAYER-PLAN-1`: define import/package compatibility before moving source.
2. `CLI-ENTRYPOINT-COMPAT-1`: add or plan stable commands that can replace `python src/main.py`.
3. `WEB-STATIC-TEMPLATE-PATH-AUDIT-1`: isolate Flask template/static folder assumptions.
4. `MARKET-FIXTURE-PATH-AUDIT-1`: isolate `sample_data/market` and provider fixture assumptions.
5. `DOCS-MOVE-WEB-ROOT-1`: move or map web docs first, no runtime code.
6. `DOCS-MOVE-DESKTOP-ROOT-1`: move or map desktop docs first, no runtime code.
7. `DOCS-MOVE-MARKET-ROOT-1`: move or map provider/market docs first, no runtime code.
8. `TEST-PATH-HELPER-1`: centralize test path setup before source movement.
9. `WEB-APP-PACKAGE-BOUNDARY-1`: only after compatibility and tests are ready.
10. `MARKET-DATABASE-PACKAGE-BOUNDARY-1`: only after fixture/config/cache boundaries are ready.

## Explicit Non-Actions

- No files were moved in this task.
- No imports were changed.
- No runtime behavior was changed.
- No UI was changed.
- No source files were edited.
- No real data was touched.
- `demo_runtime/` was not modified.
- `app_data/` contents were not created.
- No provider fetches were run.
- `providers.local.json` was not touched.
