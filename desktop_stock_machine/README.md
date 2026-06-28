# Desktop Stock Machine

This folder is the clean desktop rebuild skeleton for the local-first stock
journal and ETF research workbench.

It is separate from the legacy Flask web prototype. It does not import from
legacy `src/`, does not copy the old Flask templates or static UI, and does not
touch real data folders.

## Run

From the repository root:

```powershell
python desktop_stock_machine/run_dev.py
```

The development entry point prints skeleton startup and data-root status. It
does not create `app_data/`, start a server, open a window, migrate profiles, or
load local provider configuration.

## Test

From the repository root:

```powershell
python -m unittest discover -s desktop_stock_machine/tests -v
```

## Current Status

- `desktop_stock_machine/app/` contains the standalone skeleton CLI, path
  helpers, settings, and status helpers.
- `desktop_stock_machine/frontend/` contains the first static desktop UI shell.
- The UI shell is a polished placeholder for overview, research tools, data
  sources, import staging, backup safety, settings, and logs.
- The frontend is static HTML/CSS/JavaScript, has no build system, and is not
  copied from the web prototype.
- It does not connect to real data, call providers, import legacy runtime code,
  or create `app_data/`.
- Real profile support, migration, backup flows, packaging, installer work, and
  provider fetches are not implemented yet.
- Next implementation steps are data-root status wiring and the external tool
  adapter contract.

## Boundaries

- Do not move legacy `src/` into this folder.
- Do not import legacy `src/` by default.
- Do not write real user data, private profiles, credentials, logs, backups, or
  raw provider responses here.
- Do not create or populate `app_data/` automatically.
- Future real-data migration must use dry-run, backup, confirmation, and
  verification.

Related docs:

- [Desktop Data Root](../docs/desktop_product/DATA_ROOT.md)
- [Storage Boundaries](../docs/core/STORAGE_BOUNDARIES.md)
- [Legacy Web Prototype](../web_stock_machine/LEGACY_WEB_PROTOTYPE.md)
