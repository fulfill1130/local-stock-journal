# Codex Context Routing

## Purpose

This file is the second document Codex should read after `AGENTS.md` or other top-level agent instruction files.

Do not read every Markdown file by default. Use this file to choose the smallest relevant document set for each task. Prefer reading 1 to 5 targeted docs, not the whole docs folder.

## Core Rules

- Always follow `AGENTS.md` if present.
- Read this file next.
- Then read only the task-relevant docs listed in the routing table.
- Do not treat the web prototype UI as the final desktop UI.
- Do not treat `market_database/` as personal account storage.
- Do not put personal trades, private profiles, cost basis, or user portfolio data in `market_database/`.
- Do not move runtime code unless a task explicitly asks for it.
- Do not modify real `data/`, `demo_runtime/`, `app_data/`, provider cache, local config, or secrets unless explicitly asked and protected by the task.

## Archive Rule

`docs/archive/` contains historical/reference documents. Codex must not read `docs/archive/` by default. Only read archived docs when the task explicitly asks for migration history, old planning context, or historical audit.

## Task Routing

- Desktop product task -> read `desktop_stock_machine/README.md`, `docs/desktop_product/README.md`, and the specific desktop doc named by the task.
- Web prototype task -> read `web_stock_machine/README.md`, `docs/web_prototype/README.md`, and the specific web/prototype doc named by the task.
- Market data / provider task -> read `market_database/README.md`, `docs/providers/README.md`, and the specific provider or ETF doc named by the task.
- Core accounting/storage/import/corporate action task -> read `docs/core/README.md` and the specific core contract named by the task.
- Data root / backup / migration task -> read `docs/desktop_product/DATA_ROOT.md`, `docs/desktop_product/BACKUP_MIGRATION.md`, and `docs/core/STORAGE_BOUNDARIES.md` only when relevant.
- UI task -> read only the relevant app README and task-specific UI docs. Do not read unrelated provider/storage docs unless needed.
- Product log update task -> read only the matching `PRODUCT_LOG.md` and the task-specific plan.

## Markdown Inventory

| Path | Category | Purpose | Read when |
|---|---|---|---|
| `AGENTS.md` | Bootstrap / rules | Agent behavior and response rules. | Always first if present. |
| `README.md` | Root project | Root overview, safety, setup, structure direction. | General orientation or root docs updates. |
| `DEVLOG.md` | Product log | Public development checkpoint log. | High-level project history is requested. |
| `docs/CODEX_CONTEXT.md` | Routing / index | Compact task-to-doc routing for Codex. | Always after `AGENTS.md`. |
| `docs/README.md` | Routing / index | Human documentation index. | Docs navigation or broad doc organization tasks. |
| `web_stock_machine/README.md` | Placeholder / future home | Future web prototype root boundary. | Web prototype or future web folder tasks. |
| `desktop_stock_machine/README.md` | Placeholder / future home | Future desktop product root boundary. | Desktop product or future desktop folder tasks. |
| `market_database/README.md` | Placeholder / future home | Future market/research data boundary. | Market database/provider boundary tasks. |
| `docs/core/README.md` | Core contract | Core contract section entry. | Core/storage/accounting/import contract tasks. |
| `docs/core/STORAGE_BOUNDARIES.md` | Core contract | Shared storage truth and write boundaries. | Storage, migration, ledger, data-root boundary tasks. |
| `docs/ARCHITECTURE.md` | Core contract | Existing app architecture overview. | Architecture or module-boundary tasks. |
| `docs/DATA_MODEL.md` | Core contract | Data model reference. | Schema/data model tasks. |
| `docs/IMPORT_PIPELINE.md` | Core contract | Import pipeline overview. | Import flow or broker document import tasks. |
| `docs/IMPORT_STAGING_SPEC.md` | Core contract | Import staging contract. | Import staging or reviewed-write tasks. |
| `docs/CORPORATE_ACTIONS_SPEC.md` | Core contract | Corporate action notice/settlement contract. | Corporate action tasks. |
| `docs/desktop_product/README.md` | Desktop product | Desktop product section entry. | Any desktop product task. |
| `docs/desktop_product/PLAN.md` | Desktop product | Desktop product direction and scope. | Desktop planning, navigation, or product-scope tasks. |
| `docs/desktop_product/DATA_ROOT.md` | Desktop product | Future desktop `app_data/` plan. | Data-root/status/storage location tasks. |
| `docs/desktop_product/BACKUP_MIGRATION.md` | Desktop product | Backup and migration safety plan. | Backup, migration, restore, dry-run tasks. |
| `docs/desktop_product/PRODUCT_LOG.md` | Product log | Desktop product decision log. | Desktop product log updates. |
| `docs/DESKTOP_DATA_ARCHITECTURE.md` | Desktop product | Earlier desktop storage baseline. | Detailed desktop storage background is needed. |
| `docs/DESKTOP_SHELL_INTERFACE.md` | Desktop product | Desktop shell/container contract. | Desktop shell, pywebview, lifecycle tasks. |
| `docs/web_prototype/README.md` | Web prototype | Web prototype section entry. | Web prototype tasks. |
| `docs/STOCK_DETAIL_PAGE_REQUIREMENTS.md` | Web prototype | Stock detail page requirements. | Stock detail UI/prototype tasks. |
| `docs/providers/README.md` | Provider / market data | Provider section entry and safety rules. | Provider or data-source tasks. |
| `docs/MARKET_DATA_PROVIDERS.md` | Provider / market data | Provider contracts and ETF holdings providers. | Market provider, ETF holdings, source tasks. |
| `docs/DEVELOPMENT_TRACKS.md` | Root project | Web vs desktop track relationship. | Track/promotion/scope tasks. |
| `docs/FRAMEWORK_DIRECTION.md` | Root project | Modular workbench direction. | Framework direction or module planning tasks. |
| `docs/PRODUCT_VISION.md` | Root project | Product vision. | Vision or positioning tasks. |
| `docs/ROADMAP.md` | Root project | Roadmap reference. | Roadmap planning tasks. |
| `docs/SECURITY_AND_PRIVACY.md` | Core contract | Privacy and secret-handling rules. | Security/privacy tasks or sensitive-data concerns. |
| `docs/DISCLAIMER.md` | Root project | Legal/financial disclaimer. | Disclaimer or public-facing risk text tasks. |
| `docs/PUBLIC_RELEASE_CHECKLIST.md` | Historical / reference | Public release safety checklist. | Release hygiene or publication checks. |
| `docs/RUNTIME_CONFIG_INVENTORY.md` | Historical / reference | Runtime config/path inventory. | Config/path migration tasks. |
| `docs/archive/FRAMEWORK_MIGRATION_PLAN.md` | Historical / archive | Older framework migration plan. | Only explicit historical migration tasks. |
| `docs/archive/MIGRATION_LOG.md` | Historical / archive | Migration handoff log. | Only explicit migration-history tasks. |
| `docs/archive/OPEN_SOURCE_MIGRATION_LOG.md` | Historical / archive | Open-source migration checkpoint. | Only explicit open-source history tasks. |
| `docs/PLUGIN_SYSTEM_DRAFT.md` | Historical / reference | Plugin system draft. | Plugin planning tasks. |
