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

## Open The UI

On Windows, double-click:

```text
desktop_stock_machine/open_ui.cmd
```

The launcher opens `desktop_stock_machine/frontend/index.html` in the default
browser. It does not start a server, write files, create `app_data/`, or connect
to real data.

## Build The EXE

Install desktop/build dependencies:

```powershell
python -m pip install -r requirements-desktop.txt
```

Build the Windows executable:

```powershell
powershell -ExecutionPolicy Bypass -File desktop_stock_machine/build_exe.ps1
```

The build creates:

```text
output/desktop_exe/dist/DesktopStockMachine.exe
```

The executable packages only the desktop UI shell and bundled frontend assets.
It does not package real data, `data/`, `demo_runtime/`, `app_data/`, backups,
provider cache, logs, local config, or `config/providers.local.json`.

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
- Settings currently include a static interface-language switch for Traditional
  Chinese and English. The switch only changes the current page and does not
  write files or browser storage.
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
